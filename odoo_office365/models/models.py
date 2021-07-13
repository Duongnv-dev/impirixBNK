# -*- coding: utf-8 -*-

import logging
import re

from odoo import fields, models, api, osv
from odoo.exceptions import ValidationError
from odoo.osv import osv
from odoo import _, api, fields, models, modules, SUPERUSER_ID, tools
from odoo.exceptions import UserError, AccessError
import requests
import json
from datetime import datetime
import time
from datetime import timedelta

_logger = logging.getLogger(__name__)
_image_dataurl = re.compile(r'(data:image/[a-z]+?);base64,([a-z0-9+/]{3,}=*)([\'"])', re.I)


class OfficeSettings(models.Model):
    """
    This class separates one time office 365 settings from Token generation settings
    """
    _name = "office.settings"

    field_name = fields.Char('Office365')
    
    redirect_url = fields.Char('Redirect URL')
    client_id = fields.Char('Client Id')
    secret = fields.Char('Secret')
    login_url = fields.Char('Login URL', compute='_compute_url', readonly=True)

    @api.depends('redirect_url','client_id','secret')
    def _compute_url(self):

        settings = self.env['office.settings'].search([])
        settings = settings[0] if settings else settings
        if settings:
            self.login_url = 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?' \
                             'client_id=%s&redirect_uri=%s&response_type=code&scope=openid+offline_access+' \
                             'Calendars.ReadWrite+Mail.ReadWrite+Mail.Send+User.ReadWrite+Tasks.ReadWrite+' \
                             'Contacts.ReadWrite+MailboxSettings.Read' % (
                self.client_id, self.redirect_url)

    def save_data(self):
        try:
            if not self.client_id or not self.redirect_url or not self.secret:
                 raise osv.except_osv(_("Wrong Credentials!"), (_("Please Check your Credentials and try again")))
            else:
                self.env.user.redirect_url = self.redirect_url
                self.env.user.client_id = self.client_id
                self.env.user.secret = self.secret
                self.env.user.code = None
                self.env.user.token = None
                self.env.user.refresh_token = None
                self.env.user.expires_in = None
                self.env.user.office365_email = None
                self.env.user.office365_id_address = None

                self.env.cr.commit()
                context = dict(self._context)
                # self.env['office.usersettings'].login_url
                context['message'] = 'Successfully Saved!'
                return self.message_wizard(context)

        except Exception as e:
            raise ValidationError(_(str(e)))

    def message_wizard(self, context):

        return {
            'name': ('Success'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'message.wizard',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': context

        }

        # raise osv.except_osv(_("Success!"), (_("Successfully Saved!")))


class Office365UserSettings(models.Model):
    """
    This class facilitates the users other than admin to enter office 365 credential
    """
    _name = 'office.usersettings'
    login_url = fields.Char('Login URL', compute='_compute_url', readonly=True)
    code = fields.Char('code')
    field_name = fields.Char('office')
    token = fields.Char('Office_Token')

    def _compute_url(self):
        settings = self.env['office.settings'].search([])
        settings = settings[0] if settings else settings
        if settings:
            self.login_url = 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?' \
                             'client_id=%s&redirect_uri=%s&response_type=code&scope=openid+' \
                             'offline_access+Calendars.ReadWrite+Mail.ReadWrite+Mail.Send+User.ReadWrite+' \
                             'Tasks.ReadWrite+Contacts.ReadWrite+MailboxSettings.Read' % (
                settings.client_id, settings.redirect_url)

    def generate_token(self,code):

        try:
            settings = self.env['office.settings'].search([])
            settings = settings[0] if settings else settings

            if not settings.client_id or not settings.redirect_url or not settings.secret:
                raise osv.except_osv(_("Error!"), (_("Please ask admin to add Office365 settings!")))

            header = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            response = requests.post(
                'https://login.microsoftonline.com/common/oauth2/v2.0/token',
                data='grant_type=authorization_code&code=' + code + '&redirect_uri=' + settings.redirect_url + '&client_id=' + settings.client_id + '&client_secret=' + settings.secret
                , headers=header).content

            if 'error' in json.loads(response.decode('utf-8')) and json.loads(response.decode('utf-8'))['error']:
                raise UserError('Invalid Credentials . Please! Check your credential and  regenerate the code and try again!')

            else :
                data = {}
                response = json.loads((str(response)[2:])[:-1])
                data['token'] =response['access_token']
                data['refresh_token'] =response['refresh_token']
                data['expires_in'] =response['expires_in']

                categories = requests.get('https://graph.microsoft.com/v1.0/me/outlook/masterCategories',
                                          headers={
                                              'Host': 'outlook.office.com',
                                              'Authorization': 'Bearer {0}'.format(data['token']),
                                              'Accept': 'application/json',
                                              'X-Target-URL': 'http://outlook.office.com',
                                              'connection': 'keep-Alive'
                                          }).content
                category = json.loads(categories)

                odoo_categ = self.env['calendar.event.type']

                if 'value' in category:

                    for categ in category['value']:
                        if  self.env['calendar.event.type'].search(
                                    ['|', ('categ_id', '=', categ['id']), ('name', '=', categ['displayName'])]):
                            # office_categ.write({'categ_id': categ['id'],
                            #                     'color': categ['color'],
                            #                     'name': categ['displayName'],
                            #                     })
                            odoo_categ.write({'categ_id': categ['id'],
                                              'color': categ['color'],
                                              'name': categ['displayName'],
                                              })
                        else:
                            # office_categ.create({'categ_id': categ['id'],
                            #                      'color': categ['color'],
                            #                      'name': categ['displayName'],
                            #                      })
                            odoo_categ.create({'categ_id': categ['id'],
                                               'color': categ['color'],
                                               'name': categ['displayName'],
                                               })

                    response = json.loads((requests.get(
                        'https://graph.microsoft.com/v1.0/me',
                        headers={
                            'Host': 'outlook.office.com',
                            'Authorization': 'Bearer {0}'.format(data['token']),
                            'Accept': 'application/json',
                            'X-Target-URL': 'http://outlook.office.com',
                            'connection': 'keep-Alive'
                        }).content.decode('utf-8')))
                    if response:
                        data['userPrincipalName'] = response['userPrincipalName']
                        data['office365_id_address'] = 'outlook_' + response['id'].upper() + '@outlook.com'

                return data

        except Exception as e:
            _logger.error(e)
            data['error']=e
            return data

