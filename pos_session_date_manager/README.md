# POS Date Adjustment for Accounting and Stock

Record a Point of Sale session on the day it actually happened, with sales,
accounting and stock all agreeing.

---

## 1. The problem

Closing a POS session stamps "now" on about ten different records. Enter
yesterday's session this morning and every one of them disagrees with the day
the sale happened:

| Record | Dated by core with |
|---|---|
| `pos.session.start_at` / `stop_at` | `now()` |
| `pos.order.date_order` | the client clock |
| `pos.payment.payment_date` | `now()` |
| session `account.move` | `context_today` |
| `account.payment` | today |
| `account.bank.statement.line` | today |
| `stock.picking` scheduled / done | `now()` |
| `stock.move` | `now()` |
| stock's `account.move` | `now()` |
| `stock.valuation.layer` | `create_date` |

Miss one and you have created the inconsistency you were trying to fix.

## 2. How it works

Enable **Allow Date Adjustment** on a Point of Sale. Two date pickers then
appear — one in the opening control, one in the closing popup. Whatever is
chosen is stored on the session, and every record the session produces is dated
from it.

## 3. The one design rule

**The dates live on the session record. They are never passed as arguments.**

This is not a style preference. `pos.close.session.wizard.close_session()`
calls:

```python
session.action_pos_session_closing_control(self.account_id, self.amount_to_balance)
```

positionally. An override that adds a leading `closing_date` parameter does not
raise — it silently lands an `account.account` in a date field and an amount in
`balancing_account`. The same trap applies to `close_session_from_ui` and
`update_closing_control_state_session`, both of which core calls with its own
argument list.

So every override here keeps core's exact signature and reads what it needs from
`self`. Three tests assert those signatures, so a future edit that reintroduces
an extra parameter fails the build.

Downstream, one context key — `pos_backdate` — is set once in
`action_pos_session_closing_control` and read by the picking, move, payment and
statement-line overrides. It is set nowhere else, so those overrides are inert
during normal operation.

## 4. Opening

Core marks `set_opening_control` **"DO NOT INHERIT THIS METHOD"** and delegates
to `_set_opening_control_data`. That is the hook used here.

## 5. Valuation layers

`stock.valuation.layer` has no date field — valuation reports order and filter
on `create_date`, and the column is not writable through the ORM, so this is the
one place raw SQL is unavoidable. It is scoped by primary key:

```sql
UPDATE stock_valuation_layer SET create_date = %s WHERE id = ANY(%s)
```

> **Previously** this was an uncorrelated `UPDATE ... FROM stock_valuation_layer svl`
> with no `id = svl.id` join. Postgres paired every target row with every
> matching row, so a single matching picking name rewrote `create_date` on
> **every valuation layer in the database** — all products, all companies, all
> years, unrecoverable without a backup. A test now asserts that re-dating one
> session leaves unrelated layers untouched.

## 6. Who is allowed

Backdating writes into past accounting periods, so it is not open to every
cashier:

- it requires the group **Point of Sale: Adjust Session Dates**
  (implied by POS Manager)
- it is refused before `fiscalyear_lock_date` and `hard_lock_date`
- it is refused for dates in the future, and for a closing date earlier than the
  opening date

All of that is enforced server side. The browser only displays the refusal.

## 7. Timezones

The day a user means is the day in *their* timezone. Orders are moved onto the
session's day by converting to the user's timezone, recombining, and converting
back — and the recombined value is localised rather than `replace()`d, so DST
transitions stay correct. Combining a UTC date with a UTC time, as the previous
version did, put orders on the wrong day either side of midnight for any
offset timezone.

## 8. Requirements

Inventory must be updated **at session closing**, not in real time. With real
time updates the stock moves are written per order as they are rung up, so
there is no single moment at which they can be dated coherently. A constraint
enforces this.

## 9. Tests

```
python odoo-bin -c config/odoo.conf -d <db> -u pos_session_date_manager \
    --stop-after-init --test-enable --test-tags /pos_session_date_manager
```

(from PowerShell, not Git Bash — MSYS rewrites the leading `/` into a Windows
path and the selector silently matches nothing.)

Covers the configuration guard, all four validation rules, the three core
signatures, closing-note preservation, timezone and DST handling, and the
valuation-layer scoping.

## 10. Upgrading from the 17.0 version

The `reporting` flag on `pos.config` keeps its name and value. Everything else
was rewritten: the front end targeted the popup system removed in 18, and
several Python overrides no longer matched core's signatures.

Because the POS asset bundle is wrapped in `ignore_missing_deps`, the old
JavaScript did not error on 18 — it was **skipped silently**, so the date
pickers simply never appeared.

## 11. Compatibility

Odoo **18.0**, Community or Enterprise.
