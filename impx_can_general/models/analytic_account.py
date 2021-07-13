# -*- encoding: utf-8 -*-

from odoo import api, fields, models, _


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    cannabis_license_id = fields.Many2one('cannabis.license', string='Cannabis License')
    _sql_constraints = [
        ('unique_cannabis_license_id', 'unique (cannabis_license_id)', 'The cannabis license number must be unique!'),
    ]
