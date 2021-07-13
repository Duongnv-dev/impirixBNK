# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError
from odoo.osv import expression

import logging
import re
import base64
import requests
import json
from datetime import datetime
import iso8601
import pytz
from odoo.addons.queue_job.job import job

from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

UPDATE_LIST = ['metrc_approval_status', 'metrc_approval_status_datetime', 'metrc_is_used', 'unit_of_measure', 'strain_id', 'brand_id']

FIELDS_NORMAL_METRCT_ODOO_DICT = {
    'Name': 'name',
    'UnitThcPercent': 'metrc_unit_thc_percent',
    'UnitThcContent': 'metrc_unit_thc_content',
    'UnitThcContentDose': 'metrc_unit_thc_content_dose',
    'UnitVolume': 'volume',
    'UnitWeight': 'weight',
    'ServingSize': 'metrc_serving_size',
    'SupplyDurationDays': 'metrc_supply_duration_days',
    'NumberOfDoses': 'metrc_number_of_doses',
    'Ingredients': 'metrc_ingredients',
    'Description': 'metrc_description',
}

FIELDS_M2O_METRCT_ODOO_DICT = {
    'ItemCategory': 'categ_id',
    'UnitOfMeasure': 'uom_id',
    'Strain': 'strain_id',
    'UnitThcContentUnitOfMeasure': 'metrc_unit_thc_content_name',
    'UnitThcContentDoseUnitOfMeasure': 'metrc_unit_thc_content_dose_name',
    'UnitVolumeUnitOfMeasure': 'volume_uom_name',
    'UnitWeightUnitOfMeasure': 'weight_uom_name',
}

FIELDS_NORMAL_ODOO_METRCT_DICT = {
    'name': 'Name',
    'metrc_unit_thc_percent': 'UnitThcPercent',
    'metrc_unit_thc_content': 'UnitThcContent',
    'metrc_unit_thc_content_dose': 'UnitThcContentDose',
    'volume': 'UnitVolume',
    'weight': 'UnitWeight',
    'metrc_serving_size': 'ServingSize',
    'metrc_supply_duration_days': 'SupplyDurationDays',
    'metrc_number_of_doses': 'NumberOfDoses',
    'metrc_ingredients': 'Ingredients',
    'metrc_description': 'Description',
}

FIELDS_M2O_ODOO_METRCT_DICT = {
    'categ_id': 'ItemCategory',
    'uom_id': 'UnitOfMeasure',
    # 'strain_id': 'Strain',
    'metrc_unit_thc_content_name': 'UnitThcContentUnitOfMeasure',
    'metrc_unit_thc_content_dose_name': 'UnitThcContentDoseUnitOfMeasure',
    # 'volume_uom_name': 'UnitVolumeUnitOfMeasure',
    # 'weight_uom_name': 'UnitWeightUnitOfMeasure',
}

FIELDS_M2O_MODEL_DICT = {
    'categ_id': 'product.category',
    'uom_id': 'uom.uom',
    # 'strain_id': 'res.strain',
    'metrc_unit_thc_content_name': 'uom.uom',
    'metrc_unit_thc_content_dose_name': 'uom.uom',
    # 'volume_uom_name': 'uom.uom',
    # 'weight_uom_name': 'uom.uom',
}


