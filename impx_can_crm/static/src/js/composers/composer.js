odoo.define('impx_can_crm.composer.Basic', function (require) {
"use strict";

var BasicComposer = require('mail.composer.Basic');

var core = require('web.core');

var QWeb = core.qweb;

var Dialog = require('web.Dialog');

var _t = core._t;

BasicComposer.include({

    init: function (parent, options) {
        this._super(parent, options);
        if (this.options.isLog === false) {
            this.extended = true;
        }
    },
    start: function () {
        this._$subjectInput = this.$('.o_composer_subject input');
        return this._super.apply(this, arguments);
    },


    _preprocessMessage: function () {
        var self = this;
        return this._super().then(function (message) {
            var subject = self._$subjectInput.val();
            message.subject = subject;
            return message;
        });
    },

    _sendMessage: function () {
        if(this.$('.o_composer_subject input') != undefined){
            if(this.$('.o_composer_subject input').val() != undefined){
                 if (this.$('.o_composer_subject input').val().length == 0) {
                    Dialog.alert(self, '', {
                        title: _t("Something went wrong !"),
                        $content: $('<div/>').html(
                            _t("The following fields are invalid: Subject. Please fill in subject before sending message or log note!")
                        )
                    });
                    return;
                }
            }
        }
        return this._super.apply(this, arguments);


    },

});

});
