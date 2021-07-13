# -*- coding: utf-8 -*-

from odoo import fields, models, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    cannabis_license_id = fields.Many2one(related='analytic_account_id.cannabis_license_id', string='Cannabis License', store=True)

    @api.onchange('analytic_account_id')
    def onchange_analytic_account_id(self):
        if self.analytic_account_id:
            warehouse_id = self.env['stock.warehouse'].search(
                [('analytic_account_id', '=', self.analytic_account_id.id)])
            if warehouse_id:
                self.warehouse_id = warehouse_id.id
            else:
                self.warehouse_id = False

    def _create_invoices(self, grouped=False, final=False):
        res = super(SaleOrder, self)._create_invoices(grouped=grouped, final=final)
        current_invoice_lines = res.line_ids.filtered(lambda line: line.exclude_from_invoice_tab)
        if not self.analytic_account_id:
            return res

        for line in current_invoice_lines:
            if line.analytic_account_id:
                continue

            line.analytic_account_id = self.analytic_account_id.id
        return res

    @api.onchange('partner_id')
    def onchange_partner_id_change_price(self):
        for line in self.order_line:
            line.product_id_change()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    analytic_account_id = fields.Many2one(related='order_id.analytic_account_id', string='License Number')


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = "sale.advance.payment.inv"

    def _create_invoice(self, order, so_line, amount):
        res = super(SaleAdvancePaymentInv, self)._create_invoice(order=order, so_line=so_line, amount=amount)
        current_invoice_lines = res.line_ids.filtered(lambda line: line.exclude_from_invoice_tab)
        if not order.analytic_account_id:
            return res

        for line in current_invoice_lines:
            if line.analytic_account_id:
                continue

            line.analytic_account_id = order.analytic_account_id.id
        return res




