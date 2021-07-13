from odoo import _, api, models, fields
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    purchase_type = fields.Selection([('normal', 'Normal'), ('metrc', 'Metrc')], default='normal', required=True)

    def get_picking_type_id(self, analytic_account_id=False):
        if not analytic_account_id:
            return False

        warehouse_id = self.env['stock.warehouse'].search([('analytic_account_id', '=', analytic_account_id)])
        if not warehouse_id:
            return False

        picking_type_id = self.env['stock.picking.type'].search(
            [('code', '=', 'incoming'), ('warehouse_id', '=', warehouse_id.id)])
        if not picking_type_id:
            return False

        return picking_type_id

    def _create_picking(self):
        need_create_picking_orders = self.filtered(lambda o: o.purchase_type == 'normal')
        if not need_create_picking_orders:
            return True

        StockPicking = self.env['stock.picking']
        for order in need_create_picking_orders:
            if any([ptype in ['product', 'consu'] for ptype in order.order_line.mapped('product_id.type')]):
                pickings = order.picking_ids.filtered(lambda x: x.state not in ('done', 'cancel'))
                if not pickings:
                    res = order._prepare_picking()
                    for r in res:
                        pickings += StockPicking.create(r)

                for picking in pickings:
                    moves = order.order_line._create_stock_moves(picking)
                    moves = moves.filtered(lambda x: x.state not in ('done', 'cancel'))._action_confirm()
                    seq = 0
                    for move in sorted(moves, key=lambda move: move.date_expected):
                        seq += 5
                        move.sequence = seq
                    moves._action_assign()
                    picking.message_post_with_view('mail.message_origin_link',
                                                   values={'self': picking, 'origin': order},
                                                   subtype_id=self.env.ref('mail.mt_note').id)
        return True

    @api.model
    def _prepare_picking(self):
        res = []
        for line in self.order_line:
            if not self.group_id:
                self.group_id = self.group_id.create({
                    'name': self.name,
                    'partner_id': self.partner_id.id
                })
            if not self.partner_id.property_stock_supplier.id:
                raise UserError(_("You must set a Vendor Location for this partner %s") % self.partner_id.name)
            if line.account_analytic_id.id in [r.get('analytic_account_id') for r in res]:
                continue
            else:
                picking_type_id = self.get_picking_type_id(line.account_analytic_id.id)
                picking_type_id = picking_type_id or self.picking_type_id
                res.append({
                    'partner_id': self.partner_id.id,
                    'user_id': False,
                    'date': self.date_order,
                    'origin': self.name,
                    'picking_type_id': picking_type_id and picking_type_id.id,
                    'location_dest_id': picking_type_id and picking_type_id.default_location_dest_id.id or self._get_destination_location(),
                    'location_id': self.partner_id.property_stock_supplier.id,
                    'company_id': self.company_id.id,
                    'analytic_account_id': line.account_analytic_id.id,
                })
        return res


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def _prepare_stock_moves(self, picking):
        self.ensure_one()
        res = []
        if self.product_id.type not in ['product', 'consu']:
            return res
        qty = 0.0
        price_unit = self._get_stock_move_price_unit()
        for move in self.move_ids.filtered(
                lambda x: x.state != 'cancel' and not x.location_dest_id.usage == "supplier"):
            qty += move.product_uom._compute_quantity(move.product_uom_qty, self.product_uom, rounding_method='HALF-UP')
        description_picking = self.product_id.with_context(
            lang=self.order_id.dest_address_id.lang or self.env.user.lang)._get_description(
            self.order_id.picking_type_id)
        template = {

            'name': (self.name or '')[:2000],
            'product_id': self.product_id.id,
            'product_uom': self.product_uom.id,
            'date': self.order_id.date_order,
            'date_expected': self.date_planned,
            'location_id': picking.location_id.id,
            'location_dest_id': picking.location_dest_id.id,
            'picking_id': picking.id,
            'partner_id': self.order_id.dest_address_id.id,
            'move_dest_ids': [(4, x) for x in self.move_dest_ids.ids],
            'state': 'draft',
            'purchase_line_id': self.id,
            'company_id': self.order_id.company_id.id,
            'price_unit': price_unit,
            'picking_type_id': picking.picking_type_id.id,
            'group_id': self.order_id.group_id.id,
            'origin': self.order_id.name,
            'propagate_date': self.propagate_date,
            'propagate_date_minimum_delta': self.propagate_date_minimum_delta,
            'description_picking': description_picking,
            'propagate_cancel': self.propagate_cancel,
            'route_ids': picking.picking_type_id.warehouse_id and [(6, 0, [x.id for x in picking.picking_type_id.warehouse_id.route_ids])] or [],
            'warehouse_id': picking.picking_type_id.warehouse_id.id,
        }

        diff_quantity = self.product_qty - qty
        if float_compare(diff_quantity, 0.0, precision_rounding=self.product_uom.rounding) > 0:
            po_line_uom = self.product_uom
            quant_uom = self.product_id.uom_id
            product_uom_qty, product_uom = po_line_uom._adjust_uom_quantities(diff_quantity, quant_uom)
            template['product_uom_qty'] = product_uom_qty
            template['product_uom'] = product_uom.id
            res.append(template)
        return res

    def _create_stock_moves(self, picking):
        values = []
        for line in self.filtered(lambda l: not l.display_type):
            if line.account_analytic_id.id == picking.analytic_account_id.id or not line.account_analytic_id:
                for val in line._prepare_stock_moves(picking):
                    values.append(val)
        return self.env['stock.move'].create(values)

    def _create_or_update_picking(self):
        not_metrc_lines = self.filtered(lambda l: l.order_id.purchase_type != 'metrc')
        if not_metrc_lines:
            return super(PurchaseOrderLine, not_metrc_lines)._create_or_update_picking()


class StockMove(models.Model):

    _inherit = "stock.move"

    analytic_account_id = fields.Many2one(related='purchase_line_id.account_analytic_id', store=True)
