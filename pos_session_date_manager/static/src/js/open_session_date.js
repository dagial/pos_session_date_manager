/** @odoo-module **/

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { useService } from "@web/core/utils/hooks";
import { useState } from "@odoo/owl";
import { Input } from "@point_of_sale/app/generic_components/inputs/input/input";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { PosStore } from "@point_of_sale/app/store/pos_store";
const { DateTime } = luxon;
export class OpeningSessionDate extends AbstractAwaitablePopup {

    static template = "pos_session_date_manager.OpeningSession"

    setup(){
        super.setup()
        this.state=useState({
            opening_date:DateTime.now().toISODate()
        })
        this.pos=usePos()
        this.popup = useService("popup");
        this.orm = useService("orm");
    }
    handleDateChange(e){
        this.state.opening_date=e.target.value
    }
    async confirm(){


        this.orm.call("pos.session", "set_opening_date", [
            this.pos.pos_session.id,
            this.state.opening_date
        ]);
        this.pos.pos_session.start_at = this.state.opening_date
        super.confirm()
    }

}

patch(ProductScreen.prototype,{

    onMounted() {
        this.pos.openSessionDatePopup()
        super.onMounted(...arguments)
    }
})
patch(PosStore.prototype,{

    openSessionDatePopup(){
        if (this.shouldSetOpeningDate()){
            this.popup.add(OpeningSessionDate)
        }
    },
    shouldSetOpeningDate(){

        return this.pos_session.state === "opening_control" && this.config.reporting
    }

})