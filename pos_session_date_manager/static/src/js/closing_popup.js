import { patch } from "@web/core/utils/patch";
import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import { DateTimeInput } from "@web/core/datetime/datetime_input";
import { formatDateTime } from "@web/core/l10n/dates";
import { pushBackdate, toDateTime } from "@pos_session_date_manager/js/backdate_utils";

const { DateTime } = luxon;

ClosePosPopup.components = { ...ClosePosPopup.components, DateTimeInput };

patch(ClosePosPopup.prototype, {
    getInitialState() {
        const state = super.getInitialState();
        // Default to the session's own opening moment: a backlog session is
        // almost always closed on the day it is entered for.
        state.closingDate = toDateTime(this.pos.session.start_at) || DateTime.now();
        return state;
    },

    get allowBackdate() {
        return Boolean(this.pos.config.reporting);
    },

    /**
     * The session's opening moment, for reference while choosing the closing
     * one. Read only: it was fixed when the register was opened and changing
     * it here would leave orders already dated from it out of step.
     *
     * Rendered as text rather than a disabled DateTimeInput — that component
     * has no readonly prop, and a greyed-out picker invites clicking.
     */
    get openingDateLabel() {
        const opened = toDateTime(this.pos.session.start_at);
        return opened ? formatDateTime(opened) : "";
    },

    onClosingDateChange(value) {
        this.state.closingDate = value;
    },

    /**
     * Store the date first, then let core close exactly as it always does.
     *
     * Core's `closeSession` calls `update_closing_control_state_session` and
     * `close_session_from_ui` with its own arguments; both read the date off
     * the session record, so neither signature is touched.
     */
    async closeSession() {
        if (this.allowBackdate) {
            const accepted = await pushBackdate(
                this.pos, this.dialog, "set_backdate_stop", this.state.closingDate,
            );
            if (!accepted) {
                return;
            }
        }
        return super.closeSession();
    },
});
