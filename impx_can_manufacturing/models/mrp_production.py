from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime


class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    strain_type = fields.Selection([('hybrid', 'Hybrid'), ('sativa', 'Sativa'), ('indica', 'Indica')],
                                   string='Strain Type', required=True)
    production_batch_id = fields.Char('Production Batch ID')

    @api.onchange('strain_type')
    def _get_production_bath_id(self):
        if self.strain_type:
            if self.strain_type == 'hybrid':
                strain_type_suffix = 'H'
            elif self.strain_type == 'sativa':
                strain_type_suffix = 'S'
            elif self.strain_type == 'indica':
                strain_type_suffix = 'I'
            production_batch_id = str(datetime.today().strftime('%Y%m%d'))[-6:] + strain_type_suffix
            pbi_count = self.search_count([('production_batch_id', 'like', production_batch_id)])
            if pbi_count > 0:
                self.production_batch_id = production_batch_id + str(pbi_count)
            else:
                self.production_batch_id = production_batch_id
