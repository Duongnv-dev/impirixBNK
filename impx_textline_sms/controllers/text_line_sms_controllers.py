from datetime import datetime
from odoo import http
from odoo.http import request
import json


class TextLineSmsControllers(http.Controller):
    @http.route('/new_outbound_post', type='json', auth="public", website=True, csrf=False)
    def new_outbound_post(self, **post):
        data = http.request.jsonrequest
        res_partner = request.env['res.partner'].sudo()
        if 'post' in data and 'webhook' in data:
            if data['webhook'] == 'new_outbound_post':
                if 'uuid' in data['post'] and 'conversation_uuid' in data['post']:
                    record = request.env['sms.sms'].sudo().search([('post_uuid', '=', data['post']['uuid']),
                                                                   ('conversation_uuid', '=',
                                                                    data['post']['conversation_uuid'])])
                    if 'customer' in data['conversation']:
                        if 'phone_number' in data['conversation']['customer']:
                            if record:
                                record.write({'state': 'sent'})
                                name = ''
                                email = ''
                                if 'creator' in data['post']:
                                    if 'name' in data['post']['creator']:
                                        name = data['post']['creator']['name']
                                    if 'email' in data['post']['creator']:
                                        email = data['post']['creator']['email']
                                email_from = '''"''' + name + '''"<''' + email + '''>'''
                                textline_number = res_partner.phone_format(data['conversation']['customer']['phone_number'])
                                partners = request.env['res.partner'].sudo().search(['|', ('phone', '=', textline_number),
                                                                                     ('mobile', '=', textline_number)])
                                body = '<b>SMS:</b><br/> {}'.format(record.body)
                                for partner in partners:
                                    self.create_mail_message(partner.id, body, email_from, record.author_id)
                            else:
                                number = res_partner.phone_format(data['conversation']['customer']['phone_number'])
                                partners = res_partner.search(['|', ('phone', '=', number), ('mobile', '=', number)])
                                author_id = request.env['res.users'].sudo().search([('text_line_user', '=',
                                                                                     data['post']['creator']['email'])],
                                                                                   limit=1).partner_id.id
                                email_from = ''
                                if 'group' in data:
                                    if 'phone_number' in data['group']:
                                        email_from = '<b>SMS sent from TextLine App by {}:</b><br/>'.format(data['group']['phone_number'])
                                if partners:
                                    for partner in partners:
                                        body = email_from + data['post']['body']
                                        self.create_mail_message(partner.id, body, email_from, author_id)
                                else:
                                    name = ''
                                    if 'name' in data['conversation']['customer']:
                                        if data['conversation']['customer']['name']:
                                            name = data['conversation']['customer']['name']
                                            if not name:
                                                name = data['conversation']['customer']['phone_number']
                                    sms_text_line = res_partner.phone_format(
                                        data['conversation']['customer']['phone_number'])
                                    email = ''
                                    if 'email' in data['conversation']['customer']:
                                        email = data['conversation']['customer']['email']
                                    res_users = request.env['res.users'].sudo()
                                    res_users_email_id = None
                                    if 'email' in data['post']['creator']:
                                        res_users_email_id = res_users.search(
                                            [('text_line_user', '=', data['post']['creator']['email'])], limit=1).id
                                    if 'phone_number' in data['post']['creator']:
                                        res_users_number_id = res_users.search(
                                            [('text_line_user', '=', data['post']['creator']['phone_number'])],
                                            limit=1).id
                                    if res_users_email_id:
                                        saleperson_id = res_users_email_id
                                    else:
                                        saleperson_id = res_users_number_id
                                    partner = self.create_partner(name, sms_text_line, saleperson_id, email)
                                    body = email_from + data['post']['body']
                                    self.create_mail_message(partner.id, body, email_from, author_id)
        return json.dumps({'result': True})

    @http.route('/new_customer_post', type='json', auth="public", website=True, csrf=False)
    def new_customer_post(self, **post):
        res_partner = request.env['res.partner'].sudo()
        data = http.request.jsonrequest
        if 'post' in data and 'webhook' in data:
            if data['webhook'] == 'new_customer_post':
                if 'creator' in data['post']:
                    if 'phone_number' in data['post']['creator'] and 'name' in data['post']['creator']:
                        number = res_partner.phone_format(data['post']['creator']['phone_number'])
                        author_ids = res_partner.search(['|', ('phone', '=', number), ('mobile', '=', number),
                                                        ('active', 'in', [True, False])])
                        if author_ids:
                            email = ''
                            for author_id in author_ids:
                                name = author_id.name
                                if author_id.email:
                                    email = '''<''' + author_id.email + '>'
                                body = '<b>SMS from {}:</b><br/> {}'.format(data['post']['creator']['phone_number'], data['post']['body'])
                                email_from = name + email
                                self.create_mail_message(author_id.id, body, email_from, author_id.id)
        return json.dumps({'result': True})

    def create_partner(self, name, sms_text_line, saleperson_id, email):
        res_partner = request.env['res.partner'].sudo()
        partner = res_partner.create({
            'name': name,
            'type': 'contact',
            'phone': sms_text_line,
            'mobile': sms_text_line,
            'is_company': False,
            'user_id': saleperson_id,
            'email': email
        })
        return partner

    def create_mail_message(self, res_id, body, email_from, author_id):
        vals = {
            'model': 'res.partner',
            'res_id': res_id,
            'body': body,
            'date': datetime.now(),
            'email_from': email_from,
            'message_type': 'sms',
        }
        if author_id:
            vals['author_id'] = author_id
        request.env['mail.message'].sudo().create(vals)
