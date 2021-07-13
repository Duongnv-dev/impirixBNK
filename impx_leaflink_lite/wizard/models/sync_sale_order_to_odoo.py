import requests
import json
from odoo import fields, api, models, _
from datetime import datetime
from pytz import timezone
from odoo.exceptions import ValidationError
from . import requests_ll
import logging
import pytz
import iso8601


_logger = logging.getLogger(__name__)


class SynSaleOrders(models.TransientModel):
    _name = 'sync.sale.orders'
    created_on_gte = fields.Date(help='Filter by the created_on date, greater than or equal to', default=None)
    created_on_lte = fields.Date(help='Filter by the created_on date, less than or equal to', default=None)
    not_sandbox = fields.Boolean('Not Sandbox')

    def action_sale_order(self, order, status):
        if not order:
            return
        state = order.state or ''
        if status in ('Fulfilled', 'Shipped', 'Complete', 'Backorder', 'Accepted') and state != 'sale':
            action = order.action_draft() if state == 'cancel' else None
            order.action_confirm()
        elif status in ('Rejected', 'Cancelled') and state != 'cancel':
            order.action_cancel()
        elif status == 'Draft' and state != 'draft':
            action = order.action_cancel() if state in ('sale', 'sent') else None
            order.action_draft()

    def convert_datetime_to_utc0(self, datetime_ll):
        try:
            resp = iso8601.parse_date(datetime_ll).astimezone(pytz.utc)
            return datetime.strptime(datetime.strftime(resp, '%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S')
        except:
            return False

    def create_customer_ll(self, customer):
        customer_id_ll = customer.get('id')
        api_key = self.env.ref('base.main_company').leaf_link_api_key
        if not api_key:
            raise ValidationError(_("The field 'LeafLink API key' is missing, please check config again"))
        api_key = 'Token {}'.format(api_key)
        headers = {'Authorization': api_key}
        url = requests_ll.get_url_ll('customers/{}/'.format(customer_id_ll))
        try:
            resp = requests.get(url=url, headers=headers)
            customer_ll = json.loads(resp.content)
            values = {
                'name': customer_ll.get('name') or 'Unknown',
                'regulatory_license': customer_ll.get('license_number'),
                'leaf_link_customer_id': customer_id_ll,
                'email': customer_ll.get('email'),
                'website': customer_ll.get('website') or '',
                'phone': customer_ll.get('phone'),
                'mobile': customer_ll.get('phone'),
            }
        except:
            values = {'name': customer.get('display_name') or 'Unknown'}
        return self.env['res.partner'].sudo().create(values)

    def sync_shipping_charge(self, order, shipping_charge_ll):
        sale_order_lines = self.env['sale.order.line'].sudo()
        amount = shipping_charge_ll if self._context.get('from_webhook') else shipping_charge_ll.get('amount') or False
        shipping_charge_id = self.env.ref('impx_can_general.shipping_charge_from_leaflink').id
        shipping_charge_in_ol = sale_order_lines.search(
            [('product_id', '=', shipping_charge_id), ('order_id', '=', order.id)], limit=1)
        if shipping_charge_in_ol and not amount:
            shipping_charge_in_ol.write({'product_uom_qty': 0})
        elif shipping_charge_in_ol and amount:
            shipping_charge_in_ol.write({'price_unit': amount})
        elif not shipping_charge_in_ol and amount:
            sale_order_lines.create({
                'product_id': shipping_charge_id,
                'price_unit': amount,
                'order_id': order.id,
                'product_uom_qty': 1
            })

    def get_value_sale_order_lines_webhook_ll(self, sale_order_line_ll):
        values = {}
        product_ll = sale_order_line_ll.get('product')
        product_sku_ll = product_ll.get('sku')
        if not product_sku_ll:
            return values
        product_id = self.env['product.template'].sudo().search([('sku', '=', product_sku_ll)], limit=1)
        if not product_id:
            return values
        values.update({'product_id': product_id.id})
        values.update({'name': product_id.display_name or product_id.name})
        try:
            product_uom_qty = float(sale_order_line_ll.get('quantity'))
            values.update({'product_uom_qty': product_uom_qty})
            price_unit = float(sale_order_line_ll.get('sale_price'))
            values.update({'price_unit': price_unit})
        except:
            pass
        return values

    def sync_sale_order_lines_webhook_ll(self, data_webhook, order_id):
        sale_order_lines_ll = data_webhook.get('orderedproduct_set')
        if not sale_order_lines_ll:
            return
        sale_order_lines = self.env['sale.order.line'].sudo()
        values = []
        for sale_order_line_ll in sale_order_lines_ll:
            order_line = sale_order_lines.search([('id_ll', '=', sale_order_line_ll.get('id'))], limit=1)
            val = self.get_value_sale_order_lines_webhook_ll(sale_order_line_ll)
            if not val:
                continue
            val.update({'order_id': order_id})
            if order_line:
                order_line.write(val)
                continue
            val.update({'id_ll': sale_order_line_ll.get('id')})
            values.append(val)
        if values:
            sale_order_lines.create(values)

    def sync_sale_order_webhook_ll(self, sale_orders, data_webhook):
        order_number_ll = data_webhook.get('ll_number')
        order = sale_orders.search([('ll_number', '=', order_number_ll)], limit=1)
        val = self.get_order_values(data_webhook)
        if not val:
            return False
        if order:
            order.write(val)
            return order
        val.update({'ll_number': order_number_ll})
        order = sale_orders.create(val)
        return order

    def sync_orders_to_odoo_webhook(self, data_webhook):
        if data_webhook:
            sale_orders = self.env['sale.order'].sudo()
            sale_order_webhook = self.sync_sale_order_webhook_ll(sale_orders, data_webhook)
            if sale_order_webhook:
                self.sync_sale_order_lines_webhook_ll(data_webhook, sale_order_webhook.id)
                return

    def get_line_item_values(self, order, order_line, order_line_ll):
        context = self._context
        values = {}
        product_id_ll = order_line_ll.get('product')
        if context.get('from_webhook'):
            sale_price = order_line_ll.get('sale_price')
            sale_price = float(sale_price) if sale_price else False
            ordered_unit_price = order_line_ll.get('ordered_unit_price')
            ordered_unit_price = float(ordered_unit_price) if ordered_unit_price else False
            price_unit = sale_price or ordered_unit_price or 0.0
            domain = [('sku', '=', product_id_ll.get('sku'))]
        else:
            sale_price = order_line_ll.get('sale_price') or {}
            ordered_unit_price = order_line_ll.get('ordered_unit_price') or {}
            price_unit = sale_price.get('amount') or ordered_unit_price.get('amount') or 0.0
            domain = [('id_ll', '=', product_id_ll)]
        product_id = self.env['product.product'].sudo().search(domain, limit=1)
        if not product_id:
            return values
        if product_id.cannabis_license_id:
            analytic_account_id = self.env['account.analytic.account'].sudo().search(
                [('cannabis_license_id', '=', product_id.cannabis_license_id.id)])
            if order.analytic_account_id != analytic_account_id:
                order.write({'analytic_account_id': analytic_account_id})
        try:
            product_uom_qty = float(order_line_ll.get('quantity'))
        except:
            product_uom_qty = 0.0
        if order_line:
            if price_unit != order_line.price_unit:
                values['price_unit'] = price_unit
            if order != order_line.order_id:
                values['order_id'] = order.id
            if product_uom_qty != order_line.product_uom_qty:
                values['product_uom_qty'] = product_uom_qty
            return values
        return {
            'id_ll': order_line_ll.get('id'),
            'name': product_id.display_name or product_id.name or 'Unknown',
            'product_id': product_id.id,
            'product_uom_qty': product_uom_qty,
            'price_unit': price_unit,
            'order_id': order.id,
        }

    def sync_line_item_to_odoo(self, order, line_item):
        if not line_item:
            return
        orders_line = self.env['sale.order.line'].sudo()
        vals = ()
        for item in line_item:
            order_line = orders_line.search([('id_ll', '=', item.get('id'))], limit=1)
            val = self.get_line_item_values(order, order_line, item)
            if not val:
                continue
            if order_line:
                order_line.write(val)
                continue
            vals += (val, )
        if vals:
            orders_line.create(vals)

    def get_order_values(self, order, order_ll):
        values = {}
        customer_ll = order_ll.get('customer') or False
        customer_id_ll = customer_ll.get('id') if customer_ll else False
        domain = [('leaf_link_customer_id', '=', customer_id_ll)] if customer_id_ll else False
        partner_id = self.env['res.partner'].sudo().search(domain, limit=1) if domain else False
        partner_id = partner_id or self.create_customer_ll(customer_ll or {})
        ll_create_date = self.convert_datetime_to_utc0(order_ll.get('created_on'))
        status = order_ll.get('status') or 'Draft'
        if order:
            if status:
                if status.lower() != order.ll_status:
                    values.update({'ll_status': status.lower()})
            if partner_id != order.partner_id:
                values.update({'partner_id': partner_id.id})
            if order_ll.get('short_id') != order.external_id:
                values.update({'external_id': order_ll.get('short_id')})
            if ll_create_date != order.ll_create_date:
                values.update({'ll_create_date': ll_create_date})
            return values
        return {
            'partner_id': partner_id.id,
            'external_id': order_ll.get('short_id'),
            'date_order': datetime.now(),
            'll_create_date': ll_create_date,
            'll_status': status.lower() if status else 'draft',
        }

    def sync_orders_to_odoo(self, orders_received, line_items):
        orders_created_tuple, orders_updated_tuple = (), ()
        if not orders_received:
            return orders_created_tuple, orders_updated_tuple
        self = self.with_context(is_from_leaflink=True)
        orders = self.env['sale.order'].sudo()
        for order_ll in orders_received:
            number = order_ll.get('number')
            order = orders.search([('ll_number', '=', number)], limit=1) if number else None
            val = self.get_order_values(order, order_ll)
            if order:
                order.write(val)
                orders_updated_tuple += order._ids
            else:
                val.update({'ll_number': number})
                order = orders.create(val)
                orders_created_tuple += order._ids
            self.sync_line_item_to_odoo(order, line_items.get(number))
            order.set_warehouse_for_sale_delivery()
            shipping_charge_ll = order_ll.get('shipping_charge')
            if shipping_charge_ll:
                self.sync_shipping_charge(order, shipping_charge_ll)
            self.action_sale_order(order, order_ll.get('status'))
        return orders_created_tuple, orders_updated_tuple

    def get_order_lines_from_ll(self, created_on):
        params = {}
        created_on_gte = created_on['created_on_gte']
        created_on_lte = created_on['created_on_lte']
        if created_on_gte:
            order__created_on__gte = '{}-{}-{}'.format(created_on_gte.year, created_on_gte.month, created_on_gte.day)
            params.update({'order__created_on__gte': order__created_on__gte})
        if created_on_lte:
            order__created_on__lte = '{}-{}-{}'.format(created_on_lte.year, created_on_lte.month, created_on_lte.day)
            params.update({'order__created_on__lte': order__created_on__lte})
        url = 'https://www.leaflink.com/api/v2/line-items/' if self.not_sandbox else requests_ll.get_url_ll('line-items')
        items_ll = requests_ll.get_all_data_from_ll(url=url, params=params)
        orders_line_dict = {}
        for item in items_ll:
            order_number = item.get('order')
            if order_number in orders_line_dict.keys():
                order_list = orders_line_dict.get(order_number) + (item,)
                orders_line_dict.update({order_number: order_list})
            else:
                orders_line_dict.update({order_number: (item,)})
        return orders_line_dict

    def get_orders_from_ll(self, created_on):
        params = {}
        created_on_gte = created_on['created_on_gte']
        created_on_lte = created_on['created_on_lte']
        if created_on_gte:
            created_on__gte = '{}-{}-{}T{}:{}:{}'.format(
                created_on_gte.year, created_on_gte.month, created_on_gte.day,
                created_on_gte.hour, created_on_gte.minute, created_on_gte.second)
            params.update({'created_on__gte': created_on__gte})
        if created_on_lte:
            created_on__lte = '{}-{}-{}T{}:{}:{}'.format(
                created_on_lte.year, created_on_lte.month, created_on_lte.day,
                created_on_lte.hour, created_on_lte.minute, created_on_lte.second)
            params.update({'created_on__lte': created_on__lte})
        url = 'https://www.leaflink.com/api/v2/orders-received/' if self.not_sandbox else requests_ll.get_url_ll(
            'orders-received')
        result = requests_ll.get_all_data_from_ll(url=url, params=params)
        return result

    def convert_date_to_datetime(self, date, max=False):
        if not date:
            return False
        if max:
            return datetime.combine(date, datetime.max.time())
        return datetime.combine(date, datetime.min.time())

    def get_create_on_for_filter(self):
        tz_current = self._context.get('tz')
        created_on_gte_datetime = self.convert_date_to_datetime(self.created_on_gte)
        created_on_lte_datetime = self.convert_date_to_datetime(self.created_on_lte, max=True)

        if created_on_gte_datetime:
            created_on_gte = created_on_gte_datetime.astimezone(timezone(tz_current))
        else:
            created_on_gte = False

        if created_on_lte_datetime:
            created_on_lte = created_on_lte_datetime.astimezone(timezone(tz_current))
        else:
            created_on_lte = False

        result = {'created_on_gte': created_on_gte, 'created_on_lte': created_on_lte}
        return result

    def sync_sale_orders_to_odoo(self, data_webhook=False):
        start = datetime.now()
        vals = {
            'name': 'Sync orders from LeafLink to Odoo',
            'type': 'orders',
            'status': 'webhook' if data_webhook else 'leaflink',
        }
        try:
            if data_webhook:
                self = self.with_context(from_webhook=True)
                orders_received = (data_webhook, )
                line_items = {data_webhook.get('number'): data_webhook.get('orderedproduct_set')}
            else:
                created_on = self.get_create_on_for_filter()
                orders_received = self.get_orders_from_ll(created_on)
                line_items = self.get_order_lines_from_ll(created_on)
            orders_created_tuple, orders_updated_tuple = self.sync_orders_to_odoo(orders_received, line_items)
            vals.update({
                'state': 'success',
                'order_ids_created': [(6, 0, orders_created_tuple)],
                'order_ids_updated': [(6, 0, orders_updated_tuple)],
                'duration': '{}'.format(datetime.now() - start),
            })
        except Exception as e:
            vals.update({
                'state': 'fail',
                'note': '{}'.format(e),
                'duration': '{}'.format(datetime.now() - start)
            })
        finally:
            log_current = self.env['leaflink.logs'].sudo().create(vals)
            if self._context.get('from_webhook'):
                return
            return {
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'leaflink.logs',
                'res_id': log_current.id,
                'view_id': self.env.ref('impx_leaflink_lite.leaflink_logs_view_form').id,
                'target': 'current',
            }

