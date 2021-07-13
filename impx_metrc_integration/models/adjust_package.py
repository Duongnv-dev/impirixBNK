# -*- coding: utf-8 -*-
import requests
from requests.auth import HTTPBasicAuth
import json
import datetime
import pytz
import logging

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from odoo.addons.queue_job.job import job
from odoo.tools import exception_to_unicode

_logger = logging.getLogger(__name__)


class CannabisLicense(models.Model):
    _inherit = 'cannabis.license'

    def sync_metrc_adjust_package_reason(self):
        self.ensure_one()
        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()

        url = '{}/packages/v1/adjust/reasons?licenseNumber={}'.format(base_metrc_url, self.name)

        try:
            response = requests.get(url, auth=auth, headers=headers)

            if response.status_code == 200:
                self.process_sync_adjust_package_reason_result(response.text)
            else:
                error_msg = response.content.decode('utf-8')
                self.process_sync_adjust_package_reason_error(error_msg)
        except Exception as e:
            error_msg = exception_to_unicode(e)
            self.process_sync_adjust_package_reason_error(error_msg)

    def process_sync_adjust_package_reason_error(self, error_msg):
        _logger.error('Sync adjust package reason Error {} '.format(error_msg))
        print('Sync adjust package reason Error: {} '.format(error_msg))

    def process_sync_adjust_package_reason_result(self, datas):
        reasons = json.loads(datas)

        domain = [('metrc_license_id', '=', self.id)]
        already_exist_reasons = self.env['metrc.adjust.package.reason'].search(domain)
        already_exist_reason_names = [reason.name for reason in already_exist_reasons]

        res = []
        for reason in reasons:
            name = reason['Name']

            if name in already_exist_reason_names:
                continue

            requires_note = reason['RequiresNote']
            vals = {
                'name': name,
                'requires_note': requires_note,
                'metrc_license_id': self.id,
            }
            new_reason = self.env['metrc.adjust.package.reason'].create(vals)
            res.append(new_reason.id)
        return res


class AdjustReason(models.Model):
    _name = 'metrc.adjust.package.reason'

    name = fields.Char(required=True)
    requires_note = fields.Boolean()
    metrc_license_id = fields.Many2one('cannabis.license', 'Metrc license', required=True)


class StockProductionLot(models.Model):
    _inherit = 'stock.production.lot'

    def sync_adjust_package_to_metrc(
            self, reason, qty=None,
            adjust_date=datetime.datetime.now(pytz.utc).strftime(DEFAULT_SERVER_DATE_FORMAT), reason_note=None):
        self.ensure_one()

        if reason.requires_note and not reason_note:
            raise UserError(_('Error: Reason note invalid!'))

        if qty == None:
            qty = self.product_qty

        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()

        licenseNumber = self.license_id.name

        url = '{}/packages/v1/adjust?licenseNumber={}'.format(base_metrc_url, licenseNumber)

        label = self.package_tags_id.label
        if not label and self.external:
            label = self.name

        body = [
            {
                "Label": label,
                'Quantity': qty,
                'UnitOfMeasure': self.product_uom_id.description,
                'AdjustmentReason': reason.name,
                'AdjustmentDate': adjust_date,
                'ReasonNote': reason_note,
            }
        ]

        body = json.dumps(body)

        res = requests.post(url, data=body, auth=auth, headers=headers)
        return True
