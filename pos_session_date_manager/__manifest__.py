{
    "name": "POS Date Adjustment for Accounting and Stock",
    "author": "Dagem Alemayehu",
    "version": "18.0.2.0.0",
    "website": "mailto:dagemalemayehu123@gmail.com",
    "category": "Sales/Point of Sale",
    "summary": "Record backdated POS sessions with accounting and stock in step",
    "description": """
Adjust the opening and closing dates of a Point of Sale session.

Closing a session stamps "now" on about ten different records — the session,
the orders, the payments, the journal entry, the bank statement lines, the
picking, the stock moves, their journal entries and the valuation layers. Enter
a session late and those all disagree with the day the sale actually happened.

This module lets an authorised user set the two dates that matter, and carries
them through every record the session produces.

Enable it per Point of Sale ("Allow Date Adjustment"). It requires stock to be
updated at session closing rather than in real time: with real time updates the
moves are written per order as they are rung up, so there is no single moment
at which they can be dated coherently.
    """,
    "depends": [
        "point_of_sale",
        # `stock.move._prepare_account_move_vals` and `stock.valuation.layer`
        # both live here; POS alone does not guarantee them.
        "stock_account",
    ],
    "data": [
        "security/pos_backdate_security.xml",
        "views/pos_config_views.xml",
        "views/pos_session_views.xml",
        "views/pos_close_session_wizard_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_session_date_manager/static/src/**/*",
        ],
        # Must live under static/tests: `js_transpiler.url_to_module_path` only
        # maps /static/src, /static/lib and /static/tests to module names.
        # Anywhere else the file is served as a plain script, its imports never
        # resolve, and the tour silently never registers.
        "web.assets_tests": [
            "pos_session_date_manager/static/tests/tours/**/*",
        ],
    },
    "license": "OPL-1",
    "images": ["static/description/main_screenshot.png"],
    "installable": True,
    "application": False,
}
