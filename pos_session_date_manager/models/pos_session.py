from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class PosSession(models.Model):
    _inherit = "pos.session"

    # ------------------------------------------------------------------
    # The adjusted dates live on the record, never in a method signature.
    #
    # Core calls its own hooks positionally — `pos.close.session.wizard`
    # invokes `action_pos_session_closing_control(account_id, amount)` — so an
    # extra leading parameter does not raise, it silently lands an account in a
    # date field. Every override below therefore keeps core's exact signature
    # and reads what it needs from `self`.
    # ------------------------------------------------------------------

    backdate_start = fields.Datetime(
        string="Adjusted Opening",
        copy=False,
        readonly=True,
        help="When set, the session is treated as if it had opened at this "
             "moment, and every record it produces is dated accordingly.",
    )
    backdate_stop = fields.Datetime(
        string="Adjusted Closing",
        copy=False,
        readonly=True,
        help="When set, the closing entries, pickings, stock moves and "
             "valuation layers are dated from this moment instead of the "
             "moment the session was actually closed.",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pos_backdate_enabled(self):
        self.ensure_one()
        return bool(self.config_id.reporting)

    def _pos_backdate_close(self):
        """The moment every record created while closing must carry."""
        self.ensure_one()
        if not self._pos_backdate_enabled():
            return False
        return self.backdate_stop or self.stop_at

    def _pos_backdate_context(self):
        """One context key, set once, read by every downstream override."""
        self.ensure_one()
        value = self._pos_backdate_close()
        return {"pos_backdate": value} if value else {}

    def _pos_backdate_validate(self, value):
        self.ensure_one()
        if not self._pos_backdate_enabled():
            raise UserError(_(
                "Date adjustment is not enabled on %s.", self.config_id.display_name,
            ))
        if not self.env.user.has_group("pos_session_date_manager.group_pos_backdate"):
            raise AccessError(_(
                "You are not allowed to adjust Point of Sale session dates."
            ))

        value = fields.Datetime.to_datetime(value)
        if not value:
            raise UserError(_("A date is required."))
        if value > fields.Datetime.now():
            raise UserError(_("A session cannot be dated in the future."))

        # Backdating writes into accounting periods, so it has to respect the
        # locks accounting already enforces rather than reaching around them.
        company = self.company_id or self.env.company
        locks = [
            date for date in (
                company.user_fiscalyear_lock_date,
                company.user_hard_lock_date,
            ) if date
        ]
        if locks and value.date() <= max(locks):
            raise UserError(_(
                "Accounting is locked up to %(lock)s. Choose a later date.",
                lock=max(locks),
            ))
        return value

    # ------------------------------------------------------------------
    # Called from the Point of Sale UI
    # ------------------------------------------------------------------

    def set_backdate_start(self, value):
        self.ensure_one()
        value = self._pos_backdate_validate(value)
        self.sudo().write({"backdate_start": value})
        return fields.Datetime.to_string(value)

    def set_backdate_stop(self, value):
        self.ensure_one()
        value = self._pos_backdate_validate(value)
        if self.start_at and value < self.start_at:
            raise UserError(_("The closing date cannot be before the opening date."))
        self.sudo().write({"backdate_stop": value})
        return fields.Datetime.to_string(value)

    # ------------------------------------------------------------------
    # Opening
    # ------------------------------------------------------------------

    def _set_opening_control_data(self, cashbox_value, notes):
        """Core's documented extension point.

        `set_opening_control` carries an explicit "DO NOT INHERIT THIS METHOD"
        and delegates here, so this is where the opening date belongs. Core
        sets `start_at` to now; this moves it back afterwards.
        """
        res = super()._set_opening_control_data(cashbox_value, notes)
        for session in self:
            if session.backdate_start and session._pos_backdate_enabled():
                session.sudo().write({"start_at": session.backdate_start})
        return res

    # ------------------------------------------------------------------
    # Closing
    # ------------------------------------------------------------------

    def update_closing_control_state_session(self, notes):
        """Core stamps `stop_at` with now() here; move it back.

        Note this passes `notes` straight through — the previous version
        overwrote the cashier's closing note with a hardcoded string.
        """
        res = super().update_closing_control_state_session(notes)
        for session in self:
            if session.backdate_stop and session._pos_backdate_enabled():
                session.sudo().write({"stop_at": session.backdate_stop})
        return res

    def action_pos_session_closing_control(self, balancing_account=False, amount_to_balance=0,
                                           bank_payment_method_diffs=None):
        """Core's signature, untouched.

        The adjusted date travels in the context so that every record created
        further down — journal entry, payments, statement lines, picking, stock
        moves and their entries — picks it up without any of them needing a new
        argument.
        """
        backdating = self.filtered(
            lambda session: session.backdate_stop and session._pos_backdate_enabled()
        )
        target = self
        if len(self) == 1 and backdating:
            target = self.with_context(**self._pos_backdate_context())

        result = super(PosSession, target).action_pos_session_closing_control(
            balancing_account, amount_to_balance, bank_payment_method_diffs,
        )

        for session in backdating:
            session.sudo().write({"stop_at": session.backdate_stop})
            # Last, once every picking is done and every layer exists.
            session._pos_backdate_valuation_layers_date()
        return result

    def _create_account_move(self, balancing_account=False, amount_to_balance=0,
                             bank_payment_method_diffs=None):
        """Core dates the session entry with `context_today`."""
        res = super()._create_account_move(
            balancing_account, amount_to_balance, bank_payment_method_diffs,
        )
        backdate = self.env.context.get("pos_backdate")
        if backdate and self.move_id and self.move_id.state == "draft":
            self.move_id.sudo().write({
                "date": fields.Datetime.to_datetime(backdate).date(),
            })
        return res

    # ------------------------------------------------------------------
    # Stock valuation
    # ------------------------------------------------------------------

    def _pos_backdate_valuation_layers(self):
        self.ensure_one()
        return self.picking_ids.move_ids.sudo().stock_valuation_layer_ids

    def _pos_backdate_valuation_layers_date(self):
        """Re-date this session's valuation layers.

        `stock.valuation.layer` has no date field — valuation reports order and
        filter on `create_date`, so that is the only lever available, and it has
        to be written in SQL because the column is not writable through the ORM.

        Scoped by primary key. The previous implementation used an
        uncorrelated `UPDATE ... FROM stock_valuation_layer svl` with no
        `id = svl.id` join, which set the date on *every layer in the database*
        as soon as one picking name matched.
        """
        self.ensure_one()
        target = self._pos_backdate_close()
        layers = self._pos_backdate_valuation_layers()
        if not target or not layers:
            return
        layers.flush_recordset()
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET create_date = %s WHERE id = ANY(%s)",
            [target, layers.ids],
        )
        layers.invalidate_recordset(["create_date"])
