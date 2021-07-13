# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError

SYNC_SYSTEM_SELECTION = [
    ('leaflink', 'LeafLink'),
    ('metrc', 'Metrc'),
]
SYNC_FUNCTION = [
    ('metrc_active_package', 'Metrc active package'),
    ('metrc_adjust_package', 'Metrc adjust package'), 
    ('metrc_incoming_transfer', 'Metrc incoming transfer'), 
    ('metrc_outgoing_transfer', 'Metrc outgoing transfer'), 
    ('metrc_create_package', 'Metrc create package'), 
    ('metrc_create_item', 'Metrc create item'), 
    ('metrc_sync_item', 'Metrc sync item'),
]

class SynchronizeErrorLog(models.Model):
    _name = 'synchronize.error.log'

    name = fields.Char(required=True)
    sync_system = fields.Selection(SYNC_SYSTEM_SELECTION, required=True)
    sync_function = fields.Selection(SYNC_FUNCTION, requỉed=True)
    status_code = fields.Integer()
    error = fields.Char(required=True)
    type = fields.Selection([('error', 'Error'), ('warning', 'Warning')], default='error')
    response = fields.Char()
    note = fields.Char()
