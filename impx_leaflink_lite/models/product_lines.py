from odoo import models, fields


class ProductLine(models.Model):
    _name = 'product.lines'
    name = fields.Char('Name', required=1)
    brand_id = fields.Many2one('res.brands', 'Brand')
    id_ll = fields.Char('LeafLink Product line ID', readonly=1)
    _sql_constraints = [
        ('id_ll_uniq', 'unique (id_ll)', 'LeafLink brand ID must be unique!'),
    ]