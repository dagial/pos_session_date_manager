from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PosConfig(models.Model):
    _inherit = "pos.config"

    # Kept under its original name so existing configurations keep their value.
    reporting = fields.Boolean(
        string="Allow Date Adjustment",
        default=False,
        help="Lets an authorised user set this Point of Sale's session opening "
             "and closing dates, so backlog sales are recorded on the day they "
             "happened across sales, accounting and stock.",
    )

    @api.constrains("reporting")
    def _check_inventory_management(self):
        # Iterating matters: `@api.constrains` receives the whole written
        # recordset, and reading `self.company_id` on more than one record
        # raises a singleton error instead of validating.
        for config in self:
            if config.reporting and \
                    config.company_id.point_of_sale_update_stock_quantities == "real":
                raise ValidationError(_(
                    "Date adjustment needs inventory to be updated at session "
                    "closing. With real time updates the stock moves are written "
                    "as each order is rung up, so there is no single moment at "
                    "which they can be dated. Change it in the Point of Sale "
                    "settings first."
                ))

    @api.model
    def _load_pos_data_fields(self, config_id):
        """Make the flag visible to the front end, without narrowing the read.

        `pos.config` does not define this method — it inherits `pos.load.mixin`,
        which returns an empty list, and an empty list means "read every field".
        Appending to it therefore does the opposite of what it looks like: it
        restricts the read to that one field, and core's own `_load_pos_data`
        then dies on `data[0]['use_pricelist']`, taking the whole session load
        with it.
        """
        fields_list = super()._load_pos_data_fields(config_id)
        if fields_list and "reporting" not in fields_list:
            fields_list = fields_list + ["reporting"]
        return fields_list
