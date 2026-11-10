from datetime import datetime, timedelta
from unittest.mock import patch

import pytz

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import file_open

from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon


@tagged("post_install", "-at_install")
class TestPosBackdate(TestPointOfSaleHttpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.point_of_sale_update_stock_quantities = "closing"
        cls.main_pos_config.reporting = True
        # No microseconds: the valuation test compares the stored create_date
        # back against this value.
        cls.backdate = (fields.Datetime.now() - timedelta(days=7)).replace(microsecond=0)

    # ------------------------------------------------------------------
    # Configuration guard
    # ------------------------------------------------------------------

    def test_real_time_stock_blocks_date_adjustment(self):
        """Real time updates write stock per order, so there is no single
        moment at which the moves could be dated."""
        self.main_pos_config.reporting = False
        self.company.point_of_sale_update_stock_quantities = "real"
        with self.assertRaises(ValidationError):
            self.main_pos_config.reporting = True

    def test_constraint_validates_each_record_of_a_batch(self):
        """Reading self.company_id on a multi-record set used to raise a
        singleton error instead of validating."""
        other = self.main_pos_config.copy({"name": "MB Second POS"})
        configs = self.main_pos_config | other
        configs.write({"reporting": True})
        self.assertTrue(all(configs.mapped("reporting")))

    def test_flag_reaches_the_front_end(self):
        """Asserted on the payload, not on the field list.

        `pos.config` inherits the mixin's empty field list, which means "read
        every field" — so the list itself never mentions `reporting`, while the
        data does. Asserting the list would be both wrong and, if made to pass
        by appending, would break core's `_load_pos_data`.
        """
        with self.with_new_session() as session:
            payload = session.load_data([])
        config_data = payload["pos.config"]["data"][0]
        self.assertTrue(config_data.get("reporting"))
        self.assertIn(
            "use_pricelist", config_data,
            "narrowing the field list would break core's own _load_pos_data",
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _open_session(self):
        self.main_pos_config.with_user(self.pos_user).open_ui()
        return self.main_pos_config.current_session_id

    def test_backdate_rejected_when_not_enabled(self):
        self.main_pos_config.reporting = False
        session = self._open_session()
        with self.assertRaises(UserError):
            session.set_backdate_start(self.backdate)

    def test_backdate_rejected_in_the_future(self):
        session = self._open_session()
        with self.assertRaises(UserError):
            session.set_backdate_start(fields.Datetime.now() + timedelta(days=1))

    def test_backdate_rejected_before_the_lock_date(self):
        session = self._open_session()
        self.company.fiscalyear_lock_date = fields.Date.today() - timedelta(days=2)
        with self.assertRaises(UserError):
            session.set_backdate_start(fields.Datetime.now() - timedelta(days=10))

    def test_backdate_requires_the_group(self):
        session = self._open_session()
        group = self.env.ref("pos_session_date_manager.group_pos_backdate")
        self.pos_user.write({"groups_id": [(3, group.id)]})
        # group_pos_manager implies the backdate group, so it has to go too.
        self.pos_user.write({
            "groups_id": [(3, self.env.ref("point_of_sale.group_pos_manager").id)],
        })
        with self.assertRaises(AccessError):
            session.with_user(self.pos_user).set_backdate_start(self.backdate)

    def test_closing_cannot_precede_opening(self):
        session = self._open_session()
        session.set_backdate_start(self.backdate)
        session.sudo().write({"start_at": self.backdate})
        with self.assertRaises(UserError):
            session.set_backdate_stop(self.backdate - timedelta(days=1))

    # ------------------------------------------------------------------
    # Core signatures must stay exactly as core declares them
    # ------------------------------------------------------------------

    def test_closing_control_keeps_cores_signature(self):
        """`pos.close.session.wizard` calls this positionally with an account
        and an amount. An extra leading parameter does not raise — it silently
        lands an account.account in a date field."""
        import inspect
        signature = inspect.signature(
            self.env["pos.session"].action_pos_session_closing_control
        )
        self.assertEqual(
            list(signature.parameters),
            ["balancing_account", "amount_to_balance", "bank_payment_method_diffs"],
        )

    def test_close_session_from_ui_keeps_cores_signature(self):
        import inspect
        signature = inspect.signature(self.env["pos.session"].close_session_from_ui)
        self.assertEqual(list(signature.parameters), ["bank_payment_method_diff_pairs"])

    def test_update_closing_control_keeps_cores_signature(self):
        import inspect
        signature = inspect.signature(
            self.env["pos.session"].update_closing_control_state_session
        )
        self.assertEqual(list(signature.parameters), ["notes"])

    def test_closing_notes_are_preserved(self):
        """A hardcoded string used to overwrite whatever the cashier typed."""
        session = self._open_session()
        session.update_closing_control_state_session("counted twice")
        self.assertEqual(session.closing_notes, "counted twice")

    # ------------------------------------------------------------------
    # Timezone correctness
    # ------------------------------------------------------------------

    def test_order_date_uses_the_users_day_not_utc(self):
        """A UTC date combined with a UTC time lands orders on the wrong day
        either side of midnight for any offset timezone."""
        self.env.user.tz = "Pacific/Auckland"          # UTC+12/+13
        Order = self.env["pos.order"].with_user(self.env.user)
        # 22:00 UTC is already the next day in Auckland.
        session_start = datetime(2024, 6, 10, 22, 0, 0)
        original = datetime(2024, 6, 15, 3, 30, 0)

        result = Order._pos_backdate_order_datetime(original, session_start)

        tz = pytz.timezone("Pacific/Auckland")
        local_result = pytz.utc.localize(result).astimezone(tz)
        local_session = pytz.utc.localize(session_start).astimezone(tz)
        local_original = pytz.utc.localize(original).astimezone(tz)

        self.assertEqual(local_result.date(), local_session.date())
        self.assertEqual(local_result.time(), local_original.time())

    def test_order_date_survives_a_dst_boundary(self):
        self.env.user.tz = "Europe/Brussels"
        Order = self.env["pos.order"]
        result = Order._pos_backdate_order_datetime(
            datetime(2024, 3, 31, 10, 0, 0), datetime(2024, 3, 31, 5, 0, 0),
        )
        self.assertIsInstance(result, datetime)

    # ------------------------------------------------------------------
    # Valuation layers — the query that used to rewrite the whole table
    # ------------------------------------------------------------------

    def test_valuation_redate_touches_only_this_sessions_layers(self):
        """The exact regression: the previous `UPDATE ... FROM` had no
        `id = svl.id` correlation, so it rewrote every layer in the database."""
        product = self.env["product.product"].create({
            "name": "Backdate Widget",
            "is_storable": True,
            "categ_id": self.env.ref("product.product_category_all").id,
        })
        SVL = self.env["stock.valuation.layer"].sudo()
        layer_vals = {
            "company_id": self.env.company.id,
            "product_id": product.id,
            "quantity": 1,
            "unit_cost": 5.0,
            "value": 5.0,
        }
        ours = SVL.create({**layer_vals, "description": "this session"})
        stranger = SVL.create({**layer_vals, "description": "nothing to do with POS"})
        untouched_before = stranger.create_date

        session = self._open_session()
        session.sudo().write({"backdate_stop": self.backdate})

        with patch.object(
            type(session), "_pos_backdate_valuation_layers", lambda record: ours
        ):
            session._pos_backdate_valuation_layers_date()

        (ours | stranger).invalidate_recordset(["create_date"])
        self.assertEqual(ours.create_date, self.backdate, "the session's layer should move")
        self.assertEqual(
            stranger.create_date, untouched_before,
            "an unrelated layer must not be re-dated",
        )

    def test_valuation_redate_is_a_noop_without_a_date(self):
        session = self._open_session()
        session._pos_backdate_valuation_layers_date()  # must not raise

    # ------------------------------------------------------------------
    # Front end
    # ------------------------------------------------------------------

    def test_templates_and_code_reach_the_pos_bundle(self):
        """The 17.0 front end was bundled and served, and silently never ran.

        The POS wraps its bundle in `ignore_missing_deps`, so a module with one
        dead import is skipped without a console message. Checking the bundle
        catches the other half of that failure: a template whose `t-inherit`
        anchor no longer exists in core.
        """
        bundle = self.env["ir.attachment"].search([
            ("name", "=like", "point_of_sale.assets_prod%.js"),
        ], limit=1)
        self.assertTrue(bundle, "the POS bundle should have been generated")
        raw = bundle.raw or b""
        for needle in (
            b"opening-date-section",
            b"closing-date-section",
            b"set_backdate_start",
            b"set_backdate_stop",
        ):
            self.assertIn(needle, raw, "%s missing from the POS bundle" % needle.decode())

    def test_closing_template_anchor_still_exists_in_core(self):
        """`t-inherit` fails loudly at build time, but only if the bundle is
        rebuilt — assert the anchor directly so a core upgrade that renames it
        is caught here rather than at a till."""
        with file_open(
            "point_of_sale/static/src/app/navbar/closing_popup/closing_popup.xml", "r",
        ) as template:
            self.assertIn("closing-notes-container", template.read())

    # ------------------------------------------------------------------
    # Browser
    # ------------------------------------------------------------------

    def test_backdate_tour(self):
        """Renders both date pickers and confirms the opening dialog.

        Presence in the asset bundle proves nothing here — the POS silently
        skips a module whose imports do not resolve, which is precisely how the
        17.0 front end behaved on 18. Only rendering is evidence.
        """
        # Backdating is a manager action; the tour drives it as one.
        self.pos_user.write({
            "groups_id": [(4, self.env.ref("pos_session_date_manager.group_pos_backdate").id)],
        })
        self.main_pos_config.with_user(self.pos_user).open_ui()
        session = self.main_pos_config.current_session_id
        self.assertFalse(session.backdate_start)

        self.start_pos_tour("PosBackdateTour")

        session.invalidate_recordset(["backdate_start", "start_at"])
        self.assertTrue(
            session.backdate_start,
            "confirming the opening dialog should have stored the adjusted date",
        )
        self.assertEqual(
            session.start_at, session.backdate_start,
            "_set_opening_control_data should move start_at onto the adjusted date",
        )
