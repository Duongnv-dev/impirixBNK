from odoo import fields, models


class LeafLinkLogs(models.Model):
    _name = 'leaflink.logs'
    _order = 'id desc'

    name = fields.Char(required=1)
    state = fields.Selection([('draft', 'Draft'), ('fail', 'Fail'), ('success', 'Success')], default='draft')
    status = fields.Selection([('odoo', 'Odoo to Leaflink'), ('leaflink', 'LeafLink to Odoo'), ('webhook', 'Webhook')])
    action = fields.Char('Action')
    order_ids_created = fields.One2many('sale.order', 'leaflink_created_log_id')
    order_ids_updated = fields.One2many('sale.order', 'leaflink_updated_log_id')
    product_ids_created = fields.One2many('product.product', 'prod_created_leaflink_log_id')
    product_ids_updated = fields.One2many('product.product', 'prod_updated_leaflink_log_id')
    child_prods_ids_created = fields.One2many('product.product', 'child_prod_created_leaflink_log_id')
    child_prods_ids_updated = fields.One2many('product.product', 'child_prod_updated_leaflink_log_id')
    note = fields.Text('Note')
    type = fields.Selection([('orders', 'Sale Order'), ('products', 'Product'), ('partner', 'Customer')])
    duration = fields.Char('Duration')
