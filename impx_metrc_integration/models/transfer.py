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

FIELD_TRANSFER_TYPE_DICT = {
    'name': 'Name',
    'for_licensed_shipments': 'ForLicensedShipments',
    'for_external_incoming_shipments': 'ForExternalIncomingShipments',
    'for_external_outgoing_shipments': 'ForExternalOutgoingShipments',
    'requires_destination_gross_weight': 'RequiresDestinationGrossWeight',
    'requires_packages_gross_weight': 'RequiresPackagesGrossWeight'
}


class MetrcTransferType(models.Model):
    _name = 'metrc.transfer.type'

    name = fields.Char()
    for_licensed_shipments = fields.Boolean()
    for_external_incoming_shipments = fields.Boolean()
    for_external_outgoing_shipments = fields.Boolean()
    requires_destination_gross_weight = fields.Boolean()
    requires_packages_gross_weight = fields.Boolean()

    def get_transfer_type(self, license):
        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()

        url = '{}/transfers/v1/types?licenseNumber={}'.format(base_metrc_url, license.name)
        try:
            response = requests.get(url=url, auth=auth, headers=headers)
            if response.status_code == 200:
                datas = json.loads((response.content.decode('utf-8')))
                self.create_transfer_type_from_metrc(datas)
            else:
                error_msg = response.content.decode('utf-8')
                self.process_sync_transfer_type_error(error_msg)
        except Exception as error_msg:
            self.process_sync_transfer_type_error(error_msg)

    def create_transfer_type_from_metrc(self, datas):
        create_value = []
        transfer_type_dict = self.get_db_category_dict()
        for item in datas:
            if transfer_type_dict.get(item['Name'], False):
                continue
            val = {}
            for field in FIELD_TRANSFER_TYPE_DICT.keys():
                val[field] = item.get(FIELD_TRANSFER_TYPE_DICT[field], False)
            create_value.append(val)
        return self.create(create_value)

    def get_db_transfer_type_dict(self):
        transfer_type_list = self.search_read([], ['name'])
        transfer_type_dict = dict((row['name'], row['id']) for row in transfer_type_list)
        return transfer_type_dict

    def process_sync_transfer_type_error(self, error_msg):
        _logger.error('Sync transfer type Error {} '.format(error_msg))
        print(error_msg)
