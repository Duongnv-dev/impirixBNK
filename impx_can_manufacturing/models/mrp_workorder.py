# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, SUPERUSER_ID


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

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

    def record_production(self):
        res = super(MrpWorkorder, self).record_production()
        if self.finished_lot_id:
            self.finished_lot_id.mrp_order_id = self.production_id.id
            self.finished_lot_id.mrp_order_date = self.production_id.date_planned_start
            self.finished_lot_id.production_batch_id = self.production_id.production_batch_id
        return res

    def action_split_package(self):
        self.ensure_one()
        action_obj = self.env.ref('impx_can_inventory.wizard_split_stock_production_lot_action')
        action = action_obj.read([])[0]
        context = dict(self.lot_id._context)
        context['default_lot_id'] = self.lot_id.id
        context['default_new_qty'] = self.lot_id.product_qty - self.qty_done
        action['context'] = context
        return action

