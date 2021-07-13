# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class WizardSplitStockProductionLot(models.Model):
    _name = 'wizard.split.stock.production.lot'
    _rec_name = 'lot_id'

    lot_id = fields.Many2one('stock.production.lot', 'Package', required=True)
    new_lot_id = fields.Many2one('stock.production.lot', 'New package')
    license_id = fields.Many2one(related='lot_id.license_id', store=True)
    product_id = fields.Many2one('product.product', related='lot_id.product_id', store=True)
    is_cannabis = fields.Boolean(related='product_id.is_cannabis', store=True)
    new_package_tag_id = fields.Many2one('package.tags', 'New Tag', required=False)
    old_qty = fields.Float()
    new_qty = fields.Float()
    new_name = fields.Char()
    from_move_line_id = fields.Many2one('stock.move.line', 'Move line')
    sync_state = fields.Selection([('in_queue', 'In queue'), ('done', 'Done'), ('fail', 'Fail')],
                                  'Sync state', default='in_queue')
    sync_msg = fields.Char()
    is_sample = fields.Boolean(default=False)

    def sync_multi_to_metrc(self):
        return True

    @api.model
    def create(self, vals):
        lot_id = vals['lot_id']
        old_lot = self.env['stock.production.lot'].browse(lot_id)
        vals['old_qty'] = old_lot.product_qty
        return super().create(vals)

    @api.constrains('new_qty')
    def _check_new_qty(self):
        for wizard in self:
            if wizard.new_qty <= 0:
                raise ValidationError(_('New qty must be greater than 0!'))

            if wizard.new_qty >= wizard.lot_id.product_qty:
                raise ValidationError(_('New qty must be less than origin package qty!'))

    @api.constrains('lot_id')
    def _check_lot_id(self):
        for wizard in self:
            if not wizard.lot_id.product_qty:
                raise ValidationError(_('package qty must be greater than 0!'))

    @api.onchange('new_package_tag_id')
    def lot_id_change(self):
        if self.new_package_tag_id:
            self.new_name = self.new_package_tag_id.label

    def split_package(self):
        self = self.with_context(
            active_id=self.id,
            active_ids=self._ids,
            model=self._name,
            default_picking_id=False,
            default_is_sample=self.is_sample,
            default_mrp_order_id=self.lot_id.mrp_order_id.id,
            default_mrp_order_date=self.lot_id.mrp_order_date,
            default_lab_testing=self.lot_id.lab_testing,
            default_production_batch_id = self.lot_id.production_batch_id,
        )

        old_package_tag = self.lot_id.package_tags_id
        old_package_tag_id = old_package_tag.id if old_package_tag else False
        new_package = self.lot_id.new_package_from_origin_package(
            self.new_qty, self.new_package_tag_id.id, old_package_tag_id, new_name=self.new_name)
        new_package.state = self.lot_id.state
        remain_qty = self.lot_id.product_qty - self.new_qty
        self.lot_id.adjust_package_qty(remain_qty)

        self.write({
            'new_lot_id': new_package.id,
        })

        self.sync_to_metrc()

        return new_package
