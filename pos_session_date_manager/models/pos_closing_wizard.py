from odoo import _, fields, models
from odoo.exceptions import UserError


class PosCloseSessionWizard(models.TransientModel):
    _inherit = "pos.close.session.wizard"

    closing_date = fields.Datetime(
        string="Closing Date",
        help="Only used when the Point of Sale allows date adjustment. Leave "
             "empty to close at the current date and time.",
    )
    allow_backdate = fields.Boolean(compute="_compute_allow_backdate")

    def _compute_allow_backdate(self):
        for wizard in self:
            sessions = self.env["pos.session"].browse(self.env.context.get("active_ids", []))
            wizard.allow_backdate = any(session.config_id.reporting for session in sessions)

    def close_session(self):
        """Core's wizard closes the session from the back end.

        The previous version added the field but nothing ever read it, so a
        date typed here was silently discarded.
        """
        sessions = self.env["pos.session"].browse(self.env.context["active_ids"])
        if self.closing_date:
            backdatable = sessions.filtered(lambda session: session.config_id.reporting)
            if not backdatable:
                raise UserError(_(
                    "None of these sessions allow date adjustment."
                ))
            for session in backdatable:
                session.set_backdate_stop(self.closing_date)
        return super().close_session()
