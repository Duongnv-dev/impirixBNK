# -*- encoding: utf-8 -*-

from odoo import api, fields, models, _


class PackageTags(models.Model):
    _name = 'package.tags'
    _description = 'Package tags'
    _rec_name = 'label'

    label = fields.Char(required=True)
    metrc_id = fields.Char(required=False)
    license_id = fields.Many2one('cannabis.license', 'License', required=True)
    note = fields.Char()
    active = fields.Boolean(default=True)
    metrc_sync_state = fields.Selection(
        [('blank', 'Blank'),('need_sync', 'Need sync'),('done', 'Done'),('fail', 'Fail')],
        default='blank', required=True, readonly=True)
    receive_date = fields.Datetime('Receive Date')

    _sql_constraints = [
        ('unique_label', 'unique (label)', 'Package tag label must be unique!'),
        ('unique_metrc_id', 'unique (metrc_id)', 'Package tag metrc ID must be unique!'),
    ]
