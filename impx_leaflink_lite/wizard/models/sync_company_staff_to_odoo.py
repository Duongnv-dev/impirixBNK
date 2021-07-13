from odoo import models
from . import requests_ll


class SyncContacts(models.TransientModel):
    _name = 'sync.company.staff'

    def get_values_company_staff(self, staff, staff_ll):
        name = staff_ll.get('display_name')
        email = staff_ll.get('email')
        leaflink_id = str(staff_ll.get('id') or '')
        if not staff:
            return {
                'leaflink_id': leaflink_id,
                'name': name or 'Unknown',
                'login': email,
                'password': '1',
            }
        vals = {}
        if name != staff.name:
            vals.update({'name': name})
        if leaflink_id != staff.leaflink_id:
            vals.update({'leaflink_id': leaflink_id})
        return vals

    def sync_company_staff_to_odoo(self):
        url = requests_ll.get_url_ll('company-staff')
        company_staff_ll = requests_ll.get_all_data_from_ll(method='GET', url=url)
        res_users = self.env['res.users'].sudo()
        vals = ()
        for item in company_staff_ll:
            email = item.get('email') or False
            if not email:
                continue
            user = res_users.search([('login', '=', email), '|', ('active', '=', True), ('active', '=', False)])
            val = self.get_values_company_staff(user, item)
            if not val:
                continue
            if user:
                user.write(val)
                continue
            vals += (val,)
        if vals:
            res_users.create(vals)
