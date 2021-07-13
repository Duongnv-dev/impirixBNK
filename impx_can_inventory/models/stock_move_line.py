# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import UserError


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def _compute_need_split_package(self):
        for line in self:
            if line.picking_id.state in ('draft', 'cancel'):
                line.need_split_package = False
                continue

            if not line.product_id.is_cannabis:
                line.need_split_package = False
                continue

            if line.picking_id.picking_type_id.code != 'outgoing':
                line.need_split_package = False
                continue

            if line.product_id.tracking not in ('lot', 'serial'):
                line.need_split_package = False
                continue

            product_uom_qty = line.product_uom_qty
            lot_qty = line.lot_id.product_qty

            line.need_split_package = product_uom_qty < lot_qty

    need_split_package = fields.Boolean(compute='_compute_need_split_package')

    def open_split_package(self):
        self.ensure_one()
        product_uom_qty = self.product_uom_qty
        lot_qty = self.lot_id.product_qty
        remain_qty = lot_qty - product_uom_qty
        return self.lot_id.with_context(
            default_new_qty=remain_qty, default_from_move_line_id=self.id).open_split_package()

    def _action_done(self):
        for move_line in self:
            if move_line.need_split_package:
                raise UserError(_('Error: Please split package before validate Delivery order !'))
        return super()._action_done()
