from odoo import fields, api, models, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    shipping_charge = fields.Boolean(string='Shipping Charge', default=False)