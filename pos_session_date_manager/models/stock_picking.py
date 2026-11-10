from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _prepare_stock_move_vals(self, first_line, order_lines):
        move_vals = super()._prepare_stock_move_vals(first_line, order_lines)
        backdate = self.env.context.get("pos_backdate")
        if backdate:
            move_vals["date"] = backdate
        return move_vals

    def _prepare_picking_vals(self, partner, picking_type, location_id, location_dest_id):
        picking_vals = super()._prepare_picking_vals(
            partner, picking_type, location_id, location_dest_id,
        )
        backdate = self.env.context.get("pos_backdate")
        if backdate:
            picking_vals["scheduled_date"] = backdate
        return picking_vals

    def _action_done(self):
        action_done = super()._action_done()
        backdate = self.env.context.get("pos_backdate")
        if backdate:
            self.write({"date_done": backdate})
        return action_done