class ProductCategory(models.Model):
    _inherit = "product.category"

    category_type = fields.Selection([('buds', 'Buds'), ('concentrate', 'Concentrate'), ('plants', 'Plants'),
                                      ('infusedEdible', 'InfusedEdible'), ('shake_trim', 'ShakeTrim'), ('other', 'Other')])
    qty_type_id = fields.Many2one('uom.category', string='Quantity Type')

    def get_metrc_category(self):
        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()

        url = '{}/items/v1/categories'.format(base_metrc_url)

        try:
            response = requests.get(url, auth=auth, headers=headers)
            if response.status_code == 200:
                category_data = json.loads((response.content.decode('utf-8')))
                self.create_category_from_metrc(category_data)
            else:
                error_msg = response.content.decode('utf-8')
                self.process_sync_product_category_error(error_msg)
        except Exception as error_msg:
            self.process_sync_product_category_error(error_msg)

    def create_category_from_metrc(self, category_data):
        create_value = []
        category_db_dict = self.get_db_category_dict()
        category_type_dict = self.get_category_type_dict()
        for categ in category_data:
            if category_db_dict.get(categ['Name'], False):
                continue
            val = {
                'name': categ['Name'],
            }
            if categ.get('ProductCategoryType', False):
                val['category_type'] = category_type_dict.get(categ['ProductCategoryType'], False)
            if categ.get('QuantityType', False):
                uom_category_id = self.env['uom.uom']. get_metrc_uom_category_dict(categ['QuantityType'])
                if not uom_category_id:
                    uom_category_id = self.env['uom.uom'].create_uom_category(categ['QuantityType'], False)
                val['qty_type_id'] = uom_category_id.id
            create_value.append(val)
        return self.create(create_value)

    def get_db_category_dict(self):
        category_list = self.search_read([], ['name'])
        category_dict = dict((row['name'], row['id']) for row in category_list)
        return category_dict

    def get_category_type_dict(self):
        return {
            'Buds': 'buds',
            'Concentrate': 'concentrate',
            'Plants': 'plants',
            'InfusedEdible': 'infusedEdible',
            'ShakeTrim': 'shake_trim',
            'Other': 'other',
        }

    def process_sync_product_category_error(self, error_msg):
        _logger.error('Sync item Error {} '.format(error_msg))
        print(error_msg)


