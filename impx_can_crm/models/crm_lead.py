from odoo import api, fields, models, _, tools
from datetime import timedelta


class Opportunity(models.Model):
    _name = "opportunity.list"

    name = fields.Char('Opportunity', required=True)
    note = fields.Text('Note')


class Lead(models.Model):
    _inherit = "crm.lead"

    name = fields.Char('Opportunity', compute='_compute_opportunity_list_id', required=False, index=True, store=True)
    opportunity_list_id = fields.Many2one('opportunity.list', string='Opportunity', required=True)

    @api.depends('opportunity_list_id')
    def _compute_opportunity_list_id(self):
        for opp in self:
            if opp.opportunity_list_id:
                opp.name = opp.opportunity_list_id.name

    show_all_activities = fields.Boolean(string="Show All Activities")
    all_activity_ids = fields.One2many('mail.activity', compute='_compute_all_activity_ids', string='Activities')
    all_message_html = fields.Html('Contents', compute='_compute_all_message_html')

    @api.depends('partner_id.child_ids.message_ids')
    def _compute_all_message_html(self):
        for s in self:
            s.all_message_html = ''
            s_id = s.id
            if not isinstance(s_id, (int)):
                s_id = s._origin.id
            if not isinstance(s_id, (int)):
                continue
            if not s.partner_id:
                continue
            if s.show_all_activities:
                difference = s.partner_id.get_difference_timezone()
                res_list = (s.partner_id.id, )
                if s.partner_id.child_ids:
                    res_list += s.partner_id.child_ids._ids
                partner_activity = s.env['mail.message'].search([('model', '=', 'res.partner'), ('res_id', 'in', res_list), ('message_type', '!=', 'user_notification')])
                lead_activity = s.env['mail.message'].search([('model', '=', 'crm.lead'), ('res_id', '=', s_id), ('message_type', '!=', 'user_notification')])
                all_activity = sorted(partner_activity + lead_activity, key=lambda activity: activity.date, reverse=True)
                body_html = ''
                for activity in all_activity:
                    partner = False
                    if activity.model == 'crm.lead':
                        partner = s.env['crm.lead'].browse(activity.res_id).partner_id
                    if activity.model == 'res.partner':
                        partner = s.env['res.partner'].browse(activity.res_id)
                    if not partner:
                        continue
                    author_name = activity.author_id.display_name
                    user_date = activity.date + timedelta(hours=difference)
                    date = user_date.strftime('%m/%d/%Y %H:%M:%S')
                    activity_dict = activity.message_format()[0]
                    subject = ''
                    if activity_dict.get('subject', False):
                        subject = """Subject: {}""".format(activity_dict['subject'])
                    if not activity_dict.get('tracking_value_ids', False) or len(activity_dict['tracking_value_ids']) == 0:
                        partner_display_name = partner.display_name or ''
                        item_html = s.build_all_message_html(activity.id, activity.author_id.id, author_name, date, partner_display_name, subject, activity.body)
                    else:
                        tracking = ''
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
                        tracking = '<ul class="o_mail_thread_message_tracking">{}</ul>'.format(tracking)
                        partner_display_name = partner.display_name or ''
                        item_html = s.build_all_message_html(activity.id, activity.author_id.id, author_name, date, partner_display_name, subject, tracking)
                    body_html += item_html
                s.all_message_html = body_html

    @api.depends('partner_id.activity_ids', 'partner_id.child_ids.activity_ids', 'show_all_activities')
    def _compute_all_activity_ids(self):
        for s in self:
            s_id = s.id
            if not isinstance(s_id, (int)):
                s_id = s._origin.id
            if not isinstance(s_id, (int)):
                continue
            lead_obj = self.browse(s_id)
            partner_id = lead_obj.partner_id.id
            all_activity = list(self.env['mail.activity'].search([('res_model', '=', 'crm.lead'), ('res_id', '=', s_id)])._ids)
            if s.show_all_activities:
                if partner_id:
                    partner_list = self.env['res.partner'].search([('id', 'child_of', [partner_id])])._ids
                    domain = [('res_model', '=', 'res.partner'), ('res_id', 'in', partner_list)]
                    partner_all_activity = list(self.env['mail.activity'].search(domain)._ids)
                    all_activity.extend(partner_all_activity)
            s.all_activity_ids = [(6, 0, all_activity)]

    def show_all_activity(self):
        for s in self:
            s.write({'show_all_activities': True})
            return True

    def not_show_all_activity(self):
        for s in self:
            s.write({'show_all_activities': False})
            return True

    def build_all_message_html(self, activity_id, author_id, author_name, date, partner_display_name, subject, body):
        show_more = ''
        if len(body) > 600:
            show_more = '<span class="show-more">Show more</span>'
        message_html = '''<div class="o_thread_message   o_mail_not_discussion " data-message-id="{}">
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
                            </div>'''.format(activity_id, author_id, author_name, date, date, partner_display_name, subject, body, show_more)
        return message_html
