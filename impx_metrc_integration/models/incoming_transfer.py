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
INCOMING_TRANSFER_FIELD_MAP = {
    'Id': 'metrc_transfer_id',
    'ManifestNumber': 'metrc_manifest_number',
    'DeliveryId': 'metrc_delivery_id',
    'ShipperFacilityLicenseNumber': 'metrc_shipper_facility_license_number',
    'ShipperFacilityName': 'metrc_shipper_facility_name',
    'CreatedDateTime': 'metrc_created_datetime',
    'CreatedByUserName': 'metrc_created_by_username',
    'LastModified': 'metrc_last_modified',
    'EstimatedDepartureDateTime': 'metrc_estimated_departure_datetime',
    'EstimatedArrivalDateTime': 'metrc_estimated_arrival_datetime',
    'ReceivedDateTime': 'metrc_received_datetime',
}

DATETIME_FIELD_LIST = [
    'CreatedDateTime',
    'LastModified',
    'EstimatedDepartureDateTime',
    'EstimatedArrivalDateTime',
    'ReceivedDateTime',
]

PACKAGE_STOCK_MOVE_MAP = {
    'PackageLabel': 'package_label',
    'PackageId': 'package_id',
}


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    from_metrc_incoming_transfer = fields.Boolean()
    mapped_po = fields.Boolean()

    def set_external_for_lot_quant(self):
        lots = self.move_line_nosuggest_ids.mapped('lot_id')
        if not lots:
            return False

        license_id = self._context.get('license_id', False)
        lot_vals = {
            'external': True,
        }
        if license_id:
            lot_vals['license_id'] = license_id
        lots.write(lot_vals)
        quants = self.env['stock.quant'].sudo().search([('lot_id', 'in', lots._ids)])

        if quants:
            quants.write({'external': True})
        return False

    def auto_fill_move_line(self):
        self.ensure_one()
        move_line_nosuggest_ids = []
        for move in self.move_ids_without_package:
            package_label = move.package_label
            if not package_label:
                continue

            lot_domain = [('name', '=', package_label)]
            lot_ids = self.env['stock.production.lot'].search(lot_domain)
            lot = lot_ids and lot_ids[0] or False
            lot_id = lot and lot.id or False

            if lot:
                lot.write({'not_create_quant': True})

            move_line_vals = {
                'product_id': move.product_id.id,
                'location_dest_id': move.location_dest_id.id,
                'location_id': move.location_id.id,
                'lot_name': package_label,
                'qty_done': move.product_uom_qty,
                'product_uom_id': move.product_uom.id,
                'lot_id': lot_id,
            }
            move_line_nosuggest_ids.append((0, 0, move_line_vals))
        self.write({
            'move_line_nosuggest_ids': move_line_nosuggest_ids,
        })

    # sync package for a incoming
    @api.model
    def synchronize_metrc_delivery_package(self, picking_value):
        metrc_delivery_id = picking_value['metrc_delivery_id']

        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()

        url = '{}/transfers/v1/delivery/{}/packages'.format(
            base_metrc_url, metrc_delivery_id)
        try:
            response = requests.get(url, auth=auth, headers=headers)

            if response.status_code == 200:
                datas = json.loads((response.content.decode('utf-8')))

                result = self.process_sync_transfer_delivery_package_response(datas, picking_value)
                if not result['result']:
                    error_msg = result['msg']
                    self.process_sync_transfer_delivery_package_error(error_msg)
                    return {
                        'result': False,
                        'msg': error_msg
                    }
                return {
                    'result': True
                }
            else:
                error_msg = response.content.decode('utf-8')
                self.process_sync_transfer_delivery_package_error(error_msg)
                return {
                    'result': False,
                    'msg': error_msg
                }
        except Exception as e:
            error_msg = exception_to_unicode(e)
            self.process_sync_transfer_delivery_package_error(error_msg)
            return {
                'result': False,
                'msg': error_msg
            }

    def process_sync_transfer_delivery_package_error(self, error_msg):
        _logger.error('Sync transfer delivery Error {} '.format(error_msg))
        print(error_msg)

    def get_product_dict(self, ProductNames):
        if not ProductNames:
            return {}

        products = self.env['product.product'].search([('name', 'in', ProductNames)])
        product_dict = dict((product.name, product.id) for product in products)
        return product_dict

    def get_unit_dict(self, unit_names):
        if not unit_names:
            return {}

        units = self.env['uom.uom'].search([('description', 'in', unit_names)])
        unit_dict = dict((unit.description, unit.id) for unit in units)
        return unit_dict

    def prepare_stock_move_value(self, package, product_name, product_id, product_uom, location_dest_id, location_id):
        product_uom_qty = package['ReceivedQuantity']
        value = {
            'name': product_name,
            'company_id': self.company_id.id,
            'date_expected': self.scheduled_date or datetime.now(),
            'product_id': product_id,
            'description_picking': product_name,
            'product_uom_qty': product_uom_qty,
            'product_uom': product_uom,
            'location_id': location_id,
            'location_dest_id': location_dest_id,
            'state': 'draft',
            'picking_type_id': self.picking_type_id.id,
            # 'picking_id': self.id,
        }

        for metrc_field in PACKAGE_STOCK_MOVE_MAP.keys():
            odoo_field = PACKAGE_STOCK_MOVE_MAP[metrc_field]
            value[odoo_field] = package[metrc_field]

        return value

    @api.model
    def process_sync_transfer_delivery_package_response(self, datas, picking_value):
        # build dict key = item name, value = list of package info

        odoo_package_id_field = PACKAGE_STOCK_MOVE_MAP['PackageId']
        package_ids = [str(package['PackageId']) for package in datas]

        already_exist_moves = self.env['stock.move'].search([(odoo_package_id_field, 'in', package_ids), ('state', '=', 'done')])

        already_exist_package_ids = [str(getattr(already_exist_move, odoo_package_id_field)) for already_exist_move in already_exist_moves]

        unit_names = []
        ProductNames = []
        for package in datas:
            PackageId = package['PackageId']
            PackageLabel = package['PackageLabel']
            SourcePackageLabels = package['SourcePackageLabels']
            ProductName = package['ProductName']
            ShippedQuantity = package['ShippedQuantity']
            ReceivedQuantity = package['ReceivedQuantity']
            ShippedUnitOfMeasureName = package['ShippedUnitOfMeasureName']
            ReceivedUnitOfMeasureName = package['ReceivedUnitOfMeasureName']

            if str(PackageId) in already_exist_package_ids:
                continue

            if ShippedUnitOfMeasureName not in unit_names:
                unit_names.append(ShippedUnitOfMeasureName)

            if ReceivedUnitOfMeasureName not in unit_names:
                unit_names.append(ReceivedUnitOfMeasureName)

            if ProductName not in ProductNames:
                ProductNames.append(ProductName)

        product_dict = self.get_product_dict(ProductNames)

        unit_dict = self.get_unit_dict(unit_names)

        picking_type_id = picking_value['picking_type_id']
        picking_type = self.env['stock.picking.type'].browse(picking_type_id)
        location_dest_id = picking_type.default_location_src_id.id
        location_id = picking_value['location_dest_id']

        if not location_dest_id:
            location_dest_id = self.env.ref('stock.stock_location_suppliers').id

        move_ids_without_package = []
        for package in datas:
            PackageId = package['PackageId']
            PackageLabel = package['PackageLabel']
            SourcePackageLabels = package['SourcePackageLabels']
            ProductName = package['ProductName']
            ShippedQuantity = package['ShippedQuantity']
            ReceivedQuantity = package['ReceivedQuantity']
            ShippedUnitOfMeasureName = package['ShippedUnitOfMeasureName']
            ReceivedUnitOfMeasureName = package['ReceivedUnitOfMeasureName']
            ShipmentPackageState = package['ShipmentPackageState']

            if ShipmentPackageState != 'Accepted':
                continue

            product_id = product_dict.get(ProductName, False)
            product_uom = unit_dict.get(ReceivedUnitOfMeasureName, False)

            if not product_uom:
                return {
                    'result': False,
                    'msg': 'Unit "{}" for "{}" not found'.format(ReceivedUnitOfMeasureName, ProductName)
                }

            if not product_id:
                return {
                    'result': False,
                    'msg': 'product "{}" with unit "{}" not found'.format(ProductName, ReceivedUnitOfMeasureName)
                }

            value = self.prepare_stock_move_value(package, ProductName, product_id, product_uom, location_dest_id, location_id)
            move_ids_without_package.append((0, 0, value))

        picking_value['move_ids_without_package'] = move_ids_without_package

        return {
            'result': True
        }

