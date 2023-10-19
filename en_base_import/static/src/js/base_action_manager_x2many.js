odoo.define('en_base_import.relational_fields', function (require) {
    "use strict";

    var FieldX2Many = require('web.relational_fields').FieldX2Many;
    var DataImport = require('base_import.import').DataImport;
    var core = require('web.core');
    var data = require('web.data');
    var Dialog = require('web.Dialog');
    var dialogs = require('web.view_dialogs');
    var QWeb = core.qweb;
    var DataWebExport = require('web.DataExport');
    var rpc = require("web.rpc");

    FieldX2Many.include({
        events: _.extend({}, FieldX2Many.prototype.events, {
            'click .btn_export_data': '_onExport',
            'click .btn_import_data': '_onImport'
        }),
        on_attach_callback: function () {
            var self = this;
            this._super.apply(this, arguments);
        },
        _render: function () {
            var self = this;
            $('.context_sub_menu').remove();
            var result = this._super.apply(this, arguments);
            var rlm = QWeb.render('en_base_import.context_sub_menu',{})
            this.$el.append(rlm)
            if (this.formatType !== 'one2many') {
                this.$el.find('.btn_import_data').addClass('d-none')
            }
            this.$el.css({
                'padding-top': '25px',
                'position': 'relative'
            })
            return result
        },
        _onExport: function () {
            if (this.mode == 'edit') {
                return this.do_warn('Vui lòng tạo xong bản ghi để sử dụng chức năng này!')
            }
            this._getExportBaseDialogWidget();
        },
        _getExportBaseDialogWidget: function () {
            var self = this;
            var state_master = this.__parentedParent.__parentedParent.model.get(this.dataPointID);
            var state = state_master.data[this.name];
            let defaultExportFields = this.renderer.columns.filter(field => field.tag === 'field').map(field => field.attrs.name);
            let groupedBy = this.renderer.state.groupedBy;
            const domain = false;
            if (state.data.length > 0)
            return new DataWebExport(self, state, defaultExportFields, groupedBy,
                domain, state.res_ids).open();
        },
        _onImport: function (e) {
            if (this.mode == 'edit') {
                return this.do_warn('Vui lòng tạo xong bản ghi để sử dụng chức năng này!')
            }
            var self = this;
            $('.context_import_menu').remove();
            var context = this.field.context;
            context.import_custom = true;
            context.related_id = this.res_id;
            context.related_fields = this.field.relation_field;
            context.related_model = this.model;
            if (!this.res_id || !this.field.relation_field || !this.model) return
            const action = {
                type: 'ir.actions.client',
                tag: 'import',
                params: {
                    model: this.field.relation,
                    context: this.field.context,
                    related_fields: this.field.relation_field,
                    dataPointImportID: this.res_id,
                },
                target: 'new',
                name: 'Import',
            };
            this.do_action(action).then(function (result) {
                $('.oe_import').css({
                    'position': 'static'
                })
            })
        },
    })

    DataImport.include({
        init: function (parent, action) {
            this._super.apply(this, arguments);
            if (action.params.hasOwnProperty('related_fields')) {
                this.related_fields = action.params.related_fields;
            }
        },
        onpreview_success: function (event, from, to, result) {
            var self = this;
            this._super.apply(this, arguments);
            $('.o_import_validate').removeClass('d-none');
            $('.oe_import_file').addClass('btn-secondary');
            $('.o_import_import.o_import_import_full').removeClass('d-none');
        },
        onimport: function () {
            var self = this;
            var prom = this._super.apply(this, arguments);
            prom.then(function (results) {
                var message = results.messages;
                if (!_.any(message, function (message) {
                    return message.type === 'error';
                })) {
                    if (self.related_fields) {
                        location.reload();
                    }
                    self['import_succeeded'](results);
                    return;
                }
                self['import_failed'](results);
            });
            return prom;
        },
    });

});

