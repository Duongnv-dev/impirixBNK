# -*- coding: utf-8 -*-

from odoo import fields, models, api


class StockLocation(models.Model):
    _inherit = 'stock.location'

    @api.depends('warehouse_ids.analytic_account_id')
    def _compute_analytic_account_id(self):
        for location in self:
            analytic_account_ids = location.warehouse_ids.mapped('analytic_account_id')._ids
            analytic_account_id = analytic_account_ids and analytic_account_ids[0] or False
            location.analytic_account_id = analytic_account_id

    warehouse_ids = fields.One2many('stock.warehouse', 'lot_stock_id', readonly=True)
    analytic_account_id = fields.Many2one('account.analytic.account', compute='_compute_analytic_account_id',
                                          string='License Number', store=True)
