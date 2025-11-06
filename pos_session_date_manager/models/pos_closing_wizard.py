from odoo import models, fields, api, tools


class PosCloseSessionWizard(models.TransientModel):
    _inherit = "pos.close.session.wizard"
    closing_date = fields.Datetime(string="Closing Date")
