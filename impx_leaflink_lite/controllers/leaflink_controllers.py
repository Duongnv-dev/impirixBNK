from datetime import datetime
from odoo import http
from odoo.http import request
import json


class LeafLinkControllers(http.Controller):
    @http.route('/sync/product_and_order', type='json', auth='public', website=True, csrf=False)
    def sync_product_or_order(self):
        data_request = http.request.jsonrequest
        _action = data_request.get('action')
        _data = data_request.get('data')
        _type = data_request.get('type')
        if not _action or not _data or not _type:
            return json.dumps({'result': False})
        if _type == 'product':
            sync_products = request.env['sync.products'].sudo()
            sync_products.sync_products_to_odoo(data_webhook=_data)
            return json.dumps({'result': True})
        elif _type == 'order':
            sync_sale_order = request.env['sync.sale.orders'].sudo()
            sync_sale_order.sync_sale_orders_to_odoo(data_webhook=_data)
            return json.dumps({'result': True})
        return json.dumps({'result': False})

