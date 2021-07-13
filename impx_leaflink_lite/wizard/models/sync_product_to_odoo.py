import requests
from odoo import fields, api, models, _
from odoo.exceptions import ValidationError
import html2text
from . import requests_ll
import base64
from datetime import datetime

NO_UPDATE_LIST = ('uom_id',)


class SyncProductLines(models.TransientModel):
    _name = 'sync.product.lines'

    def get_value(self, product_line_ll):
        values = {'name': product_line_ll.get('name') or 'Unknown'}
        brand = product_line_ll.get('brand')
        if brand:
            brand_id = self.env['res.brands'].sudo().search([('id_ll', '=', brand)], limit=1)
            if not brand_id:
                return {}
            values.update({'brand_id': brand_id.id} if brand_id else {})
        return values

    def sync_product_line_ll(self, product_lines, url):
        product_lines_ll = requests_ll.get_all_data_from_ll(url=url, params={})
        if not product_lines_ll:
            return
        values = []
        for product_line_ll in product_lines_ll:
            product_line = product_lines.search([('id_ll', '=', product_line_ll.get('id'))], limit=1)
            val = self.get_value(product_line_ll)
            if product_line:
                product_line.write(val)
                continue
            val.update({'id_ll': product_line_ll.get('id')})
            values.append(val)
        if values:
            product_lines.create(values)

    def sync_product_lines_to_odoo(self):
        product_lines = self.env['product.lines'].sudo()
        url = requests_ll.get_url_ll('product-lines')
        self.sync_product_line_ll(product_lines, url)
        if self._context.get('cron_job'):
            return
        # return {
        #     'name': 'Sync products',
        #     'type': 'ir.actions.act_window',
        #     'view_mode': 'tree',
        #     'res_model': 'product.product',
        #     'view_id': self.env.ref('product.product_product_tree_view').id,
        #     'target': 'current',
        # }


class SyncProductCategory(models.TransientModel):
    _name = 'sync.product.categories'

    def sync_parent_category(self, product_category_id):
        product_category = self.env['product.category.leaflink'].sudo()
        if not product_category_id:
            return False
        url = requests_ll.get_url_ll('product-categories/{}'.format(product_category_id))
        product_category_ll = requests_ll.requests_ll(method='GET', url=url)
        if not product_category_ll:
            return False
        category = product_category.search(
            [('id_ll', '=', product_category_ll.get('id')), ('parent_id', '=', None)], limit=1)
        if category:
            category.write({
                'name': product_category_ll.get('name')
            })
        else:
            category = product_category.create({
                'id_ll': product_category_ll.get('id'),
                'name': product_category_ll.get('name')
            })
        return category

    def sync_product_categories_to_odoo(self):
        product_category = self.env['product.category.leaflink'].sudo()
        url = requests_ll.get_url_ll('product-subcategories')
        product_subcategories_ll = requests_ll.get_all_data_from_ll(url=url, params={})
        if not product_subcategories_ll:
            return
        values = []
        for product_subcategory_ll in product_subcategories_ll:
            parent_category = self.sync_parent_category(product_subcategory_ll.get('category'))
            subcategory = product_category.search(
                [('id_ll', '=', product_subcategory_ll.get('id')), ('parent_id', '!=', None)], limit=1)
            val = {'name': product_subcategory_ll.get('name')}
            if parent_category:
                val.update({'parent_id': parent_category.id})
            if subcategory:
                subcategory.write(val)
                continue
            val.update({'id_ll': product_subcategory_ll.get('id')})
            values.append(val)
        if values:
            product_category.create(values)
        if self._context.get('cron_job'):
            return
        return
        return {
            'name': 'Sync product categories',
            'type': 'ir.actions.act_window',
            'view_mode': 'tree',
            'res_model': 'product.category.leaflink',
            'view_id': self.env.ref('product.product_category_list_view').id,
            'target': 'current',
        }


