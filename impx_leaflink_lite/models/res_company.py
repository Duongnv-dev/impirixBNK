from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'
    id_ll = fields.Char('LeafLink brand ID', readonly=1)
    _sql_constraints = [
        ('id_ll_uniq', 'unique (id_ll)', 'LeafLink brand ID must be unique!'),
    ]
