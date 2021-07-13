# -*- coding: utf-8 -*-

from odoo import api, fields, models, _, tools
from odoo.exceptions import UserError, ValidationError, AccessError
import datetime, pytz
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
from datetime import timedelta


class ResPartner(models.Model):
    _inherit = 'res.partner'

    doing_business_as = fields.Char()
    licensee_name = fields.Char()
    regulatory_license = fields.Char()
    regulatory_license_type = fields.Selection([('rec', 'Rec'), ('med', 'Med')])
    sales_territory = fields.Char()
    social_facebook_link = fields.Char(string="Facebook Link")
    social_linkedin_link = fields.Char(string="LinkedIn Link")
    social_twitter_link = fields.Char(string="Twitter Link")

    # WO04
    show_all_activities = fields.Boolean(string="Show All Activities")
    all_activity_ids = fields.One2many('mail.activity', compute='_compute_all_activity_ids', string='Activities')
    all_message_html = fields.Html('Contents', compute='_compute_all_message_html')

    #For transporter and testing facilities
    is_transporter = fields.Boolean(string="Transporter")
    transporter_type = fields.Char()
    is_testing_facility = fields.Boolean(string="Testing Facility")
    license_expired = fields.Boolean(default=False, string="License Expired")

    @api.constrains('parent_id', 'child_ids')
    def _check_already_parent(self):
        if self.parent_id and self.child_ids:
            already_parent = False
            for child in self.child_ids:
                if child.company_type == 'company':
                    already_parent = True
                    break
            if already_parent:
                raise ValidationError(_(
                    'This customer already has subsidiary, so it cannot become a subsidiary of another company. Please leave the Company field blank'))

    @api.depends('child_ids.activity_ids', 'show_all_activities')
    def _compute_all_activity_ids(self):
        for s in self:
            s_id = s.id
            if not isinstance(s_id, (int)):
                s_id = s._origin.id

            if not isinstance(s_id, (int)):
                continue

            partner_list = [s_id]
            if s.show_all_activities:
                partner_list = self.search([('id', 'child_of', [s_id])])._ids
            domain = [('res_model', '=', 'res.partner'), ('res_id', 'in', partner_list)]
            all_activity = list(self.env['mail.activity'].search(domain)._ids)
            s.all_activity_ids = [(6, 0, all_activity)]

    @api.onchange('parent_id')
    def onchange_parent_id(self):
        # return values in result, as this method is used by _fields_sync()
        if not self.parent_id:
            return
        result = {}
        partner = self._origin
        if partner.parent_id and partner.parent_id != self.parent_id:
            result['warning'] = {
                'title': _('Warning'),
                'message': _('Changing the company of a contact should only be done if it '
                             'was never correctly set. If an existing contact starts working for a new '
                             'company then a new contact should be created under that new '
                             'company. You can use the "Discard" button to abandon this change.')}
        if partner.type == 'contact' or self.type == 'contact':
            # for person contacts: copy the parent address, if set (aka, at least one
            # value is set in the address: otherwise, keep the one from the
            # contact)
            if self.company_type != 'company':
                address_fields = self._address_fields()
                if any(self.parent_id[key] for key in address_fields):
                    def convert(value):
                        return value.id if isinstance(value, models.BaseModel) else value

                    result['value'] = {key: convert(self.parent_id[key]) for key in address_fields}
        return result

    def _fields_sync(self, values):
        """ Sync commercial fields and address fields from company and to children after create/update,
        just as if those were all modeled as fields.related to the parent """
        # 1. From UPSTREAM: sync from parent
        if values.get('parent_id') or values.get('type') == 'contact':
            # 1a. Commercial fields: sync if parent changed
            if values.get('parent_id'):
                self._commercial_sync_from_company()
            # 1b. Address fields: sync if parent or use_parent changed *and* both are now set
            if self.parent_id and self.type == 'contact' and self.is_company == False:
                onchange_vals = self.onchange_parent_id().get('value', {})
                self.update_address(onchange_vals)

        # 2. To DOWNSTREAM: sync children
        self._children_sync(values)

    def _children_sync(self, values):
        if not self.child_ids:
            return
        # 2a. Commercial Fields: sync if commercial entity
        if self.commercial_partner_id == self:
            commercial_fields = self._commercial_fields()
            if any(field in values for field in commercial_fields):
                self._commercial_sync_to_children()
        for child in self.child_ids.filtered(lambda c: not c.is_company):
            if child.commercial_partner_id != self.commercial_partner_id:
                self._commercial_sync_to_children()
                break
        # 2b. Address fields: sync if address changed
        address_fields = self._address_fields()
        if any(field in values for field in address_fields):
            contacts = self.child_ids.filtered(lambda c: c.type == 'contact' and not c.is_company)
            contacts.update_address(values)

    # Function takes the time difference between user timezone and database timezone
    def get_difference_timezone(self):
        difference = 0
        user_tz = self.env.user.tz or self.env.context.get('tz')
        if user_tz:
            display_tz = user_tz
        else:
            user_admin = self.env.ref('base.user_admin')
            display_tz = user_admin.tz
        if display_tz:
            tz_now = datetime.datetime.now(pytz.timezone(display_tz))
            difference = tz_now.utcoffset().total_seconds() / 60 / 60
            difference = int(difference)
        return difference

    @api.depends('child_ids.message_ids')
    def _compute_all_message_html(self):
        for s in self:
            s_id = s.id
            if not isinstance(s_id, (int)):
                s_id = s._origin.id

            if not isinstance(s_id, (int)):
                continue

            if s.show_all_activities:
                difference = s.get_difference_timezone()
                partner_list = self.search([('id', 'child_of', [s_id])])._ids
                domain = [('model', '=', 'res.partner'), ('res_id', 'in', partner_list),
                          ('message_type', '!=', 'user_notification')]
                all_activity = self.env['mail.message'].search(domain, order='date desc')
                body_html = ""
                for activity in all_activity:
                    partner = self.env['res.partner'].browse(activity.res_id)
                    author_name = activity.author_id.display_name
                    user_date = activity.date + timedelta(hours=difference)
                    date = user_date.strftime('%m/%d/%Y %H:%M:%S')
                    activity_dict = activity.message_format()[0]
                    body = activity.body
                    show_more = ''
                    if len(body) > 600:
                        show_more = '<span class="show-more">Show more</span>'
                    subject = ''
                    if activity_dict.get('subject', False):
                        subject = """Subject: {}""".format(activity_dict['subject'])
                    if not activity_dict.get('tracking_value_ids', False) or len(activity_dict['tracking_value_ids']) == 0:
                        item_html = """
                        <div class="o_thread_message   o_mail_not_discussion " data-message-id="{}">
                            <div class="o_thread_message_sidebar">
                                <div class="o_thread_message_sidebar_image">
                                    <img alt="" src="/web/image/res.partner/{}/image_128" data-oe-model="res.partner" data-oe-id="" class="o_thread_message_avatar rounded-circle ">
                                    <span class="o_updatable_im_status" data-partner-id="3">
                                        <i class="o_mail_user_status o_user_online fa fa-circle" title="Online" role="img" aria-label="User is online"></i>
                                    </span>
                                </div> 
                            </div>
                            <div class="o_thread_message_core">
                                <p class="o_mail_info text-muted">
                                        Note by
                                    <strong data-oe-model="res.partner" data-oe-id="" class="o_thread_author ">
                                        {}
                                    </strong>
                                    - <small class="" title="{}">{}</small>
                                    <span class="o_thread_icons"> 
                                    </span>
                                </p>
                                <p>
                                    <em>
                                        To: {}<br/>
                                        <b>
                                            {}
                                        </b
                                    </em>
                                </p>
                                <div class="o_thread_message_content overflow-content-chat">
                                    {}  
                                </div>
                                {}
                            </div>
                        </div>""".format(activity.id, activity.author_id.id, author_name, date, date, partner.display_name or '', subject, body, show_more)

                    else:
                        tracking = ""
                        for track in activity_dict['tracking_value_ids']:
                            old_value = track.get('old_value', '')
                            new_value = track.get('new_value', '')
                            track_line = """
                                <li>
                                            {}:
                    
                                            <span>{}</span>
                                            <span class ="fa fa-long-arrow-right" role="img" aria-label="Changed" title="Changed"> </span>
                                            <span>{}</span >
                                </li>""".format(track.get('changed_field', ''), old_value, new_value)
                        tracking += track_line

                        item_html = """
                            <div class="o_thread_message   o_mail_not_discussion " data-message-id="{}">
                                <div class="o_thread_message_sidebar">
                                    <div class="o_thread_message_sidebar_image">
                                        <img alt="" src="/web/image/res.partner/{}/image_128" data-oe-model="res.partner" data-oe-id="" class="o_thread_message_avatar rounded-circle ">
                                        <span class="o_updatable_im_status" data-partner-id="3">
                                            <i class="o_mail_user_status o_user_online fa fa-circle" title="Online" role="img" aria-label="User is online"></i>
                                        </span>
                                    </div> 
                                </div>
                                <div class="o_thread_message_core">
                                    <p class="o_mail_info text-muted">
                                            Note by
                                        <strong data-oe-model="res.partner" data-oe-id="" class="o_thread_author ">
                                            {}
                                        </strong>
                                        - <small class="" title="{}">{}</small>
                                        <span class="o_thread_icons"> 
                                        </span>
                                    </p>
                                    <p>
                                        <em>
                                            To: {}<br/>
                                            <b>
                                                {}
                                            </b
                                        </em>
                                    </p>
                                    <div class="o_thread_message_content">
                                        <ul class="o_mail_thread_message_tracking">
                                            {}
                                        </ul>
                                    </div>
                                </div>
                            </div>""".format(activity.id, activity.author_id.id, author_name, date, date, partner.display_name or '', subject, tracking)
                    body_html += item_html
                s.all_message_html = body_html
            else:
                s.all_message_html = False

    def show_all_activity(self):
        for s in self:
            s.write({'show_all_activities': True})
            return True

    def not_show_all_activity(self):
        for s in self:
            s.write({'show_all_activities': False})
            return True

    # WO10
    @api.model
    def create(self, values):
        if not values.get('is_company', False) and values.get('parent_id', False):
            user_id = self.browse(values['parent_id']).user_id.id
            if user_id:
                values['user_id'] = user_id
        return super(ResPartner, self).create(values)

    def update_user_id_for_company(self, value):
        if 'user_id' not in value.keys():
            return
        for partner in self.child_ids:
            if not partner.is_company and partner.user_id != self.user_id:
                super(ResPartner, partner).write({'user_id': self.user_id.id})

    def update_user_id_for_individual(self, value):
        if self.parent_id:
            if self.user_id.id != self.parent_id.user_id.id:
                super(ResPartner, self).write({'user_id': self.parent_id.user_id.id})

    def update_user_id(self, value):
        if self.is_company:
            self.update_user_id_for_company(value)
        else:
            self.update_user_id_for_individual(value)

    def write(self, values):
        res = super(ResPartner, self).write(values)
        for p in self:
            p.update_user_id(values)
        return res

    @api.onchange('parent_id', 'is_company')
    def parent_id_onchange(self):
        if self.parent_id or self.is_company:
            if self.parent_id and not self.is_company:
                self.user_id = self.parent_id.user_id
            else:
                self.user_id = None

    def update_sale_person(self):
        partners = self.env['res.partner'].sudo().search([('parent_id', '!=', None), ('is_company', '!=', True)])
        for partner in partners:
            if partner.user_id != partner.parent_id.user_id:
                partner.write({
                    'user_id': partner.parent_id.user_id.id
                })


class MailMessage(models.Model):
    _inherit = 'mail.message'

    @api.model
    def create(self, values):
        context = self._context
        """ Create Document sequences after create the journal """
        if not context.get('from_office_365', False):
            if values.get('model', False) in ['res.partner', 'crm.lead'] and values.get('res_id', False) \
                    and values.get('message_type', False) not in ['user_notification', 'notification']:
                if self.env[values['model']].browse(values['res_id']).show_all_activities:
                    raise UserError(_(
                        "You can not send message or log a note in show all activities mode. "
                        "Please turn off the show all activities mode to be able to do this. (Click NOT ALL ACTIVITIES)"))
        res = super(MailMessage, self).create(values)
        return res