class SyncProductProduct(models.TransientModel):
    _name = 'sync.products'

    uom_ll_dict = {
        'milligram': ('milligram', 'mg', 'Milligram'),
        'gram': ('gram', 'g', 'Gram'),
        'kilogram': ('kilogram', 'kg', 'Kilogram'),
        'ounce': ('ounce', 'oz', 'Ounce'),
        'pound': ('pound', 'lp', 'Pound'),
        'unit': ('unit', 'units', 'Units')
    }

    def get_uom_id(self, uom_ll, uom_odoo_dict):
        uom = self.env['uom.uom'].sudo().search([('name_ll', '=', uom_ll)], limit=1)
        if uom:
            return uom.id
        uom_ll = str(uom_ll).lower() if uom_ll else False
        uom_list = self.uom_ll_dict.get(uom_ll) or ()
        for item in uom_list:
            uom_id = uom_odoo_dict.get(item)
            if uom_id:
                return uom_id
        return False

    def get_uom_odoo_convert_to_dict(self):
        uom_uom = self.env['uom.uom'].sudo().search_read([], ['name'])
        return {item.get('name'): item.get('id') for item in uom_uom}

    def get_value(self, parent, product, product_ll, uom_odoo_dict):
        values = {}
        ll_connect = True
        id_ll = product_ll.get('id')
        product_type = 'product'
        name = product_ll.get('name') or product_ll.get('display_name') or 'Unknown'
        description = product_ll.get('description') or ''
        retail_price = product_ll.get('retail_price')
        wholesale_price = product_ll.get('price_schedule_price')
        sale_price = product_ll.get('sale_price')
        minimum_order = float(product_ll.get('minimum_order') or '0')
        maximum_order = float(product_ll.get('maximum_order') or '0')
        listing_state = product_ll.get('listing_state')
        inventory_management = str(product_ll.get('inventory_management') or '')
        unit_of_measure = product_ll.get('unit_of_measure') or False
        uom_id = self.get_uom_id(unit_of_measure, uom_odoo_dict) if unit_of_measure else False
        if not uom_id:
            return values
        unit_denomination = product_ll.get('unit_denomination')
        unit_denomination_id = unit_denomination.get('id')
        subcateg_ll, categ_ll = product_ll.get('sub_category'), product_ll.get('category')
        categ_domain = [('id_ll', '=', subcateg_ll), ('parent_id', '!=', False)] \
            if subcateg_ll else [('id_ll', '=', categ_ll), ('parent_id', '=', None)]
        categ = self.env['product.category.leaflink'].sudo().search(categ_domain)
        seller = product_ll.get('seller')
        brand = product_ll.get('brand')
        brand_id = self.env['res.brands'].sudo().search([('id_ll', '=', str(brand or ''))], limit=1)
        manufacturer = product_ll.get('manufacturer')
        strains = product_ll.get('strains') or []
        strain_ids = self.env['res.strains'].sudo().search([('id_ll', 'in', [str(item) for item in strains])])
        strain_classification = product_ll.get('strain_classification') or 'na'
        sku = product_ll.get('sku')
        product_line_ll = product_ll.get('product_line')
        extern_sts_ids = ', '.join(map(str, product_ll.get('extern_sts_ids') or ''))
        license = product_ll.get('license') or False
        license_number = license.get('number') if license else False
        cannabis_license = self.env['cannabis.license'].sudo().search(
            [('name', '=', license_number)], limit=1) if license_number else None
        # cannabis_license = parent.cannabis_license_id if parent else None
        cannabis_license_id = cannabis_license.id if cannabis_license else None
        if product_line_ll:
            product_line_id = self.env['product.lines'].search([('id_ll', '=', product_line_ll)], limit=1)
            if product_line_id:
                values.update({'product_line_id': product_line_id.id})
        if product:
            values = {}
            if product.id_ll != str(id_ll or ''):
                values['id_ll'] = id_ll
            if product.ll_connect != ll_connect:
                values['ll_connect'] = ll_connect
            if product.type != product_type:
                values['type'] = product_type
            if product.name != name:
                values['name'] = name
            if html2text.html2text(product.des) != html2text.html2text(description):
                values['des'] = description
            retail_price_amount = retail_price.get('amount')
            if product.retail_price != retail_price_amount:
                values['retail_price'] = retail_price_amount
            wholesale_price_amount = wholesale_price.get('amount')
            if product.wholesale_price != wholesale_price_amount:
                values['wholesale_price'] = wholesale_price_amount
            sale_price_amount = sale_price.get('amount')
            if product.lst_price != sale_price_amount:
                values['lst_price'] = sale_price_amount
            if product.minimum_order != minimum_order:
                values['minimum_order'] = minimum_order
            if product.maximum_order != maximum_order:
                values['maximum_order'] = maximum_order
            listing_state = listing_state.lower()
            if product.listing_state != listing_state:
                values['listing_state'] = listing_state
            if product.inventory_management != inventory_management:
                values['inventory_management'] = inventory_management
            unit_denomination_id = str(unit_denomination_id)
            if product.unit_denomination != unit_denomination_id:
                values['unit_denomination'] = unit_denomination_id
            if product.leaflink_category_id != categ:
                values['leaflink_category_id'] = categ.id
            if product.seller != seller:
                values['seller'] = seller
            if product.brand_id != brand_id:
                values['brand_id'] = brand_id.id
            if product.strain_ids != strain_ids:
                values['strain_ids'] = [(6, 0, strain_ids._ids)]
            if product.strain_classification != strain_classification:
                values['strain_classification'] = strain_classification
            if product.sku != sku:
                values['sku'] = sku
            if product.manufacturer != manufacturer:
                values['manufacturer'] = manufacturer
            if cannabis_license != (product.cannabis_license_id or None):
                values['cannabis_license_id'] = cannabis_license_id
            if extern_sts_ids != product.extern_sts_ids:
                values['extern_sts_ids'] = extern_sts_ids
            if parent and parent != product.parent_id:
                values['parent_id'] = parent.id
            # uom_val = {'uom_po_id': uom_id, 'uom_id': uom_id} if product.uom_id.id != uom_id else {}
            # if uom_val:
            #     product.product_tmpl_id.write(uom_val)
            return values
        return {
            'id_ll': id_ll,
            'll_connect': ll_connect,
            'type': product_type,
            'name': name,
            'des': description,
            'retail_price': retail_price.get('amount') or 0.0,
            'wholesale_price': wholesale_price.get('amount') or 0.0,
            'lst_price': sale_price.get('amount') or 0.0,
            'minimum_order': minimum_order,
            'maximum_order': maximum_order,
            'listing_state': listing_state.lower(),
            'inventory_management': inventory_management,
            'uom_id': uom_id,
            'uom_po_id': uom_id,
            'unit_denomination': str(unit_denomination_id),
            'leaflink_category_id': categ.id,
            'seller': seller,
            'brand_id': brand_id.id,
            'strain_ids': [(6, 0, strain_ids._ids)],
            'strain_classification': strain_classification,
            'sku': sku,
            'manufacturer': manufacturer,
            'parent_id': parent.id if parent else None,
            'cannabis_license_id': cannabis_license_id,
            'extern_sts_ids': extern_sts_ids
        }

    def sync_child_products_ll(self, parent, product_product, child_products_list, uom_odoo_dict):
        child_prod_created_tuple, child_prod_updated_tuple = (), ()
        if not parent or not child_products_list:
            return child_prod_created_tuple, child_prod_updated_tuple
        values = ()
        for item in child_products_list:
            id_ll = item.get('id') or ''
            sku_ll = item.get('sku') or ''
            if id_ll or sku_ll:
                domain = ['|', ('id_ll', '=', str(id_ll)), ('sku', '=', str(sku_ll))]
            else:
                domain = [('name', '=', str(item.get('name'), ''))]
            domain.append(('parent_id', '!=', False))
            product = product_product.search(domain, limit=1)
            val = self.get_value(parent, product, item, uom_odoo_dict)
            if val.get('uom_po_id') != val.get('uom_id'):
                raise
            if not val:
                continue
            val['log_note_ll'] = '{}'.format(val)
            if product:
                product.write(val)
                child_prod_updated_tuple += product._ids
                continue
            values += (val,)
        if values:
            products = product_product.create(values)
            child_prod_created_tuple += products._ids
        return child_prod_created_tuple, child_prod_updated_tuple

    def get_parent_product_values(self, product, parent_product_ll):
        license = parent_product_ll.get('license') or False
        license_number = license.get('number') if license else False
        cannabis_license = self.env['cannabis.license'].sudo().search(
            [('name', '=', license_number)], limit=1) if license_number else None
        name = parent_product_ll.get('name') or parent_product_ll.get('display_name') or 'Unknown'
        if not product:
            return {
                'name': name,
                'll_connect': True,
                'id_ll': parent_product_ll.get('id'),
                'cannabis_license_id': cannabis_license.id if cannabis_license else None
            }
        values = {}
        if product.name != name:
            values.update({'name': name})
        if product.cannabis_license_id != cannabis_license:
            values.update({'cannabis_license_id': cannabis_license.id if cannabis_license else None})
        if not product.ll_connect:
            values.update({'ll_connect': True})
        return values

    def sync_parent_products_ll(self, product_product, url, child_products_ll):
        uom_odoo_dict = self.get_uom_odoo_convert_to_dict()
        params = {'parent__isnull': True}
        parent_products_ll = requests_ll.get_all_data_from_ll(url=url, params=params)
        child_prod_created_tuple, child_prod_updated_tuple = (), ()
        prod_created_tuple, prod_updated_tuple = (), ()
        if not parent_products_ll:
            return child_prod_created_tuple, child_prod_updated_tuple
        for parent_product_ll in parent_products_ll:
            id_ll = parent_product_ll.get('id') or ''
            sku_ll = parent_product_ll.get('sku') or ''
            if id_ll or sku_ll:
                domain = ['|', ('id_ll', '=', str(id_ll)), ('sku', '=', str(sku_ll))]
            else:
                domain = [('name', '=', str(parent_product_ll.get('name'), ''))]
            domain.append(('parent_id', '=', None))
            product = product_product.search(domain, limit=1)
            # val = self.get_parent_product_values(product, parent_product_ll)
            val = self.get_value(None, product, parent_product_ll, uom_odoo_dict)
            if val.get('uom_po_id') != val.get('uom_id'):
                raise
            if not val:
                continue
            val['log_note_ll'] = '{}'.format(val)
            if product:
                product.write(val)
                prod_updated_tuple += product._ids
            else:
                product = product_product.create(val)
                prod_created_tuple += product._ids
            child_product_ll = child_products_ll.get(id_ll)
            child_prods_created, child_prods_updated = self.sync_child_products_ll(product, product_product, child_product_ll, uom_odoo_dict)
            child_prod_created_tuple += child_prods_created
            child_prod_updated_tuple += child_prods_updated
        return {
            'prod_created_tuple': prod_created_tuple,
            'prod_updated_tuple': prod_updated_tuple,
            'child_prod_created_tuple': child_prod_created_tuple,
            'child_prod_updated_tuple': child_prod_updated_tuple,
        }

    def sync_product_webhook_ll(self, product_product, data_webhook):
        uom_odoo_dict = self.get_uom_odoo_convert_to_dict()
        product_ll_id = data_webhook.get('id')
        product = product_product.search([('id_ll', '=', product_ll_id)], limit=1)
        val = self.get_value(None, product, data_webhook, uom_odoo_dict)
        result = {}
        if product:
            product.write(val)
            if product.parent_id:
                result['child_prod_updated_tuple'] = (product.id, )
            else:
                result['prod_updated_tuple'] = (product.id,)
        else:
            val.update({'id_ll': product_ll_id})
            product = product_product.create(val)
            if product.parent_id:
                result['child_prod_created_tuple'] = (product.id, )
            else:
                result['prod_created_tuple'] = (product.id,)
        return result

    def get_child_products_ll(self, url):
        params = {'parent__isnull': False}
        child_products_ll = requests_ll.get_all_data_from_ll(url=url, params=params)
        if not child_products_ll:
            return False
        child_products_dict = {}
        for item in child_products_ll:
            parent = item.get('parent') or {}
            parent_id = parent.get('id') or False
            if not parent_id:
                continue
            if parent_id in child_products_dict.keys():
                child_product_list = child_products_dict.get(parent_id) + (item,)
                child_products_dict.update({parent_id: child_product_list})
                continue
            child_products_dict.update({parent_id: (item,)})
        return child_products_dict

    def sync_products_to_odoo(self, **kw):
        start = datetime.now()
        data_webhook = kw.get('data_webhook')
        product_product = self.env['product.product'].sudo()
        vals = {
            'name': 'Sync products from LeafLink to Odoo',
            'type': 'products',
            'status': 'webhook' if data_webhook else 'leaflink'
        }
        try:
            if data_webhook:
                prods_tuple = self.sync_product_webhook_ll(product_product, data_webhook)
            else:
                url = requests_ll.get_url_ll('products')
                child_products_ll = self.get_child_products_ll(url)
                prods_tuple = self.sync_parent_products_ll(product_product, url, child_products_ll)
            vals.update({
                'state': 'success',
                'product_ids_created': [(6, 0, prods_tuple.get('prod_created_tuple'))],
                'product_ids_updated': [(6, 0, prods_tuple.get('prod_updated_tuple'))],
                'child_prods_ids_created': [(6, 0, prods_tuple.get('child_prod_created_tuple'))],
                'child_prods_ids_updated': [(6, 0, prods_tuple.get('child_prod_updated_tuple'))],
                'duration': '{}'.format(datetime.now() - start),
            })
        except Exception as e:
            vals.update({'state': 'fail', 'note': '{}'.format(e), 'duration': '{}'.format(datetime.now() - start)})
        finally:
            log_current = self.env['leaflink.logs'].sudo().create(vals)
            return {
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'leaflink.logs',
                'res_id': log_current.id,
                'view_id': self.env.ref('impx_leaflink_lite.leaflink_logs_view_form').id,
                'target': 'current',
            }


