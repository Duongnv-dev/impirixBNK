from odoo import models
from . import requests_ll


class SyncContacts(models.TransientModel):
    _name = 'sync.contacts'

    def get_values_contact(self, contact, contact_ll):
        contact_id_ll = contact_ll.get('id')
        name = contact_ll.get('first_name')
        phone = contact_ll.get('phone')
        email = contact_ll.get('email')
        company_type = 'person'
        if not contact:
            return {
                'contact_id_ll': contact_id_ll,
                'name': name or 'Unknown',
                "phone": phone or '',
                "mobile": phone or '',
                "email": email or '',
                'company_type': 'person',
                'is_contact_ll': True
            }
        vals = {}
        if name != contact.name:
            vals.update({'name': name})
        if phone != contact.phone:
            vals.update({'phone': phone})
        if phone != contact.mobile:
            vals.update({'mobile': phone})
        if email != contact.email:
            vals.update({'email': email})
        if company_type != contact.company_type:
            vals.update({'company_type': company_type})
        return vals

    def sync_contacts_to_odoo(self):
        url = requests_ll.get_url_ll('contacts')
        contacts_ll = requests_ll.get_all_data_from_ll(method='GET', url=url)
        res_partner = self.env['res.partner'].sudo()
        vals = ()
        for contact_ll in contacts_ll:
            contact_id_ll = str(contact_ll.get('id') or '')
            contact = res_partner.search([('contact_id_ll', '=', contact_id_ll), ('is_contact_ll', '=', True)])
            val = self.get_values_contact(contact, contact_ll)
            if not val:
                continue
            if contact:
                contact.write(val)
                continue
            vals += (val,)
        if vals:
            res_partner.create(vals)
