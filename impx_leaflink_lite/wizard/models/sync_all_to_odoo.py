from odoo import fields, models


class SyncAll(models.TransientModel):
    _name = 'sync.all.ll'
    log = fields.Text()

    def sync_all_to_odoo(self):
        self.env['sync.strains'].sudo().with_context(not_return=True).action_sync_strains_to_odoo()
        self.env['sync.brands'].sudo().with_context(not_return=True).sync_brands_to_odoo()
        self.env['sync.product.lines'].sudo().with_context(not_return=True).sync_product_lines_to_odoo()
        self.env['sync.product.categories'].sudo().with_context(not_return=True).sync_product_categories_to_odoo()
        self.env['sync.products'].sudo().with_context(not_return=True).sync_products_to_odoo()
        self.env['sync.product.images'].sudo().with_context(not_return=True).sync_product_images_to_odoo()