class SyncProductImages(models.TransientModel):
    _name = 'sync.product.images'

    def download_image_from_ll(self, url):
        try:
            resp = requests.get(url.strip())
            if resp.status_code == 200:
                return base64.b64encode(resp.content)
            raise ValidationError(_('Status code: {}\nError: {}'.format(resp.status_code, resp.content)))
        except Exception as error:
            raise ValidationError(_(error))

    def get_val_from_ll(self, product_image_ll, product_product):
        img_url = product_image_ll.get('image')
        position = product_image_ll.get('position')
        product_id_ll = product_image_ll.get('product')
        product = product_product.search([('id_ll', '=', product_id_ll)], limit=1)
        if img_url and product:
            image = self.download_image_from_ll(img_url)
            if position == 1 and not product.image_1920:
                product.write({'image_1920': image})
            return {
                'name': '{}/{}'.format(product.name, position),
                'position': position,
                'product_id': product.id,
                'img_url': img_url,
                'image': image,
            }
        return False

    def sync_product_images_ll(self, product_images, url):
        product_images_ll = requests_ll.get_all_data_from_ll(url=url, params={})
        if not product_images_ll:
            return
        product_product = self.env['product.product'].sudo()
        values = []
        for product_image_ll in product_images_ll:
            product_image_ll_id = str(product_image_ll.get('id') or '')
            product_image = product_images.search([('id_ll', '=', product_image_ll_id)], limit=1)
            val = self.get_val_from_ll(product_image_ll, product_product)
            if not val:
                continue
            if product_image:
                product_image.write(val)
                continue
            val.update({'id_ll': product_image_ll_id})
            values.append(val)
        if values:
            product_images.create(values)

    def sync_product_images_to_odoo(self, **kw):
        product_images = self.env['product.images'].sudo()
        url = requests_ll.get_url_ll('product-images')
        self.sync_product_images_ll(product_images, url)
        return
