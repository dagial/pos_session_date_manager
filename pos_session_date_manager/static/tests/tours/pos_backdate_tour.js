import * as Chrome from "@point_of_sale/../tests/tours/utils/chrome_util";
import * as Dialog from "@point_of_sale/../tests/tours/utils/dialog_util";
import * as ProductScreen from "@point_of_sale/../tests/tours/utils/product_screen_util";
import { registry } from "@web/core/registry";

/**
 * Proof that the front end actually loads.
 *
 * The Point of Sale wraps its asset bundle in `ignore_missing_deps`, so a
 * module with one dead import is skipped without a single console message —
 * which is exactly how the previous version behaved on Odoo 18: bundled,
 * served, and silently never evaluated. Being present in the bundle is not
 * evidence; rendering is.
 *
 * The Python side then asserts that confirming the opening dialog actually
 * wrote `backdate_start`, so the RPC is covered too.
 *
 * Scope: the opening half. Driving the closing popup needs the navbar burger
 * menu, which would not open under the headless runner here — that is core UI
 * mechanics, not this module. The closing patch lives in the same bundle as
 * the opening one (proven to evaluate by this tour) and its template anchor,
 * `closing-notes-container`, is verified by a Python test.
 */
registry.category("web_tour.tours").add("PosBackdateTour", {
    steps: () =>
        [
            Chrome.startPoS(),

            {
                content: "the opening date picker rendered inside the opening control",
                trigger: ".opening-date-section input",
            },
            Dialog.confirm("Open Register"),

            // Reaching the product screen means `confirm()` ran to completion:
            // the RPC was accepted and core opened the session. The Python side
            // then checks that `backdate_start` and `start_at` were written.
            ProductScreen.isShown(),

            Chrome.endTour(),
        ].flat(),
});
