# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError
from odoo.osv import expression
from odoo.tools import exception_to_unicode

import logging
import re
import base64
import requests
import json
from datetime import datetime, timedelta
import iso8601
import pytz
from odoo.addons.queue_job.job import job

from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


class CannabisLicense(models.Model):
    _inherit = 'cannabis.license'

    outgoing_transfer_last_sync = fields.Datetime()

    @api.model
    def sync_incoming_transfer(self):
        lisences = self.search([])
        if not lisences:
            return False
        for lisence in lisences:
            lisence.sync_incoming_transfer_for_a_license()
        return True

    # sync outgoing for a license with last sync on license
    def sync_outgoing_transfer_for_a_license(self):
        self.ensure_one()

        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()

        outgoing_transfer_last_sync = self.outgoing_transfer_last_sync
        if not outgoing_transfer_last_sync:
            outgoing_transfer_last_sync = datetime.now() + timedelta(days=-1)

        lastModifiedStart = outgoing_transfer_last_sync.strftime('%Y-%m-%dT%H:%M:%S')

        modifire_end = outgoing_transfer_last_sync + timedelta(days=1)
        modifire_end = min(modifire_end, datetime.now())
        lastModifiedEnd = modifire_end.strftime('%Y-%m-%dT%H:%M:%S')

        license_number = self.name
        url = '{}/transfers/v1/outgoing?licenseNumber={}&lastModifiedStart={}&lastModifiedEnd={}'.format(
            base_metrc_url, license_number, lastModifiedStart, lastModifiedEnd)
        outgoing_transfer_list_id = []
        try:
            response = requests.get(url, auth=auth, headers=headers)
            if response.status_code == 200:

                datas = json.loads((response.content.decode('utf-8')))
                outgoing_transfer_list_id = self.get_outgoing_transfer_list_id(datas)
                self.write({
                    'outgoing_transfer_last_sync': modifire_end
                })
            else:
                error_msg = response.content.decode('utf-8')
                self.process_sync_incoming_transfer_error(error_msg)
        except Exception as e:
            error_msg = exception_to_unicode(e)
            self.process_sync_incoming_transfer_error(error_msg)
        return outgoing_transfer_list_id

    def get_outgoing_transfer_list_id(self, datas):
        outgoing_transfer_list_id = [data.get('Id', False) for data in datas if data.get('Id', False)]
        return outgoing_transfer_list_id

    def get_deliveries_by_outgoing_id(self, outgoing_id, base_metrc_url, headers, auth):
        url = '{}/transfers/v1/{}/deliveries'.format(base_metrc_url, outgoing_id)
        deliveries_list_id = []
        try:
            response = requests.get(url, auth=auth, headers=headers)
            if response.status_code == 200:
                datas = json.loads((response.content.decode('utf-8')))
                deliveries_list_id = [data.get('Id', False) for data in datas if data.get('Id', False)]
            else:
                error_msg = response.content.decode('utf-8')
                self.process_sync_incoming_transfer_error(error_msg)
        except Exception as e:
            error_msg = exception_to_unicode(e)
            self.process_sync_incoming_transfer_error(error_msg)
        return deliveries_list_id

    def get_packages_by_transfer_id(self, transfer_id, base_metrc_url, headers, auth):
        url = '/transfers/v1/delivery/{}/packages'.format(base_metrc_url, transfer_id)
        try:
            response = requests.get(url, auth=auth, headers=headers)
            if response.status_code == 200:
                datas = json.loads((response.content.decode('utf-8')))
            else:
                error_msg = response.content.decode('utf-8')
                self.process_sync_incoming_transfer_error(error_msg)
                return False
        except Exception as e:
            error_msg = exception_to_unicode(e)
            self.process_sync_incoming_transfer_error(error_msg)
        return datas

    def process_sync_outgoing_transfer_error(self, error_msg):
        _logger.error('Sync outgoing transfer Error {} '.format(error_msg))
        print('Sync outgoing transfer Error {} '.format(error_msg))