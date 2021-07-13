# -*- coding: utf-8 -*-

from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    analytic_account_id = fields.Many2one('account.analytic.account', string='License Number', required=True,
                                          domain=[('cannabis_license_id', '!=', False)])

    _sql_constraints = [
        ('analytic_account_id_uniq', 'unique (analytic_account_id)', 'The license number must be unique!')
    ]
