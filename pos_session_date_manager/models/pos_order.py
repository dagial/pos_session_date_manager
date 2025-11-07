from odoo import fields, models, api
from datetime import datetime

class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def _order_fields(self, ui_order):
        order_fields= super()._order_fields(ui_order)
        session=self.env["pos.session"].search([("id","=",order_fields["session_id"])])

        if session.config_id.reporting:
            original_dt = fields.Datetime.from_string(order_fields["date_order"])
            updated_dt = datetime.combine(session.start_at, original_dt.time())
            order_fields["date_order"]=updated_dt
        return order_fields

    @api.model
    def _payment_fields(self, order, ui_paymentline):
        payment_fields=super()._payment_fields(order,ui_paymentline)
        order = self.env["pos.order"].search([("id", "=", payment_fields["pos_order_id"])])
        if order.session_id.config_id.reporting:
            original_dt = fields.Datetime.from_string(payment_fields["payment_date"])
            # updated_dt = datetime.combine(session.start_at, original_dt.time())
            payment_fields["payment_date"] = order.date_order

        return payment_fields
