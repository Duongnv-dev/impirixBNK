import json
import time
import os

from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError
from . import requests_ll
import requests
import tempfile
import base64
from PIL import Image


def set_image_file_local_path(img_id, img_bin):
    file_bin = '/leaflink_image_tmp_{}'.format(img_id)
    file_local_path = tempfile.gettempdir() + file_bin
    with open(file_local_path, 'wb') as img_file:
        img_file.write(base64.b64decode(img_bin))
    return file_local_path


class ProductProduct(models.Model):
    _inherit = 'product.product'

    ll_connect = fields.Boolean('Connected to LeafLink', default=False)

    sku = fields.Char('SKU')
    _sql_constraints = [
        ('sku_uniq', 'unique (sku)', 'SKU must be unique!'),
    ]
    des = fields.Html('Description')
    id_ll = fields.Char('Leaflink product ID', readonly=1)
    _sql_constraints = [
        ('id_ll_uniq', 'unique (id_ll)', 'Leaflink product ID must be unique!'),
    ]
    listing_state = fields.Selection([
        ('available', 'Available'),
        ('archived', 'Archived'),
        ('sample', 'Sample'),
        ('backorder', 'Backorder'),
        ('internal', 'Internal'),
        ('unavailable', 'Unavailable')
    ])
    inventory_management = fields.Selection([
        ('1', 'Managed'),
        ('2', 'Unlimited'),
        ('3', 'Inherited'),
    ])
    parent_id = fields.Many2one('product.product', 'Parent Product')
    product_line_id = fields.Many2one('product.lines', 'Product Line')
    retail_price = fields.Float('Retail Price')
    wholesale_price = fields.Float('Wholesale Price')
    minimum_order = fields.Float('Minimum Order', default=1.00)
    maximum_order = fields.Float('Maximum Order', default=1.00)
    unit_denomination = fields.Selection([
        ('1', "1"), ('2', "1/2"), ('3', "1/4"), ('4', "1/8"), ('5', "3/4"),
        ('6', "2"), ('7', "3 1/2"), ('8', "7"), ('9', "14"), ('10', "6"),
        ('11', "28"), ('12', "5 1/4"), ('13', "4"), ('14', "2 1/2"), ('15', "8"),
        ('16', "3 3/4"), ('17', "1/10"), ('18', "6/5"), ('19', "3/2"), ('20', "2/10"),
        ('21', "1/5"), ('22', "1/3"), ('23', "1/6"), ('24', "3/10"), ('25', "4/10")
    ])
    strain_ids = fields.Many2many('res.strains', 'product_id', 'strain_id', 'product_strain_rel', string='Strains')
    strain_classification = fields.Selection([
        ('sativa', 'Sativa'), ('indica', 'Indica'), ('hybrid', 'Hybrid'), ('na', 'N/A'),
        ('11-cbd', '1:1 CBD'), ('high-cbd', 'High CBD'), ('sativa-hybrid', 'Sativa Hybrid'),
        ('indica-hybrid', 'Indica Hybrid')], string='Strain Classification')
    brand_id = fields.Many2one('res.brands', 'Brand')
    manufacturer = fields.Integer('Manufacturer', default=3823)
    seller = fields.Integer('Seller', default=3823)
    product_image_ids = fields.One2many('product.images', 'product_id', string="Extra Variant Images")
    extern_sts_ids = fields.Char('Metrc IDs')
    leaflink_category_id = fields.Many2one('product.category.leaflink', 'Leaflink Category')
    prod_created_leaflink_log_id = fields.Many2one('leaflink.logs')
    prod_updated_leaflink_log_id = fields.Many2one('leaflink.logs')
    child_prod_created_leaflink_log_id = fields.Many2one('leaflink.logs')
    child_prod_updated_leaflink_log_id = fields.Many2one('leaflink.logs')
    log_note_ll = fields.Text('Sync LeafLink Note')

    def unlink(self):
        for rec in self:
            id_ll = rec.id_ll
            if id_ll:
                url = requests_ll.get_url_ll('products/{}'.format(id_ll))
                requests_ll.requests_ll(method='DELETE', url=url)
        return super(ProductProduct, self).unlink()

    @api.constrains('product_image_ids', 'product_image_ids.image')
    def _constrains_image(self):
        media = self.product_image_ids
        media_f = media[0] if media else None
        self.image_1920 = media_f.image if media_f else None

    @api.constrains('parent_id')
    def _check_m2o_field(self):
        if not self._check_recursion(parent='parent_id'):
            raise ValidationError(
                _('You cannot create recursive relationships.'))

    def get_headers_ll(self):
        api_key = self.env.ref('base.main_company').leaf_link_api_key
        if not api_key:
            raise ValidationError(_("The field 'LeafLink API key' is missing, please check config again"))
        api_key = 'Token {}'.format(api_key)
        return {
            'Authorization': api_key,
        }

    def sync_product_image_to_ll(self):
        headers = self.get_headers_ll()
        images = self.product_image_ids
        if not images:
            return False
        url = requests_ll.get_url_ll('product-images')
        for image in images:
            if image.id_ll:
                continue
            data = {'product': int(self.id_ll or 0), 'position': image.position}
            filepath = set_image_file_local_path(image.id, image.image)
            while 1:
                if os.path.exists(filepath):
                    break
                time.sleep(0.1)
            try:
                Image.open(r'{}'.format(filepath)).save('{}.png'.format(filepath))
            except Exception as e:
                raise ValidationError(_(e))
            with open('{}.png'.format(filepath), 'rb') as f:
                try:
                    resp = requests.post(url=url, headers=headers, files=[('image', f)], data=data)
                    result = json.loads(resp.content)
                    if resp.status_code != 201:
                        raise ValidationError(_('Status code: {}\nDetail: {}'.format(resp.status_code, result)))
                    image.write({'id_ll': str(result.get('id')), 'img_url': result.get('image')})
                except Exception as e:
                    raise ValidationError(_(e))

    def get_uom_leaflink(self):
        uom_odoo = self.uom_id
        uom_ll_name = uom_odoo.name_ll or False
        if uom_ll_name:
            return uom_ll_name
        elif not uom_odoo:
            return False
        elif uom_odoo.name in ('milligram', 'mg', 'Milligram'):
            return 'Milligram'
        elif uom_odoo.name in ('gram', 'g', 'Gram'):
            return 'Gram'
        elif uom_odoo.name in ('kilogram', 'kg', 'Kilogram'):
            return 'Kilogram'
        elif uom_odoo.name in ('ounce', 'oz', 'Ounce'):
            return 'Ounce'
        elif uom_odoo.name in ('pound', 'lp', 'Pound'):
            return 'Pound'
        elif uom_odoo.name in ('unit', 'units', 'Units'):
            return 'Unit'
        return False

    def get_license_id(self):
        cannabis_license_id = self.cannabis_license_id
        if cannabis_license_id:
            license_id = cannabis_license_id.id_ll or False
            if license_id:
                return license_id
            url = requests_ll.get_url_ll('licenses')
            params = {'number': cannabis_license_id.name}
            resp = requests_ll.requests_ll(method='GET', url=url, params=params)
            results = resp.get('results') or ()
            results_f = results[0] if results else {}
            license_id = results_f.get('id')
            cannabis_license_id.write({'id_ll': license_id})
            return license_id
        return False

    def get_data_sync_to_ll(self, method, sub_category, brand_id_ll, product_line_id_ll):
        error = ()
        category = sub_category.parent_id
        if category:
            category_id_ll = category.id_ll or False
            sub_category_id_ll = sub_category.id_ll or False
        else:
            category_id_ll = sub_category.id_ll or False
            sub_category_id_ll = False
        if not category_id_ll:
            error += ('LeafLink category ID', )
        if not brand_id_ll:
            error += ('LeafLink Brand ID', )
        if method == 'POST' and error:
            error_log = '\n\t\t\t'.join(map(str, error))
            raise ValidationError(_('The following fields are missing: \n\t\t\t{}'.format(error_log)))
        values = {
            'category': int(category_id_ll),
            'brand': brand_id_ll,
        }
        if product_line_id_ll:
            values.update({'sub_category': sub_category_id_ll})
        if product_line_id_ll:
            values.update({'product_line': product_line_id_ll})
        license_id = self.get_license_id()
        if license_id:
            values.update({'license': int(license_id)})
        return values

    def get_quantity(self):
        on_hand = 0.0
        cannabis_license_id = self.cannabis_license_id
        if not cannabis_license_id:
            return on_hand
        for item in self.stock_quant_ids:
            location_id = item.location_id
            if not location_id:
                continue
            if location_id.usage != 'internal':
                continue
            analytic_account_id = location_id.analytic_account_id
            if not analytic_account_id:
                continue
            if analytic_account_id.name == cannabis_license_id.name:
                on_hand += item.quantity
        return on_hand

    def get_data_sync_to_leaf_link(self, prod_ll, method):
        name = self.name
        sku = self.sku
        description = self.des
        minimum_order = self.minimum_order
        maximum_order = self.maximum_order
        listing_state = self.listing_state
        inventory_management = self.inventory_management
        unit_of_measure = self.get_uom_leaflink()
        unit_denomination = self.unit_denomination
        category = self.leaflink_category_id
        seller = self.seller
        brand = self.brand_id
        brand_id_ll = brand.id_ll if brand else False
        manufacturer = self.manufacturer
        strain_ids = self.strain_ids
        strain_classification = self.strain_classification
        product_line = self.product_line_id
        product_line_id_ll = product_line.id_ll if product_line else None
        quantity = self.get_quantity()
        error = ()
        if not name:
            error += ('Name',)
        if not sku:
            error += ('SKU',)
        if not description:
            error += ('Description',)
        if not minimum_order:
            error += ('Minimum Order',)
        if not maximum_order:
            error += ('Maximum Order',)
        if not listing_state:
            error += ('Listing State',)
        if not inventory_management:
            error += ('Inventory Management',)
        if not unit_of_measure:
            error += ('Unit Of Measure',)
        if not unit_denomination:
            error += ('Unit Denomination',)
        if not category:
            error += ('Category',)
        if not seller:
            error += ('Seller',)
        if not brand:
            error += ('Brand',)
        if not manufacturer:
            error += ('Manufacturer',)
        if not strain_classification:
            error += ('Strain Classification',)
        if method == 'POST' and error:
            error_log = '\n\t\t\t'.join(map(str, error))
            raise ValidationError(_('The following fields are required: \n\t\t\t{}'.format(error_log)))
        values = self.get_data_sync_to_ll(method, category, brand_id_ll, product_line_id_ll)
        currency_id = self.env.ref('base.main_company').currency_id or False
        currency = currency_id.display_name if currency_id else 'USD'
        values.update({
            'name': name,
            'sku': sku,
            'description': description,
            'quantity': quantity,
            'retail_price': {'amount': self.retail_price, 'currency': currency},
            'wholesale_price': {'amount': self.wholesale_price, 'currency': currency},
            'sale_price': {'amount': self.lst_price, 'currency': currency},
            'minimum_order': minimum_order,
            'maximum_order': maximum_order,
            'listing_state': listing_state.title(),
            'inventory_management': inventory_management,
            'unit_denomination': int(unit_denomination),
            'unit_of_measure': unit_of_measure,
            'seller': seller,
            'manufacturer': manufacturer,
            'strains': strain_ids.mapped('id_ll'),
            'strain_classification': strain_classification,
        })
        return values

    def sync_to_leaf_link(self):
        method = 'POST'
        url = requests_ll.get_url_ll('products')
        id_ll = self.id_ll
        sku = self.sku
        name = self.name
        params = False
        if id_ll:
            method = 'PATCH'
            url = '{}{}/'.format(url, id_ll)
        elif sku:
            params = {'sku': sku, 'limit': 1}
        elif name:
            params = {'name': name, 'limit': 1}
        prod_ll = requests_ll.requests_ll(method='GET', url=url, params=params) if params else {}
        if 'results' in prod_ll.keys():
            results = prod_ll['results'] or False
            prod_ll = results[0] if results else False
        if prod_ll:
            method = 'PATCH'
        data = json.dumps(self.get_data_sync_to_leaf_link(prod_ll, method))
        resp = requests_ll.requests_ll(method=method, url=url, data=data)
        self.write({'id_ll': str(resp.get('id') or '')})
        self.sync_product_image_to_ll()


