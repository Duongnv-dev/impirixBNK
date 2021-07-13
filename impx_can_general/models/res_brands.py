from odoo import models, fields


class ResBrands(models.Model):
    _name = 'res.brands'
    name = fields.Char('Name', required=1)
    company_id = fields.Many2one('res.company', 'Company')
    description = fields.Html('Description')
    image = fields.Char('Image')
    banner = fields.Char('Image')
    id_ll = fields.Char('LeafLink brand ID', readonly=1)
    _sql_constraints = [
        ('id_ll_uniq', 'unique (id_ll)', 'LeafLink brand ID must be unique!'),
    ]