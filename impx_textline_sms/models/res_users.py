from odoo import fields, models, api, _, SUPERUSER_ID
from odoo.exceptions import ValidationError, Warning


class InheritResUsers(models.Model):
    _inherit = "res.users"

    text_line_user = fields.Char(string='User')
    text_line_password = fields.Char(string='Password')
    text_line_api_key = fields.Char(string='API Key')
    text_line_number = fields.Char(string='TextLine Number')

    def write(self, vals):
        textline_vals = {}
        normal_vals = {}
        for key in vals.keys():
            if key in ['text_line_user', 'text_line_password', 'text_line_api_key', 'text_line_number']:
                textline_vals[key] = vals[key]
            else:
                normal_vals[key] = vals[key]
        if textline_vals:
            super(InheritResUsers, self.with_user(SUPERUSER_ID)).write(textline_vals)
        if normal_vals:
            return super(InheritResUsers, self).write(normal_vals)
        return True

    @api.onchange('text_line_number')
    def onchange_text_line_number(self):
        self.text_line_number = self.env['res.partner'].phone_format(self.text_line_number)

    def check_connect(self):
        sms_composer = self.env['sms.composer'].sudo()
        token, group_list = sms_composer.get_access_token(self.text_line_user, self.text_line_password, self.text_line_api_key)
        if not token:
            raise Warning(_('Invalid user or password or API key. Please check the authentication information'))
        else:
            if group_list:
                if self.text_line_number not in sms_composer.get_phone_group_dict(token, group_list):
                    raise Warning(_('Your TextLine Number does not match any department'))
            else:
                raise Warning(_('TextLine account does not belong to any department. Please contact the administrator'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Odoo'),
            'target': 'new',
            'res_model': 'res.users',
            'view_id': self.env.ref('impx_textline_sms.view_config_successful').id,
            'view_mode': 'form'
        }


