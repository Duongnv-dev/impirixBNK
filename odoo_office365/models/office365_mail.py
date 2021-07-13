import logging
import re
from odoo.exceptions import ValidationError, Warning
from odoo.osv import osv
from odoo import _, api, fields, models, modules, SUPERUSER_ID, tools
import requests
import json
from datetime import datetime
import time
from datetime import timedelta
from odoo.addons.queue_job.job import job


class Office365mailaddress(models.Model):
    _name = 'office365.mail.address'

    name = fields.Char()


class Office365Mail(models.Model):
    _name = 'office365.mail'
    _order = 'id desc'

    subject = fields.Char()
    date = fields.Datetime()
    office_id = fields.Char()
    mail_conversationIndex = fields.Char()
    user_id = fields.Many2one('res.users')
    type = fields.Selection([('inbox', 'Inbox'), ('outbox', 'Sent')])
    state = fields.Selection([('new', 'New'), ('assigned', 'assigned'),
                              ('assign_fail', 'Assign Fail'), ('mismatch', 'Mismatch'),
                              ('special', 'Special')], default='new')
    email_from = fields.Char()
    email_to = fields.Text('To', help='Message recipients (emails)')
    email_cc = fields.Char('Cc', help='Carbon copy message recipients')
    email_bcc = fields.Char('Bcc')
    body = fields.Html()
    attachment_ids = fields.Many2many(
        'ir.attachment', 'office_mail_attachment_rel',
        'office_mail_id', 'attachment_id',
        string='Attachments',
        help='Attachments are linked to a document through model / res_id and to the message through this field.')
    partner_ids = fields.Many2many(
        'res.partner', 'office_mail_partner_rel',
        'office_mail_id', 'partner_id')

    crm_lead_ids = fields.Many2many('crm.lead', 'office_mail_crm_lead_rel',
                                    'office_mail_id', 'crm_lead_id')
    assign_log = fields.Char()

    mail_address_ids = fields.Many2many('office365.mail.address', compute='_compute_mail_address_ids', store=True)

    @api.depends('email_from', 'email_to', 'email_cc', 'email_bcc')
    def _compute_mail_address_ids(self):
        for s in self:
            email_list = [s.email_from]
            if s.email_to and s.email_to.strip() != '':
                email_to_list = s.email_to.split(';')
                email_list.extend(email_to_list)
            if s.email_cc and s.email_cc.strip() != '':
                email_cc_list = s.email_cc.split(';')
                email_list.extend(email_cc_list)
            if s.email_bcc and s.email_bcc.strip() != '':
                email_bcc_list = s.email_bcc.split(';')
                email_list.extend(email_bcc_list)
            s.create_mail_address(email_list)
            mail_inf = s.env['office365.mail.address'].search([('name', 'in', email_list)])
            s.mail_address_ids = [(6, 0, mail_inf._ids)]

    def create_mail_address(self, all_mail):
        for mail in all_mail:
            mail_obj = self.env['office365.mail.address'].search([('name', '=', mail)])
            if not mail_obj:
                new_mail = self.env['office365.mail.address'].create({'name': mail})
        return True

    @job
    def assign_mail_to_partner(self, id):
        mail_obj = self.browse(id).sudo()
        email_from = mail_obj.email_from
        email_to_list = []
        email_cc_list = []
        email_bcc_list = []

        if mail_obj.email_to and mail_obj.email_to.strip() != '':
            email_to_list = mail_obj.email_to.split(';')
        if mail_obj.email_cc and mail_obj.email_cc.strip() != '':
            email_cc_list = mail_obj.email_cc.split(';')
        if mail_obj.email_bcc and mail_obj.email_bcc.strip() != '':
            email_bcc_list = mail_obj.email_bcc.split(';')
        all_mail = [email_from] + email_to_list + email_cc_list + email_bcc_list
        self.create_mail_address(all_mail)
        special_emails_list = self.get_special_emails_list()
        if mail_obj.type == 'outbox':
            # Sent
            cus_email_all_list = email_to_list
            if email_cc_list:
                cus_email_all_list += email_cc_list
            if email_bcc_list:
                cus_email_all_list += email_bcc_list
            cus_email_cus_only_list = []
            for mail in cus_email_all_list:
                if not self.check_internal(mail):
                    cus_email_cus_only_list.append(mail)

            if cus_email_all_list and special_emails_list:
                special_flag = self.check_special_email(cus_email_cus_only_list, special_emails_list)
                if special_flag:
                    mail_obj.write({'state': 'special'})
                    self.env.cr.commit()
                    return

            if not cus_email_cus_only_list:
                mail_obj.write({'state': 'assign_fail', 'assign_log': 'It is an internal email'})
                self.env.cr.commit()
                return

            all_cus = self.env['res.partner'].sudo().search([('email', 'in', cus_email_cus_only_list)])
            if not all_cus:
                mail_obj.write({'state': 'mismatch', 'assign_log': 'Can not find a match customer'})
                self.env.cr.commit()
                return

            from_user = self.env['res.users'].sudo().search([('office365_email', "=", email_from)])
            if not from_user:
                mail_obj.write({'state': 'assign_fail', 'assign_log': 'Can not find a sender'})
                self.env.cr.commit()
                return

            partner_ids = []
            crm_lead_ids = []

            # The customers are assigned to the saleperson
            cus_assigned_saleperson = self.env['res.partner'].sudo().search(
                [('user_id', '=', from_user.id), ('email', 'in', cus_email_cus_only_list)])
            if cus_assigned_saleperson:
                for cus in cus_assigned_saleperson:
                    message_val = {}
                    if cus.id not in partner_ids:
                        message_val = self.build_message_val(mail_obj, from_user.partner_id, [cus.id], cus, 'res.partner')
                    oppos = self.get_opportunity(cus, mail_obj.date)
                    mes_opp_create_flag = self.create_message_in_opportunity(mail_obj, from_user.partner_id, crm_lead_ids, oppos)
                    if not mes_opp_create_flag and message_val:
                        partner_ids.append(cus.id)
                        message = self.create_mail_message(message_val)
                self.env.cr.commit()
            else:
                # If no customer is assigned, find all satisfied customers and opps
                for cus in all_cus:
                    message_val = {}
                    if cus.id not in partner_ids:
                        message_val = self.build_message_val(mail_obj, from_user.partner_id, [cus.id], cus, 'res.partner')
                    oppos = self.get_opportunity(cus, mail_obj.date)
                    mes_opp_create_flag = self.create_message_in_opportunity(mail_obj, from_user.partner_id, crm_lead_ids, oppos)
                    if not mes_opp_create_flag and message_val:
                        partner_ids.append(cus.id)
                        message = self.create_mail_message(message_val)
                self.env.cr.commit()
            mail_obj.write({'state': 'assigned',
                            'partner_ids': [[6, 0, partner_ids]],
                            'crm_lead_ids': [[6, 0, crm_lead_ids]]})
        else:
            # Inbox
            if special_emails_list:
                special_flag = self.check_special_email([email_from], special_emails_list)
                if special_flag:
                    mail_obj.write({'state': 'special'})
                    self.env.cr.commit()
                    return
            user_send = self.env['res.users'].sudo().search([('office365_email', "=", email_from)])
            if user_send:
                mail_obj.write({'state': 'assign_fail', 'assign_log': 'It is an internal email'})
                self.env.cr.commit()
                return
            customers = self.env['res.partner'].sudo().search([('email', '=', email_from)])
            if not customers:
                mail_obj.write({'state': 'mismatch', 'assign_log': 'Can not find a match customer'})
                self.env.cr.commit()
                return
            partner_ids = []
            crm_lead_ids = []
            for cus in customers:
                message_val = {}
                if cus.id not in partner_ids:
                    message_val = self.build_message_val(mail_obj, cus, [cus.id], cus, 'res.partner')
                oppos = self.get_opportunity(cus, mail_obj.date)
                mes_opp_create_flag = self.create_message_in_opportunity(mail_obj, cus, crm_lead_ids, oppos)
                if not mes_opp_create_flag and message_val:
                    partner_ids.append(cus.id)
                    message = self.create_mail_message(message_val)
            self.env.cr.commit()
            mail_obj.write({'state': 'assigned',
                            'partner_ids': [[6, 0, partner_ids]],
                            'crm_lead_ids': [[6, 0, crm_lead_ids]]})
        return

    def build_message_val(self, mail_obj, author_id, partner, res_obj, res_model):
        message_val = {'subject': mail_obj.subject,
                       'date': mail_obj.date,
                       'body': mail_obj.body,
                       'email_from': mail_obj.email_from,
                       'partner_ids': [[6, 0, partner]],
                       'attachment_ids': [[6, 0, mail_obj.attachment_ids._ids]],
                       'author_id': author_id.id,
                       'office_id': mail_obj.office_id,
                       'mail_conversationIndex': mail_obj.mail_conversationIndex,
                       'model': res_model,
                       'res_id': res_obj.id}
        disccusion_subtype = self.env.ref('mail.mt_comment')
        if disccusion_subtype:
            message_val['subtype_id'] = disccusion_subtype.id
        return message_val

    def get_root_partner(self, partner_id):
        if partner_id.parent_id.is_company:
            return partner_id.parent_id
        else:
            return partner_id

    # Get the list of satisfied opportunities
    def get_opportunity(self, partner_id, date):
        partner_list = [partner_id.id]
        won_stages = self.env['crm.stage'].search([('is_won', '=', True)])
        opps_list = []

        oppos = self.env['crm.lead'].search(['&', '&', ('partner_id', 'in', partner_list),
                                             ('create_date', '<=', date), '|', ('active', '=', True), ('active', '=', False)])
        for oppo in oppos:
            if not oppo.active or oppo.stage_id.id in won_stages._ids:
                if oppo.date_closed and oppo.date_closed >= date:
                    opps_list.append(oppo.id)
            else:
                opps_list.append(oppo.id)
        return self.env['crm.lead'].browse(opps_list)

    def create_mail_message(self, message_val):
        message = self.env['mail.message'].with_context(from_office_365=True).create(message_val)
        self.sudo().update_create_write_date(message)
        return message

    def create_message_in_opportunity(self, mail_obj, author_id, crm_lead_ids, oppos):
        mes_opp_create_flag = False
        for opp in oppos:
            if opp.id not in crm_lead_ids and opp.create_date <= mail_obj.date:
                crm_lead_ids.append(opp.id)
                message_opp_val = self.build_message_val(mail_obj, author_id, [], opp, 'crm.lead')
                message = self.create_mail_message(message_opp_val)
                mes_opp_create_flag = True
        return mes_opp_create_flag

    def update_create_write_date(self, message):
        query = """update mail_message 
                    set create_date = '{}', write_date = '{}'
                    where id = {}""".format(message.date, message.date, message.id)
        self.env.cr.execute(query)
        return True

    def check_internal(self, mail):
        user_type_internal_id = self.env.ref('base.group_user')
        internal_user = self.env['res.users'].sudo().search(['&', '|', ('office365_email', "=", mail), ('email', '=', mail), ('groups_id', 'in', user_type_internal_id._ids)])
        if not internal_user:
            return False
        return True

    def check_special_email(self, cus_email_all_list, special_emails_list):
        special_flag = False
        cus_mail_address = self.env['office365.mail.address'].sudo().search([('name', "in", cus_email_all_list)])
        if cus_mail_address:
            special_flag = True
            for cus_mail in cus_mail_address:
                if cus_mail.id not in special_emails_list:
                    special_flag = False
        return special_flag

    def get_special_emails_list(self):
        special_emails_list = []
        sync_obj = self.env['office.sync'].search([])[0]
        if sync_obj and sync_obj.special_email_ids:
            special_emails_list = sync_obj.special_email_ids._ids
        return special_emails_list

    def manual_assign_mail_to_partner_opportunity(self):
        from_partner = False
        if self.type == 'outbox':
            from_user = self.env['res.users'].sudo().search([('office365_email', "=", self.email_from)])
            if from_user:
                from_partner = from_user[0].partner_id.id
        else:
            from_partners = self.env['res.partner'].sudo().search([('email', '=', self.email_from)])
            if from_partners:
                from_partner = from_partners[0].id
        action_obj = self.env.ref('odoo_office365.action_wizard_assign_mail')
        action = action_obj.read([])[0]
        action['context'] = {'default_office_mail': self.id,
                             'default_type': self.type,
                             'default_email_from': self.email_from,
                             'default_email_to': self.email_to,
                             'default_email_cc': self.email_cc,
                             'default_email_bcc': self.email_bcc,
                             }
        # if not from_partner:
        #     from_partner = self.env.user.partner_id.id
        action['context'].update({'default_author_id': from_partner})
        return action

    def move_to_special(self):
        action_obj = self.env.ref('odoo_office365.action_wizard_suggest_special_mail')
        action = action_obj.read([])[0]
        action['context'] = {'default_office_mail_id': self.id}
        special_emails_list = self.get_special_emails_list()
        mail_address_suggest_list = []
        for mail_address in self.mail_address_ids:
            if not self.check_internal(mail_address.name) and mail_address.id not in special_emails_list:
                mail_address_suggest_list.append(mail_address.id)
        action['context']['default_suggest_mail_address_ids'] = [(6, 0, mail_address_suggest_list)]
        return action
