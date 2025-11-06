from odoo import models,fields,api
from odoo.exceptions import ValidationError

class POSConfigUpdate(models.Model):
    _inherit = "pos.config"
    reporting = fields.Boolean(default=False, string="Allow Date Adjustment", help="Used for entering backlog Data")

    @api.constrains('reporting')
    def _check_inventory_management(self):
        if self.company_id.point_of_sale_update_stock_quantities == "real" and self.reporting:
            raise ValidationError(
                "To allow date adjustment, inventory management type must be at session closing. Please change setting in pos configuration.")