class CustomUser(models.Model):
    """
    Add custom fields for office365 users
    """
    _inherit = 'res.users'

    login_url = fields.Char('Login URL', compute='_compute_url', readonly=True)
    code = fields.Char('code')
    token = fields.Char('Token', readonly=True)
    refresh_token = fields.Char('Refresh Token', readonly=True)
    expires_in = fields.Char('Expires IN', readonly=True)
    redirect_url = fields.Char('Redirect URL')
    client_id = fields.Char('Client Id')
    secret = fields.Char('Secret')
    office365_email = fields.Char('Office365 Email Address', readonly=True)
    office365_id_address = fields.Char('Office365 Id Address', readonly=True)
    send_mail_flag = fields.Boolean(string='Send messages using office365 Mail', default=True)
    is_task_sync_on = fields.Boolean('is sync in progress', default=False)
    last_mail_import = fields.Datetime(string="Last Import", required=False, readonly=True)
    last_calender_import = fields.Datetime(string="Last Import", required=False, readonly=True)
    last_task_import = fields.Datetime(string="Last Import", required=False, readonly=True)
    last_contact_import = fields.Datetime(string="Last Import", required=False, readonly=True)
    event_del_flag = fields.Boolean('Delete events from Office365 calendar when delete in Odoo.')
    event_create_flag = fields.Boolean('Create events in Office365 calendar when create in Odoo.')
    allow_connect_365 = fields.Boolean()
    last_login = fields.Datetime(readonly=True)
    export_history_id = fields.Many2one('export.history')

    def get_code(self):
        context = dict(self._context)
        settings = self.env['office.settings'].search([])
        if settings.redirect_url and settings.client_id and settings.login_url:
            if self.id == self.env.user.id:
                self.sudo().write({'last_login': datetime.now(), 'send_mail_flag': True})
                # return self.message_wizard(context)
                return {
                    'name': 'login',
                    'view_id': False,
                    "type": "ir.actions.act_url",
                    'target': 'self',
                    'url': settings.login_url
                }
        else:
            raise ValidationError('Office365 Credentials are missing. Please! ask admin to add Office365 Client id, '
                                      'client secret and redirect Url ')
        
    def write(self, vals):
        value = {
                    'code': False,
                    'token': False,
                    'refresh_token': False,
                    'expires_in': False,
                    'redirect_url': False,
                    'client_id': False,
                    'secret': False,
                    'office365_email': False,
                    'office365_id_address': False,
                    'send_mail_flag': False,
                    'last_login': False,
                }
        if 'allow_connect_365' in vals.keys():
            if vals['allow_connect_365'] is not True:
                vals.update(value)
        if 'active' in vals.keys():
            if vals['active'] is not True:
                value['allow_connect_365'] = False
                vals.update(value)
        return super(CustomUser, self).write(vals)

    def auto_generate_refresh_token(self):
        if not self.expires_in:
            return False
        expires_in = datetime.fromtimestamp(int(self.expires_in) / 1e3) + timedelta(seconds=3600)
        if datetime.now() <= expires_in:
            return False
        if self.refresh_token:
            settings = self.env['office.settings'].search([])
            settings = settings[0] if settings else settings

            if not settings.client_id or not settings.redirect_url or not settings.secret:
                raise osv.except_osv(_("Error!"), (_("Please ask admin to add Office365 settings!")))

            header = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = requests.post(
                'https://login.microsoftonline.com/common/oauth2/v2.0/token',
                data='grant_type=refresh_token&refresh_token={}&redirect_uri={}&client_id={}&client_secret={}'.format(
                    self.refresh_token, settings.redirect_url, settings.client_id, settings.secret),
                headers=header).content

            response = json.loads((str(response)[2:])[:-1])
            if 'access_token' not in response:
                response["error_/opt/odoo13/custom_addons/odoo_xerodescription"] = response[
                    "error_description"].replace("\\r\\n", " ")
                raise osv.except_osv(_("Error!"), (_(response["error"] + " " + response["error_description"])))
            else:
                self.token = response['access_token']
                self.refresh_token = response['refresh_token']
                self.expires_in = int(round(time.time() * 1000))
        else:
            _logger.error('Refresh token not found!')

    def get_calendar_id_office_365(self):
        self.auto_generate_refresh_token()
        url = 'https://graph.microsoft.com/v1.0/me/calendars'
        headers = {
            'Host': 'outlook.office.com',
            'Authorization': 'Bearer {0}'.format(self.token),
            'Accept': 'application/json',
            'X-Target-URL': 'http://outlook.office.com',
            'connection': 'keep-Alive'
        }
        try:
            response = requests.get(url=url, headers=headers)
            if response.status_code == 200:
                response = json.loads((response.content.decode('utf-8')))
                if response.get('value'):
                    return response['value'][0]['id']
                raise osv.except_osv(("Access Token Expired!"), (" Please Regenerate Access Token !"))
            return False
        except Exception as error:
            _logger.info('Error {} when get uid {}'.format(error, self.name))
            return False


