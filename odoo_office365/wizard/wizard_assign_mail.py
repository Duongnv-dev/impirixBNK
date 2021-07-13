import logging
import re
from odoo.exceptions import ValidationError, Warning
from odoo.osv import osv
from odoo import _, api, fields, models, modules, SUPERUSER_ID, tools


class WizardAddSpecialMails(models.TransientModel):
    _name = 'wizard.add.special.mail'

    office_sync_id = fields.Many2one('office.sync')
    special_email_ids = fields.Many2many('office365.mail.address', 'wizard_add_special_mail_address',
                                         'office_sync', 'mail_address_id')

    def save_special_mails(self):
        if self.office_sync_id:
            special_email_ids = []
            if self.special_email_ids:
                special_email_ids = self.special_email_ids._ids
            self.office_sync_id.sudo().write({'special_email_ids': [(6, 0, special_email_ids)]})
            mails = self.get_mail_need_reassign_after_change_special_list()
            for mail in mails:
                mail.sudo().with_delay().assign_mail_to_partner(mail.id)
        return True

    def get_mail_need_reassign_after_change_special_list(self):
        if self.special_email_ids:
            mails = self.env['office365.mail'].search([('state', 'not in', ('assigned', 'special')),
                                                       ('mail_address_ids', 'in', self.special_email_ids._ids)])
        return mails


class WizardAddSpecialMails(models.TransientModel):
    _name = 'wizard.suggest.special.mail'

    office_mail_id = fields.Many2one('office365.mail')
    check_similar = fields.Boolean(default=True)
    suggest_mail_address_ids = fields.Many2many('office365.mail.address', 'wizard_suggest_special_mail_address',
                                         'wizard_suggest_special_id', 'mail_address_id')

    suggest_office_mail = fields.Many2many('office365.mail', 'wizard_suggest_special_office_mail',
                                           'wizard_suggest_special_id', 'office_mail_id')

    @api.onchange('suggest_mail_address_ids')
    def change_suggest_mail_address_ids(self):
        mails_list = []
        if self.suggest_mail_address_ids:
            mails = self.env['office365.mail'].search([('state', 'not in', ('assigned', 'special')),
                                                       ('mail_address_ids', 'in', self.suggest_mail_address_ids._ids)])
            if mails:
                mails_list = mails._ids
        self.suggest_office_mail = [(6, 0, mails_list)]

    def apply_add_special_mail(self):
        sync_datas = self.env['office.sync'].search([], limit=1)
        if self.office_mail_id:
            self.office_mail_id.write({'state': 'special'})
        if sync_datas:
            special_email_ids = []
            suggest_mail_address_ids = []
            if self.suggest_mail_address_ids:
                suggest_mail_address_ids = self.suggest_mail_address_ids._ids
                for mail_address in suggest_mail_address_ids:
                    special_email_ids.append((4, mail_address))
            if self.check_similar:
                sync_datas[0].sudo().write({'special_email_ids': special_email_ids})
                self.re_auto_assign_by_suggest(suggest_mail_address_ids)
        return True

    def re_auto_assign_by_suggest(self, suggest_mail_address_ids):
        mails = self.env['office365.mail'].search([('state', 'not in', ('assigned', 'special')),
                                                   ('mail_address_ids', 'in', suggest_mail_address_ids)])
        for mail in mails:
            mail.sudo().with_delay().assign_mail_to_partner(mail.id)
        return True


class WizardSuggestAssignMail(models.TransientModel):
    _name = 'wizard.suggest.assign.mail'

    office_mail_ids = fields.Many2many('office365.mail')
    similar_mail_numbers = fields.Integer(compute='_compute_similar_mail_numbers')

    @api.depends('office_mail_ids')
    def _compute_similar_mail_numbers(self):
        for s in self:
            if s.office_mail_ids:
                s.similar_mail_numbers = len(s.office_mail_ids)
            else:
                s.similar_mail_numbers = 0

    def re_auto_assign_by_suggest(self):
        for mail in self.office_mail_ids:
            mail.sudo().with_delay().assign_mail_to_partner(mail.id)
        return True


class WizardManualAssignMail(models.TransientModel):
    _name = 'wizard.assign.mail'

    type = fields.Selection([('inbox', 'Inbox'), ('outbox', 'Sent')])
    email_from = fields.Char(readonly=True)
    email_to = fields.Char(readonly=True)
    email_cc = fields.Char(readonly=True)
    email_bcc = fields.Char(readonly=True)
    author_id = fields.Many2one('res.partner', required=True)
    partner_ids = fields.Many2many(
        'res.partner', 'manual_assign_partner_rel',
        'manual_assign_id', 'partner_id')

    crm_lead_ids = fields.Many2many('crm.lead', 'manual_assign_crm_lead_rel',
                                    'manual_assign_id', 'crm_lead_id')

    office_mail = fields.Many2one('office365.mail')

    @api.onchange('partner_ids')
    def change_partner_ids(self):
        if self.type == 'inbox':
            if self.partner_ids:
                if not isinstance(self.partner_ids[0].id, (int)):
                    self.author_id = self.partner_ids[0]._origin
                else:
                    self.author_id = self.partner_ids[0]

    def assign_mail_to_partner_opportunity(self):
        if self.office_mail:
            if self.partner_ids or self.crm_lead_ids:
                for partner in self.partner_ids:
                    message_val = self.build_message_val(self.office_mail, self.author_id, partner.id)
                    message_val['model'] = 'res.partner'
                    self.env['mail.message'].with_context(from_office_365=True).create(message_val)
                for opp in self.crm_lead_ids:
                    message_opp_val = self.build_message_val(self.office_mail, self.author_id, opp.id)
                    message_opp_val['model'] = 'crm.lead'
                    self.env['mail.message'].with_context(from_office_365=True).create(message_opp_val)
                self.office_mail.write({
                    'partner_ids': [(6, 0, self.partner_ids._ids)],
                    'crm_lead_ids': [(6, 0, self.crm_lead_ids._ids)], 'state': 'assigned', 'assign_log': 'Re-assigned successful'})
                if self.partner_ids:
                    suggest_list = self.get_office_365_mail_similar()
                    if suggest_list:
                        action_obj = self.env.ref('odoo_office365.action_wizard_suggest_assign_mail')
                        action = action_obj.read([])[0]
                        action['context'] = {'default_office_mail_ids': [(6, 0, suggest_list)]}
                        return action
        return True

    def build_message_val(self, office_mail, author_id, res_id):
        message_val = {'subject': office_mail.subject,
                       'date': office_mail.date,
                       'body': office_mail.body,
                       'email_from': office_mail.email_from,
                       'attachment_ids': [[6, 0, office_mail.attachment_ids._ids]],
                       'author_id': author_id.id or False,
                       'office_id': office_mail.office_id,
                       'mail_conversationIndex': office_mail.mail_conversationIndex,
                       'res_id': res_id
                       }
        return message_val

    def get_office_365_mail_similar(self):
        email_list = [partner.email for partner in self.partner_ids if partner.email]
        partner_mails = self.env['office365.mail.address'].search([('name', 'in', email_list)])
        mails = self.env['office365.mail'].search([('mail_address_ids', 'in', partner_mails._ids), ('state', 'not in', ('assigned', 'special'))])
        return mails._ids
