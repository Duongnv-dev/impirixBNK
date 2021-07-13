# -*- coding: utf-8 -*-

from odoo import fields, models, api


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    package_tags_id = fields.Many2one('package.tags', 'Package tags', related='lot_id.package_tags_id', store=True)
    license_id = fields.Many2one(related='lot_id.license_id', string='Cannabis License')
    external = fields.Boolean()

    def _gather(self, product_id, location_id, lot_id=None, package_id=None, owner_id=None, strict=False):
        """override function to check if product is cannabis and package not external, not assign tag
         => cannot not fill to outgoing
        """
        res = super()._gather(
            product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict)

        assign_outgoing_picking = self._context.get('assign_outgoing_picking', False)

        if not product_id.is_cannabis or not assign_outgoing_picking:
            return res

        res = res.filtered(lambda q: q.package_tags_id or q.external)

        return res

    @api.model
    def _update_available_quantity(self, product_id, location_id, quantity, lot_id=None, package_id=None, owner_id=None,
                                   in_date=None):
        """override function to process not create quant when done move line from metrc sync
        """
        if lot_id.not_create_quant:
            in_date = fields.Datetime.now()
            return self._get_available_quantity(product_id, location_id, lot_id=lot_id, package_id=package_id,
                                                owner_id=owner_id, strict=False,
                                                allow_negative=True), fields.Datetime.from_string(in_date)
        return super()._update_available_quantity(
            product_id, location_id, quantity, lot_id=lot_id, package_id=package_id, owner_id=owner_id, in_date=in_date)
