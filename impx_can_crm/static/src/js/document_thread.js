odoo.define('impx_can_crm.ThreadField', function (require) {
"use strict";
var ThreadField = require('mail.ThreadField');
var session = require('web.session');
ThreadField.include({
    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------
    /**
    * Override the thread rendering to warn the FormRenderer about attachments.
    * This is used by the FormRenderer to display an attachment preview.
    *
    * @override
    * @private
    */

    events: _.extend({}, ThreadField.prototype.events, {
    "click .show-more" : "message_action_show_more",
    }),

    _render: function () {
        var self = this;
        var _id = self.recordData.id;
        var el = this.$el;
        if (this.attrs.options != undefined){
            if (this.attrs.options['root_parent_id'] == 1){
                if (_id != false){
                    this._rpc({
                        model: 'res.partner',
                        method: 'read',
                        args: [[_id], ['show_all_activities', 'all_message_html']],
                    }).then(function (partner) {
                        if (partner[0]['show_all_activities']) {
                            var o_mail_thread = $('.o_mail_thread')
                            o_mail_thread.html(partner[0]['all_message_html']);
                            return;
                        }
                    });
                }
            }
            if (this.attrs.options['root_lead_id'] == 1){
                if (_id != false){
                    this._rpc({
                        model: 'crm.lead',
                        method: 'read',
                        args: [[_id], ['show_all_activities', 'all_message_html']],
                    }).then(function (partner) {
                        if (partner[0]['show_all_activities']) {
                            var o_mail_thread = $('.o_mail_thread')
                            o_mail_thread.html(partner[0]['all_message_html']);
                            return;
                        }
                    });
                }
            }
        }
        return this._super.apply(this, arguments);
    },

//    message_action_show_more: function (ev) {
//        var child_element = ev.currentTarget.parentElement.children;
//        for (var index in child_element){
//            if ($(child_element[Number(index)]).hasClass('show-message')){
//                if ($(ev.currentTarget)[0].textContent === 'more...'){
//                     if ($(child_element[Number(index)]).hasClass('hide-message')){
//                        $(ev.currentTarget).text("less...");
//                        $(child_element[Number(index)]).removeClass('hide-message');
//                        break;
//                    }
//                }else{
//                    if (!$(child_element[Number(index)]).hasClass('hide-message')){
//                        $(ev.currentTarget).text("more...");
//                        $(child_element[Number(index)]).addClass('hide-message');
//                        break;
//                    }
//                }
//            }
//        }
//    },

//    $('.o_thread_message_content').addClass('overflow-content-chat');
    message_action_show_more: function (ev) {
        if($(ev.currentTarget).prev('div').hasClass('overflow-content-chat')){
            //show conent
            $(ev.currentTarget).prev('div').removeClass('overflow-content-chat')
            $(ev.currentTarget).text('Show less')
        }else{
            $(ev.currentTarget).prev('div').addClass('overflow-content-chat')
            $(ev.currentTarget).text('Show more')
        }
    },

});
});
