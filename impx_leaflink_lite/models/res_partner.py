from odoo import fields, api, models, _
from odoo.exceptions import ValidationError
import requests
import json
from . import requests_ll


class ResPartner(models.Model):
    _inherit = 'res.partner'
    leaf_link_customer_id = fields.Char(string='LeafLink External ID', readonly=1)
    leaf_link_customer_url = fields.Char(string='LeafLink Customer Link', compute='compute_leaf_link_url')
    leaf_link_order_url = fields.Char(string='LeafLink Create Order Link', compute='compute_leaf_link_url')
    edit_leaflink_id = fields.Boolean(compute='compute_edit_external_id')
    show_url_button = fields.Boolean(compute='compute_show_url_button')
    contact_id_ll = fields.Char('LeafLink Contact ID', readonly=1)
    is_contact_ll = fields.Boolean(default=False, string='Is Contact LeafLink', readonly=1)

    def create_contact_for_customer(self):
        contacts = self.child_ids
        url = requests_ll.get_url_ll('contacts')
        _ids = []
        for contact in contacts:
            val = {
                'owner': 3823,
                'first_name': contact.name or 'Unknown',
                'phone': contact.phone or contact.mobile or '',
                'email': contact.email or '',
                'description': contact.comment or '',
            }
            contact_id_ll = contact.contact_id_ll
            if contact_id_ll:
                method = 'PATCH'
                url = '{}{}/'.format(url, contact_id_ll)
            else:
                method = 'POST'
            resp = requests_ll.requests_ll(method=method, url=url, data=json.dumps(val))
            contact_id = resp.get('id')
            contact.write({'is_contact_ll': True, 'contact_id_ll': contact_id})
            _ids.append(contact_id)
        return _ids

    def get_sale_person(self):
        saleperson = self.user_id
        if not saleperson:
            return []
        staff_id = saleperson.leaflink_id
        if not staff_id:
            return []
        url = requests_ll.get_url_ll('company-staff/{}'.format(staff_id))
        resp = requests_ll.requests_ll(method='GET', url=url)
        if resp:
            return [resp.get('id')]
        return []

    def get_value_customer_ll(self, customer_ll):
        license_type_dict = {'med': 1, 'rec': 4, 'unknown': 6}
        state_id = self.state_id or False
        state_code = state_id.code if state_id else False
        managers = self.get_sale_person()
        name = self.name
        license_number = self.regulatory_license or False
        license_type = self.regulatory_license_type or False
        license_type_id = license_type_dict.get(license_type or 'unknown')
        currency_id = self.env.ref('base.main_company').currency_id or False
        currency = currency_id.display_name if currency_id else False
        dba = self.doing_business_as or False
        website = self.website or False
        address = '{} {}'.format(self.street, self.street2) or False
        zipcode = self.zip or False
        city = self.city or False
        country_id = self.country_id or False
        country = country_id.code if country_id else False
        phone = self.phone or self.mobile or False
        email = self.email or False
        archived = not self.active
        owner = 3823
        values = {}
        if not customer_ll:
            values = {
                "nickname": name or 'Unknown',
                "name": name or 'Unknown',
                "archived": archived,
                "owner": owner,
            }
            if state_code:
                values.update({"state": state_code})
            if managers:
                values.update({"managers": managers})
            if license_number:
                values.update({"license_number": license_number})
                values.update({"license_type": license_type_id})
            if currency:
                values.update({"currency": currency})
            if dba:
                values.update({"dba": dba})
            if website:
                values.update({"website": website})
            if address:
                values.update({"address": address})
            if zipcode:
                values.update({"zipcode": zipcode})
            if city:
                values.update({"city": city})
            if country:
                values.update({"country": country})
            if phone:
                values.update({"phone": phone})
            if email:
                values.update({"email": email})
            return values
        if state_code and state_code != customer_ll.get('state'):
            values.update({'state': state_code})
        if managers != customer_ll.get('managers'):
            values.update({'managers': managers})
        if name != customer_ll.get('nickname'):
            values.update({'nickname': name})
        if license_number != customer_ll.get('license_number'):
            values.update({'license_number': license_number})
        if license_type_id != customer_ll.get('license_type'):
            values.update({'license_type': license_type_id})
        if currency != customer_ll.get('currency'):
            values.update({'currency': currency})
        if name != customer_ll.get('name'):
            values.update({'name': name})
        if dba and dba != customer_ll.get('dba'):
            values.update({'dba': dba})
        if website != customer_ll.get('website'):
            values.update({'website': website})
        if address != customer_ll.get('address'):
            values.update({'address': address})
        if zipcode and zipcode != customer_ll.get('zipcode'):
            values.update({'zipcode': zipcode})
        if city and city != customer_ll.get('city'):
            values.update({'city': city})
        if country != customer_ll.get('country'):
            values.update({'country': country})
        if phone != customer_ll.get('phone'):
            values.update({'phone': phone})
        if email != customer_ll.get('email'):
            values.update({'email': email})
        if archived != customer_ll.get('archived'):
            values.update({'archived': archived})
        if owner != customer_ll.get('owner'):
            values.update({'owner': owner})
        return values

    def sync_to_leaflink(self):
        customer_id = self.leaf_link_customer_id
        license_number = self.regulatory_license
        customer_name = self.name
        url = requests_ll.get_url_ll('customers')
        params = None
        if customer_id:
            url = '{}{}/'.format(url, customer_id)
        elif license_number:
            params = {'license_number': license_number, 'limit': 1}
        elif customer_name:
            params = {'name': customer_name, 'limit': 1}
        try:
            customer_ll = requests_ll.requests_ll(method='GET', url=url, params=params)
            if 'results' in customer_ll.keys():
                customer_ll = customer_ll['results'][0]
        except:
            customer_ll = False
        values = self.get_value_customer_ll(customer_ll)
        method = 'POST'
        if customer_ll:
            url = requests_ll.get_url_ll('customers/{}'.format(customer_ll.get('id')))
            method = 'PATCH'
        resp = requests_ll.requests_ll(method=method, url=url, data=json.dumps(values))
        _id = resp.get('id')
        if self.leaf_link_customer_id != _id:
            self.write({'leaf_link_customer_id': _id})

    def requests_ll_customers(self, **kwargs):
        api_key = self.env.ref('base.main_company').leaf_link_api_key
        if not api_key:
            raise ValidationError(_("The field 'LeafLink API key' is missing, please check config again"))
        api_key = 'Token {}'.format(api_key)
        headers = {'Authorization': api_key}
        try:
            resp = requests.request(
                method=kwargs.get('method'),
                url=kwargs.get('url'),
                headers=headers,
                params=kwargs.get('params'),
                data=kwargs.get('data'))
            content = json.loads(resp.content)
            if resp.ok and (200 <= resp.status_code < 400):
                if self._context.get('write_ll_external_id'):
                    _id = content.get('id')
                    self.write({'leaf_link_customer_id': _id} if _id else {})
                return content
            else:
                raise ValidationError(_('Requests is fail. Status code {}'.format(resp.status_code)))
        except ValueError as error:
            raise ValidationError(_('Bad requests: {}'.format(error)))

    def build_data_value(self):
        data = {'name': self.name, 'nickname': self.name, 'archived': not self.active}
        email = self.email
        if email:
            data.update({'email': email})
        phone = self.phone
        if phone:
            data.update({'phone': phone})
        website = self.website
        if website:
            data.update({'website': website})
        street, street2 = self.street, self.street2
        if street or street2:
            data.update({'address': '{} {}'.format(street, street2)})
        city = self.city
        if city:
            data.update({'city': city})
        state = self.state_id
        if state:
            data.update({'state': state.code or ''})
        zipcode = self.zip
        if zipcode:
            data.update({'zipcode': zipcode})
        country = self.country_id
        if country:
            data.update({'country': country.code or ''})
        dba = self.doing_business_as
        if dba:
            data.update({'dba': dba})
        return data

    def patch_customer_on_leaf_link(self, base_url, leaf_link_customer, leaf_link_company_id):
        license_number = self.regulatory_license
        license_type = self.regulatory_license_type
        if not license_number or not license_type:
            raise ValidationError(
                _("The fields 'Regulatory License' and 'Regulatory License Type' is required, please complete it")
            )
        license_type_dict = {'med': 1, 'rec': 4, 'unknown': 6}
        data = self.build_data_value()
        data.update({'license_type': license_type_dict.get(license_type, 'unknown')})
        method = 'PATCH'
        url = 'https://{}/api/v2/customers/{}'.format(
            base_url, '{}/'.format(leaf_link_customer[0].get('id')) if leaf_link_customer else '')
        if not leaf_link_customer:
            method = 'POST'
            data.update({'owner': leaf_link_company_id})
            data.update({'license_number': license_number} if license_number else {})
        self = self.with_context(write_ll_external_id=True)
        self.requests_ll_customers(method=method, url=url, data=data)

    def get_leaf_link_company_id(self, base_url):
        url = 'https://{}/api/v2/companies/'.format(base_url)
        content = self.requests_ll_customers(method='GET', url=url)
        if not content:
            raise ValidationError(_('Bad request, please check it and try again'))
        results = content.get('results')
        if not results:
            raise ValidationError(_('Cannot get LeafLink company id, please check it and try again'))
        return results[0].get('id') or False

    def sync_to_leaf_link(self):
        leaf_link_base_url = self.env.ref('base.main_company').leaf_link_base_url or ''
        if not leaf_link_base_url:
            raise ValidationError(_('LeafLink base URL is missing, please check config again'))
        base_url = leaf_link_base_url.split('/')[2]
        url = 'https://{}/api/v2/customers/'.format(base_url)
        params = {
            'license_number': self.regulatory_license,
            # 'archived': False
        }
        content = self.requests_ll_customers(method='GET', url=url, params=params)
        leaf_link_customer = content.get('results')
        leaf_link_company_id = self.get_leaf_link_company_id(base_url)
        self.patch_customer_on_leaf_link(base_url, leaf_link_customer, leaf_link_company_id)
        self.create_contact_for_customer()

    def compute_show_url_button(self):
        for rec in self:
            rec.show_url_button = False
            if rec.is_company:
                if rec.leaf_link_customer_id:
                    rec.show_url_button = True
            else:
                if rec.parent_id:
                    if rec.parent_id.leaf_link_customer_id:
                        rec.show_url_button = True

    def get_leaflink_custom_url(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': self.leaf_link_customer_url,
        }

    def get_leaflink_order_url(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': self.leaf_link_order_url,
        }

    @api.depends('leaf_link_customer_id')
    def compute_leaf_link_url(self):
        for rec in self:
            rec.leaf_link_customer_url = ''
            rec.leaf_link_order_url = ''
            leaf_link_url = rec.env.user.company_id.leaf_link_base_url or 'https://www.leaflink.com/c/montem-pharmlabs-limited'
            if rec.is_company:
                if rec.leaf_link_customer_id:
                    rec.leaf_link_customer_url = '{}/customers/companies/{}/'.format(leaf_link_url,
                                                                                     rec.leaf_link_customer_id)
                    rec.leaf_link_order_url = '{}/order-create/{}/'.format(leaf_link_url, rec.leaf_link_customer_id)
            else:
                if rec.parent_id:
                    if rec.parent_id.is_company:
                        if rec.parent_id.leaf_link_customer_id:
                            rec.leaf_link_customer_url = '{}/customers/companies/{}/'.format(leaf_link_url,
                                                                                             rec.parent_id.leaf_link_customer_id)
                            rec.leaf_link_order_url = '{}/order-create/{}/'.format(leaf_link_url,
                                                                                   rec.parent_id.leaf_link_customer_id)

    def compute_edit_external_id(self):
        for rec in self:
            rec.edit_leaflink_id = False
            user = rec.env.user.browse(rec.env.uid)
            user_recipient = True if user in rec.env.user.company_id.leaf_link_recipient_ids else False
            if user.has_group('base.group_partner_manager') or user.has_group(
                    'sales_team.group_sale_manager') or user_recipient:
                rec.edit_leaflink_id = True


class ResCompany(models.Model):
    _inherit = 'res.company'
    leaf_link_api_key = fields.Char('LeafLink API key')
    leaf_link_base_url = fields.Char('LeafLink base URL')
    leaf_link_recipient_ids = fields.Many2many('res.users', string='Notify by Email')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    leaf_link_api_key = fields.Char(related='company_id.leaf_link_api_key', readonly=False)
    leaf_link_base_url = fields.Char(related='company_id.leaf_link_base_url', readonly=False)
    leaf_link_recipient_ids = fields.Many2many(related='company_id.leaf_link_recipient_ids', readonly=False)


class ResUsers(models.Model):
    _inherit = 'res.users'

    leaflink_id = fields.Char('LeafLink staff ID', readonly=1)
    _sql_constraints = [
        ('leaflink_id_uniq', 'unique (leaflink_id)', 'LeafLink staff ID must be unique !')
    ]
