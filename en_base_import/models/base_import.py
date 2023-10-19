# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import binascii
import codecs
import collections
import unicodedata

import chardet
import datetime
import io
import itertools
import logging
import psycopg2
import operator
import os
import re
import requests

from PIL import Image

from odoo import api, fields, models
_logger = logging.getLogger(__name__)


class Import(models.TransientModel):
    _inherit = 'base_import.import'
    def do(self, fields, columns, options, dryrun=False):
        self.ensure_one()
        self._cr.execute('SAVEPOINT import')

        try:
            data, import_fields = self._convert_import_data(fields, options)
            # Parse date and float field
            data = self._parse_import_data(data, import_fields, options)
        except ValueError as error:
            return {
                'messages': [{
                    'type': 'error',
                    'message': str(error),
                    'record': False,
                }]
            }

        _logger.info('importing %d rows...', len(data))

        name_create_enabled_fields = options.pop('name_create_enabled_fields', {})
        import_limit = options.pop('limit', None)
        model = self.env[self.res_model].with_context(import_file=True, name_create_enabled_fields=name_create_enabled_fields, _import_limit=import_limit)
        if 'import_custom' in self._context and 'related_id' in self._context and 'related_fields' in self._context and 'related_model' in self._context:
            if self._context['import_custom'] and self._context['related_id'] and self._context['related_fields'] and self._context['related_model']:
                related_ids = self.env[self._context['related_model']].browse(self._context['related_id'])
                import_fields.append(self._context['related_fields'])
                for line in data:
                    line.append(related_ids.name)
        import_result = model.load(import_fields, data)
        _logger.info('done')
        try:
            if dryrun:
                self._cr.execute('ROLLBACK TO SAVEPOINT import')
                # cancel all changes done to the registry/ormcache
                self.pool.clear_caches()
                self.pool.reset_changes()
            else:
                self._cr.execute('RELEASE SAVEPOINT import')
        except psycopg2.InternalError:
            pass

        if import_result['ids'] and options.get('headers'):
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
            r.extend(x[index_of_name] for x in data[:import_limit])
            r.extend([''] * (len(data) - (import_limit or 0)))
        else:
            import_result['name'] = []

        skip = options.get('skip', 0)
        if import_result['nextrow']:
            import_result['nextrow'] += skip

        return import_result