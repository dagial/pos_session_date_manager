import { patch } from "@web/core/utils/patch";
import { OpeningControlPopup } from "@point_of_sale/app/store/opening_control_popup/opening_control_popup";
import { DateTimeInput } from "@web/core/datetime/datetime_input";
import { pushBackdate } from "@pos_session_date_manager/js/backdate_utils";

const { DateTime } = luxon;

// Owl reads `components` off the class, so the picker has to be registered
// there — `patch` only reaches the prototype.
OpeningControlPopup.components = { ...OpeningControlPopup.components, DateTimeInput };

patch(OpeningControlPopup.prototype, {
    setup() {
        super.setup();
        // `state` is already reactive; adding a key here is picked up by the
        // template.
        this.state.openingDate = DateTime.now();
    },

    get allowBackdate() {
        return Boolean(this.pos.config.reporting);
    },

    onOpeningDateChange(value) {
        this.state.openingDate = value;
    },

    /**
     * The date is stored before core opens the session, so that core's own
     * `_set_opening_control_data` can read it off the record and move
     * `start_at` back. Nothing about core's call is changed.
     */
    async confirm() {
        if (this.allowBackdate) {
            const accepted = await pushBackdate(
                this.pos, this.dialog, "set_backdate_start", this.state.openingDate,
            );
            if (!accepted) {
                return;
            }
            // The server has moved `start_at`, but the browser is holding the
            // copy it loaded when the session opened and nothing refetches it.
            // Set from the value just accepted rather than from the call's
            // result: `pos.data.call` does not hand back a method's return
            // value. Without this the closing popup, which seeds its date from
            // `session.start_at`, would default to the wrong day.
            this.pos.session.start_at = this.state.openingDate;
        }
        return super.confirm();
    },
});
