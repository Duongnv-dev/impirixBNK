# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.tools.translate import _


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    shipping_charge = fields.Boolean(string='Shipping Charge', default=False)

    def remove_shipping_charge_from_account_move(self, move):
        shipping_charge_id = self.env.ref('impx_can_general.shipping_charge_from_leaflink').id
        other_invoice_line = move.line_ids.filtered(lambda line: line.product_id.id == shipping_charge_id)
        for line in other_invoice_line:
            line.with_context(check_move_validity=False).unlink()
        move.with_context(check_move_validity=False)._onchange_invoice_line_ids()

    def reverse_moves(self):
        res = super(AccountMoveReversal, self).reverse_moves()
        if self.shipping_charge:
            return res

        if 'res_id' in res:
            move = self.env['account.move'].search([('id', '=', res['res_id'])])
            self.remove_shipping_charge_from_account_move(move)

        if 'domain' in res:
            move_ids = self.env['account.move'].search(res['domain'])
            for move in move_ids:
                self.remove_shipping_charge_from_account_move(move)
        return res