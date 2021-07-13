from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProductLeafLinkCategory(models.Model):
    _name = 'product.category.leaflink'
    _parent_name = 'parent_id'

    id_ll = fields.Char()
    name = fields.Char('Name')
    display_name = fields.Char(compute='_compute_display_name', store=True)
    parent_id = fields.Many2one('product.category.leaflink', 'Parent Category', index=True, ondelete='cascade')
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('product.category.leaflink', 'parent_id', 'Child Categories')

    @api.constrains('id_ll')
    def _check_id_ll_uniq(self):
        for rec in self:
            if rec.parent_id:
                if rec.search([('id_ll', '=', rec.id_ll), ('parent_id', '!=', None), ('id', '!=', rec.id)]):
                    raise ValidationError(_('Leaflink product subcategory ID must be unique!'))
            else:
                if rec.search([('id_ll', '=', rec.id_ll), ('parent_id', '=', None), ('id', '!=', rec.id)]):
                    raise ValidationError(_('Leaflink product category ID must be unique!'))

    @api.depends('name', 'parent_id.name')
    def _compute_display_name(self):
        for rec in self:
            names = [rec.parent_id.name, rec.name]
            rec.display_name = ' / '.join(filter(None, names))
