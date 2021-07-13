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
from dateutil.parser import *

_logger = logging.getLogger(__name__)
_image_dataurl = re.compile(r'(data:image/[a-z]+?);base64,([a-z0-9+/]{3,}=*)([\'"])', re.I)
_import_history = {}


class Office365(models.Model):
    """
    This class give functionality to user for Office365 Integration
    """
    _name = 'office.sync'

    field_name = fields.Char(string="office365", required=False, )
    code = fields.Char('code', related='res_user.code', readonly=True)
    office365_email = fields.Char('Office365 Email Address', compute='compute_value', readonly=True)
    office365_id_address = fields.Char('Office365 Id Address', compute='compute_value', readonly=True)
    send_mail_flag = fields.Boolean(string='Send messages using office365 Mail', default=True)
    is_active = fields.Boolean('Active Office365 Account')
    is_inbox = fields.Boolean(string="Sync inbox")

    is_sent = fields.Boolean(string="Sync Send")

    def default_user(self):
        return self.env.user.id

    res_user = fields.Many2one('res.users', string='User', default=default_user, readonly=True)
    is_manual_sync = fields.Boolean(string="Custom Date Range", )
    is_auto_sync = fields.Boolean(string="Auto Scheduler", )
    mail_import = fields.Datetime(string="Emails", compute='get_computed_date', required=False, readonly=True)
    calender_import = fields.Datetime(string="Calender", compute='get_computed_date', required=False, readonly=True)
    task_import = fields.Datetime(string="Tasks", compute='get_computed_date', required=False, readonly=True)
    task_export = fields.Datetime(string="Last Export", compute='get_computed_date', required=False, readonly=True)
    calender_export = fields.Datetime(string="Last Export", compute='get_computed_date', required=False, readonly=True)
    contact_export = fields.Datetime(string="Last Export", compute='get_computed_date', required=False, readonly=True)
    contact_import = fields.Datetime(string="Contacts", compute='get_computed_date', required=False, readonly=True)

    is_import_contact = fields.Boolean()
    is_import_email = fields.Boolean(default=True)
    is_import_calendar = fields.Boolean()
    is_import_task = fields.Boolean()

    is_export_contact = fields.Boolean()
    is_export_calendar = fields.Boolean()
    is_export_task = fields.Boolean()

    interval_number = fields.Integer(string="Time Interval", required=False, )
    interval_unit = fields.Selection([
        ('minutes', 'Minutes'),
        ('hours', 'Hours'),
        # ('work_days', 'Work Days'),
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months'),
    ], string='Interval Unit')
    from_date = fields.Datetime(string="From Date", required=False, )
    to_date = fields.Datetime(string="To Date", required=False, )
    history_line = fields.One2many('sync.history', 'sync_id', copy=True)
    ex_history_line = fields.One2many('export.history', 'sync_export_id', copy=True)

    is_manual_execute = fields.Boolean(string="Manual Execute",  )
    categories = fields.Many2many('calendar.event.type', string='Select Event Category')
    all_event = fields.Boolean(string="All categories events", )

    user_manual_sync_ids = fields.Many2many('res.users', 'office_sync_res_users', 'office_sync_id', 'user_sync_id')

    special_email_ids = fields.Many2many('office365.mail.address', 'office_sync_mail_address',
                                         'office_sync', 'mail_address_id')

    @api.constrains('from_date', 'to_date')
    def _check_from_date_to_date(self):
        if self.from_date and self.to_date:
            if self.to_date < self.from_date:
                raise ValidationError(_('To Date must be greater than From Date'))

    def add_special_email(self):
        action_obj = self.env.ref('odoo_office365.action_wizard_add_special_mail')
        action = action_obj.read([])[0]
        action['context'] = {'default_office_sync_id': self.id}
        if self.special_email_ids:
            action['context']['default_special_email_ids'] = [(6, 0, self.special_email_ids._ids)]
        return action

    def get_users_connect_office_365(self):
        res_users = self.env['res.users'].search([('office365_email', '!=', False), ('allow_connect_365', '!=', False)])
        return res_users

    # sync only email
    def sync_data(self):
        self.is_manual_execute = True
        if self.user_manual_sync_ids:
            users_connect = self.user_manual_sync_ids
        else:
            users_connect = self.get_users_connect_office_365()
        if not self.is_manual_sync or not self.from_date or not self.to_date:
            raise ValidationError('Please input the from date and to date before synchronizing manually!')
        if self.is_import_email:
            is_manual = True
            for res_user in users_connect:
                self.sudo().with_delay().sync_customer_mail_each_user(is_manual, res_user, self.from_date, self.to_date)
        self.is_manual_execute = False
        self.is_manual_sync = False
        self.from_date = False
        self.to_date = False
        self.user_manual_sync_ids = False
        return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }

    @api.depends('res_user')
    def get_computed_date(self):
        """
        @api.depends() should contain all fields that will be used in the calculations.
        """
        if self.res_user:
            self.mail_import = self.res_user.last_mail_import
            self.calender_import = self.res_user.last_calender_import
            self.contact_import = self.res_user.last_contact_import
            self.task_import = self.res_user.last_task_import

    @api.depends('res_user')
    def compute_value(self):
        self.office365_id_address = self.res_user.office365_id_address
        self.office365_email = self.res_user.office365_email

    def get_attachment(self, message):
        context = self._context
        current_uid = context.get('uid')
        res_user = self.env['res.users'].browse(current_uid)
        if res_user.expires_in:
            expires_in = datetime.fromtimestamp(int(res_user.expires_in) / 1e3)
            expires_in = expires_in + timedelta(seconds=3600)
            nowDateTime = datetime.now()
            if nowDateTime > expires_in:
                self.generate_refresh_token()

        response = requests.get(
            'https://graph.microsoft.com/v1.0/me/messages/' + message['id'] + '/attachments/',
            headers={
                'Host': 'outlook.office.com',
                'Authorization': 'Bearer {0}'.format(res_user.token),
                'Accept': 'application/json',
                'X-Target-URL': 'http://outlook.office.com',
                'connection': 'keep-Alive'
            }).content
        attachments = json.loads((response.decode('utf-8')))['value']
        attachment_ids = []
        for attachment in attachments:
            _logger.info('Importing attachments of email from office')
            if 'contentBytes' not in attachment or 'name' not in attachment:
                continue
            odoo_attachment = self.env['ir.attachment'].create({
                'datas': attachment['contentBytes'],
                'name': attachment["name"],
                'store_fname': attachment["name"]})
            self.env.cr.commit()
            attachment_ids.append(odoo_attachment.id)
        return attachment_ids

    def getAttachment(self, message, res_user):
        if res_user.expires_in:
            expires_in = datetime.fromtimestamp(int(res_user.expires_in) / 1e3)
            expires_in = expires_in + timedelta(seconds=3600)
            nowDateTime = datetime.now()
            if nowDateTime > expires_in:
                self.generate_refresh_token()

        response = requests.get(
            'https://graph.microsoft.com/v1.0/me/messages/' + message['id'] + '/attachments/',
            headers={
                'Host': 'outlook.office.com',
                'Authorization': 'Bearer {0}'.format(res_user.token),
                'Accept': 'application/json',
                'X-Target-URL': 'http://outlook.office.com',
                'connection': 'keep-Alive'
            }).content
        attachments = json.loads((response.decode('utf-8')))['value']
        attachment_ids = []
        for attachment in attachments:
            if 'contentBytes' not in attachment or 'name' not in attachment:
                continue
            odoo_attachment = self.env['ir.attachment'].create({
                'datas': attachment['contentBytes'],
                'name': attachment["name"],
                'store_fname': attachment["name"]})
            self.env.cr.commit()
            attachment_ids.append(odoo_attachment.id)
        return attachment_ids

    @api.model
    def sync_customer_mail_scheduler(self):
        try:
            res_users = self.env['res.users'].search([('office365_email', '!=', False)])
            for res_user in res_users:
                self.env.cr.commit()
                self.sync_customer_inbox_mail(None, res_user)
                self.sync_customer_sent_mail(None, res_user)
                res_user.last_mail_import = datetime.now()
        except Exception as e:
            self.env.cr.commit()
            raise ValidationError(_(str(e)))
        self.env.cr.commit()

        # self.sync_customer_mail()

    @api.model
    def create_queue_sync_mail_scheduler(self):
        res_users = self.get_users_connect_office_365()
        for res_user in res_users:
            task = u'office.sync().sync_customer_mail_each_user(None, {}, None, None)'.format(res_user)
            job = self.env['queue.job'].sudo().search([('func_string', '=', task), ('state', 'not in', ('done', 'fail'))])
            if not job:
                self.sudo().with_delay().sync_customer_mail_each_user(None, res_user, None, None)

    @job
    def sync_customer_mail_each_user(self, is_manual, res_user, from_date, to_date):
        status = None
        log = ''
        no_im_email = 0
        no_sent_email = 0
        history = self.env['sync.history'].sudo()
        time_now = datetime.now()
        clock = history.check_clock_interval(time_now)
        try:
            self.env.cr.commit()
            no_im_email = self.sync_customer_inbox_mail(is_manual, res_user, from_date, to_date)
            no_sent_email = self.sync_customer_sent_mail(is_manual, res_user, from_date, to_date)
            if not is_manual:
                res_user.sudo().last_mail_import = time_now
        except Exception as e:
            self.env.cr.commit()
            status = 'Error'
            log = e
            _logger.error(e)
        finally:
            type = None
            if not is_manual:
                type = 'auto'
            else:
                type = 'manual'
            his_status = status if status else 'Success'
            his_vals = {'last_sync': time_now,
                        'user_id': res_user.id or False,
                        'no_im_email': no_im_email,
                        'no_sent_email': no_sent_email,
                        'status': his_status,
                        'message_log': log,
                        'sync_type': type,
                        'no_up_task': 0,
                        'no_up_contact': 0,
                        'no_im_contact': 0,
                        'no_im_calender': 0,
                        'no_up_calender': 0,
                        'no_im_task': 0,
                        'sync_id': 1,
                        }
            if type == 'manual':
                his_vals['from_date'] = from_date
                his_vals['to_date'] = to_date
            if clock or no_im_email or no_sent_email or his_status == 'Error' or type == 'manual':
                history.create(his_vals)
        self.env.cr.commit()

    def sync_customer_inbox_mail(self, is_manual=None, res_user=None, from_date=None, to_date=None):
        new_email = []
        status = None
        no_im_email = 0
        if res_user.token:
            try:
                if res_user.expires_in:
                    expires_in = datetime.fromtimestamp(int(res_user.expires_in) / 1e3)
                    expires_in = expires_in + timedelta(seconds=3600)
                    nowDateTime = datetime.now()
                    if nowDateTime > expires_in:
                        self.auto_generate_refresh_token(res_user)
                _logger.info('Sending request to get folders of  outlook')

                inbox_id = self.get_mail_folder_id('inbox', res_user)
                if inbox_id:
                    _logger.info('inbox_id{}: {}'.format(res_user.name, inbox_id))

                    url = self.get_url_fetch_mail(is_manual, inbox_id, 'ReceivedDateTime', from_date, to_date, res_user)
                    response = requests.get(url,
                                            headers={
                                                'Host': 'outlook.office.com',
                                                'Authorization': 'Bearer {0}'.format(res_user.token),
                                                'Accept': 'application/json',
                                                'X-Target-URL': 'http://outlook.office.com',
                                                'connection': 'keep-Alive'
                                            }).content
                    result = json.loads((response.decode('utf-8')))
                    if 'value' not in result.keys():
                        raise osv.except_osv("ERROR!", "{}".format(result))
                    else:
                        messages = result['value']
                        for message in messages:
                            _logger.info('importing emails')
                            if 'from' not in message.keys() or self.env['mail.message'].search(
                                    [('office_id', '=', message['id'])]) or self.env['office365.mail'].search(
                                [('office_id', '=', message['id'])]):
                                continue

                            if 'address' not in message.get('from').get('emailAddress') or message['bodyPreview'] == "":
                                continue

                            attachment_ids = self.getAttachment(message, res_user)

                            email_from = message['from']['emailAddress']['address']
                            email_to_list = []
                            email_cc_list = []
                            email_bcc_list = []

                            internal_mail = False
                            for recipient in message['toRecipients']:
                                if self.check_internal_mail(message['from']['emailAddress']['address'], recipient['emailAddress']['address']):
                                    internal_mail = True
                                    break
                                email_to_list.append(recipient['emailAddress']['address'].lower())

                            for cc in message['ccRecipients']:
                                if (cc['emailAddress']['address'] in (res_user.office365_email, res_user.email)) and \
                                        self.check_internal_mail(message['from']['emailAddress']['address'], cc['emailAddress']['address']):
                                    internal_mail = True
                                    break
                                email_cc_list.append(cc['emailAddress']['address'].lower())

                            for bcc in message['bccRecipients']:
                                if (cc['emailAddress']['address'] in (res_user.office365_email, res_user.email)) and \
                                        self.check_internal_mail(message['from']['emailAddress']['address'], bcc['emailAddress']['address']):
                                    internal_mail = True
                                    break
                                email_bcc_list.append(bcc['emailAddress']['address'].lower())
                            if internal_mail:
                                continue
                            date = datetime.strptime(message['sentDateTime'], "%Y-%m-%dT%H:%M:%SZ")
                            _logger.info('importing email sent by: {}'.format(email_from))
                            office_mail = self.env['office365.mail'].sudo().create({
                                'subject': message['subject'],
                                'date': date,
                                'body': message['body']['content'],
                                'email_from': email_from,
                                'email_to': ';'.join(email_to_list),
                                'email_cc': ';'.join(email_cc_list),
                                'email_bcc': ';'.join(email_bcc_list),
                                'attachment_ids': [[6, 0, attachment_ids]],
                                'office_id': message['id'],
                                'mail_conversationIndex': message['conversationIndex'],
                                'type': 'inbox',
                                'user_id': res_user.id,
                            })
                            self.env['office365.mail'].sudo().with_delay().assign_mail_to_partner(office_mail.id)
                            new_email.append(message['id'])
                            self.env.cr.commit()
            except Exception as e:
                status = 'Error'
                _logger.error('Exception_inbox_{}: '.format(res_user.name, e))
                raise ValidationError(_(str(e)))

            no_im_email = len(new_email) if new_email else 0
            self.env.cr.commit()
        return no_im_email

    def sync_customer_sent_mail(self, is_manual=None, res_user=None, from_date=None, to_date=None):
        """
        :return:
        """
        new_email = []
        status = None
        no_sent_email = 0
        if res_user.token:
            try:
                if res_user.expires_in:
                    expires_in = datetime.fromtimestamp(int(res_user.expires_in) / 1e3)
                    expires_in = expires_in + timedelta(seconds=3600)
                    nowDateTime = datetime.now()
                    if nowDateTime > expires_in:
                        self.auto_generate_refresh_token(res_user)

                sentbox_id = self.get_mail_folder_id('sentitems', res_user)
                if sentbox_id:
                    _logger.info('sentbox_id_{}: {}'.format(res_user.name, sentbox_id))
                    # filter by time
                    url = self.get_url_fetch_mail(is_manual, sentbox_id, 'sentDateTime', from_date, to_date, res_user)
                    _logger.info('url_{}: {}'.format(res_user.name, url))
                    response = requests.get(url,
                                            headers={'Host': 'outlook.office.com',
                                                     'Authorization': 'Bearer {0}'.format(res_user.token),
                                                     'Accept': 'application/json',
                                                     'X-Target-URL': 'http://outlook.office.com',
                                                     'connection': 'keep-Alive'}).content
                    result = json.loads((response.decode('utf-8')))
                    if 'value' not in result.keys():
                        raise osv.except_osv("ERROR!", "{}".format(result))
                    else:
                        messages = result['value']
                        for message in messages:
                            if 'from' not in message.keys() or self.env['mail.message'].search(
                                    [('office_id', '=', message['conversationId']),
                                     ('mail_conversationIndex', '=', message['conversationIndex'])]) \
                                    or self.env['office365.mail'].search(
                                [('office_id', '=', message['conversationId']),
                                 ('mail_conversationIndex', '=', message['conversationIndex'])]):
                                continue

                            if message['body']['content'] == "":
                                continue

                            attachment_ids = self.getAttachment(message, res_user)

                            email_from = message['from']['emailAddress']['address']
                            email_to_list = []
                            email_cc_list = []
                            email_bcc_list = []

                            for recipient in message['toRecipients']:
                                if self.check_internal_mail(email_from, recipient['emailAddress']['address']):
                                    continue
                                email_to_list.append(recipient['emailAddress']['address'].lower())

                            for cc in message['ccRecipients']:
                                email_cc_list.append(cc['emailAddress']['address'].lower())

                            for bcc in message['bccRecipients']:
                                email_bcc_list.append(bcc['emailAddress']['address'].lower())

                            date = datetime.strptime(message['sentDateTime'], "%Y-%m-%dT%H:%M:%SZ")
                            _logger.info('importing email sent by: {}'.format(email_from))
                            office_mail = self.env['office365.mail'].sudo().create({
                                'subject': message['subject'],
                                'date': date,
                                'body': message['body']['content'],
                                'email_from': email_from,
                                'email_to': ';'.join(email_to_list),
                                'email_cc': ';'.join(email_cc_list),
                                'email_bcc': ';'.join(email_bcc_list),
                                'attachment_ids': [[6, 0, attachment_ids]],
                                'office_id': message['conversationId'],
                                'mail_conversationIndex': message['conversationIndex'],
                                'type': 'outbox',
                                'user_id': res_user.id,
                            })
                            self.env['office365.mail'].sudo().with_delay().assign_mail_to_partner(office_mail.id)
                            new_email.append(message['id'])
                            self.env.cr.commit()

            except Exception as e:
                status = 'Error'
                _logger.error('Exception_sent_{}: '.format(res_user.name, e))
                raise ValidationError(_(str(e)))

            no_sent_email = len(new_email) if new_email else 0
            self.env.cr.commit()
        return no_sent_email

    def get_mail_folder_id(self, folder_type, res_user):
        response = requests.get(
            'https://graph.microsoft.com/v1.0/me/mailFolders',
            headers={
                'Host': 'outlook.office.com',
                'Authorization': 'Bearer {0}'.format(res_user.token),
                'Accept': 'application/json',
                'X-Target-URL': 'http://outlook.office.com',
                'connection': 'keep-Alive'
            }).content
        result = json.loads((response.decode('utf-8')))
        folder_id = False
        if 'value' in result.keys():
            folders = json.loads((response.decode('utf-8')))['value']
            _logger.info('folder_mail_from_sync_{}: {}'.format(res_user.name, folders))
            folder_id_list = []
            if folder_type == 'inbox':
                folder_id_list = [folder['id'] for folder in folders if folder['displayName'] == 'Inbox']
            elif folder_type == 'sentitems':
                folder_id_list = [folder['id'] for folder in folders if folder['displayName'] == 'Sent Items']
            if folder_id_list:
                folder_id = folder_id_list[0]

        # If there is an error or not get the folder in response
        if 'value' not in result.keys() or not folder_id:
            folder_id = self.get_mail_folder_by_whell_know_name(folder_type, res_user)
        return folder_id

    def get_mail_folder_by_whell_know_name(self, folder_type, res_user):
        response = requests.get('https://graph.microsoft.com/v1.0/me/mailFolders/{}'.format(folder_type),
                                headers={
                                    'Host': 'outlook.office.com',
                                    'Authorization': 'Bearer {0}'.format(res_user.token),
                                    'Accept': 'application/json',
                                    'X-Target-URL': 'http://outlook.office.com',
                                    'connection': 'keep-Alive'
                                }).content
        result = json.loads((response.decode('utf-8')))
        if 'error' in result.keys():
            return False
        return result.get('id', False)

    def get_url_fetch_mail(self, is_manual, mailbox_id, field_filter, from_date, to_date, res_user):
        url = ''
        if is_manual:
            if from_date and to_date:
                url = 'https://graph.microsoft.com/v1.0/me/mailFolders/' + mailbox_id + \
                      '/messages?$top=10000&$count=true&$filter={} ge {} and {} le {}' \
                    .format(field_filter, from_date.strftime("%Y-%m-%dT%H:%M:%SZ"), field_filter,
                            to_date.strftime("%Y-%m-%dT%H:%M:%SZ"))
            else:
                if res_user.last_mail_import:
                    url = 'https://graph.microsoft.com/v1.0/me/mailFolders/' + mailbox_id + \
                          '/messages?$top=10000&$count=true&$filter={} ge {} and {} le {}' \
                        .format(field_filter, res_user.last_mail_import.strftime("%Y-%m-%dT%H:%M:%SZ"), field_filter,
                                datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
                else:
                    url = 'https://graph.microsoft.com/v1.0/me/mailFolders/' + mailbox_id + '/messages?$top=10000&$count=true'
        else:
            if res_user.last_mail_import:
                url = 'https://graph.microsoft.com/v1.0/me/mailFolders/' + mailbox_id + \
                      '/messages?$top=10000&$count=true&$filter={} ge {} and {} le {}' \
                    .format(field_filter, res_user.last_mail_import.strftime("%Y-%m-%dT%H:%M:%SZ"), field_filter,
                            datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
            else:
                url = 'https://graph.microsoft.com/v1.0/me/mailFolders/' + mailbox_id + '/messages?$top=10000&$count=true'
        return url

    def check_internal_mail(self, email_from, recipient):
        sent_user = self.env['res.users'].search(['|', ('office365_email', "=", email_from), ('email', '=', email_from)])
        recipient_user = self.env['res.users'].search(['|', ('office365_email', "=", recipient), ('email', '=', recipient)])
        if sent_user and recipient_user:
            return True
        else:
            return False

    def get_partner_to_write_email(self, salepersons, customers):
        partner_assigned = self.env['res.partner'].search([('user_id', 'in', salepersons._ids)])
        partner_to_write_email = []
        for customer in customers:
            if customer in partner_assigned:
                if customer.is_company:
                    partner_to_write_email.append(customer)
                else:
                    partner_to_write_email.append(customer.parrent_id)
        return partner_to_write_email

    def generate_refresh_token(self):
        context = self._context
        current_uid = context.get('uid')
        res_user = self.env['res.users'].browse(current_uid)

        if res_user.refresh_token:
            settings = self.env['office.settings'].search([])
            settings = settings[0] if settings else settings

            if not settings.client_id or not settings.redirect_url or not settings.secret:
                raise osv.except_osv(_("Error!"), (_("Please ask admin to add Office365 settings!")))

            header = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = requests.post(
                'https://login.microsoftonline.com/common/oauth2/v2.0/token',
                data='grant_type=refresh_token&refresh_token=' + res_user.refresh_token + '&redirect_uri=' + settings.redirect_url + '&client_id=' + settings.client_id + '&client_secret=' + settings.secret
                , headers=header).content

            response = json.loads((str(response)[2:])[:-1])
            if 'access_token' not in response:
                response["error_/opt/odoo13/custom_addons/odoo_xerodescription"] = response[
                    "error_description"].replace("\\r\\n", " ")
                raise osv.except_osv(_("Error!"), (_(response["error"] + " " + response["error_description"])))
            else:
                res_user.token = response['access_token']
                res_user.refresh_token = response['refresh_token']
                res_user.expires_in = int(round(time.time() * 1000))
        else:
            _logger.error('Refresh token not found!')

    def auto_generate_refresh_token(self, res_user):
        if res_user.refresh_token:
            settings = self.env['office.settings'].search([])
            settings = settings[0] if settings else settings

            if not settings.client_id or not settings.redirect_url or not settings.secret:
                raise osv.except_osv(_("Error!"), (_("Please ask admin to add Office365 settings!")))

            header = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = requests.post(
                'https://login.microsoftonline.com/common/oauth2/v2.0/token',
                data='grant_type=refresh_token&refresh_token=' + res_user.refresh_token + '&redirect_uri=' + settings.redirect_url + '&client_id=' + settings.client_id + '&client_secret=' + settings.secret
                , headers=header).content

            response = json.loads((str(response)[2:])[:-1])
            if 'access_token' not in response:
                response["error_/opt/odoo13/custom_addons/odoo_xerodescription"] = response[
                    "error_description"].replace("\\r\\n", " ")
                raise osv.except_osv(_("Error!"), (_(response["error"] + " " + response["error_description"])))
            else:
                res_user.token = response['access_token']
                res_user.refresh_token = response['refresh_token']
                res_user.expires_in = int(round(time.time() * 1000))
        else:
            _logger.error('Refresh token not found!')
