# -*- coding: utf-8 -*-

from odoo import api, fields, models, _, tools
import requests
import base64
import json
from requests.auth import HTTPBasicAuth
import logging

_logger = logging.getLogger(__name__)


class UoM(models.Model):
    _inherit = 'uom.uom'

    description = fields.Char()
    not_verified = fields.Boolean(default=False)

    @api.depends('name', 'not_verified')
    def name_get(self):
        res = []
        for record in self:
            name = record.name
            if record.not_verified:
                name = '{}-Not Verified'.format(record.name)
            res.append((record.id, name))
        return res

    def get_metrc_uom(self):
        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()

        url = '{}/unitsofmeasure/v1/active'.format(base_metrc_url)
        try:
            response = requests.get(url=url, auth=auth, headers=headers)
            if response.status_code == 200:
                uom_data = json.loads((response.content.decode('utf-8')))
                self.create_uom_from_metrc(uom_data)
            else:
                error_msg = response.content.decode('utf-8')
                self.process_sync_uom_error(error_msg)
        except Exception as error_msg:
            self.process_sync_uom_error(error_msg)

    def get_db_uom_dict(self):
        uom_list = self.search_read([], ['name'])
        uom_dict = dict((row['name'], row['id']) for row in uom_list)
        return uom_dict

    def get_db_uom_description_dict(self):
        uom_list = self.search_read([], ['description'])
        uom_dict = dict((row['description'], row['id']) for row in uom_list if row['description'] != '')
        return uom_dict

    def create_uom_from_metrc(self, uom_data):
        create_value = []
        uom_db_dict = self.get_db_uom_dict()
        for uom in uom_data:
            if uom_db_dict.get(uom['Abbreviation'], False):
                uom_odoo = self.browse(uom_db_dict[uom['Abbreviation']])
                if uom.get('Name' or False) != uom_odoo.description:
                    uom_odoo.write({'description': uom.get('Name' or False)})
                continue
            val = {
                'name': uom['Abbreviation'],
                'description': uom.get('Name' or False),
                'not_verified': True,
            }
            category_id = self.get_metrc_uom_category_dict(uom['QuantityType'])
            if not category_id:
                category_id = self.create_uom_category(uom['QuantityType'], False)
            val['category_id'] = category_id.id
            create_value.append(val)
        return self.create(create_value)

    def get_metrc_uom_category_dict(self, categ):
        metrc_dict = {
            'CountBased': 'uom.product_uom_categ_unit',
            'VolumeBased': 'uom.product_uom_categ_vol',
            'WeightBased': 'uom.product_uom_categ_kgm',
        }
        category_id = False
        if metrc_dict.get(categ, False):
            category_id = self.env.ref(metrc_dict[categ])
        return category_id

    def create_uom_category(self, name, measure_type):
        val = {
            'name': name,
            'measure_type': measure_type,
        }
        return self.env['uom.category'].create(val)

    def process_sync_uom_error(self, error_msg):
        _logger.error('Sync uom Error {} '.format(error_msg))
        print(error_msg)



