from datetime import datetime

import pytz

from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def _pos_backdate_order_datetime(self, raw, session_start):
        """Move an order onto the session's day, keeping its time of day.

        Both values are stored in UTC, but the *day* a user means is the day in
        their own timezone. Combining a UTC date with a UTC time — what the
        previous version did — lands orders on the wrong day either side of
        midnight for any timezone with an offset.

        Localising the naive result rather than calling `replace()` on an
        aware one also keeps DST transitions correct.
        """
        original = fields.Datetime.to_datetime(raw) or fields.Datetime.now()
        tzname = self.env.user.tz or "UTC"
        timezone = pytz.timezone(tzname)

        local_original = pytz.utc.localize(original).astimezone(timezone)
        local_session = pytz.utc.localize(session_start).astimezone(timezone)

        combined = timezone.localize(
            datetime.combine(local_session.date(), local_original.time())
        )
        return combined.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _process_order(self, order, existing_order):
        """Date incoming orders from the session rather than the clock.

        Core's signature is `(order, existing_order)` and it returns the order
        id — the previous version declared a third `draft` parameter and
        returned nothing, which broke order sync outright.
        """
        session = self.env["pos.session"].browse(order.get("session_id"))
        if session.exists() and session.config_id.reporting and session.start_at:
            order = dict(order)
            order["date_order"] = fields.Datetime.to_string(
                self._pos_backdate_order_datetime(order.get("date_order"), session.start_at)
            )
        return super()._process_order(order, existing_order)


class PosPayment(models.Model):
    _inherit = "pos.payment"

    @api.model_create_multi
    def create(self, vals_list):
        """A payment belongs to the moment of its order, not of its sync."""
        for vals in vals_list:
            order = self.env["pos.order"].browse(vals.get("pos_order_id"))
            if order.exists() and order.session_id.config_id.reporting and order.date_order:
                vals["payment_date"] = order.date_order
        return super().create(vals_list)
