# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, SUPERUSER_ID
from odoo.exceptions import ValidationError, UserError


class MrpProductProduce(models.TransientModel):
    _inherit = "mrp.product.produce"

    def _record_production(self):
        res = super(MrpProductProduce, self)._record_production()
        if self.finished_lot_id:
            self.finished_lot_id.mrp_order_id = self.production_id.id
            self.finished_lot_id.mrp_order_date = self.production_id.date_planned_start
            self.finished_lot_id.production_batch_id = self.production_id.production_batch_id
        return res

    def do_produce(self):
        for rec in self.raw_workorder_line_ids:
            if rec.is_need_split_package:
                if not rec.new_package_tag_id or not rec.new_name:
                    raise ValidationError(_("Some component must be split package!"))
                new_qty = rec.lot_id.product_qty - rec.qty_done
                new_package = rec.lot_id.new_package_from_origin_package(
                    new_qty, rec.new_package_tag_id.id, new_name=rec.new_name)
                remain_qty = rec.lot_id.product_qty - new_qty
                rec.lot_id.adjust_package_qty(remain_qty)
        return super(MrpProductProduce, self).do_produce()


class MrpProductProduceLine(models.TransientModel):
    _inherit = "mrp.product.produce.line"

    new_package_tag_id = fields.Many2one('package.tags', 'New Tag', required=False, domain=[('used', '=', False)])
    new_name = fields.Char()
    is_need_split_package = fields.Boolean(compute='_compute_need_split_package', string='Need split package')

    @api.depends("lot_id")
    def _compute_need_split_package(self):
        for rec in self:
            if rec.lot_id and rec.lot_id.product_id.is_cannabis and rec.qty_done:
                if rec.lot_id.product_qty - rec.qty_done > 0:
                    rec.is_need_split_package = True
                else:
                    rec.is_need_split_package = False
            else:
                rec.is_need_split_package = False

