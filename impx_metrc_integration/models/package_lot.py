# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from odoo.addons.queue_job.job import job
import requests
import json


class StockProductionLot(models.Model):
    _inherit = 'stock.production.lot'

    @job
    def sync_new_test_sample_to_metrc(self):
        self.ensure_one()
        if not self.is_sample or self.is_connected or not self.is_cannabis or not self.license_id:
            exit()
        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()
        license_number = self.license_id.name
        url = '{}/packages/v1/create/testing?licenseNumber={}'.format(base_metrc_url, license_number)
        old_package_label = self.package_tags_id.label
        if not old_package_label and self.external:
            old_package_label = self.name

        body = [
            {
                "Tag": self.package_tags_id.label,
                "Location": None,
                "Item": self.product_id.name,
                "Quantity": self.product_qty,
                "UnitOfMeasure": self.product_uom_id.description,
                "PatientLicenseNumber": license_number,
                "Note": "Test sample package!",
                "IsProductionBatch": False,
                "ProductionBatchNumber": None,
                "IsDonation": False,
                "ProductRequiresRemediation": False,
                "UseSameItem": False,
                "ActualDate": self.create_date.strftime(DEFAULT_SERVER_DATE_FORMAT),
                "Ingredients": [
                    {
                        "Package": old_package_label,
                        "Quantity": self.product_qty,
                        "UnitOfMeasure": self.product_uom_id.description,
                    },
                ]
            }
        ]

        body = json.dumps(body)
        try:
            res = requests.post(url, data=body, auth=auth, headers=headers)
            if res.status_code == 200:
                self.is_connected = True
                self.message_post(body='Create sample test successfully!', subtype="mail.mt_note")
            if res.status_code != 200 and res.content:
                self.message_post(body=json.loads(res.content.decode('utf-8')), subtype="mail.mt_note")
        except Exception as error_msg:
            self.message_post(body=error_msg, subtype="mail.mt_note")

    @api.model
    def sync_multi_new_test_sample_to_metrc(self):
        lot_production = self.env['stock.production.lot'].search([])
        need_syncs = lot_production.filtered(lambda p: p.is_sample and not p.is_connected and p.is_cannabis and p.license_id)
        if not need_syncs:
            return False

        for sample in need_syncs:
            sample.with_delay().sync_new_test_sample_to_metrc()
        return True

    @job
    def sync_state_test_sample_to_metrc(self):
        self.ensure_one()
        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()
        license_number = self.license_id.name
        old_package_label = self.package_tags_id.label
        if not old_package_label and self.external:
            old_package_label = self.name

        url = '{}/packages/v1/{}?licenseNumber={}'.format(base_metrc_url, old_package_label, license_number)
        try:
            res = requests.get(url, auth=auth, headers=headers)
            if res.status_code == 200 and res.content:
                content = json.loads(res.content.decode('utf-8'))
                msg = ''
                msg += 'Lab testing state: ' + content['InitialLabTestingState'] if 'InitialLabTestingState' in content else ''
                msg += ' -> ' + content['LabTestingState'] if 'LabTestingState' in content else ''
                self.message_post(body=msg, subtype="mail.mt_note")
                self.lab_testing = json.loads(res.content)['LabTestingState'] if 'LabTestingState' in json.loads(res.content) else self.lab_testing

        except Exception as error_msg:
            self.message_post(body=error_msg, subtype="mail.mt_note")

    def sync_multi_state_sample_to_metrc(self):
        lot_production = self.env['stock.production.lot'].search([])
        need_syncs = lot_production.filtered(lambda p: p.is_sample and p.is_connected and p.is_cannabis and p.license_id)
        if not need_syncs:
            return False

        for sample in need_syncs:
            sample.with_delay().sync_state_test_sample_to_metrc()
        return True