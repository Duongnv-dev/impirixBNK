# -*- coding: utf-8 -*-

from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_assign(self):
        picking_type_codes = self.filtered(
            lambda m: m.state in ['confirmed', 'waiting', 'partially_available']).mapped(
            'picking_id.picking_type_id.code')

        if 'outgoing' in picking_type_codes:
            return super(StockMove, self.with_context(assign_outgoing_picking=True))._action_assign()

        return super()._action_assign()
