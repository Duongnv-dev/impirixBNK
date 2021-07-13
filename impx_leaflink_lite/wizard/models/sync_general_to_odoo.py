from odoo import fields, api, models, _
from . import requests_ll


class SyncStrains(models.TransientModel):
    _name = 'sync.strains'

    def get_values(self, strain, strain_ll):
        name = strain_ll.get('name')
        strain_classification = strain_ll.get('strain_classification')
        val = {}
        if strain:
            if strain.name != name:
                val['name'] = name
            if strain.strain_classification != strain_classification:
                val['strain_classification'] = strain_classification
            return val
        return {
            'name': name,
            'strain_classification': strain_classification,
        }

    def sync_strains_to_odoo(self, res_strains, url):
        params = {'archive': False}
        strains_ll = requests_ll.get_all_data_from_ll(url=url, params=params)
        values = []
        for strain_ll in strains_ll:
            strain_id_ll = str(strain_ll.get('id'))
            strain = res_strains.search([('id_ll', '=', strain_id_ll)], limit=1)
            val = self.get_values(strain, strain_ll)
            if not val:
                continue
            if strain:
                strain.write(val)
                continue
            val.update({'id_ll': strain_id_ll})
            values.append(val)
        res_strains.create(values)

    def action_sync_strains_to_odoo(self):
        res_strains = self.env['res.strains'].sudo()
        url = requests_ll.get_url_ll('strains')
        self.sync_strains_to_odoo(res_strains, url)


class SyncBrands(models.TransientModel):
    _name = 'sync.brands'

    def get_value(self, brands_ll):
        values = {'name': brands_ll.get('name') or 'Unknown'}
        description = brands_ll.get('description')
        if description:
            values.update({'description': description})
        company = brands_ll.get('company')
        if company:
            company_id = self.env['res.company'].sudo().search([('id_ll', '=', company)], limit=1)
            values.update({'company_id': company_id.id} if company_id else {})
        image = brands_ll.get('image')
        if image:
            values.update({'image': image})
        banner = brands_ll.get('banner')
        if banner:
            values.update({'banner': banner})
        return values

    def sync_brands_ll(self, res_brands, url):
        params = {'archive': False}
        brands_ll = requests_ll.get_all_data_from_ll(url=url, params=params)
        values = []
        for brand_ll in brands_ll:
            product = res_brands.search(
                [('id_ll', '=', brand_ll.get('id'))], limit=1)
            val = self.get_value(brand_ll)
            if product:
                product.write(val)
                continue
            val.update({'id_ll': brand_ll.get('id')})
            values.append(val)
        if values:
            res_brands.create(values)

    def sync_brands_to_odoo(self):
        res_brands = self.env['res.brands'].sudo()
        url = requests_ll.get_url_ll('brands')
        self.sync_brands_ll(res_brands, url)
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
