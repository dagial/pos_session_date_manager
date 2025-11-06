from odoo import models, fields


class StockMoveUpdate(models.Model):
    _inherit = "stock.move"

    def _prepare_account_move_vals(self, credit_account_id, debit_account_id, journal_id, qty, description, svl_id,
                                   cost):
        move_val = super()._prepare_account_move_vals(credit_account_id, debit_account_id, journal_id, qty, description,
                                                      svl_id, cost)

        if self.env.context.get('pos_session'):
            move_val["date"] = self.env.context.get('pos_session')["closing_date"]

        return move_val

    def _action_done(self, cancel_backorder=False):
        moves_todo = super()._action_done(cancel_backorder)

        if self.env.context.get("pos_session"):
            moves_todo.write({"date": self.env.context.get("pos_session")["closing_date"]})

        return moves_todo
