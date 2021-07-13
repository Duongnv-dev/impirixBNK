# -*- coding: utf-8 -*-

from odoo import api, fields, models, _, tools
import base64
from requests.auth import HTTPBasicAuth


class InheritResCompany(models.Model):
    _inherit = 'res.company'

    metrc_url = fields.Char('Metrc url')
    metrc_software_api_key = fields.Char('Metrc Software API key')
    metrc_user_api_key = fields.Char('Metrc User API key')

    def get_metrc_headers(self, metrc_software_api_key, metrc_user_api_key):
        if not metrc_software_api_key or not metrc_user_api_key:
            return False
        userpass = '{}:{}'.format(metrc_software_api_key, metrc_user_api_key)
        encoded_u = base64.b64encode(userpass.encode()).decode()
        headers = {"Authorization": "Basic {}".format(encoded_u)}
        return headers

    def get_metrc_connect_info(self):
        metrc_url = self.metrc_url
        metrc_software_api_key = self.metrc_software_api_key
        metrc_user_api_key = self.metrc_user_api_key

        if not metrc_url or not metrc_software_api_key or not metrc_user_api_key:
            return False

        headers = {
            'Content-Type': 'application/json'
        }
        return metrc_url, headers

    def get_authen(self):
        metrc_software_api_key = self.metrc_software_api_key
        metrc_user_api_key = self.metrc_user_api_key

        res = HTTPBasicAuth(metrc_software_api_key, metrc_user_api_key)
        return res


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    metrc_url = fields.Char('Metrc url')
    metrc_software_api_key = fields.Char('Metrc Software API key')
    metrc_user_api_key = fields.Char('Metrc User API key')

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        company = self.env.user.company_id
        res['metrc_url'] = company.metrc_url
        res['metrc_software_api_key'] = company.metrc_software_api_key
        res['metrc_user_api_key'] = company.metrc_user_api_key
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        company = self.env.user.company_id
        company.sudo().write({
            'metrc_url': self.metrc_url,
            'metrc_software_api_key': self.metrc_software_api_key,
            'metrc_user_api_key': self.metrc_user_api_key,
        })


# get similar customer from other system
class ResPartner(models.Model):
    _inherit = 'res.partner'

    def get_similar_partner(self, vendor):
        query = """
                    SELECT
                        name, id
                    FROM res_partner
                    WHERE SIMILARITY(name, '{}') > 0.4
                    LIMIT 3;
                """.format(vendor)
        self._cr.execute(query)
        res = self.env.cr.fetchall()
        return res
