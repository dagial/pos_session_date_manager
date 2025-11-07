from odoo import models, fields, api, tools, _
from odoo.exceptions import AccessDenied, AccessError, UserError, ValidationError
from odoo.tools import float_is_zero, float_compare, convert
from itertools import groupby
import re


class PosSession(models.Model):
    _inherit = "pos.session"

    def _create_account_move(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        """ Create account.move and account.move.line records for this session.

        Side-effects include:
            - setting self.move_id to the created account.move record
            - reconciling cash receivable lines, invoice receivable lines and stock output lines
        """
        account_move = self.env['account.move'].create({
            'journal_id': self.config_id.journal_id.id,
            'date': self.stop_at,
            'ref': self.name,
        })
        self.write({'move_id': account_move.id})

        data = {'bank_payment_method_diffs': bank_payment_method_diffs or {}}
        data = self._accumulate_amounts(data)
        data = self._create_non_reconciliable_move_lines(data)
        data = self._create_bank_payment_moves(data)
        data = self._create_pay_later_receivable_lines(data)
        data = self._create_cash_statement_lines_and_cash_move_lines(data)
        data = self._create_invoice_receivable_lines(data)
        data = self._create_stock_output_lines(data)

        if self.config_id.reporting:
            self._change_stock_valuation_date()
        if balancing_account and amount_to_balance:
            data = self._create_balancing_line(data, balancing_account, amount_to_balance)

        return data

    # To Do dont pass stop_at always only if passed from ui
    def update_closing_control_state_session(self, notes, closing_date):
        # Prevent closing the session again if it was already closed
        if self.state == 'closed':
            raise UserError(_('This session is already closed.'))
        # Prevent the session to be opened again.
        self.write({'state': 'closing_control', 'stop_at': closing_date, 'closing_notes': "always work"})
        self._post_cash_details_message('Closing', self.cash_register_difference, notes)

    def close_session_from_ui(self, closing_date, bank_payment_method_diff_pairs=None):
        """Calling this method will try to close the session.

        param bank_payment_method_diff_pairs: list[(int, float)]
            Pairs of payment_method_id and diff_amount which will be used to post
            loss/profit when closing the session.

        If successful, it returns {'successful': True}
        Otherwise, it returns {'successful': False, 'message': str, 'redirect': bool}.
        'redirect' is a boolean used to know whether we redirect the user to the back end or not.
        When necessary, error (i.e. UserError, AccessError) is raised which should redirect the user to the back end.
        """
        bank_payment_method_diffs = dict(bank_payment_method_diff_pairs or [])
        self.ensure_one()
        # Even if this is called in `post_closing_cash_details`, we need to call this here too for case
        # where cash_control = False
        check_closing_session = self._cannot_close_session(bank_payment_method_diffs)
        if check_closing_session:
            return check_closing_session
        if self.config_id.reporting:
            new_context = dict(self.env.context)
            new_context.update({'pos_session': {'id': self.id, 'closing_date': closing_date}})
            self = self.with_context(new_context)
        validate_result = self.action_pos_session_closing_control(closing_date=closing_date,
                                                                  bank_payment_method_diffs=bank_payment_method_diffs)

        # If an error is raised, the user will still be redirected to the back end to manually close the session.
        # If the return result is a dict, this means that normally we have a redirection or a wizard => we redirect the user
        if isinstance(validate_result, dict):
            # imbalance accounting entry
            return {
                'successful': False,
                'message': validate_result.get('name'),
                'redirect': True
            }

        self.message_post(body='Point of Sale Session ended')

        return {'successful': True}

    def action_pos_session_closing_control(self, closing_date=None, balancing_account=False, amount_to_balance=0,
                                           bank_payment_method_diffs=None):

        bank_payment_method_diffs = bank_payment_method_diffs or {}
        for session in self:
            if any(order.state == 'draft' for order in session.order_ids):
                raise UserError(_("You cannot close the POS when orders are still in draft"))
            if session.state == 'closed':
                raise UserError(_('This session is already closed.'))
            stop_at = closing_date if self.config_id.reporting and closing_date and self.update_stock_at_closing else fields.Datetime.now()
            session.write({'state': 'closing_control', 'stop_at': stop_at})
            if not session.config_id.cash_control:
                return session.action_pos_session_close(balancing_account, amount_to_balance, bank_payment_method_diffs)
            # If the session is in rescue, we only compute the payments in the cash register
            # It is not yet possible to close a rescue session through the front end, see `close_session_from_ui`
            if session.rescue and session.config_id.cash_control:
                default_cash_payment_method_id = self.payment_method_ids.filtered(lambda pm: pm.type == 'cash')[0]
                orders = self._get_closed_orders()
                total_cash = sum(
                    orders.payment_ids.filtered(lambda p: p.payment_method_id == default_cash_payment_method_id).mapped(
                        'amount')
                ) + self.cash_register_balance_start

                session.cash_register_balance_end_real = total_cash

            return session.action_pos_session_validate(balancing_account, amount_to_balance, bank_payment_method_diffs)

    def _create_combine_account_payment(self, payment_method, amounts, diff_amount):
        outstanding_account = payment_method.outstanding_account_id or self.company_id.account_journal_payment_debit_account_id
        destination_account = self._get_receivable_account(payment_method)

        if float_compare(amounts['amount'], 0, precision_rounding=self.currency_id.rounding) < 0:
            # revert the accounts because account.payment doesn't accept negative amount.
            outstanding_account, destination_account = destination_account, outstanding_account

        account_payment = self.env['account.payment'].create({
            'amount': abs(amounts['amount']),
            'journal_id': payment_method.journal_id.id,
            'force_outstanding_account_id': outstanding_account.id,
            'destination_account_id': destination_account.id,
            'ref': _('Combine %s POS payments from %s', payment_method.name, self.name),
            'pos_payment_method_id': payment_method.id,
            'pos_session_id': self.id,
            'company_id': self.company_id.id,
            'date': self.stop_at
        })

        diff_amount_compare_to_zero = self.currency_id.compare_amounts(diff_amount, 0)
        if diff_amount_compare_to_zero != 0:
            self._apply_diff_on_account_payment_move(account_payment, payment_method, diff_amount)

        account_payment.action_post()
        return account_payment.move_id.line_ids.filtered(
            lambda line: line.account_id == account_payment.destination_account_id)

    def _create_split_account_payment(self, payment, amounts):
        payment_method = payment.payment_method_id
        if not payment_method.journal_id:
            return self.env['account.move.line']
        outstanding_account = payment_method.outstanding_account_id or self.company_id.account_journal_payment_debit_account_id
        accounting_partner = self.env["res.partner"]._find_accounting_partner(payment.partner_id)
        destination_account = accounting_partner.property_account_receivable_id

        if float_compare(amounts['amount'], 0, precision_rounding=self.currency_id.rounding) < 0:
            # revert the accounts because account.payment doesn't accept negative amount.
            outstanding_account, destination_account = destination_account, outstanding_account

        account_payment = self.env['account.payment'].create({
            'amount': abs(amounts['amount']),
            'partner_id': payment.partner_id.id,
            'journal_id': payment_method.journal_id.id,
            'force_outstanding_account_id': outstanding_account.id,
            'destination_account_id': destination_account.id,
            'ref': _('%s POS payment of %s in %s', payment_method.name, payment.partner_id.display_name,
                     self.name),
            'pos_payment_method_id': payment_method.id,
            'pos_session_id': self.id,
            'date': self.stop_at
        })
        account_payment.action_post()
        return account_payment.move_id.line_ids.filtered(
            lambda line: line.account_id == account_payment.destination_account_id)

    def _create_picking_at_end_of_session(self):
        self.ensure_one()
        lines_grouped_by_dest_location = {}
        picking_type = self.config_id.picking_type_id

        if not picking_type or not picking_type.default_location_dest_id:
            session_destination_id = self.env['stock.warehouse']._get_partner_locations()[0].id
        else:
            session_destination_id = picking_type.default_location_dest_id.id

        for order in self._get_closed_orders():
            if order.company_id.anglo_saxon_accounting and order.is_invoiced or order.shipping_date:
                continue
            destination_id = order.partner_id.property_stock_customer.id or session_destination_id
            if destination_id in lines_grouped_by_dest_location:
                lines_grouped_by_dest_location[destination_id] |= order.lines
            else:
                lines_grouped_by_dest_location[destination_id] = order.lines

        for location_dest_id, lines in lines_grouped_by_dest_location.items():
            pickings = self.env['stock.picking']._create_picking_from_pos_order_lines(location_dest_id, lines,
                                                                                      picking_type)
            if self.env.context.get('force_period_date'):
                pickings.write({'pos_session_id': self.id, 'origin': self.name,
                                "date_done": self.env.context.get('force_period_date'),
                                "scheduled_date": self.env.context.get('force_period_date')})
            else:
                pickings.write({'pos_session_id': self.id, 'origin': self.name})

    def _get_combine_statement_line_vals(self, journal_id, amount, payment_method):
        combine_statement_vals = super()._get_combine_statement_line_vals(journal_id, amount, payment_method)

        if self.env.context.get("pos_session"):
            combine_statement_vals["date"] = self.env.context.get("pos_session")["closing_date"]

        return combine_statement_vals

    def _post_statement_difference(self, amount, is_opening, opening_date=None):
        if amount:
            if self.config_id.cash_control:
                st_line_vals = {
                    'journal_id': self.cash_journal_id.id,
                    'amount': amount,
                    'date': opening_date if opening_date else (
                            self.statement_line_ids.sorted()[-1:].date or fields.Date.context_today(self)),
                    'pos_session_id': self.id,
                }

            if amount < 0.0:
                if not self.cash_journal_id.loss_account_id:
                    raise UserError(
                        _('Please go on the %s journal and define a Loss Account. This account will be used to record cash difference.',
                          self.cash_journal_id.name))

                st_line_vals['payment_ref'] = _("Cash difference observed during the counting (Loss)") + (
                    _(' - opening') if is_opening else _(' - closing'))
                if not is_opening:
                    st_line_vals['counterpart_account_id'] = self.cash_journal_id.loss_account_id.id
            else:
                # self.cash_register_difference  > 0.0
                if not self.cash_journal_id.profit_account_id:
                    raise UserError(
                        _('Please go on the %s journal and define a Profit Account. This account will be used to record cash difference.',
                          self.cash_journal_id.name))

                st_line_vals['payment_ref'] = _("Cash difference observed during the counting (Profit)") + (
                    _(' - opening') if is_opening else _(' - closing'))
                if not is_opening:
                    st_line_vals['counterpart_account_id'] = self.cash_journal_id.profit_account_id.id

            self.env['account.bank.statement.line'].create(st_line_vals)

    def set_cashbox_pos(self, cashbox_value: int, notes: str, opening_date=None):
        self.state = 'opened'
        self.opening_notes = notes
        difference = cashbox_value - self.cash_register_balance_start
        self.cash_register_balance_start = cashbox_value
        self.sudo()._post_statement_difference(difference, True, opening_date)
        self._post_cash_details_message('Opening', difference, notes)

    def set_opening_date(self, opening_date):
        if self.config_id.reporting:
            self.write({
                "start_at": opening_date
            })

    def _change_stock_valuation_date(self):
        picking_ids = self.picking_ids.mapped("name")

        query = """
                UPDATE stock_valuation_layer
                SET create_date = %s
                FROM stock_valuation_layer svl 
                LEFT JOIN stock_move sm on sm.id = svl.stock_move_id
                WHERE sm.reference = ANY(%s::text[])
        """

        self.env.cr.execute(query, [self.stop_at, picking_ids])

