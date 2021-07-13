from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ResStrains(models.Model):
    _name = 'res.strains'
    id_ll = fields.Char('LeafLink Strain ID')
    _sql_constraints = [
        ('id_ll_uniq', 'unique (id_ll)', 'LeafLink Strain ID must be unique!'),
    ]
    name = fields.Char('Name')
    company_id = fields.Many2one('res.company')
    strain_classification = fields.Selection([
        ('sativa', 'sativa'),
        ('indica', 'indica'),
        ('hybrid', 'hybrid'),
        ('na', 'na'),
        ('11-cbd', '11-cbd'),
        ('high-cbd', 'high-cbd'),
        ('high-cbd', 'high-cbd'),
        ('sativa-hybrid', 'sativa-hybrid'),
        ('indica-hybrid', 'indica-hybrid'),
    ])

    @api.constrains('name', 'strain_classification')
    def constrains_strain(self):
        for rec in self:
            name = rec.name
            strain_classification = rec.strain_classification
            self.env.cr.execute("""SELECT * FROM res_strains WHERE name=%s AND strain_classification=%s""",
                                (name, strain_classification))
            if len(self.env.cr.fetchall()) > 1:
                raise ValidationError(_(
                    'Strain with this Strain Name({}) and Strain classification({}) already exists.'.format(
                        name, strain_classification)))
