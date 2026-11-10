from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _prepare_account_move_vals(self, credit_account_id, debit_account_id, journal_id, qty,
                                   description, svl_id, cost):
        move_val = super()._prepare_account_move_vals(
            credit_account_id, debit_account_id, journal_id, qty, description, svl_id, cost,
        )
        backdate = self.env.context.get("pos_backdate")
        if backdate:
            move_val["date"] = backdate
        return move_val

    def _action_done(self, cancel_backorder=False):
        moves_todo = super()._action_done(cancel_backorder)
        backdate = self.env.context.get("pos_backdate")
        if backdate and moves_todo:
            moves_todo.write({"date": backdate})
        return moves_todo
