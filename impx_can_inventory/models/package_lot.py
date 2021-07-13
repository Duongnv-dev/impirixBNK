# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError


class StockProductionLot(models.Model):
    _inherit = 'stock.production.lot'

    package_tags_id = fields.Many2one('package.tags', 'Package tags', domain=[('used', '=', False)])
    package_tags_label = fields.Char(related='package_tags_id.label')
    external = fields.Boolean(default=False) # package from purchase, not assign internal tag label
    not_create_quant = fields.Boolean(default=False) #use in sync metrc incoming
    expiration_date = fields.Datetime()
    license_id = fields.Many2one('cannabis.license', string='Cannabis License')
    is_cannabis = fields.Boolean(related='product_id.is_cannabis')
    old_package_tags_id = fields.Many2one('package.tags', 'Old Package tags', readonly=1)
    is_source_package = fields.Boolean(compute='compute_is_source_package')
    state = fields.Selection([
        ('active', 'Active'),
        ('onhold', 'Onhold'),
        ('in_transit', 'In Transit'),
        ('inactive', 'Inactive'),
    ], string='Lots/Package tags status', compute='_get_lot_state')
    is_sample = fields.Boolean(default=False)
    is_connected = fields.Boolean(default=False)
    lab_testing = fields.Char(default='NotSubmitted', readonly=True)

    @api.model
    def create(self, vals):
        if 'package_tags_id' in vals and vals['package_tags_id']:
            package_tags_id = self.env['package.tags'].browse(vals['package_tags_id'])
            vals.update({'license_id': package_tags_id.license_id.id if package_tags_id.license_id else False})
        return super(StockProductionLot, self).create(vals)

    def write(self, vals):
        if 'package_tags_id' in vals and vals['package_tags_id']:
            package_tags_id = self.env['package.tags'].browse(vals['package_tags_id'])
            vals.update({'license_id': package_tags_id.license_id.id if package_tags_id.license_id else False})
        return super(StockProductionLot, self).write(vals)

    def compute_is_source_package(self):
        for rec in self:
            domain = [('old_package_tags_id', '=', rec.package_tags_id.id), ('is_sample', '=', True)]
            if rec.env['stock.production.lot'].search(domain):
                rec.is_source_package = True
            else:
                rec.is_source_package = False

    @api.depends('product_qty')
    def _get_lot_state(self):
        for rec in self:
            if rec.product_qty == 0.0:
                rec.state = 'inactive'
            else:
                rec.state = 'active'

    @api.constrains('package_tags_id')
    def check_package_tags(self):
        for lot in self:
            if not lot.product_id.is_cannabis and lot.package_tags_id:
                raise ValidationError(_('Lot {} is not cannabis, cannot assign package tags').format(lot.name))

    def open_split_package(self):
        self.ensure_one()

        action_obj = self.env.ref('impx_can_inventory.wizard_split_stock_production_lot_action')
        action = action_obj.read([])[0]
        context = dict(self._context)

        context['default_lot_id'] = self.id
        package_tags_id = self.package_tags_id
        if package_tags_id:
            context['old_package_tags_id'] = package_tags_id.id

        action['context'] = context
        return action

    def new_package_from_origin_package(self, new_qty, new_tag_id, old_tag_id, new_name=False):
        self.ensure_one()

        package_value = {
            'product_id': self.product_id.id,
            'company_id': self.env.user.company_id.id,
            'external': self.external,
            'package_tags_id': new_tag_id,
        }

        if new_name:
            package_value['name'] = new_name
        if old_tag_id:
            package_value['old_package_tags_id'] = old_tag_id

        package = self.env['stock.production.lot'].create(package_value)
        package.with_context(stock_inventory_name='Adjust qty for new package when split package'
                             ).adjust_package_qty(new_qty, orgin_package=self)
        return package

    def adjust_package_qty(self, new_qty, orgin_package=False):
        self.ensure_one()
        # update qty for package
        metrc_license = self.product_id.cannabis_license_id
        location_id = False

        if metrc_license:
            warehouse, picking_type = metrc_license.get_incoming_picking_type()
            location_id = warehouse.lot_stock_id.id

        if not location_id:
            lot_id = self.id
            if orgin_package:
                lot_id = orgin_package.id

            quants = self.env['stock.quant'].search([('lot_id', '=', lot_id)])

            for quant in quants:
                if quant.location_id.usage == 'internal':
                    location_id = quant.location_id.id
                    break
        if not location_id:
            raise UserError(_('Error: Cannot define stock location for this package!'))

        stock_inventory_name = self._context.get('stock_inventory_name', 'Adjust package')
        stock_inventory_vals = {
            'name': _(stock_inventory_name),
            'location_ids': [(6, False, [location_id])],
            'product_ids': [(6, False, [self.product_id.id])],
        }
        stock_inventory = self.env['stock.inventory'].create(stock_inventory_vals)
        stock_inventory.action_start()

        line_to_update = False
        for line in stock_inventory.line_ids:
            if line.prod_lot_id.id != self.id:
                line.unlink()
                continue

            line_to_update = line

        if not line_to_update:
            stock_inventory_line_vals = {
                'location_id': location_id,
                'product_id': self.product_id.id,
                'product_uom_id': self.product_id.uom_id.id,
                'prod_lot_id': self.id,
                'product_qty': new_qty,
                'inventory_id': stock_inventory.id,
            }
            line_to_update = self.env['stock.inventory.line'].create(stock_inventory_line_vals)
        else:
            line_to_update.write({
                'product_qty': new_qty,
            })

        return stock_inventory.action_validate()


class PackageTags(models.Model):
    _inherit = 'package.tags'

    @api.depends('lot_ids')
    def _compute_used(self):
        for tag in self:
            tag.used = bool(tag.lot_ids._ids)

    lot_ids = fields.One2many('stock.production.lot', 'package_tags_id', string='Lot')
    used = fields.Boolean(compute='_compute_used', store=True)
