# -*- encoding: utf-8 -*-

from odoo import api, fields, models, _


class CannabisLicense(models.Model):
    _name = 'cannabis.license'
    _description = 'Cannabis License'

    name = fields.Char(string='License')
    license_type = fields.Selection([('rec', 'Rec'), ('med', 'Med')])
    note = fields.Text()
    active = fields.Boolean(default=True)
    id_ll = fields.Char()
    package_tags_ids = fields.One2many('package.tags', 'license_id',
                                       string='Package Tags')
    analytic_account_ids = fields.One2many('account.analytic.account', 'cannabis_license_id', string='Analytic Account')
    license_unique = fields.Boolean(compute='_check_license_number_analytic_account', store=True)

    @api.depends('analytic_account_ids')
    def _check_license_number_analytic_account(self):
        for rec in self:
            if len(rec.analytic_account_ids) > 0:
                rec.license_unique = True
            else:
                rec.license_unique = False

    # _sql_constraints = [
    #     ('id_ll_uniq', 'unique (id_ll)', 'Leaflink license ID must be unique!'),
    # ]
