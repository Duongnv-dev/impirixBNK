odoo.define('impx_can_crm.model.Message', function (require) {
"use strict";

    var Message = require('mail.model.Message');

    Message.include({
        _setInitialData: function (data){
            this._customerEmailData = data.customer_email_data || [];
            this._customerEmailStatus = data.customer_email_status;
            this._documentModel = data.model;
            this._documentName = data.record_name;
            this._rootdocumentName = data.root_name;
            this._documentID = data.res_id;
            this._emailFrom = data.email_from;
            this._info = data.info;
            this._isNote = data.is_note;
            this._moduleIcon = data.module_icon;
            this._needactionPartnerIDs = data.needaction_partner_ids || [];
            this._starredPartnerIDs = data.starred_partner_ids || [];
            this._historyPartnerIDs = data.history_partner_ids || [];
            this._subject = data.subject;
            this._subtypeDescription = data.subtype_description;
            this._threadIDs = data.channel_ids || [];
            this._trackingValueIDs = data.tracking_value_ids;

            this._moderationStatus = data.moderation_status || 'accepted';
        }
    });
});
