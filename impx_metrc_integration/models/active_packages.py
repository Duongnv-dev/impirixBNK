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

METRC_PACKAGE_STOCK_PRODUCTION_LOT_MAP = {
    'Label': 'name',
    'Quantity': 'product_qty',
}

class CannabisLicense(models.Model):
    _inherit = 'cannabis.license'

    @api.model
    def sync_active_package(self):
        lisences = self.search([])
        if not lisences:
            return False

        for lisence in lisences:
            lisence.sync_active_package_for_a_license()
        return True

    # sync incoming for a license with last sync on license
    def sync_active_package_for_a_license(self, lastModifiedStart=False, lastModifiedEnd=False):
        self.ensure_one()

        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()

        license_number = self.name
        url = '{}/packages/v1/active?licenseNumber={}'.format(
            base_metrc_url, license_number)

        if lastModifiedStart:
            url = '{}?lastModifiedStart={}'.format(url, lastModifiedStart)

        if lastModifiedEnd:
            url = '{}?lastModifiedEnd={}'.format(url, lastModifiedEnd)

        response = requests.get(url, auth=auth, headers=headers)
        status_code = response.status_code
        if response.status_code == 200:
            datas = json.loads((response.content.decode('utf-8')))
            process_active_package_result = self.process_sync_active_package_response(datas)

        try:
            response = requests.get(url, auth=auth, headers=headers)
            status_code = response.status_code
            if response.status_code == 200:
                datas = json.loads((response.content.decode('utf-8')))
                process_active_package_result = self.process_sync_active_package_response(datas)
            else:
                error_msg = response.content.decode('utf-8')
                self.process_sync_active_package_error(error_msg, status_code)
        except Exception as e:
            error_msg = exception_to_unicode(e)
            self.process_sync_active_package_error(error_msg, status_code)

    def process_sync_active_package_error(self, error_msg, status_code):
        _logger.error('Sync active package Error status_code:{} {} '.format(status_code, error_msg))
        print('Sync active package Error: status_code: {} {} '.format(status_code, error_msg))

    def process_sync_active_package_response(self, datas):
        new_package_ids = []
        update_package_ids = []
        skip_package_ids = []
        update_error_package_ids = []
        create_error_package_ids = []

        for metrc_package in datas:
            # need action include: not thing, update already exist package, create new
            already_packages = self.check_already_exist_for_active_package(metrc_package)

            if already_packages:
                update_result = already_packages[0].update_from_metrc(self, metrc_package)
                if update_result['result'] == 'OK':
                    update_package_ids.append(already_packages[0].id)

                elif update_result['result'] == 'SKIP':
                    skip_package_ids.append(already_packages[0].id)

                elif update_result['result'] == 'ERROR':
                    update_error_package_ids.append({
                        'package_id': already_packages[0].id,
                        'msg': update_result.get('msg', False)
                    })
            else:
                create_result = self.create_new_package_from_metrc(metrc_package)
                if create_result['result'] == 'OK':
                    new_package_ids.append(create_result['new_package_id'])

                elif create_result['result'] == 'ERROR':
                    create_error_package_ids.append({
                        'Label': create_result.get('Label', False),
                        'msg': create_result.get('msg', False)
                    })
        res = {
            'new_package_ids': new_package_ids,
            'update_package_ids': update_package_ids,
            'skip_package_ids': skip_package_ids,
            'update_error_package_ids': update_error_package_ids,
            'create_error_package_ids': create_error_package_ids,
        }

        return res

    def check_already_exist_for_active_package(self, metrc_package):
        label = metrc_package['Label']
        domain = [('name', '=', label)]
        already_packages = self.env['stock.production.lot'].search(domain)

        return already_packages

    def create_new_package_from_metrc(self, metrc_package):
        self.ensure_one()
        create_result = {}

        product_name = metrc_package['ProductName']

        product_domain = [('name', '=', product_name)]
        product_ids = self.env['product.product'].search(product_domain)

        if not product_ids:
            create_result['result'] = 'ERROR'
            create_result['Label'] = metrc_package['Label']
            create_result['msg'] = 'Item "{}" not found!'.format(product_name)
            return create_result

        package_value = {
            'product_id': product_ids[0].id,
            'company_id': self.env.user.company_id.id,
            'external': True,
            'license_id': self.id,
        }
        for metrc_field in METRC_PACKAGE_STOCK_PRODUCTION_LOT_MAP.keys():
            odoo_field = METRC_PACKAGE_STOCK_PRODUCTION_LOT_MAP[metrc_field]
            package_value[odoo_field] = metrc_package[metrc_field]

        package = self.env['stock.production.lot'].create(package_value)

        # update qty for package
        warehouse, picking_type = self.get_incoming_picking_type()
        location_id = warehouse.lot_stock_id.id
        metrc_qty = metrc_package['Quantity']
        metrc_qty = float(metrc_qty)

        if metrc_qty < 0:
            create_result['result'] = 'ERROR'
            create_result['msg'] = 'Negative qty'
            return create_result

        stock_inventory_vals = {
            'name': self.name,
            'location_ids': [(6, False, [location_id])],
            'product_ids': [(6, False, [package.product_id.id])],
        }
        stock_inventory = self.env['stock.inventory'].create(stock_inventory_vals)
        stock_inventory.action_start()

        line_to_update = False
        for line in stock_inventory.line_ids:
            if line.prod_lot_id.id != package.id:
                continue
            line_to_update = line
            break

        if not line_to_update:
            stock_inventory_line_vals = {
                'location_id': location_id,
                'product_id': package.product_id.id,
                'product_uom_id': package.product_id.uom_id.id,
                'prod_lot_id': package.id,
                'product_qty': metrc_qty,
                'inventory_id': stock_inventory.id,
            }
            line_to_update = self.env['stock.inventory.line'].create(stock_inventory_line_vals)
        else:
            line_to_update.write({
                'product_qty': metrc_qty,
            })

        stock_inventory.action_validate()

        create_result['result'] = 'OK'
        create_result['new_package_id'] = package.id

        return create_result


