from odoo import models, fields


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    ll_number = fields.Char('Leaflink number', readonly=1)
    external_id = fields.Char('External ID', readonly=1)
    _sql_constraints = [
        ('ll_number_uniq', 'unique (ll_number)', 'Leaflink number must be unique!'),
    ]
    ll_status = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('accepted', 'Accepted'),
        ('fulfilled', 'Fulfilled'),
        ('shipped', 'Shipped'),
        ('rejected', 'Rejected'),
        ('complete', 'Complete'),
        ('cancelled', 'Cancelled'),
        ('backorder', 'Backorder')
    ], default='draft', string='LeafLink Status')

    ll_create_date = fields.Datetime('Creation date on LeafLink', default=fields.Datetime.now)
    leaflink_created_log_id = fields.Many2one('leaflink.logs')
    leaflink_updated_log_id = fields.Many2one('leaflink.logs')

    def set_warehouse_for_sale_delivery(self):
        if self.analytic_account_id:
            warehouse_id = self.env['stock.warehouse'].search(
                [('analytic_account_id', '=', self.analytic_account_id.id)], limit=1)
            if warehouse_id:
                if self.warehouse_id != warehouse_id:
                    self.write({'warehouse_id': warehouse_id})


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    id_ll = fields.Char('Leaflink order line ID', readonly=1)
    _sql_constraints = [
        ('id_ll_uniq', 'unique (id_ll)', 'Leaflink order line ID must be unique!'),
    ]
