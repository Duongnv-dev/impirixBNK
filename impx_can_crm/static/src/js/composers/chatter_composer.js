odoo.define('impx_can_crm.composer.Chatter', function (require) {
"use strict";

var ChatterComposer = require('mail.composer.Chatter');

var mailUtils = require('mail.utils');
var session = require('web.session');

var core = require('web.core');
var viewDialogs = require('web.view_dialogs');

var _t = core._t;

ChatterComposer.include({

    _onOpenFullComposer: function () {
        if (!this._doCheckAttachmentUpload()){
            return false;
        }

        var self = this;
        var recipientDoneDef = new Promise(function (resolve, reject) {
            // any operation on the full-composer will reload the record, so
            // warn the user that any unsaved changes on the record will be lost.
            self.trigger_up('discard_record_changes', {
                proceed: function () {
                    if (self.options.isLog) {
                        resolve([]);
                    } else {
                        var checkedSuggestedPartners = self._getCheckedSuggestedPartners();
                        self._checkSuggestedPartners(checkedSuggestedPartners)
                            .then(resolve);
                    }
                },
            });
        });

        recipientDoneDef.then(function (partnerIDs) {
            var context = {
                default_parent_id: self.id,
                default_body: mailUtils.getTextToHTML(self.$input.val()),
                default_attachment_ids: _.pluck(self.get('attachment_ids'), 'id'),
                default_partner_ids: partnerIDs,
                default_is_log: self.options.isLog,
                mail_post_autofollow: true,
            };
            if (self.options.isLog === false){
                context.default_subject = mailUtils.getTextToHTML(self.$('.o_composer_subject input').val());
            }
            if (self.context.default_model && self.context.default_res_id) {
                context.default_model = self.context.default_model;
                context.default_res_id = self.context.default_res_id;
            }
            var action = {
                type: 'ir.actions.act_window',
                res_model: 'mail.compose.message',
                view_mode: 'form',
                views: [[false, 'form']],
                target: 'new',
                context: context,
            };
            self.do_action(action, {
                on_close: self.trigger.bind(self, 'need_refresh'),
            }).then(self.trigger.bind(self, 'close_composer'));
        });
    }

});

});

