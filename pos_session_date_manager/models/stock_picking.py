from odoo import models, fields, api


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _prepare_stock_move_vals(self, first_line, order_lines):
        move_vals = super()._prepare_stock_move_vals(first_line, order_lines)
        if self.env.context.get('pos_session'):
            move_vals["date"] = self.env.context.get('pos_session')["closing_date"]

        return move_vals

    def _prepare_picking_vals(self, partner, picking_type, location_id, location_dest_id):
        picking_vals = super()._prepare_picking_vals(partner, picking_type, location_id, location_dest_id)
        if self.env.context.get('pos_session'):
            picking_vals["scheduled_date"] = self.env.context.get('pos_session')["closing_date"]

        return picking_vals

    def _action_done(self):
        action_done = super()._action_done()
        if self.env.context.get("pos_session"):
            self.write({"date_done": self.env.context.get("pos_session")["closing_date"]})
        return action_done
