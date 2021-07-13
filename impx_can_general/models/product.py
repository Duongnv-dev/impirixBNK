# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    cannabis_license_id = fields.Many2one('cannabis.license', 'License')
    is_cannabis = fields.Boolean(default=False)

    @api.model
    def default_get(self, fields_list):
        result = super(ProductTemplate, self).default_get(fields_list)
        result['type'] = 'product'
        return result

    def unlink(self):
        self = self - self.env.ref('impx_can_general.shipping_charge_from_leaflink').product_tmpl_id
        return super(ProductTemplate, self).unlink()


class ProductProduct(models.Model):
    _inherit = 'product.product'

    metrc_connect = fields.Boolean('Connected to Metrc', default=False)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res['type'] = 'product'
        return res

    def unlink(self):
        self = self - self.env.ref('impx_can_general.shipping_charge_from_leaflink')
        return super(ProductProduct, self).unlink()
