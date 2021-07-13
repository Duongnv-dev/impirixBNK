# -*- coding: utf-8 -*-

from odoo import api, fields, models, _, tools


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    def get_co_customer_setting(self):
        config = self.env['batch.update.customer.config'].search([], limit=1)
        if config:
            return {
                        'name': _('Colorado MED Licensing for Customer Import Settings'),
                        'view_mode': 'form',
                        'view_id': self.env.ref('impx_can_co_customers.batch_update_customer_config_form').id,
                        'res_model': 'batch.update.customer.config',
                        'type': 'ir.actions.act_window',
                        'target': 'new',
                        'res_id': config.id,
                        'flags': {'mode': 'edit'}
                    }
        else:
            return {
                'name': _('Colorado MED Licensing for Customer Import Settings'),
                'view_mode': 'form',
                'view_id': self.env.ref('impx_can_co_customers.batch_update_customer_config_form').id,
                'res_model': 'batch.update.customer.config',
                'type': 'ir.actions.act_window',
                'target': 'new',
                'flags': {'mode': 'edit'}
            }

