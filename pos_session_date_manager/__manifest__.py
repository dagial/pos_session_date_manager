{
    "name": "POS Date Adjustment for Accounting and Stock",
    "author": "Dagem Alemayehu",
    "version": "17.0.1.0.0",
    "website": "mailto:dagemalemayehu123@gmail.com",
    "category": "Point Of Sale",
    "price": "150",
    "currency": "USD",
    "description": """
    Adds A Functionality for adding Backlog sales on the pos.
    """,
    "depends": ["point_of_sale"],
    "data": [
        "views/pos_closing_session_wizard.xml",
        "views/point_of_sale.xml",
        "views/pos_order_update.xml",
        "views/pos_order_list.xml"

    ],
    'assets': {
        'point_of_sale._assets_pos': [
            "pos_session_date_manager/static/src/**/*"
        ]
    },
    "licence": "LGPL-3"
}