class ProductProduct(models.Model):
    _inherit = "product.product"

    metrc_id = fields.Char(readonly=True)
    metrc_default_lab_testing_state = fields.Selection([('not_submitted', 'Not Submitted'),
                                                        ('awaiting_confirmation', 'Awaiting Confirmation')], string='Default Lab Testing State')
    metrc_approval_status = fields.Selection([('draft', 'Draft'), ('approved', 'Approved')], string='Approval Status')
    metrc_approval_status_datetime = fields.Datetime(string='Approval Status DateTime')
    strain_id = fields.Many2one('res.strain', string='Strain')
    metrc_unit_thc_percent = fields.Float(string='UnitThcPercent')
    metrc_unit_thc_content = fields.Float(string='UnitThcContent')
    metrc_unit_thc_content_name = fields.Many2one('uom.uom', string='UnitThcContentUnitOfMeasureName')
    metrc_unit_thc_content_dose = fields.Float(string='UnitThcContentDose')
    metrc_unit_thc_content_dose_name = fields.Many2one('uom.uom', string='UnitThcContentDoseUnitOfMeasureName')
    metrc_serving_size = fields.Float(string='Serving Size')
    metrc_supply_duration_days = fields.Float(string='Supply Duration Days')
    metrc_number_of_doses = fields.Float(string='Number Of Doses')
    metrc_ingredients = fields.Char(string='Ingredients')
    metrc_description = fields.Char(string='Metrc Description')
    metrc_is_used = fields.Boolean()

    # @api.constrains('metrc_connect', 'categ_id', 'uom_id')
    # def _check_uom_category_of_product_categ_with_uom_category_of_product(self):
    #     for prod in self:
    #         if prod.metrc_connect:
    #             if prod.categ_id.qty_type_id != prod.uom_id.category_id:
    #                 raise ValidationError((_('The Product must have the same unit type as the Product Category')))

    # Temporarily hide the function of pushing products on Metrc so we will comment create, write
    # call function create a corresponding item on Metrc
    # @api.model
    # def create(self, values):
    #     context = self._context
    #     res = super(ProductProduct, self).create(values)
    #     if not context.get('create_from_metrc', False) and res.metrc_connect:
    #         self.with_delay(eta=1).create_item_to_metrc(values)
    #     return res

    # call function update a corresponding item on Metrc
    # def write(self, values):
    #     context = self._context
    #     res = super(ProductProduct, self).write(values)
    #     if not context.get('write_from_metrc', False) and self.metrc_connect:
    #         self.update_item_to_metrc(values)
    #     return res

    # Get all item from Metrc to Odoo by license
    @api.model
    def get_metrc_item(self):
        can_licenses = self.env['cannabis.license'].search([])
        if can_licenses:
            for license in can_licenses:
                self.with_delay().get_metrc_item_by_lisence(license)
        return True

    @job
    def get_metrc_item_by_lisence(self, license):
        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()
        url = '{}/items/v1/active?licenseNumber={}'.format(base_metrc_url, license.name)
        try:
            response = requests.get(url=url, auth=auth, headers=headers)
            if response.status_code == 200:
                item_data = json.loads((response.content.decode('utf-8')))
                self.check_create_product_from_metrc(license.id, item_data)
            else:
                error_msg = response.content.decode('utf-8')
                self.process_sync_item_error(error_msg)
        except Exception as error_msg:
            self.process_sync_item_error(error_msg)

    def get_db_product_dict(self):
        product_list = self.search_read([], ['name', 'metrc_id'])
        product_name_dict = dict((row['name'].lower().strip(), row['id']) for row in product_list)
        product_metrc_id_dict = dict((row['metrc_id'], row['id']) for row in product_list)
        return product_name_dict, product_metrc_id_dict

    # Function create or update product in odoo by item get from Metrc
    def check_create_product_from_metrc(self, license_id, item_data):
        create_value = []
        product_name_dict, product_metrc_id_dict = self.get_db_product_dict()
        uom_name_dict = self.env['uom.uom'].get_db_uom_dict()
        uom_description_dict = self.env['uom.uom'].get_db_uom_description_dict()
        category_dict = self.env['product.category'].get_db_category_dict()
        for item in item_data:
            if product_metrc_id_dict.get(item['Id'], False):
                product = self.env['product.product'].browse(product_metrc_id_dict[item['Id']])
                odoo_prod = self.env['product.product'].search_read([('id', '=', product_metrc_id_dict[item['Id']])])
                val_update = self.get_val_update_from_item(item, license_id, uom_description_dict, uom_name_dict, odoo_prod[0], category_dict)
                if val_update:
                    try:
                        product.with_context(write_from_metrc=True).write(val_update)
                        continue
                    except Exception as error_msg:
                        self.process_sync_item_error(error_msg)
                        continue
            if product_name_dict.get(item['Name'].lower().strip(), False):
                val = {'metrc_id': item['Id'], 'metrc_connect': True}
                product = self.env['product.product'].browse(product_name_dict[item['Name'].lower().strip()])
                product.with_context(write_from_metrc=True).write(val)
                continue
            val = self.get_val_create_from_item(item, license_id, uom_description_dict, uom_name_dict, category_dict)
            create_value.append(val)
        return self.sudo().with_context(create_from_metrc=True).create(create_value)

    # Build value to create product
    def get_val_create_from_item(self, item, license_id, uom_description_dict, uom_name_dict, category_dict):
        categ_id = self.get_categ_id_from_item(item, category_dict)
        val = {
            'name': item['Name'],
            'metrc_connect': True,
            'is_cannabis': True,
            'tracking': 'lot',
            'cannabis_license_id': license_id,
            'metrc_id': item['Id'],
            'metrc_is_used': item['IsUsed'],
            'categ_id': categ_id,
        }

        lab_testing_dict = {'Not Submitted': 'not_submitted',
                            'Awaiting Confirmation': 'awaiting_confirmation'}
        approval_status_dict = {'Draft': 'draft', 'Approved': 'approved'}
        if item.get('DefaultLabTestingState', False):
            val['metrc_default_lab_testing_state'] = lab_testing_dict.get(item['DefaultLabTestingState'], False)
        if item.get('UnitOfMeasureName', False):
            val['uom_id'] = uom_description_dict.get(item['UnitOfMeasureName'], False)
            val['uom_po_id'] = uom_description_dict.get(item['UnitOfMeasureName'], False)
            if not val['uom_id']:
                val['uom_id'] = uom_name_dict.get(item['UnitOfMeasureName'], False)
                val['uom_po_id'] = uom_description_dict.get(item['UnitOfMeasureName'], False)

        if item.get('ApprovalStatus') == 'Approved':
            val['metrc_approval_status'] = 'approved'
        else:
            val['metrc_approval_status'] = 'draft'
        # if item.get('ApprovalStatusDateTime', False):
        #     try:
        #         approval_date = self.change_datetime_from_iso_with_timezone_to_utc(item['ApprovalStatusDateTime'])
        #         if approval_date:
        #             val['metrc_approval_status_datetime'] = approval_date
        #     except Exception as error:
        #         pass
        if item.get('UnitThcPercent', False):
            val['metrc_unit_thc_percent'] = item['UnitThcPercent']
        if item.get('UnitThcContent', False):
            val['metrc_unit_thc_content'] = item['UnitThcContent']
        if item.get('UnitThcContentUnitOfMeasureName', False):
            val['metrc_unit_thc_content_name'] = uom_description_dict.get(item['UnitThcContentUnitOfMeasureName'], False)
        if item.get('UnitThcContentDose', False):
            val['metrc_unit_thc_content_dose'] = item['UnitThcContentDose']
        if item.get('UnitThcContentDoseUnitOfMeasureName', False):
            val['metrc_unit_thc_content_dose_name'] = uom_description_dict.get(item['UnitThcContentDoseUnitOfMeasureName'], False)
        if item.get('UnitVolume', False):
            val['volume'] = item['UnitVolume']
        if item.get('UnitVolumeUnitOfMeasureName', False):
            val['volume_uom_name'] = uom_description_dict.get(item['UnitVolumeUnitOfMeasureName'], False)
        if item.get('UnitWeight', False):
            val['weight'] = item['UnitWeight']
        if item.get('UnitWeightUnitOfMeasureName', False):
            val['weight_uom_name'] = uom_description_dict.get(item['UnitWeightUnitOfMeasureName'], False)
        if item.get('ServingSize', False):
            val['metrc_serving_size'] = item['ServingSize']
        if item.get('SupplyDurationDays', False):
            val['metrc_supply_duration_days'] = item['SupplyDurationDays']
        if item.get('NumberOfDoses', False):
            val['metrc_number_of_doses'] = item['NumberOfDoses']
        if item.get('Ingredients', False):
            val['metrc_ingredients'] = item['Ingredients']
        return val

    # Build value to update product
    def get_val_update_from_item(self, item, license_id, uom_description_dict, uom_name_dict, odoo_prod, category_dict):
        val = {}
        categ_id = self.get_categ_id_from_item(item, category_dict)
        if odoo_prod.get('categ_id', False):
            if categ_id != odoo_prod['categ_id'][0]:
                val['categ_id'] = categ_id
        else:
            if categ_id != False:
                val['categ_id'] = categ_id
        key_normal_dict = {
            'Name': 'name',
            'IsUsed': 'metrc_is_used',
            'UnitThcPercent': 'metrc_unit_thc_percent',
            'UnitThcContent': 'metrc_unit_thc_content',
            'UnitThcContentDose': 'metrc_unit_thc_content_dose',
            'UnitVolume': 'volume',
            'UnitWeight': 'weight',
            'ServingSize': 'metrc_serving_size',
            'SupplyDurationDays': 'metrc_supply_duration_days',
            'NumberOfDoses': 'metrc_number_of_doses',
            'Ingredients': 'metrc_ingredients',
        }

        for key_item in key_normal_dict.keys():
            if item.get(key_item, False):
                if item[key_item] != odoo_prod.get(key_normal_dict[key_item], False):
                    val[key_normal_dict[key_item]] = item[key_item]

        lab_testing_dict = {'Not Submitted': 'not_submitted',
                            'Awaiting Confirmation': 'awaiting_confirmation'}
        approval_status_dict = {'Draft': 'draft', 'Approved': 'approved'}

        if item.get('DefaultLabTestingState', False):
            if lab_testing_dict.get(item['DefaultLabTestingState'], False):
                if lab_testing_dict[item['DefaultLabTestingState']] != odoo_prod.get('metrc_default_lab_testing_state', False):
                    val['metrc_default_lab_testing_state'] = lab_testing_dict[item['DefaultLabTestingState']]

        if item.get('ApprovalStatus', False):
            if lab_testing_dict.get(item['ApprovalStatus'], False):
                if lab_testing_dict[item['ApprovalStatus']] != odoo_prod.get('metrc_approval_status', False):
                    val['metrc_approval_status'] = lab_testing_dict[item['ApprovalStatus']]

        # if item.get('ApprovalStatusDateTime', False):
        #     try:
        #         approval_date = self.change_datetime_from_iso_with_timezone_to_utc(item['ApprovalStatusDateTime'])
        #         if approval_date:
        #             approval_date = datetime.strptime(approval_date, '%Y-%m-%d %H:%M:%S')
        #             if approval_date != odoo_prod.get('metrc_approval_status_datetime', False):
        #                 val['metrc_approval_status_datetime'] = approval_date
        #     except Exception as error:
        #         pass

        key_m2o_dict = {
            'UnitOfMeasureName': 'uom_id',
            'UnitThcContentUnitOfMeasureName': 'metrc_unit_thc_content_name',
            'UnitThcContentDoseUnitOfMeasureName': 'metrc_unit_thc_content_dose_name',
            'UnitVolumeUnitOfMeasureName': 'volume_uom_name',
            'UnitWeightUnitOfMeasureName': 'weight_uom_name',
        }

        for key_m2o_item in key_m2o_dict.keys():
            if item.get(key_m2o_item, False):
                if uom_description_dict.get(item[key_m2o_item], False) and odoo_prod.get(key_m2o_dict[key_m2o_item], False):
                    if uom_description_dict[item[key_m2o_item]] != odoo_prod[key_m2o_dict[key_m2o_item]][0]:
                        val[key_m2o_dict[key_m2o_item]] = uom_description_dict[item[key_m2o_item]]
        return val

    # Get all category from Metrc
    def get_categ_id_from_item(self, item, category_dict):
        categ_id = False
        if item.get('ProductCategoryName', False):
            if category_dict.get(item['ProductCategoryName'], False):
                categ_id = category_dict[item['ProductCategoryName']]
            else:
                val_catg = {
                    'name': item['ProductCategoryName']
                }
                category_type_dict = self.env['product.category'].get_category_type_dict()
                if category_type_dict.get(item['ProductCategoryType'], False):
                    val_catg['category_type'] = category_type_dict[item['ProductCategoryType']]
                if item.get('QuantityType', False):
                    uom_category_id = self.env['uom.uom'].get_metrc_uom_category_dict(item['QuantityType'])
                    if not uom_category_id:
                        uom_category_id = self.env['uom.uom'].create_uom_category(item['QuantityType'], False)
                    val_catg['qty_type_id'] = uom_category_id.id
                category_id = self.env['product.category'].create(val_catg)
                categ_id = category_id.id
                category_dict[item['ProductCategoryName']] = categ_id
        return categ_id

    def change_datetime_from_iso_with_timezone_to_utc(self, datetime_iso):
        try:
            datetime_ll = iso8601.parse_date(datetime_iso)
            resp = datetime_ll.astimezone(pytz.utc)
            return datetime.strftime(resp, '%Y-%m-%d %H:%M:%S')
        except Exception as error:
            return False

    # Job creates a corresponding item on Metrc
    # build data to post
    # @job
    def create_item_to_metrc(self, value):
        vals_post = {}
        if not value.get('cannabis_license_id', False):
            return True
        license_id = value['cannabis_license_id']
        if isinstance((value['cannabis_license_id']), list) or isinstance((value['cannabis_license_id']), tuple):
            license_id = value['cannabis_license_id'][0]
        license = self.env['cannabis.license'].browse(license_id)
        for key in value.keys():
            if key in FIELDS_NORMAL_ODOO_METRCT_DICT.keys():
                vals_post[FIELDS_NORMAL_ODOO_METRCT_DICT[key]] = value[key]

            if key in FIELDS_M2O_ODOO_METRCT_DICT.keys():
                target_id = value[key]
                if isinstance((value[key]), list) or isinstance((value[key]), tuple):
                    target_id = value[key][0]
                target_object = self.env[FIELDS_M2O_MODEL_DICT[key]].browse(target_id)
                if FIELDS_M2O_MODEL_DICT[key] == 'uom.uom':
                    target_name = target_object.description
                else:
                    target_name = target_object.name
                vals_post[FIELDS_M2O_ODOO_METRCT_DICT[key]] = target_name
        return self.request_create_item_to_metrc(license, vals_post)

    # Call API to create Item
    def request_create_item_to_metrc(self, license, vals):
        item_name = vals.get('Name', False)
        if not item_name:
            return
        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()

        url = '{}/items/v1/create?licenseNumber={}'.format(base_metrc_url, license.name)

        data = json.dumps([vals])
        try:
            response = requests.post(url=url, auth=auth, headers=headers, data=data)
            if response.status_code == 200:
                self.with_delay(eta=1).map_product_item_after_create(license, item_name)
            else:
                error_msg = response.content.decode('utf-8')
                self.process_sync_item_error(error_msg)
        except Exception as error_msg:
            self.process_sync_item_error(error_msg)

    # map product with item metrc by metrc id after create product in odoo
    @job
    def map_product_item_after_create(self, license, item_name):
        self.map_an_item_by_lisence(license, item_name)

    def map_an_item_by_lisence(self, license, item_name):
        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()

        url = '{}/items/v1/active?licenseNumber={}'.format(base_metrc_url, license.name)
        try:
            response = requests.get(url=url, auth=auth, headers=headers)
            if response.status_code == 200:
                item_datas = json.loads((response.content.decode('utf-8')))
                self.map_an_item_from_metrc(license, item_name, item_datas)
            else:
                error_msg = response.content.decode('utf-8')
                self.process_sync_item_error(error_msg)
        except Exception as error_msg:
            self.process_sync_item_error(error_msg)

    def map_an_item_from_metrc(self, license, item_name, item_datas):
        product_name_dict, product_metrc_id_dict = self.get_db_product_dict()
        for item in item_datas:
            if item['Name'] == item_name:
                if product_name_dict.get(item['Name'].lower().strip(), False):
                    val = {'metrc_id': item['Id']}
                    product = self.env['product.product'].browse(product_name_dict[item['Name'].lower().strip()])
                    product.write(val)
                break
        return True

    # Temporarily hide the function of pushing products on Metrc so we will comment create, write
    # def manual_create_item_metrct(self):
    #     values = self.read()[0]
    #     if values.get('metrc_connect', False):
    #         self.with_delay(eta=1).create_item_to_metrc(values)
    #     return True

    # function update item metrct when change product in doo
    def update_item_to_metrc(self, value):
        if not self.metrc_connect or not self.metrc_id or not self.cannabis_license_id:
            return True
        vals_post = {'ID': self.metrc_id}
        if 'name' not in value.keys():
            vals_post['Name'] = self.name
        if 'categ_id' not in value.keys():
            vals_post['ItemCategory'] = self.categ_id.name
        license = self.cannabis_license_id
        for key in value.keys():
            if key in FIELDS_NORMAL_ODOO_METRCT_DICT.keys():
                vals_post[FIELDS_NORMAL_ODOO_METRCT_DICT[key]] = value[key]

            if key in FIELDS_M2O_ODOO_METRCT_DICT.keys():
                target_id = value[key]
                if isinstance((value[key]), list) or isinstance((value[key]), tuple):
                    target_id = value[key][0]
                target_object = self.env[FIELDS_M2O_MODEL_DICT[key]].browse(target_id)
                if FIELDS_M2O_MODEL_DICT[key] == 'uom.uom':
                    target_name = target_object.description
                else:
                    target_name = target_object.name
                vals_post[FIELDS_M2O_ODOO_METRCT_DICT[key]] = target_name
        return self.request_update_item_to_metrc(license, vals_post)

    def request_update_item_to_metrc(self, license, vals_post):
        if not vals_post or len(vals_post.keys() == 3):
            return True
        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()
        url = '{}/items/v1/update?licenseNumber={}'.format(base_metrc_url, license.name)
        data = json.dumps([vals_post])
        try:
            response = requests.post(url=url, auth=auth, headers=headers, data=data)
            if response.status_code != 200:
                return True
            else:
                error_msg = response.content.decode('utf-8')
                self.process_sync_item_error(error_msg)
        except Exception as error_msg:
            self.process_sync_item_error(error_msg)

    def process_sync_item_error(self, error_msg):
        _logger.error('Sync item Error {} '.format(error_msg))
        print(error_msg)