class CustomMessageInbox(models.Model):
    """
    Email will store in mail.message class so that's why we need office_id
    """
    _inherit = 'mail.message'
    office_id = fields.Char('Office Id')
    mail_conversationIndex = fields.Char()


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, *,
                     body='', subject=None, message_type='notification',
                     email_from=None, author_id=None, parent_id=False,
                     subtype_id=False, subtype=None, partner_ids=None, channel_ids=None,
                     attachments=None, attachment_ids=None,
                     add_sign=True, record_name=False,
                     **kwargs):
        self.ensure_one()  # should always be posted on a record, use message_notify if no record
        # split message additional values from notify additional values
        context = self._context
        current_uid = context.get('uid')
        user = self.env['res.users'].browse(current_uid)
        if user.allow_connect_365 and user.office365_email:
            if user.token:
                if self.check_re_generate(user):
                    self.generate_refresh_token()
            else:
                raise UserError('Office account invalid')

            msg_kwargs = dict((key, val) for key, val in kwargs.items() if key in self.env['mail.message']._fields)
            notif_kwargs = dict((key, val) for key, val in kwargs.items() if key not in msg_kwargs)

            if self._name == 'mail.thread' or not self.id or message_type == 'user_notification':
                raise ValueError(
                    'message_post should only be call to post message on record. Use message_notify instead')

            if 'model' in msg_kwargs or 'res_id' in msg_kwargs:
                raise ValueError(
                    "message_post doesn't support model and res_id parameters anymore. Please call message_post on record")

            self = self.with_lang()  # add lang to context imediatly since it will be usefull in various flows latter.

            # Explicit access rights check, because display_name is computed as sudo.
            self.check_access_rights('read')
            self.check_access_rule('read')
            record_name = record_name or self.display_name

            partner_ids = set(partner_ids or [])
            channel_ids = set(channel_ids or [])

            if any(not isinstance(pc_id, int) for pc_id in partner_ids | channel_ids):
                raise ValueError('message_post partner_ids and channel_ids must be integer list, not commands')

            # Find the message's author
            author_info = self._message_compute_author(author_id, email_from, raise_exception=True)
            author_id, email_from = author_info['author_id'], author_info['email_from']

            if not subtype_id:
                subtype = subtype or 'mt_note'
                if '.' not in subtype:
                    subtype = 'mail.%s' % subtype
                subtype_id = self.env['ir.model.data'].xmlid_to_res_id(subtype)

            # automatically subscribe recipients if asked to
            if self._context.get('mail_post_autofollow') and partner_ids:
                self.message_subscribe(list(partner_ids))

            MailMessage_sudo = self.env['mail.message'].sudo()
            if self._mail_flat_thread and not parent_id:
                parent_message = MailMessage_sudo.search(
                    [('res_id', '=', self.id), ('model', '=', self._name), ('message_type', '!=', 'user_notification')],
                    order="id ASC", limit=1)
                # parent_message searched in sudo for performance, only used for id.
                # Note that with sudo we will match message with internal subtypes.
                parent_id = parent_message.id if parent_message else False
            elif parent_id:
                old_parent_id = parent_id
                parent_message = MailMessage_sudo.search([('id', '=', parent_id), ('parent_id', '!=', False)], limit=1)
                # avoid loops when finding ancestors
                processed_list = []
                if parent_message:
                    new_parent_id = parent_message.parent_id and parent_message.parent_id.id
                    while (new_parent_id and new_parent_id not in processed_list):
                        processed_list.append(new_parent_id)
                        parent_message = parent_message.parent_id
                    parent_id = parent_message.id

            values = dict(msg_kwargs)
            values.update({
                'author_id': author_id,
                'email_from': email_from,
                'model': self._name,
                'res_id': self.id,
                'body': body,
                'subject': subject or False,
                'message_type': message_type,
                'parent_id': parent_id,
                'subtype_id': subtype_id,
                'partner_ids': partner_ids,
                'channel_ids': channel_ids,
                'add_sign': add_sign,
                'record_name': record_name,
            })
            attachments = attachments or []
            attachment_ids = attachment_ids or []
            attachement_values = self._message_post_process_attachments(attachments, attachment_ids, values)
            values.update(attachement_values)  # attachement_ids, [body]
            new_message = self._message_create(values)

            self._message_set_main_attachment_id(values['attachment_ids'])

            if values['author_id'] and values['message_type'] != 'notification' and not self._context.get(
                    'mail_create_nosubscribe'):
                # if self.env['res.partner'].browse(values['author_id']).active:  # we dont want to add odoobot/inactive as a follower
                self._message_subscribe([values['author_id']])
            self._message_post_after_hook(new_message, values)
            if context.get('mail_post_autofollow', False):
                recipients_data = self._notify_compute_recipients(new_message, values)
                email_to = self.get_email_to(values, recipients_data)
                if not email_to:
                    new_message.sudo().unlink()
                    raise UserError("Can't find a valid email to send. Please check customer's email address.")
                new_data = {
                    "subject": subject or False,
                    "body": {
                        "contentType": "HTML",
                        "content": new_message.body
                    },
                    "toRecipients": [
                        {
                            "emailAddress": {
                                "address": email_to
                            }
                        }
                    ]
                }
                send = self.send_mail_365(user, new_message, new_data)
                if not send:
                    new_message.sudo().unlink()
                    raise UserError('An error occurred while sending message by email.'
                                    'Please check configuration, connect to office 365 account and try again.')
            return new_message
        else:
            return super(MailThread, self).message_post(
                     body=body, subject=subject, message_type=message_type,
                     email_from=email_from, author_id=author_id, parent_id=parent_id,
                     subtype_id=subtype_id, subtype=subtype, partner_ids=partner_ids, channel_ids=channel_ids,
                     attachments=attachments, attachment_ids=attachment_ids,
                     add_sign=add_sign, record_name=record_name,
                     **kwargs)

    def get_email_to(self, value, recipient_data):
        email_to = False
        if value.get('model', False) == 'res.partner' and value.get('res_id', False):
            partner_object = self.env['res.partner'].browse(value['res_id'])
            if partner_object and partner_object.email:
                email_to = partner_object.email or False
        else:
            if value.get('model', False) and value.get('res_id', False) and 'partner_id' in self.env[value['model']]._fields:
                if isinstance(self._fields['partner_id'], (fields.Many2one)):
                    obj = self.env[value['model']].browse(value['res_id'])
                    partner_object = obj.partner_id
                    email_to = partner_object.email or False
            else:
                for partner in recipient_data['partners']:
                    if partner.get('active', False) and partner.get('notif', False) == 'email' and \
                                    partner.get('type', False) == 'customer':
                        partner_object = self.env['res.partner'].browse(partner['id'])
                        email_to = partner_object.email or False
                        if email_to:
                            break
        return email_to

    def check_re_generate(self, user):
        if user.expires_in:
            expires_in = datetime.fromtimestamp(int(user.expires_in) / 1e3)
            expires_in = expires_in + timedelta(seconds=3600)
            nowDateTime = datetime.now()
            if nowDateTime > expires_in:
                return True
        return False

    def send_mail_365(self, user, message, new_data):
        try:
            response = requests.post(
                'https://graph.microsoft.com/v1.0/me/messages', data=json.dumps(new_data),
                headers={
                    'Host': 'outlook.office.com',
                    'Authorization': 'Bearer {0}'.format(user.token),
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-Target-URL': 'http://outlook.office.com',
                    'connection': 'keep-Alive'
                })

            result = json.loads((response.content.decode('utf-8')))

            if 'conversationId' in result.keys():
                conv_id = result['conversationId']

            if 'conversationIndex' in result.keys():
                conv_index_id = result['conversationIndex']

            if 'id' in result.keys():
                o365_id = result['id']
                if message.attachment_ids:
                    for attachment in self.getAttachments(message.attachment_ids):
                        attachment_response = requests.post(
                            'https://graph.microsoft.com/beta/me/messages/' + o365_id + '/attachments',
                            data=json.dumps(attachment),
                            headers={
                                'Host': 'outlook.office.com',
                                'Authorization': 'Bearer {0}'.format(user.token),
                                'Accept': 'application/json',
                                'Content-Type': 'application/json',
                                'X-Target-URL': 'http://outlook.office.com',
                                'connection': 'keep-Alive'
                            })
                send_response = requests.post(
                    'https://graph.microsoft.com/v1.0/me/messages/' + o365_id + '/send',
                    headers={
                        'Host': 'outlook.office.com',
                        'Authorization': 'Bearer {0}'.format(user.token),
                        'Accept': 'application/json',
                        'Content-Type': 'application/json',
                        'X-Target-URL': 'http://outlook.office.com',
                        'connection': 'keep-Alive'
                    })

                val_message_update = {}
                if conv_id:
                    val_message_update['office_id'] = conv_id
                if conv_index_id:
                    val_message_update['mail_conversationIndex'] = conv_index_id
                if val_message_update:
                    message.write(val_message_update)
            return True
        except Exception as e:
            return False

    def getAttachments(self, attachment_ids):
        attachment_list = []
        if attachment_ids:
            attachments = self.env['ir.attachment'].search([('id', 'in', [i.id for i in attachment_ids])])
            for attachment in attachments:
                attachment_list.append({
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": attachment.name,
                    "contentBytes": attachment.datas.decode("utf-8")
                })
        return attachment_list

    def generate_refresh_token(self):
        context = self._context

        current_uid = context.get('uid')

        user = self.env['res.users'].browse(current_uid)
        if user.refresh_token:
            settings = self.env['office.settings'].search([])
            settings = settings[0] if settings else settings

            if not settings.client_id or not settings.redirect_url or not settings.secret:
                raise osv.except_osv(_("Error!"), (_("Please ask admin to add Office365 settings!")))
            header = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = requests.post(
                'https://login.microsoftonline.com/common/oauth2/v2.0/token',
                data='grant_type=refresh_token&refresh_token=' + user.refresh_token + '&redirect_uri=' + settings.redirect_url + '&client_id=' + settings.client_id + '&client_secret=' + settings.secret
                , headers=header).content

            response = json.loads((str(response)[2:])[:-1])
            if 'access_token' not in response:
                response["error_description"] = response["error_description"].replace("\\r\\n", " ")
                raise osv.except_osv(_("Error!"), (_(response["error"] + " " + response["error_description"])))
            else:
                user.token = response['access_token']
                user.refresh_token = response['refresh_token']
                user.expires_in = int(round(time.time() * 1000))
                self.env.cr.commit()


