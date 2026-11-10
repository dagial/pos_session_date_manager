from odoo import api, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    @api.model_create_multi
    def create(self, vals_list):
        """Core creates and posts these inline while closing the session.

        There is no vals hook and no chance to correct the date afterwards —
        the payment is already posted — so the date is applied on the way in.
        The `pos_backdate` key is only ever set by
        `pos.session.action_pos_session_closing_control`, so this is inert
        everywhere else.
        """
        backdate = self.env.context.get("pos_backdate")
        if backdate:
            for vals in vals_list:
                vals.setdefault("date", backdate)
        return super().create(vals_list)


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    @api.model_create_multi
    def create(self, vals_list):
        """Same reasoning: `_post_statement_difference` and
        `_get_combine_statement_line_vals` both build their vals inline and
        date them from today."""
        backdate = self.env.context.get("pos_backdate")
        if backdate:
            for vals in vals_list:
                vals["date"] = backdate
        return super().create(vals_list)