class StockProductionLot(models.Model):
    _inherit = 'stock.production.lot'

    def update_from_metrc(self, license, metrc_package):
        self.ensure_one()

        warehouse, picking_type = license.get_incoming_picking_type()
        location_id = warehouse.lot_stock_id.id
        metrc_qty = metrc_package['Quantity']
        metrc_qty = float(metrc_qty)

        if metrc_qty < 0:
            update_result = {
                'result': 'ERROR',
                'msg': 'Negative qty',
            }
            return update_result

        package_qty = self.product_qty

        if package_qty == metrc_qty:
            update_result = {
                'result': 'SKIP',
            }
            return update_result

        stock_inventory_vals = {
            'name': self.name,
            'location_ids': [(6, False, [location_id])],
            'product_ids': [(6, False, [self.product_id.id])],
        }
        stock_inventory = self.env['stock.inventory'].create(stock_inventory_vals)
        stock_inventory.action_start()

        line_to_update = False
        for line in stock_inventory.line_ids:
            if line.prod_lot_id.id != self.id:
                continue

            if line.product_qty == metrc_qty:
                update_result = {
                    'result': 'SKIP',
                }
                return update_result

            line_to_update = line

        if not line_to_update:
            stock_inventory_line_vals = {
                'location_id': location_id,
                'product_id': self.product_id.id,
                'product_uom_id': self.product_id.uom_id.id,
                'prod_lot_id': self.id,
                'product_qty': metrc_qty,
                'inventory_id': stock_inventory.id,
            }
            line_to_update = self.env['stock.inventory.line'].create(stock_inventory_line_vals)
        else:
            line_to_update.write({
                'product_qty': metrc_qty,
            })

        stock_inventory.action_validate()

        update_result = {
            'result': 'OK',
        }
        return update_result
