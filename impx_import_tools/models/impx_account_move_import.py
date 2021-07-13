# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError
import xlrd
import base64
from dateutil.parser import parse


class ImpxImport(models.Model):
    _name = 'impx.import'
    _rec_name = 'name'

    name = fields.Char(string='Import Reference')
    date_action = fields.Datetime('Import Date', readonly=True, default=lambda self: fields.datetime.now())
    user_id = fields.Many2one('res.users', string='Imported by', default=lambda self: self.env.user, readonly=True)
    file = fields.Binary(string='Import file name', required=True, attachment=False)
    file_name = fields.Char("Import file name")
    impx_account_import_ids = fields.One2many('impx.account.import', 'impx_import_id', string='Impx account import')
    transaction_type = fields.Many2many('account.journal', string='Journal to sync', required=True)

    def _check_account_id(self, account):
        account_object = self.env['account.account']
        account_id = account_object.search([('display_name', '=', account)])

        if not account_id:
            raise ValidationError(_("Don't found account: %s" % account))

        if len(account_id) > 1:
            raise ValidationError(_("Found multi account! %s" % account_id))

        return account_id.id

    def _check_partner_id(self, partner):
        partner_obj = self.env['res.partner']
        partner_id = partner_obj.search([('name', '=', partner)])

        if not partner_id:
            return False

        if len(partner_id) > 1:
            raise ValidationError(_("Found multi partner! %s" % partner_id))

        return partner_id.id

    def sync_account_data(self):
        transaction_type_dict = {journal_type.name: journal_type.id for journal_type in self.transaction_type}
        journal_entry_object = self.env['account.move']

        for rec in self.impx_account_import_ids:
            if not rec.transaction_type:
                continue

            if rec.transaction_type not in list(transaction_type_dict.keys()):
                continue

            if rec.state == 'success':
                continue

            try:
                create_value = {
                    'ref': rec.reference,
                    'date': parse(rec.accounting_date).strftime("%Y-%m-%d"),
                    'journal_id': transaction_type_dict[rec.transaction_type],
                    'line_ids': [(0, 0, {
                        'account_id': self._check_account_id(line.account),
                        'partner_id': self._check_partner_id(rec.partner),
                        'name': line.description,
                        'debit': line.debit,
                        'credit': line.credit,
                    }) for line in rec.impx_import_line_ids]
                }

                journal_entry_id = journal_entry_object.create(create_value)
                journal_entry_id.action_post()
                rec.journal_entry_id = journal_entry_id.id
                rec.state = 'success'

            except Exception as e:
                rec.state = 'fail'
                rec.note = e

    def generate_data_file(self):
        try:
            book = xlrd.open_workbook(file_contents=base64.decodebytes(self.file))
        except TypeError as e:
            raise ValidationError(u'ERROR: {}'.format(e))

        sheet = book.sheet_by_index(0)
        self.env['impx.account.import'].search([('impx_import_id', '=', self.id)]).unlink()
        impx_account_import_object = self.env['impx.account.import']
        impx_account_import_line_object = self.env['impx.account.import.line']
        last_create_import_id = False
        for row in range(1, sheet.nrows):
            res = []
            for col in range(sheet.ncols):
                res.append(sheet.cell_value(row, col))
            if not res[0] and not res[1] and not res[2] and not res[3] and not res[4] and not res[5]:
                continue
            if res[0] and res[1]:
                last_create_import_id = impx_account_import_object.create(
                    {
                        'impx_import_id': self.id,
                        'accounting_date': res[0],
                        'transaction_type': res[1],
                        'partner': res[3],
                        'reference': res[2],
                        'impx_import_line_ids': [(0, 0, {
                            'account': res[5],
                            'description': res[4],
                            'debit': res[6],
                            'credit': res[7],
                        })],
                    })
            else:
                if not last_create_import_id:
                    continue

                impx_account_import_line_object.create(
                    {
                        'impx_account_import_id': last_create_import_id.id,
                        'account': res[5],
                        'description': res[4],
                        'debit': res[6],
                        'credit': res[7],
                    })


class ImpxAccountImport(models.Model):
    _name = 'impx.account.import'
    _rec_name = 'reference'

    impx_import_id = fields.Many2one('impx.import', string='Impx import', ondelete='restrict')
    accounting_date = fields.Char(string='Accounting Date', states={'success': [('readonly', True)]})
    transaction_type = fields.Char(string='Transaction Type', states={'success': [('readonly', True)]})
    reference = fields.Char(string='Reference', states={'success': [('readonly', True)]})
    partner = fields.Char(string='Partner')
    impx_import_line_ids = fields.One2many('impx.account.import.line', 'impx_account_import_id',
                                           states={'success': [('readonly', True)]}, string='Impx import Line')
    state = fields.Selection([
        ('ready', 'Ready'),
        ('success', 'Success'),
        ('fail', 'Fail'),
    ], string='Sync data status', default='ready')
    journal_entry_id = fields.Many2one('account.move', string='Journal Entry', readonly=True)
    note = fields.Char(string='Error Note', readonly=True)

    def unlink(self):
        for rec in self:
            if rec.state == 'success' and rec.journal_entry_id:
                raise UserError(_("This record is synchronized, cannot be deleted!."))


class ImpxAccountImportLine(models.Model):
    _name = 'impx.account.import.line'

    impx_account_import_id = fields.Many2one('impx.account.import', string='Impx account import', ondelete='restrict')
    account = fields.Char(string='Account')
    description = fields.Char(string='Description')
    debit = fields.Float(string='Debit')
    credit = fields.Float(string='Credit')