class CustomMessage(models.Model):

    # Email will be sent to the recipient of the message.
    _inherit = 'mail.mail'
    office_id = fields.Char('Office Id')

    # Move function to model mail.thread
    # @api.model
    # def create(self, values):
    #     # raise
    #     """
    #     overriding create message to send email on message creation
    #     :param values:
    #     :return:
    #     """
    #     ################## New Code ##################
    #     ################## New Code ##################
    #     o365_id = None
    #     conv_id = None
    #     conv_index_id = None
    #     context = self._context
    #
    #     current_uid = context.get('uid')
    #
    #     user = self.env['res.users'].browse(current_uid)
    #     if user.send_mail_flag:
    #         if user.token:
    #             if user.expires_in:
    #                 expires_in = datetime.fromtimestamp(int(user.expires_in) / 1e3)
    #                 expires_in = expires_in + timedelta(seconds=3600)
    #                 nowDateTime = datetime.now()
    #                 if nowDateTime > expires_in:
    #                     self.generate_refresh_token()
    #             if 'mail_message_id' in values:
    #                 email_obj = self.env['mail.message'].search([('id', '=', values['mail_message_id'])])
    #                 print("values['recipient_ids']",values['recipient_ids'])
    #                 partner_id = values['recipient_ids'][0][1]
    #                 partner_obj = self.env['res.partner'].search([('id', '=', partner_id)])
    #
    #                 new_data = {
    #                             "subject": values['subject'] if values['subject'] else email_obj.body,
    #                             # "importance": "high",
    #                             "body": {
    #                                 "contentType": "HTML",
    #                                 "content": email_obj.body
    #                             },
    #                             "toRecipients": [
    #                                 {
    #                                     "emailAddress": {
    #                                         "address": partner_obj.email
    #                                     }
    #                                 }
    #                             ]
    #                         }
    #                 try:
    #                     response = requests.post(
    #                         'https://graph.microsoft.com/v1.0/me/messages', data=json.dumps(new_data),
    #                                             headers={
    #                                                 'Host': 'outlook.office.com',
    #                                                 'Authorization': 'Bearer {0}'.format(user.token),
    #                                                 'Accept': 'application/json',
    #                                                 'Content-Type': 'application/json',
    #                                                 'X-Target-URL': 'http://outlook.office.com',
    #                                                 'connection': 'keep-Alive'
    #                                             })
    #
    #                     result = json.loads((response.content.decode('utf-8')))
    #
    #                     if 'conversationId' in result.keys():
    #                         conv_id = result['conversationId']
    #
    #                     if 'conversationIndex' in result.keys():
    #                         conv_index_id = result['conversationIndex']
    #
    #                     if 'id' in result.keys():
    #                         o365_id = result['id']
    #                         if email_obj.attachment_ids:
    #                             for attachment in self.getAttachments(email_obj.attachment_ids):
    #                                 attachment_response = requests.post(
    #                                     'https://graph.microsoft.com/beta/me/messages/' + o365_id + '/attachments',
    #                                     data=json.dumps(attachment),
    #                                     headers={
    #                                         'Host': 'outlook.office.com',
    #                                         'Authorization': 'Bearer {0}'.format(user.token),
    #                                         'Accept': 'application/json',
    #                                         'Content-Type': 'application/json',
    #                                         'X-Target-URL': 'http://outlook.office.com',
    #                                         'connection': 'keep-Alive'
    #                                     })
    #                         send_response = requests.post(
    #                             'https://graph.microsoft.com/v1.0/me/messages/' + o365_id + '/send',
    #                             headers={
    #                                 'Host': 'outlook.office.com',
    #                                 'Authorization': 'Bearer {0}'.format(user.token),
    #                                 'Accept': 'application/json',
    #                                 'Content-Type': 'application/json',
    #                                 'X-Target-URL': 'http://outlook.office.com',
    #                                 'connection': 'keep-Alive'
    #                             })
    #                         # print('send_response', json.loads((send_response.content.decode('utf-8'))))
    #
    #                         message = super(CustomMessage, self).create(values)
    #                         message.email_from = None
    #                         val_message_update = {}
    #                         if conv_id:
    #                             message.office_id = conv_id
    #                             val_message_update['office_id'] = conv_id
    #                         if conv_index_id:
    #                             val_message_update['mail_conversationIndex'] = conv_index_id
    #                         if val_message_update:
    #                             email_obj.write(val_message_update)
    #                         return message
    #                     else:
    #                         raise UserError('ABCBCBCBB Xay ra loi')
    #                         # print('Check your credentials! Mail does not send due to invlide office365 credentials ')
    #                 except Exception as e:
    #                     print(e)
    #                     raise UserError('ABCBCBCBB_1')
    #             else:
    #
    #                 return super(CustomMessage, self).create(values)
    #
    #         else:
    #             # print('Office354 Token is missing.. Please add your account token and try again!')
    #             return super(CustomMessage, self).create(values)
    #
    #     else:
    #         return super(CustomMessage, self).create(values)

    def getAttachments(self, attachment_ids):
        attachment_list = []
        if attachment_ids:
            # attachments = self.env['ir.attachment'].browse([id[0] for id in attachment_ids])
            attachments = self.env['ir.attachment'].search([('id', 'in', [i.id for i in attachment_ids])])
            for attachment in attachments:
                attachment_list.append({
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": attachment.name,
                    "contentBytes": attachment.datas.decode("utf-8")
                })
        return attachment_list

    def generate_refresh_token(self):
        context = self._context

        current_uid = context.get('uid')

        user = self.env['res.users'].browse(current_uid)
        if user.refresh_token:
            settings = self.env['office.settings'].search([])
            settings = settings[0] if settings else settings

            if not settings.client_id or not settings.redirect_url or not settings.secret:
                raise osv.except_osv(_("Error!"), (_("Please ask admin to add Office365 settings!")))
            header = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }


            response = requests.post(
                'https://login.microsoftonline.com/common/oauth2/v2.0/token',
                data='grant_type=refresh_token&refresh_token=' + user.refresh_token + '&redirect_uri=' + settings.redirect_url + '&client_id=' + settings.client_id + '&client_secret=' + settings.secret
                , headers=header).content

            response = json.loads((str(response)[2:])[:-1])
            if 'access_token' not in response:
                response["error_description"] = response["error_description"].replace("\\r\\n", " ")
                raise osv.except_osv(_("Error!"), (_(response["error"] + " " + response["error_description"])))
            else:
                user.token = response['access_token']
                user.refresh_token = response['refresh_token']
                user.expires_in = int(round(time.time() * 1000))
                self.env.cr.commit()


