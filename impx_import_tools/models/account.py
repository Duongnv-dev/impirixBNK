# -*- coding: utf-8 -*-

from odoo import fields, models, api


class AccountAccount(models.Model):
    _inherit = "account.account"

    display_name = fields.Char(compute='get_display_name', string='Display Name', store=True)

    @api.depends('code', 'name')
    def get_display_name(self):
        for account in self:
            if account.code and account.name:
                account.display_name = account.code + ' ' + account.name
            else:
                account.display_name = account.code or account.name