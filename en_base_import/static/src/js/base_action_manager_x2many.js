import { _t } from "@web/core/l10n/translation";
import { download } from "@web/core/network/download";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { StaticList } from "@web/model/relational_model/static_list";
import { ListRenderer } from "@web/views/list/list_renderer";
import { ExportDataDialog } from "@web/views/view_dialogs/export_data_dialog";

patch(ListRenderer.prototype, {
    // The "add a line" row exists both on top-level list views and on
    // x2many sub-lists: only a StaticList (an x2many's own records) should
    // get the Import/Export links.
    get isX2ManySubList() {
        return this.props.list instanceof StaticList;
    },

    // Import creates new child records through the relation field, so it
    // only makes sense for one2many (many2many has no relation field).
    get isOne2manySubList() {
        return this.isX2ManySubList && Boolean(this.props.list.config.relationField);
    },

    async x2m_export() {
        const list = this.props.list;
        if (!list.resIds.length) {
            this.notificationService.add(_t("There is nothing to export."), {
                type: "warning",
            });
            return;
        }

        const domain = [["id", "in", list.resIds]];
        const getExportedFields = async (isCompatible, parentParams) => {
            return await rpc("/web/export/get_fields", {
                model: list.resModel,
                domain: parentParams ? [] : domain,
                import_compat: isCompatible,
                ...parentParams,
            });
        };
        const downloadExport = async (exportList, isCompatible, format) => {
            const exportedFields = exportList.map((field) => ({
                name: field.name || field.id,
                label: field.label || field.string,
                store: field.store,
                type: field.field_type || field.type,
            }));
            if (isCompatible) {
                exportedFields.unshift({ name: "id", label: _t("External ID") });
            }
            await download({
                data: {
                    data: JSON.stringify({
                        import_compat: isCompatible,
                        context: list.context,
                        domain,
                        fields: exportedFields,
                        groupby: [],
                        ids: false,
                        model: list.resModel,
                    }),
                },
                url: `/web/export/${format}`,
            });
        };
        const defaultExportList = Object.keys(list.activeFields)
            .map((fieldName) => list.fields[fieldName])
            .filter(Boolean);

        this.env.services.dialog.add(ExportDataDialog, {
            context: list.context,
            defaultExportList,
            download: downloadExport,
            getExportedFields,
            root: list,
        });
    },

    x2m_import() {
        const list = this.props.list;
        const parent = list._parent;
        if (!parent || parent.isNew) {
            this.notificationService.add(
                _t("Please save the record before importing lines here."),
                { type: "warning" }
            );
            return;
        }

        this.env.services.action.doAction(
            {
                type: "ir.actions.client",
                tag: "import",
                target: "new",
                name: _t("Import"),
                params: {
                    active_model: list.resModel,
                    context: {
                        ...list.context,
                        import_custom: true,
                        related_id: parent.resId,
                        related_model: parent.resModel,
                        related_fields: list.config.relationField,
                    },
                },
            },
            {
                onClose: () => parent.load(),
            }
        );
    },
});
