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

    def find_po_line(self, po):
        for line in po.order_line:
            if line.product_id == self.product_id:
                return line
        return False


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.model
    def create(self, vals):
        res = super().create(vals)
        res.set_partner_id_by_metrc_shipper_facility_license_number()
        return res

    def set_partner_id_by_metrc_shipper_facility_license_number(self):
        self.ensure_one()
        if not self.metrc_shipper_facility_license_number or self.partner_id:
            return True

        domain = [('regulatory_license', '=', self.metrc_shipper_facility_license_number)]
        partners = self.env['res.partner'].search(domain)

        if not partners:
            domain.append(('active', '=', False))
            partners = self.env['res.partner'].search(domain)

        if not partners:
            return True

        partner_id = partners[0].id
        vals = {
            'partner_id': partner_id,
        }
        return self.write(vals)

    @api.model
    def find_and_mapping_incoming_transfers_with_po(self):
        domain = [
            ('mapped_po', '=', False),
            ('from_metrc_incoming_transfer', '=', True),
            ('state', '=', 'done'),
        ]
        pickings = self.search(domain)
        if not pickings:
            return False

        return pickings.mapping_incoming_transfers_with_po()

    def mapping_incoming_transfers_with_po(self):
        for picking in self:
            picking.mapping_incoming_transfer_with_po()
        return True

    def find_po(self):
        self.ensure_one()
        po_domain = [
            ('state', 'not in', ('done', 'cancel', 'draft')),
            ('partner_id', '=', self.partner_id.id),
        ]
        po_s = self.env['purchase.order'].search(po_domain)

        picking_product_dict = {}
        for move_line in self.move_ids_without_package:
            product_id = move_line.product_id.id
            if not picking_product_dict.get(product_id, False):
                picking_product_dict[product_id] = 0
            picking_product_dict[product_id] += move_line.product_uom_qty

        for po in po_s:
            po_product_dict = {}
            for line in po.order_line:
                product_id = line.product_id.id
                if not po_product_dict.get(product_id, False):
                    po_product_dict[product_id] = 0
                po_product_dict[product_id] += line.product_uom_qty

            flag = True
            for product_id in picking_product_dict.keys():
                picking_qty = picking_product_dict.get(product_id, 0)
                po_qty = po_product_dict.get(product_id, 0)

                if product_id not in po_product_dict.keys():
                    flag = False
                    break

                if picking_qty > po_qty:
                    flag = False
                    break

            if not flag:
                continue

            return po

        return False

    def mapping_incoming_transfer_with_po(self):
        self.ensure_one()
        if not self.partner_id:
            self.set_partner_id_by_metrc_shipper_facility_license_number()

        if not self.partner_id:
            return False

        po = self.find_po()
        if not po:
            return False

        write_dict = {}

        for move in self.move_ids_without_package:
            po_line = move.find_po_line(po)
            if not po_line:
                return False

            write_dict[move] = po_line

        for move in write_dict.keys():
            po_line = write_dict[move]
            move.purchase_line_id = po_line.id
        return self.write({'mapped_po': True})
