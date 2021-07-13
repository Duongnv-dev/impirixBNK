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


class StockMove(models.Model):
    _inherit = 'stock.move'

    package_id = fields.Char()
    package_label = fields.Char()


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    metrc_transfer_id = fields.Char()
    metrc_manifest_number = fields.Char()
    metrc_delivery_id = fields.Char()

    metrc_shipper_facility_license_number = fields.Char()
    metrc_shipper_facility_name = fields.Char()

    metrc_created_datetime = fields.Datetime()
    metrc_created_by_username = fields.Char()

    metrc_last_modified = fields.Datetime()
    metrc_estimated_departure_datetime = fields.Datetime()
    metrc_estimated_arrival_datetime = fields.Datetime()
    metrc_received_datetime = fields.Datetime()

    #for transfer template
    metrc_template_id = fields.Char()
    metrc_template_state = fields.Selection(
        [('not_create', 'Not create yet'), ('created', 'Created'), ('create_error', 'Faulty creation'), ('confirmed', 'Confirmed')], default='not_create')

    # Need to check available package before to create template
    def check_package_to_create_or_update_template(self):
        return True

    def create_metrc_transfer_template(self):
        license = self.analytic_account_id.cannabis_license_id
        data = self.get_data_to_create_template()
        raise UserError(_("Data to post: {}".format(data)))
        # self.request_create_metrc_transfer_template(license, data)

    def request_create_metrc_transfer_template(self, license, data):
        # base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()
        data = json.dumps(data)
        print(data)
        # url = '{}/transfers/v1/templates?licenseNumber={}'.format(base_metrc_url, license.name)
        url = 'https://sandbox-api-co.metrc.com/transfers/v1/templates?licenseNumber=403-X0001'
        try:
            response = requests.post(url=url, auth=auth, headers=headers, data=data)
            if response.status_code == 200:
                self.write({'metrc_template_state': 'created'})
            else:
                error_msg = response.content.decode('utf-8')
                self.write({'metrc_template_state': 'create_error'})
                self.process_sync_metrc_transfer_template_error(error_msg)
        except Exception as error_msg:
            print('Exception', error_msg)
            self.write({'metrc_template_state': 'create_error'})
            self.process_sync_metrc_transfer_template_error(error_msg)

    def get_data_to_create_template(self):
        self.ensure_one()
        package_tags_list = self.get_package_list_to_create_transfer_template()
        metrc_estimated_departure_datetime = None
        metrc_estimated_arrival_datetime = None
        if self.metrc_estimated_departure_datetime:
            metrc_estimated_departure_datetime = self.metrc_estimated_departure_datetime.strftime('%Y-%m-%dT%H:%M:%S')
        if self.metrc_estimated_arrival_datetime:
            metrc_estimated_arrival_datetime = self.metrc_estimated_arrival_datetime.strftime('%Y-%m-%dT%H:%M:%S')
        value = {
            "Name": "{}".format(self.name),
            "TransporterFacilityLicenseNumber": None,
            "DriverOccupationalLicenseNumber": None,
            "DriverName": None,
            "DriverLicenseNumber": None,
            "PhoneNumberForQuestions": None,
            "VehicleMake": None,
            "VehicleModel": None,
            "VehicleLicensePlateNumber": None,
            "Destinations": [
                {
                    "RecipientLicenseNumber": "{}".format(self.partner_id.regulatory_license),
                    "TransferTypeName": "Transfer",
                    "PlannedRoute": "I will drive down the road to the place.",
                    "EstimatedDepartureDateTime": metrc_estimated_departure_datetime,
                    "EstimatedArrivalDateTime": metrc_estimated_arrival_datetime,
                    "Transporters": [
                        {
                            "TransporterFacilityLicenseNumber": "{}".format(self.transporter_license_id.regulatory_license),
                            "DriverOccupationalLicenseNumber": None,
                            "DriverName": None,
                            "DriverLicenseNumber": None,
                            "PhoneNumberForQuestions": None,
                            "VehicleMake": None,
                            "VehicleModel": None,
                            "VehicleLicensePlateNumber": None,
                            "IsLayover": False,
                            "EstimatedDepartureDateTime": metrc_estimated_departure_datetime,
                            "EstimatedArrivalDateTime": metrc_estimated_arrival_datetime,
                            "TransporterDetails": None
                        }
                    ],
                    "Packages": package_tags_list
                  }
                ]
              }

        data = [value]
        return data

    def get_package_list_to_create_transfer_template(self):
        self.ensure_one()
        package_tags_list = []
        for line in self.move_line_ids_without_package:
            if line.lot_id and line.lot_id.package_tags_id and line.lot_id.package_tags_id.label:
                package_tags_list.append({'PackageLabel': '{}'.format(line.lot_id.package_tags_id.label)})
        return package_tags_list

    def request_update_transfer_template(self, license, data):
        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()
        data = json.dumps(data)
        url = '{}/transfers/v1/templates?licenseNumber={}'.format(base_metrc_url, license.name)
        try:
            response = requests.put(url=url, auth=auth, headers=headers, data=data)
            if response.status_code == 200:
                print('done')
            else:
                print('else')
                error_msg = response.content.decode('utf-8')
                print(error_msg)
                self.process_sync_metrc_transfer_template_error(error_msg)
        except Exception as error_msg:
            print('Exception', error_msg)
            self.process_sync_metrc_transfer_template_error(error_msg)

    # mapping tranfer template in metrc after create
    def request_get_transfer_template(self, license):
        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()
        url = '{}/transfers/v1/templates?licenseNumber={}'.format(base_metrc_url, license.name)
        try:
            response = requests.get(url=url, auth=auth, headers=headers)
            if response.status_code == 200:
                datas = json.loads((response.content.decode('utf-8')))
                self.map_transfer_template_from_metrc(datas)
            else:
                error_msg = response.content.decode('utf-8')
                self.process_sync_metrc_transfer_template_error(error_msg)
        except Exception as error_msg:
            self.process_sync_metrc_transfer_template_error(error_msg)

    def map_transfer_template_from_metrc(self, datas):
        for data in datas:
            if data.get('Name', False) == self.name:
                val = {'metrc_template_id': data.get('Id', False)}
                self.write(val)
                break
        return True

    # delete template
    def delete_transfer_template(self, metrc_template_id):
        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()
        url = '{}/transfers/v1/templates/{}'.format(base_metrc_url, metrc_template_id)
        try:
            response = requests.delete(url=url, auth=auth, headers=headers)
            if response.status_code == 200:
                print('done')
            else:
                error_msg = response.content.decode('utf-8')
                self.process_sync_metrc_transfer_template_error(error_msg)
        except Exception as error_msg:
            self.process_sync_metrc_transfer_template_error(error_msg)

    def process_sync_metrc_transfer_template_error(self, error_msg):
        _logger.error('Sync transfer type Error {} '.format(error_msg))
        print(error_msg)