class CannabisLicense(models.Model):
    _inherit = 'cannabis.license'

    incoming_transfer_last_sync = fields.Datetime()

    # get warehouse, picking type for license
    def get_incoming_picking_type(self):
        self.ensure_one()
        analytic_accounts = self.env['account.analytic.account'].search(
            [('cannabis_license_id', '=', self.id)])

        if not analytic_accounts:
            return False, False

        warehouses = self.env['stock.warehouse'].search([('analytic_account_id', '=', analytic_accounts[0].id)])
        if not warehouses:
            return False, False

        picking_type_domain = [('warehouse_id', '=', warehouses[0].id), ('code', '=', 'incoming')]
        picking_types = self.env['stock.picking.type'].search(picking_type_domain)

        picking_type = picking_types and picking_types[0] or False
        return warehouses[0], picking_type

    def get_analytic_account(self):
        self.ensure_one()
        analytic_accounts = self.env['account.analytic.account'].search(
            [('cannabis_license_id', '=', self.id)])
        return analytic_accounts and analytic_accounts[0] or False

    @api.model
    def sync_incoming_transfer(self):
        lisences = self.search([])
        if not lisences:
            return False
        for lisence in lisences:
            lisence.sync_incoming_transfer_for_a_license()
        return True

    # sync incoming for a license with last sync on license
    def sync_incoming_transfer_for_a_license(self):
        self.ensure_one()

        base_metrc_url, headers = self.env.user.company_id.get_metrc_connect_info()
        headers = {
            'Content-Type': 'application/json'
        }
        auth = self.env.user.company_id.get_authen()

        incoming_transfer_last_sync = self.incoming_transfer_last_sync
        if not incoming_transfer_last_sync:
            incoming_transfer_last_sync = datetime.now() + timedelta(days=-1)

        lastModifiedStart = incoming_transfer_last_sync.strftime('%Y-%m-%dT%H:%M:%S')

        modifire_end = incoming_transfer_last_sync + timedelta(days=1)
        modifire_end = min(modifire_end, datetime.now())
        lastModifiedEnd = modifire_end.strftime('%Y-%m-%dT%H:%M:%S')

        license_number = self.name
        url = '{}/transfers/v1/incoming?licenseNumber={}&lastModifiedStart={}&lastModifiedEnd={}'.format(
            base_metrc_url, license_number, lastModifiedStart, lastModifiedEnd)

        picking_ids = []
        try:
            response = requests.get(url, auth=auth, headers=headers)
            if response.status_code == 200:

                datas = json.loads((response.content.decode('utf-8')))
                picking_ids = self.process_sync_incoming_transfer_response(datas)
                self.write({
                    'incoming_transfer_last_sync': modifire_end
                })
            else:
                error_msg = response.content.decode('utf-8')
                self.process_sync_incoming_transfer_error(error_msg)
        except Exception as e:
            error_msg = exception_to_unicode(e)
            self.process_sync_incoming_transfer_error(error_msg)

        for picking in self.env['stock.picking'].browse(picking_ids):
            picking.action_confirm()
            picking.auto_fill_move_line()
            picking.action_done()
            picking.with_context(license_id=self.id).set_external_for_lot_quant()
        return True

    def process_sync_incoming_transfer_error(self, error_msg):
        _logger.error('Sync incoming transfer Error {} '.format(error_msg))
        print('Sync incoming transfer Error {} '.format(error_msg))

    @api.model
    def format_metrc_transfer_value(self, metrc_field, value):
        if metrc_field in DATETIME_FIELD_LIST:
            res = self.env['product.product'].change_datetime_from_iso_with_timezone_to_utc(value)
            return res
        return value

    # prepare picking create value from each transfer data of Metrc API response
    def prepare_value_from_metrc_incoming_transfer_data(self, transfer_data):
        warehouse, picking_type = self.get_incoming_picking_type()
        if not warehouse or not picking_type:
            raise UserError(_('Error: License "{}" not assigned for any warehouse!').format(self.name))

        analytic_account = self.get_analytic_account()

        value = {
            'picking_type_id': picking_type.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': warehouse.lot_stock_id.id,
            'analytic_account_id': analytic_account.id,
            'from_metrc_incoming_transfer': True,
        }

        for metrc_field in INCOMING_TRANSFER_FIELD_MAP.keys():
            odoo_field = INCOMING_TRANSFER_FIELD_MAP[metrc_field]

            metrc_value = transfer_data.get(metrc_field, False)
            odoo_value = self.format_metrc_transfer_value(metrc_field, metrc_value)

            value[odoo_field] = odoo_value

        value['scheduled_date'] = value.get('metrc_estimated_arrival_datetime', False)
        return value

    # process response data of incoming transfer API
    def process_sync_incoming_transfer_response(self, datas):
        if not datas:
            return False

        picking_ids = []
        for transfer in datas:

            value = self.prepare_value_from_metrc_incoming_transfer_data(transfer)
            result = self.env['stock.picking'].synchronize_metrc_delivery_package(value)
            if result['result'] and value['move_ids_without_package']:
                picking = self.env['stock.picking'].create(value)

                picking_ids.append(picking.id)

        return picking_ids
