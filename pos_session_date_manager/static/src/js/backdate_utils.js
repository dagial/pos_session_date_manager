import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { serializeDateTime, deserializeDateTime } from "@web/core/l10n/dates";

const { DateTime } = luxon;

/**
 * Whatever the POS data service handed us, as a luxon DateTime.
 *
 * Datetime fields normally arrive already deserialised, but a value written
 * back by our own RPC comes through as a string, so both are accepted.
 */
export function toDateTime(value) {
    if (!value) {
        return false;
    }
    if (value instanceof DateTime) {
        return value;
    }
    try {
        return deserializeDateTime(value);
    } catch {
        return false;
    }
}

/**
 * Push an adjusted date to the server and report failures where the user can
 * see them.
 *
 * Validation lives on the server — group membership, the accounting lock
 * dates, dates in the future — because the browser is not where that decision
 * belongs. This surfaces whatever the server refused.
 *
 * @returns {Promise<boolean>} whether the date was accepted
 */
export async function pushBackdate(pos, dialog, method, value) {
    if (!value || !value.isValid) {
        dialog.add(AlertDialog, {
            title: _t("Invalid date"),
            body: _t("Please provide a valid date before continuing."),
        });
        return false;
    }
    try {
        // `pos.data.call` does not hand back the method's return value, so a
        // rejection is the only signal available. A refusal therefore has to
        // stop the caller here — `confirm`/`closeSession` return without
        // calling super, leaving the dialog open with the error on screen
        // rather than quietly proceeding on today's date.
        await pos.data.call("pos.session", method, [pos.session.id, serializeDateTime(value)]);
        return true;
    } catch (error) {
        dialog.add(AlertDialog, {
            title: _t("Date not accepted"),
            body: error?.data?.message || error?.message || _t("The date could not be saved."),
        });
        return false;
    }
}
