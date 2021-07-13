# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError


class StockProductionLot(models.Model):
    _inherit = 'stock.production.lot'

    mrp_order_id = fields.Many2one('mrp.production', 'Manufacturing order')
    mrp_order_date = fields.Datetime('Manufacturing order date')
    production_batch_id = fields.Char('Production Batch ID', readonly=True)