class ProductImages(models.Model):
    _name = 'product.images'

    id_ll = fields.Char('LeafLink image ID', readonly=1)
    name = fields.Char('Name', required=1)
    img_url = fields.Char('Image URL')
    product_id = fields.Many2one('product.product', required=1)
    _sql_constraints = [
        ('id_ll_uniq', 'unique (id_ll)', 'LeafLink ID must be unique!'),
    ]
    image = fields.Binary('Image', required=1)

    def default_position(self):
        context = self._context
        prod_id = context.get('default_product_id')
        if prod_id:
            position_list = self.search([('product_id', '=', prod_id)]).mapped('position')
            if position_list:
                return max(position_list) + 1
            return 1
        return 1

    position = fields.Integer('Position', required=1, default=default_position)

    @api.constrains('position', 'product_id')
    def constrain_product_position(self):
        for rec in self:
            query = 'SELECT count(id) FROM product_images WHERE position={} AND product_id={}'.format(rec.position, rec.product_id.id)
            self.env.cr.execute(query)
            if self.env.cr.fetchall()[0][0] > 1:
                raise ValidationError(_("Image's position already exists, please check and try again"))

    def unlink(self):
        for rec in self:
            id_ll = rec.id_ll
            if id_ll:
                try:
                    requests_ll.requests_ll(method='DELETE', url=requests_ll.get_url_ll('product-images/{}'.format(id_ll)))
                except:
                    pass
        return super(ProductImages, self).unlink()


class UoM(models.Model):
    _inherit = 'uom.uom'

    name_ll = fields.Char('LafLink UOM')