class CustomActivity(models.Model):
    _inherit = 'mail.activity'

    office_id = fields.Char('Office365 Id')

    @api.model
    def create(self, values):
        if self.env.user.expires_in:
            expires_in = datetime.fromtimestamp(int(self.env.user.expires_in) / 1e3)
            expires_in = expires_in + timedelta(seconds=3600)
            nowDateTime = datetime.now()
            if nowDateTime > expires_in:
                self.generate_refresh_token()

        o365_id = None
        if self.env.user.office365_email and not self.env.user.is_task_sync_on and values[
            'res_id'] == self.env.user.partner_id.id:
            data = {
                'subject': values['summary'] if values['summary'] else values['note'],
                "body": {
                    "contentType": "html",
                    "content": values['note']
                },
                "dueDateTime": {
                    "dateTime": values['date_deadline'] + 'T00:00:00Z',
                    "timeZone": "UTC"
                },
            }
            response = requests.post(
                'https://graph.microsoft.com/beta/me/outlook/tasks', data=json.dumps(data),
                headers={
                    'Host': 'outlook.office.com',
                    'Authorization': 'Bearer {0}'.format(self.env.user.token),
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-Target-URL': 'http://outlook.office.com',
                    'connection': 'keep-Alive'
                }).content
            if 'id' in json.loads((response.decode('utf-8'))).keys():
                o365_id = json.loads((response.decode('utf-8')))['id']

        """
        original code!
        """

        activity = super(CustomActivity, self).create(values)
        self.env[activity.res_model].browse(activity.res_id).message_subscribe(
            partner_ids=[activity.user_id.partner_id.id])
        if activity.date_deadline <= fields.Date.today():
            self.env['bus.bus'].sendone(
                (self._cr.dbname, 'res.partner', activity.user_id.partner_id.id),
                {'type': 'activity_updated', 'activity_created': True})
        if o365_id:
            activity.office_id = o365_id
        return activity

    def generate_refresh_token(self):

        if self.env.user.refresh_token:
            settings = self.env['office.settings'].search([])
            settings = settings[0] if settings else settings

            if not settings.client_id or not settings.redirect_url or not settings.secret:
                raise osv.except_osv(_("Error!"), (_("Please ask admin to add Office365 settings!")))

            header = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = requests.post(
                'https://login.microsoftonline.com/common/oauth2/v2.0/token',
                data='grant_type=refresh_token&refresh_token=' + self.env.user.refresh_token + '&redirect_uri=' + settings.redirect_url + '&client_id=' + settings.client_id + '&client_secret=' + settings.secret
                , headers=header).content

            response = json.loads((str(response)[2:])[:-1])
            if 'access_token' not in response:
                response["error_description"] = response["error_description"].replace("\\r\\n", " ")
                raise osv.except_osv(("Error!"), (response["error"] + " " + response["error_description"]))
            else:
                self.env.user.token = response['access_token']
                self.env.user.refresh_token = response['refresh_token']
                self.env.user.expires_in = int(round(time.time() * 1000))

    # @api.multi
    def unlink(self):
        for activity in self:
            if activity.office_id:
                response = requests.delete(
                    'https://graph.microsoft.com/beta/me/outlook/tasks/' + activity.office_id,
                    headers={
                        'Host': 'outlook.office.com',
                        'Authorization': 'Bearer {0}'.format(self.env.user.token),
                        'Accept': 'application/json',
                        'Content-Type': 'application/json',
                        'X-Target-URL': 'http://outlook.office.com',
                        'connection': 'keep-Alive'
                    })
                if response.status_code != 204 and response.status_code != 404:
                    raise osv.except_osv(_("Office365 SYNC ERROR"), (_("Error: " + str(response.status_code))))
            if activity.date_deadline <= fields.Date.today():
                self.env['bus.bus'].sendone(
                    (self._cr.dbname, 'res.partner', activity.user_id.partner_id.id),
                    {'type': 'activity_updated', 'activity_deleted': True})
        return super(CustomActivity, self).unlink()


class CustomContacts(models.Model):

    _inherit = 'res.partner'

    office_contact_id = fields.Char('Office365 Id')

