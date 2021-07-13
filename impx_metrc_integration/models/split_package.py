# -*- coding: utf-8 -*-
import requests
from requests.auth import HTTPBasicAuth
import json

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from odoo.addons.queue_job.job import job
from odoo.tools import exception_to_unicode


class WizardSplitStockProductionLot(models.Model):
    _inherit = 'wizard.split.stock.production.lot'

    @job
    def sync_to_metrc(self):
        self.ensure_one()
        try:
            self.sync_new_package_to_metrc()
        except Exception as e:
            self.sync_msg = exception_to_unicode(e)
            self.sync_state = 'fail'

    def sync_new_package_to_metrc(self):
        self.ensure_one()
        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()

        licenseNumber = self.license_id.name

        url = '{}/packages/v1/create?licenseNumber={}'.format(base_metrc_url, licenseNumber)

        old_package_label = self.lot_id.package_tags_id.label
        if not old_package_label and self.lot_id.external:
            old_package_label = self.lot_id.name

        body = [
            {
                "Tag": self.new_lot_id.package_tags_id.label,
                "Location": None,
                "Item": self.product_id.name,
                "Quantity": self.new_qty,
                "UnitOfMeasure": self.new_lot_id.product_uom_id.description,
                "PatientLicenseNumber": licenseNumber,
                "Note": "Split package.",
                "IsProductionBatch": False,
                "ProductionBatchNumber": None,
                "IsDonation": False,
                "ProductRequiresRemediation": False,
                "UseSameItem": False,
                "ActualDate": self.create_date.strftime(DEFAULT_SERVER_DATE_FORMAT),
                "Ingredients": [
                    {
                        "Package": old_package_label,
                        "Quantity": self.new_qty,
                        "UnitOfMeasure": self.new_lot_id.product_uom_id.description,
                    },
                ]
            }
        ]

        body = json.dumps(body)

        # comment code to prevent wrong sync to NS production

        # res = requests.post(url, data=body, auth=auth, headers=headers)
        #
        # if res.status_code == 200:
        #     self.sync_state = 'done'
        #     return True
        # self.sync_msg = res.text
        # self.sync_state = 'fail'
        return False

    def sync_multi_to_metrc(self):
        need_syncs = self.filtered(lambda p: p.sync_state in ('in_queue', 'fail') and p.is_cannabis and p.license_id)
        if not need_syncs:
            return False

        for wizard in need_syncs:
            wizard.with_delay().sync_to_metrc()
        return True
