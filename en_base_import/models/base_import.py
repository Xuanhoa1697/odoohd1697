# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import contextlib
import logging

import psycopg2

from odoo import models
from odoo.addons.base_import.models.base_import import ImportValidationError

_logger = logging.getLogger(__name__)


class Import(models.TransientModel):
    _inherit = 'base_import.import'

    def execute_import(self, fields, columns, options, dryrun=False):
        """Same as base_import.import.execute_import(), except that when the
        import is opened from an x2many sub-list (see en_base_import's
        ListRenderer patch), the imported rows are linked to the parent
        record via ``related_fields/.id`` so each row is created as a child
        of that record instead of a standalone one.
        """
        self.ensure_one()
        context = self._context
        related_id = context.get('related_id')
        related_fields = context.get('related_fields')
        related_model = context.get('related_model')

        import_savepoint = self.env.cr.savepoint(flush=False)

        try:
            input_file_data, import_fields = self._convert_import_data(fields, options)
            # Parse date and float field
            input_file_data = self._parse_import_data(input_file_data, import_fields, options)
        except ImportValidationError as error:
            return {'messages': [error.__dict__]}

        if context.get('import_custom') and related_id and related_fields and related_model:
            # ".id" targets the database id directly (see models.py:load), so
            # every imported row is attached to the parent record by id.
            import_fields = list(import_fields) + ['%s/.id' % related_fields]
            for line in input_file_data:
                line.append(related_id)

        _logger.info('importing %d rows...', len(input_file_data))

        binary_filenames = self._extract_binary_filenames(import_fields, input_file_data)

        import_fields, merged_data = self.with_context(import_options=options)._handle_multi_mapping(import_fields, input_file_data)

        if options.get('fallback_values'):
            merged_data = self._handle_fallback_values(import_fields, merged_data, options['fallback_values'])

        name_create_enabled_fields = options.pop('name_create_enabled_fields', {})
        import_limit = options.pop('limit', None)
        model = self.env[self.res_model].with_context(
            import_file=True,
            name_create_enabled_fields=name_create_enabled_fields,
            import_set_empty_fields=options.get('import_set_empty_fields', []),
            import_skip_records=options.get('import_skip_records', []),
            _import_limit=import_limit)
        import_result = model.load(import_fields, merged_data)
        _logger.info('done importing data into model: %s', model._name)

        # If transaction aborted, RELEASE SAVEPOINT is going to raise
        # an InternalError (ROLLBACK should work, maybe). Ignore that.
        with contextlib.suppress(psycopg2.InternalError):
            import_savepoint.close(rollback=dryrun)
        if dryrun:
            # cancel all changes done to the registry/ormcache
            self.pool.clear_all_caches()
            # don't propagate to other workers since it was rollbacked
            self.pool.reset_changes()
            _logger.info('Previous import was a dry/test run, changes were reset')

        # Insert/Update mapping columns when import complete successfully
        if import_result['ids'] and options.get('has_headers'):
            BaseImportMapping = self.env['base_import.mapping']
            for index, column_name in enumerate(columns):
                if column_name:
                    # Update to latest selected field
                    mapping_domain = [('res_model', '=', self.res_model), ('column_name', '=', column_name)]
                    column_mapping = BaseImportMapping.search(mapping_domain, limit=1)
                    if column_mapping:
                        if column_mapping.field_name != fields[index]:
                            column_mapping.field_name = fields[index]
                    else:
                        BaseImportMapping.create({
                            'res_model': self.res_model,
                            'column_name': column_name,
                            'field_name': fields[index]
                        })
        if 'name' in import_fields:
            index_of_name = import_fields.index('name')
            skipped = options.get('skip', 0)
            r = import_result['name'] = [''] * skipped
            r.extend(self._stringify_date_like_objects(x[index_of_name], options) for x in input_file_data[:import_limit])
            r.extend([''] * (len(input_file_data) - (import_limit or 0)))
        else:
            import_result['name'] = []

        skip = options.get('skip', 0)
        if import_result['nextrow']:
            import_result['nextrow'] += skip
        if binary_filenames:
            import_result['binary_filenames'] = binary_filenames

        return import_result