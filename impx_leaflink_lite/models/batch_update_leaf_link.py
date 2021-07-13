import datetime
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
import requests, json, logging
from odoo import fields, api, models, _, SUPERUSER_ID
from dateutil.parser import *
from odoo.http import request
from . import requests_ll

_logger = logging.getLogger(__name__)


class BatchUpdateLeafLink(models.Model):
    _name = 'batch.update.leaf.link'

    def get_datetime_now(self):
        change_datetime = self.env['change.datetime'].sudo()
        time_now = datetime.datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        return change_datetime.change_utc_to_local_datetime(time_now)

    def default_name(self):
        if self.get_datetime_now():
            return 'LeafLink Update Report {}'.format(self.get_datetime_now())
        return 'LeafLink Update Report {}'.format(datetime.datetime.now())

    name = fields.Char('Name', default=default_name)
    partner_ids = fields.Many2many('res.partner')
    partner_not_fond = fields.Html()
    batch_url = fields.Char()
    log = fields.Char('Log')

    def get_partner_dict(self):
        part_dict = {}
        partners = self.env['res.partner'].sudo().search([('is_company', '=', True)])
        for partner in partners:
            if partner.regulatory_license:
                part_dict[partner.regulatory_license] = {}
        return part_dict

    def leaf_link_cron(self):
        data = []
        res_partner = self.env['res.partner'].sudo()
        params = {'archived': False, 'limit': 500, 'offset': 0}
        master_data = self.leaf_link_request(method='GET', url=requests_ll.get_url_ll('customers'), params=params)
        if master_data:
            if 'count' in master_data and 'results' in master_data:
                data = self.get_data_request(master_data, params)
        partner_list = []
        partner_not_found_list = ''
        log = 'Bad request. Please check config again'
        if data:
            leaf_link_url = request.env.ref('base.main_company').leaf_link_base_url
            odoo_dict = self.get_partner_dict()
            count_customer_not_fount = 0
            for item in data:
                if 'license_number' in item:
                    if item['license_number'] in odoo_dict:
                        if not odoo_dict[item['license_number']].get('created_on', False):
                            odoo_dict[item['license_number']] = item
                        else:
                            current = odoo_dict[item['license_number']]['created_on']
                            current = parse(current)
                            compare = item.get('created_on', False)
                            if compare:
                                compare = parse(compare)
                                if compare > current:
                                    odoo_dict[item['license_number']] = item
                    else:
                        count_customer_not_fount += 1
                        partner_not_found_list += "&nbsp;<a href='{}/customers/companies/{}/'>{}({})</a><br/>".format(
                            leaf_link_url, item['id'], item['name'], item['license_number'])
            log = 'Successful request'
            for sub_data in odoo_dict.keys():
                partners = res_partner.search([('regulatory_license', '=', sub_data), ('is_company', '=', True)])
                if partners:
                    for partner in partners:
                        vals = self.get_values(partner, odoo_dict[sub_data])
                        if vals:
                            if partner.write(vals):
                                partner_list.append(partner.id)
        partner_not_found_list = '<b>Not found {} customers</b><br/>{}'.format(str(count_customer_not_fount), partner_not_found_list)
        self.create_leaf_link_report(partner_list, partner_not_found_list, log)

    def action_send_notify_mail(self):
        ir_model_data = self.env['ir.model.data'].sudo()
        try:
            template_id = \
            ir_model_data.get_object_reference('impx_leaflink_lite', 'notify_batch_update_leaf_link_email_template')[1]
        except ValueError:
            template_id = False
        partner_ids = [user.partner_id.id for user in self.env.user.company_id.leaf_link_recipient_ids]
        if not partner_ids:
            return
        ctx = {
            'default_model': 'batch.update.leaf.link',
            'default_res_id': self.ids[0],
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_partner_ids': [(6, False, partner_ids)],
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True,
            'proforma': self.env.context.get('proforma', False),
            'force_email': True,
            'default_author_id': self.env.user.browse(SUPERUSER_ID).partner_id.id,
        }
        message = self.env['mail.compose.message'].sudo().with_context(**ctx).create({})
        message.onchange_template_id_wrapper()
        message.send_mail()
        return True

    def leaf_link_request(self, method, url, params):
        try:
            api_key = 'Token {}'.format(self.env.user.company_id.leaf_link_api_key)
            headers = {'Authorization': api_key}
            responsive = requests.request(method, url=url, headers=headers, params=params)
            if responsive.status_code == 200:
                _logger.warning('Successful request')
                return json.loads(responsive.content)
            content = 'Bad request. Error code {}. Please check config again'.format(str(responsive.status_code))
            _logger.error(content)
            return False
        except:
            _logger.exception('Bad request. Please check config again')
            return False

    def get_data_request(self, master_data, params):
        params['offset'] += params['limit']
        data = self.leaf_link_request(method='GET', url='https://www.leaflink.com/api/v2/customers/', params=params)
        if 'results' in data and 'count' in data:
            for sub_data in data['results']:
                master_data['results'].append(sub_data)
            if len(master_data['results']) < master_data['count']:
                return self.get_data_request(master_data, params)
        return master_data['results']

    def get_values(self, partner, data_request):
        values = {}
        comment = '\n\nUpdate from LeafLink ({}):'.format(self.get_datetime_now())
        len_comment = len(comment)
        if 'id' in data_request:
            if not partner.leaf_link_customer_id and data_request['id']:
                values['leaf_link_customer_id'] = data_request['id']
                comment += '\n\t+ LeafLink External ID: {}'.format(data_request['id'])
        if 'phone' in data_request:
            if data_request['phone']:
                phone = self.env['res.partner'].sudo().phone_format(data_request['phone'])
                if not partner.phone:
                    values['phone'] = phone
                    comment += '\n\t+ Phone: {}'.format(phone)
                if not partner.mobile:
                    values['mobile'] = phone
                    comment += '\n\t+ Mobile: {}'.format(phone)
        if 'email' in data_request:
            if not partner.email and data_request['email']:
                values['email'] = data_request['email']
                comment += '\n\t+ Email: {}'.format(data_request['email'])
        if len(comment) > len_comment:
            if partner.comment:
                comment = partner.comment + comment
            values['comment'] = comment
        return values

    def create_leaf_link_report(self, partner, partner_not_found, log):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        values = {
            'partner_ids': [(6, False, partner)],
            'partner_not_fond': partner_not_found,
            'log': log,
        }
        res = self.sudo().create(values)
        if res:
            res.write(
                {'batch_url': '{}/web#id={}&model=batch.update.leaf.link&view_type=form'.format(base_url, res.id)})
        res.action_send_notify_mail()
        return res
