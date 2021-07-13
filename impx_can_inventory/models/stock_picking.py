# -*- coding: utf-8 -*-

from odoo import fields, models, api


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    analytic_account_id = fields.Many2one('account.analytic.account', string='License Number')
    transporter_license_id = fields.Many2one('res.partner', u'Transporter License')

