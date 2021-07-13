import logging
import re
from odoo.exceptions import ValidationError, Warning
from odoo.osv import osv
from odoo import _, api, fields, models, modules, SUPERUSER_ID, tools
import requests
import json
from datetime import datetime
import time
from datetime import timedelta


class ImportHistory(models.Model):
    _name = 'export.history'
    _order = 'last_sync desc'
    last_sync = fields.Datetime(string="Last Sync", required=False, )
    no_ex_contact = fields.Integer(string="New Contacts", required=False, )
    no_up_contact = fields.Integer(string="Updated Contacts", required=False, )
    no_ex_email = fields.Integer(string="New Emails", required=False, )
    no_ex_task = fields.Integer(string="New Tasks", required=False, )
    no_up_task = fields.Integer(string="Updated Tasks", required=False, )
    no_up_calender = fields.Integer(string="Updated Events", required=False, )
    no_ex_calender = fields.Integer(string="New Events", required=False, )
    status = fields.Char('Status')
    sync_type = fields.Selection(string="Sync_type", selection=[('auto', 'Auto'), ('manual', 'Manual'), ],
                                 required=False, )

    # sync_import_id = fields.Many2one("office.sync", string="Sync reference", required=False, )
    sync_export_id = fields.Many2one("office.sync", string="Sync reference", required=False, )
    user_ids = fields.One2many('res.users', 'export_history_id')


class HistoryLine(models.Model):
    _name = 'sync.history'
    _order = 'last_sync desc'

    sync_id = fields.Many2one('office.sync', string='Partner Reference', required=True, ondelete='cascade',
                              index=True, copy=False)
    last_sync = fields.Datetime(string="Last Sync", required=False, )
    no_im_contact = fields.Integer(string="New Contacts", required=False, )
    no_up_contact = fields.Integer(string="Updated Contacts", required=False, )
    no_im_email = fields.Integer(string="New Inbox", required=False, )
    no_sent_email = fields.Integer(string="New Sent Items", required=False, )
    no_im_task = fields.Integer(string="New Tasks", required=False, )
    no_up_task = fields.Integer(string="Updated Tasks", required=False, )
    no_up_calender = fields.Integer(string="Updated Events", required=False, )
    no_im_calender = fields.Integer(string="New Events", required=False, )
    status = fields.Char('Status')
    message_log = fields.Text()
    sync_type = fields.Selection(string="Sync Type", selection=[('auto', 'Auto'), ('manual', 'Manual'), ],
                                 required=False, )
    from_date = fields.Datetime(string="From Date", required=False)
    to_date = fields.Datetime(string="To Date", required=False)
    user_id = fields.Many2one('res.users')

    def auto_unlink_sync_history(self):
        now = datetime.now()
        time_to_unlink = now - timedelta(days=30)
        res_to_delete = self.sudo().search([('last_sync', '<=', time_to_unlink)])
        for res in res_to_delete:
            try:
                res.unlink()
            except Exception as e:
                continue
        return True

    def check_clock_interval(self, time):
        time_str = time.strftime("%Y-%m-%d %H:%M:%SZ")
        if time_str[14:16] == '00':
            return True
        else:
            return False
