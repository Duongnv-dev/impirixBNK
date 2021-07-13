from odoo import models, fields, api
from odoo.exceptions import ValidationError


class GeneratePackageTag(models.TransientModel):
    _name = 'generate.package.tags'
    _description = 'Generate package tag number'

    cannabis_license_id = fields.Many2one('cannabis.license', string='License_number', readonly=1)
    beginning_id = fields.Char('Beginning ID', required=True)
    quantities = fields.Integer('Quantities', required=True)
    sequence_start = fields.Integer('Sequence start', required=True)
    receive_date = fields.Datetime('Receive Date', required=True)

    @api.constrains('quantities')
    def _check_quantities(self):
        if any(rec for rec in self
               if rec.quantities and rec.quantities < 0):
            raise ValidationError('The quantities must be than 0')

    @api.constrains('sequence_start')
    def _check_sequence_start(self):
        if any(rec for rec in self
               if rec.sequence_start and rec.sequence_start < 0):
            raise ValidationError('The sequence start must be than 0')

    def action_generate_package_tag_number(self):
        package_tags = self.env['package.tags'].sudo()
        cannabis_license_id = self.cannabis_license_id.id
        quantities = self.quantities
        beginning_id = self.beginning_id
        sequence_start = self.sequence_start
        receive_date = self.receive_date
        vals = ()
        for number in range(quantities):
            vals += ({
                         'label': beginning_id + str(sequence_start + number),
                         'license_id': cannabis_license_id,
                         'receive_date': receive_date,
                     },)
        if not vals:
            return False
        package_tags.create(vals)
