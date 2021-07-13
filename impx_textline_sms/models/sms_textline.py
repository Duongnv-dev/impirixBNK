import requests
import json
# import phonenumbers
from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError, ValidationError


class SMSTextLine(models.TransientModel):
    _inherit = 'sms.composer'

    def action_send_sms(self):
        if self.number_field_name not in ['phone', 'mobile']:
            return super(SMSTextLine, self).action_send_sms()
        records = self._get_records()
        body = {
            "phone_number": self.get_number_text_line(),
            "comment": {
                'body': self.body
            }
        }
        text_line_request_values = self.send_textline_sms(body)
        sms_record_values = self._prepare_textline_sms_values(records, text_line_request_values)
        self._prepare_textline_sms(records, sms_record_values)
        return True

    def get_access_token(self, email, password, api_key):
        if not email or not password or not api_key:
            return False, False
        body_sign_in = {
            "user": {
                "email": email,
                "password": password,
            },
            "api_key": api_key,
        }
        try:
            responsive = requests.request('POST', 'https://application.textline.com/auth/sign_in.json?',
                                          json=body_sign_in)

            if not responsive.status_code == 201:
                return False, False
            result = json.loads(responsive.content)

            if not result.get('access_token', False):
                return False, False
            if not result['access_token'].get('token', False):
                return False, False
            group_list = []
            if result.get('user', False):
                if result['user'].get('group_uuids', False):
                    group_list = result['user'].get('group_uuids', False)
            return result['access_token']['token'], group_list
        except Exception:
            return False, False

    # def get_phone_group_dict(self, access_token, group_list):
    #     phone_group_dict = {}
    #     if not access_token or not group_list:
    #         return phone_group_dict
    #     for group_uuids in group_list:
    #         phone_number = self.get_phone_from_group_uuids(access_token, group_uuids)
    #         if phone_number:
    #             phone_number = self.env['res.partner'].sudo().phone_format(phone_number)
    #             phone_group_dict[phone_number] = group_uuids
    #     return phone_group_dict

    def get_phone_group_dict(self, access_token, group_uuids):
        phone_group_dict = {}
        headers = {'X-TGP-ACCESS-TOKEN': access_token}
        try:
            res = requests.get('https://application.textline.com/api/groups.json?uuid={}'.format(group_uuids), headers=headers)
            if res.status_code != 200:
                return False
            result = json.loads(res.content)
            if not result:
                return phone_group_dict
            for res in result:
                if res.get('phone_number', False):
                    phone_number = self.env['res.partner'].sudo().phone_format(res['phone_number'])
                    if res.get('uuid', False):
                        phone_group_dict[phone_number] = res['uuid']
            return phone_group_dict
        except Exception:
            raise phone_group_dict

    def send_textline_sms(self, body):
        email = self.env.user.text_line_user
        password = self.env.user.text_line_password
        api_key = self.env.user.text_line_api_key
        access_token, group_list = self.get_access_token(email, password, api_key)
        phone_group_dict = {}
        if group_list:
            phone_group_dict = self.get_phone_group_dict(access_token, group_list[0])
        phone_number = self.env.user.text_line_number
        group_uuid = phone_group_dict.get(phone_number, False)
        if group_uuid:
            body['group_uuid'] = group_uuid
        if not access_token:
            raise ValidationError(
                _("Could not connect to TextLine. Please contact the administrator to check connection configuration"))
        headers = {'X-TGP-ACCESS-TOKEN': access_token}
        try:
            res = requests.post('https://application.textline.com/api/conversations.json?', headers=headers, json=body)
            if res.status_code != 200 or res.reason != 'OK':
                raise ValidationError(_("The error occurred, please try again later"))
            result = json.loads(res.content)
            return result
        except Exception:
            raise ValidationError(_("The error occurred, please try again later"))

    @api.depends('partner_ids', 'res_model', 'res_id', 'res_ids', 'use_active_domain', 'composition_mode', 'number_field_name', 'sanitized_numbers')
    def get_number_text_line(self):
        if self.partner_ids:
            return self.partner_ids[0].phone or self.partner_ids[0].mobile or None if len(self.partner_ids) == 1 else None
        elif self.composition_mode in ('comment', 'mass') and self.res_model:
            records = self._get_records()
            if records and issubclass(type(records), self.pool['mail.thread']):
                res = records._sms_get_recipients_info(force_field=self.number_field_name)
                return res[records.id]['sanitized'] or None if len(records) == 1 else None
            else:
                return None
        else:
            return None

    def _prepare_textline_sms(self, records, sms_record_values):
        sms_create_vals = [sms_record_values[record.id] for record in records]
        return self.env['sms.sms'].sudo().create(sms_create_vals)

    def _prepare_textline_sms_values(self, records, text_line_request_values):
        all_bodies = self._prepare_body_values(records)
        all_recipients = self._prepare_recipient_values(records)
        done_ids = self._get_done_record_ids(records, all_recipients)
        result = {}
        for record in records:
            recipients = all_recipients[record.id]
            sanitized = recipients['sanitized']
            if sanitized and record.id in done_ids:
                state = 'canceled'
                error_code = 'sms_duplicate'
            elif not sanitized:
                state = 'error'
                error_code = 'sms_number_format' if recipients['number'] else 'sms_number_missing'
            else:
                state = 'outgoing'
                error_code = ''

            result[record.id] = {
                'body': all_bodies[record.id],
                'partner_id': recipients['partner'].id,
                'number': sanitized if sanitized else recipients['number'],
                'state': state,
                'error_code': error_code,
                'post_uuid': text_line_request_values['post']['uuid'] or None,
                'creator_uuid': text_line_request_values['post']['creator']['uuid'] or None,
                'creator_email': text_line_request_values['post']['creator']['email'] or None,
                'conversation_uuid': text_line_request_values['post']['conversation_uuid'] or None,
                'customer_uuid': text_line_request_values['conversation']['customer']['uuid'] or None,
                'res_model': self.res_model,
                'res_id': self.res_id,
                'author_id': self.env['res.users'].browse(self.env.uid).partner_id.id
            }
        return result

class InheritSmsSms(models.Model):
    _inherit = 'sms.sms'

    post_uuid = fields.Char()
    creator_uuid = fields.Char()
    creator_email = fields.Char()
    conversation_uuid = fields.Char()
    customer_uuid = fields.Char()
    res_model = fields.Char()
    res_id = fields.Integer()
    author_id = fields.Integer()
