# -*- coding: utf-8 -*-

from odoo import api, fields, models, _, tools
from odoo.exceptions import UserError, ValidationError, AccessError

class MailComposer(models.TransientModel):
    _inherit = 'mail.compose.message'

    @api.model
    def get_record_data(self, values):
        res = super(MailComposer, self).get_record_data(values)
        context = self._context
        if res.get('subject', False):
            if context.get('default_composition_mode') == 'comment':
                res.pop('subject')
        return res