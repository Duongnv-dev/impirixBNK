from builtins import super

from odoo import api, fields, models, _, SUPERUSER_ID
import logging
import requests
import json
from datetime import datetime
from datetime import timedelta
from odoo.exceptions import ValidationError
from odoo.addons.queue_job.job import job
from dateutil.parser import *
from odoo.osv import osv
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
from odoo.http import request
import time

_logger = logging.getLogger(__name__)

VIRTUALID_DATETIME_FORMAT = "%Y%m%d%H%M%S"


def calendar_id2real_id(calendar_id=None, with_date=False):
    """ Convert a "virtual/recurring event id" (type string) into a real event id (type int).
        E.g. virtual/recurring event id is 4-20091201100000, so it will return 4.
        :param calendar_id: id of calendar
        :param with_date: if a value is passed to this param it will return dates based on value of withdate + calendar_id
        :return: real event id
    """
    if calendar_id and isinstance(calendar_id, str):
        res = [bit for bit in calendar_id.split('-') if bit]
        if len(res) == 2:
            real_id = res[0]
            if with_date:
                real_date = time.strftime(DEFAULT_SERVER_DATETIME_FORMAT, time.strptime(res[1], VIRTUALID_DATETIME_FORMAT))
                start = datetime.datetime.strptime(real_date, DEFAULT_SERVER_DATETIME_FORMAT)
                end = start + timedelta(hours=with_date)
                return (int(real_id), real_date, end.strftime(DEFAULT_SERVER_DATETIME_FORMAT))
            return int(real_id)
    return calendar_id and int(calendar_id) or calendar_id


class CalendarEventCateg(models.Model):
    _inherit = 'calendar.event.type'
    color = fields.Char(string="Color", required=False, )
    categ_id = fields.Char(string="o_category id", required=False, )


class MailActivityType(models.Model):
    _inherit = 'mail.activity.type'
    sync_office365 = fields.Boolean(string='Sync to Office365', default=False)

    @api.constrains('category')
    def constrains_file_sync(self):
        if self.category != 'meeting':
            self.sync_office365 = False


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    office_id = fields.Char('Office365 Id')
    category_name = fields.Char('Categories')
    end_type = fields.Selection([
        ('end_date', 'End date'),
    ], string='Recurrence Termination', default='end_date')

    # @api.model
    # def default_get(self, fields):
    #     res = super(CalendarEvent, self).default_get(fields)
    #     alarm_ids = self.get_calendar_alarm(15)
    #     if alarm_ids:
    #         res['alarm_ids'] = [(6, 0, alarm_ids)]
    #     return res

    # def get_calendar_alarm(self, outlook_alarm):
    #     alarm_id = self.env['calendar.alarm'].sudo().search([('duration_minutes', '=', outlook_alarm)], limit=1)
    #     alarm_1_day = self.env['calendar.alarm'].sudo().search([('duration_minutes', '=', 1440)], limit=1)
    #     if alarm_id:
    #         return (alarm_id.id, )
    #     if alarm_1_day:
    #         return (alarm_1_day.id, )
    #     return ()

    @api.onchange('categ_ids')
    def change_category(self):
        if self.categ_ids:
            self.category_name = self.categ_ids[0].name

    @api.model
    def create(self, values):
        res = super(CalendarEvent, self.with_context(not_push_event_to_queue=True)).create(values)
        if values.get('recurrent_id'):
            return res
        if not self._context.get('event_from_unlink_not_push_to_queue') \
                and not self._context.get('event_create_from_office'):
            if res.activity_ids:
                activity = res.activity_ids[0].activity_type_id
                if activity.sync_office365:
                    res.call_api_create_queue_update(res.id)
                return res
            res.push_new_event_to_queue()
        return res

    def write(self, values):
        context = self._context
        if context.get('not_push_event_to_queue')\
                or context.get('event_from_unlink_not_push_to_queue')\
                or context.get('event_from_request_not_push_to_queue'):
            return super(CalendarEvent, self).write(values)
        val = values
        if values.get('partner_ids'):
            val.update({'partner_ids': values.get('partner_ids')[0][-1]})
        if values.get('categ_ids'):
            val.update({'categ_ids': values.get('categ_ids')[0][-1]})
        office_id = self.get_sub_event_repeat()
        if office_id:
            values.update({'office_id': office_id})
        calendar_sync = self.create_calendar_sync(val, office_id)
        self.call_api_create_queue_write(calendar_sync.id)
        return super(CalendarEvent, self).write(values)

    def unlink(self):
        for event in self:
            if self._context.get('event_from_unlink_request'):
                continue
            calendar_id = event.user_id.get_calendar_id_office_365()
            header = {
                'Authorization': 'Bearer {0}'.format(event.user_id.token),
                'Content-Type': 'application/json'
            }
            event_id = event.get_event_id_office365(calendar_id, header)
            if event_id:
                url_del = 'https://graph.microsoft.com/v1.0/me/calendars/{}/events/{}'.format(calendar_id, event_id)
                try:
                    response = requests.delete(url=url_del, headers=header)
                    if response.status_code == 204:
                        _logger.info('Successful deleted event {} from Office365 Calendar'.format(event.name))
                    else:
                        _logger.info('Bad request: status code {}'.format(response.status_code))
                except Exception as error:
                    _logger.info('Error {} when syncing event {} with user {}'.format(error, event.name, event.user_id.name))
                    raise ValidationError(
                        _('Error {} when syncing event {} with user {}'.format(error, event.name, event.user_id.name)))
        return super(CalendarEvent, self.with_context(event_from_unlink_not_push_to_queue=True)).unlink()

    # in create an event, call api to create a queue job to sync event to office
    # fix case: create an event from activities. Error if calling queue job constructor directly in create method
    def call_api_create_queue_update(self, event_id):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        api_key = self.env['ir.config_parameter'].sudo().get_param('auth_sync_external_event')
        url = '{}/sync/{}/{}'.format(base_url, event_id, api_key)
        headers = {'api_key': api_key}
        try:
            response = requests.get(url=url, headers=headers)
            if response.status_code == 200:
                return True
            return False
        except Exception as error:
            _logger.error('Error {} - Event {}'.format(error, self.name))

    def call_api_create_queue_write(self, sync_id):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        api_key = self.env['ir.config_parameter'].sudo().get_param('auth_sync_external_event')
        url = '{}/sync-write/{}/{}'.format(base_url, sync_id, api_key)
        headers = {'api_key': api_key}
        try:
            response = requests.get(url=url, headers=headers)
            if response.status_code == 200:
                return True
            return False
        except Exception as error:
            _logger.error('Error {} - Event {}'.format(error, self.name))

    def get_sub_event_repeat(self):
        if self.recurrent_id and self.recurrent_id > 0:
            parent_event = self.browse(self.recurrent_id)
            calendar_id = self.user_id.get_calendar_id_office_365()
            header = {
                'Authorization': 'Bearer {0}'.format(self.user_id.token),
                'Content-Type': 'application/json'
            }
            url = 'https://graph.microsoft.com/v1.0/me/calendars/{}/calendarView?startDateTime={}&endDateTime={}'.format(
                calendar_id, self.start, self.stop)
            try:
                response = requests.get(url=url, headers=header)
                if response.status_code != 200:
                    raise ValidationError(_('Bad request: status code {}'.format(response.status_code)))
                events365 = json.loads((response.content.decode('utf-8')))
                for ev in events365.get('value'):
                    if ev.get('seriesMasterId') == parent_event.office_id:
                        return ev.get('id')
                return False
            except Exception as error:
                _logger.error('Error {} - Event {}'.format(error, self.name))
                return False
        return False

    # override base function, do not copy office_id
    def detach_recurring_event(self, values=None):
        """ Detach a virtual recurring event by duplicating the original and change reccurent values
            :param values : dict of value to override on the detached event
        """
        if not values:
            values = {}

        real_id = calendar_id2real_id(self.id)
        meeting_origin = self.browse(real_id)

        data = self.read(['allday', 'start', 'stop', 'rrule', 'duration'])[0]
        if data.get('rrule'):
            data.update(
                values,
                recurrent_id=real_id,
                recurrent_id_date=data.get('start'),
                rrule_type=False,
                rrule='',
                recurrency=False,
                final_date=False,
                end_type=False,
                office_id=None
            )

            # do not copy the id
            if data.get('id'):
                del data['id']
            return meeting_origin.with_context(detaching=True).copy(default=data)

    # Cron job to update/delete calendar view in office 365 (Sync action to odoo)
    def cron_job_delete_and_update_repeat_events(self):
        task = u'calendar.event().push_delete_and_update_events_to_queue()'
        job = self.env['queue.job'].sudo().search([('func_string', '=', task), ('state', 'not in', ('done', 'fail'))])
        if not job:
            self.with_delay().push_delete_and_update_events_to_queue()

    @job
    def push_delete_and_update_events_to_queue(self):
        search_date_from = datetime.now() - timedelta(days=90)
        search_date_from = search_date_from.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        events = self.env['calendar.event'].sudo().search([('office_id', '!=', False),
                                                           ('create_date', '>', search_date_from)])
        for event in events:
            calendar_id = event.user_id.get_calendar_id_office_365()
            url = 'https://graph.microsoft.com/v1.0/me/calendars/{}/events/{}'.format(calendar_id, event.office_id)
            headers = {
                'Host': 'outlook.office.com',
                'Authorization': 'Bearer {0}'.format(event.user_id.token),
                'Accept': 'application/json',
                'X-Target-URL': 'http://outlook.office.com',
                'connection': 'keep-Alive'
            }
            if event.recurrency:
                start = datetime.strptime(event.start, '%Y-%m-%d %H:%M:%S')
                stop = datetime.strptime(event.stop, '%Y-%m-%d %H:%M:%S')
                start = start.strftime('%Y-%m-%d') + ' 00:00:00'
                stop = stop.strftime('%Y-%m-%d') + ' 23:59:59'
                url = 'https://graph.microsoft.com/v1.0/me/calendars/{}/calendarView?startDateTime={}&endDateTime={}'.format(
                    calendar_id, start, stop)
                try:
                    response = requests.get(url=url, headers=headers)
                    if response.status_code == 404:
                        event.with_context(event_from_unlink_request=True).unlink()
                        continue
                    events_view = json.loads((response.content.decode('utf-8')))
                    self.update_and_delete_events_view_to_odoo(events_view, event)
                except Exception as error:
                    _logger.error('Error {} - Event {}'.format(error, event.name))
            else:
                try:
                    response = requests.get(url=url, headers=headers)
                    if response.status_code == 404:
                        event.with_context(event_from_unlink_request=True).unlink()
                        continue
                    elif response.status_code == 200:
                        if event.recurrent_id:
                            events_view = json.loads((response.content.decode('utf-8')))
                            val_update = event.get_value_update_from_outlook(events_view)
                            event.sudo().with_context(not_push_event_to_queue=True).write(val_update)
                except Exception as error:
                    _logger.error('Error {} - Event {}'.format(error, event.name))

    def update_and_delete_events_view_to_odoo(self, values, event):
        delete = True
        for ev in values.get('value'):
            if ev.get('seriesMasterId') == event.office_id:
                val = event.get_value_update_from_outlook(ev)
                if isinstance(event.id, str) and val:
                    event = event.detach_recurring_event()
                    val.update({'office_id': ev.get('id')})
                    event.with_context(not_push_event_to_queue=True).write(val)
                delete = False
                break
        if delete:
            event.with_context(event_from_unlink_request=True).unlink()

    def get_value_update_from_outlook(self, office_value):
        val = self.get_time_value_odoo_and_outlook_event(office_value)
        if self.name != office_value.get('subject', 'No Subject'):
            val.update({'name': office_value.get('subject', 'No Subject')})
        if self.location or '' != office_value['location'].get('displayName', ''):
            val.update({'location': office_value['location'].get('displayName', '')})
        if self.description or '' != office_value.get('bodyPreview', ''):
            val.update({'description': office_value.get('bodyPreview', '')})
        return val

    def get_time_value_odoo_and_outlook_event(self, outlook_time):
        val = {}
        odoo_start = self.start
        if not isinstance(self.start, str):
            odoo_start = self.start.strftime('%Y-%m-%d %H:%M:%S')
        odoo_start = datetime.strptime(odoo_start, '%Y-%m-%d %H:%M:%S').replace(second=0)
        odoo_stop = odoo_start + timedelta(hours=self.duration)
        odoo_stop = odoo_stop.replace(second=0)
        outlook_start = datetime.strptime(outlook_time['start']['dateTime'][:-8], '%Y-%m-%dT%H:%M:%S').replace(second=0)
        outlook_stop = datetime.strptime(outlook_time['end']['dateTime'][:-8], '%Y-%m-%dT%H:%M:%S').replace(second=0)
        if odoo_start != outlook_start:
            val.update({'start': outlook_start})
        if odoo_stop != outlook_stop:
            val.update({'stop': outlook_stop})
        return val

    @api.model
    def call_queue_job_push_event(self, event_id):
        event_id = self.sudo().browse(event_id)
        if event_id:
            event_id.sudo().with_delay(eta=5).push_new_event_to_queue()

    @job
    def push_new_event_to_queue(self):
        self = self.sudo()
        val_need_to_sync = ['name', 'description', 'categ_ids', 'partner_ids', 'start', 'stop', 'show_as', 'location', 'recurrency']
        if self.recurrency:
            extend_val_need_to_sync = ['rrule_type', 'interval', 'end_type']
            val_need_to_sync.extend(extend_val_need_to_sync)
        values = self.search_read([('id', '=', self.id)], val_need_to_sync)
        if not values:
            return False
        value = values[-1]
        for key in list(value.keys()):
            if key not in val_need_to_sync:
                value.pop(key)
        value.update({'start': str(value.get('start')), 'stop': str(value.get('stop'))})
        value = self.get_value_according_to_rrule_type(value)
        calendar_sync = self.create_calendar_sync(value, office_id=False)
        calendar_sync.push_new_event_to_queue_using_cron_job(calendar_sync.id)

    def get_value_according_to_rrule_type(self, value):
        if not value.get('recurrency'):
            return value
        if value.get('end_type') == 'count':
            value.update({'count': self.count})
        if value.get('end_type') == 'end_date':
            value.update({'final_date': str(self.final_date)})
        if value.get('rrule_type') == 'weekly':
            value.update({'mo': self.mo, 'tu': self.tu, 'we': self.we,
                          'th': self.th, 'fr': self.fr, 'sa': self.sa, 'su': self.su})
        if value.get('rrule_type') == 'monthly':
            value.update({'month_by': self.month_by})
            if value.get('monthly') == 'date':
                value.update({'day': self.day})
            if value.get('monthly') == 'day':
                value.update({'byday': self.byday})
                value.update({'week_list': self.week_list})
        return value

    def create_calendar_sync(self, values, office_id):
        event_id = str(self.id).split('-')[0]
        event = self.browse(int(event_id))
        if values.get('start'):
            values.update({'start': str(values.get('start'))})
        if values.get('stop'):
            values.update({'stop': str(values.get('stop'))})
        vals = {
            'name': event.name,
            'event_from': 'odoo',
            'value': json.dumps(values),
            'state': 'new',
            'last_modified': datetime.now(),
            'event_id': event.id,
            'office_id': office_id or event.office_id
        }
        calendar_sync = self.env['calendar.sync'].sudo().create(vals)
        self.env.cr.commit()
        return calendar_sync

    def get_event_id_office365(self, calendar_id, header):
        self.ensure_one()
        event_id = str(self.id).split('-')[0]
        event_id = self.browse(int(event_id))
        if self.recurrency:
            url = 'https://graph.microsoft.com/v1.0/me/calendars/{}/calendarView?startDateTime={}&endDateTime={}'.format(
                calendar_id, self.start, self.stop)
            try:
                response = requests.get(url=url, headers=header)
                if response.status_code != 200:
                    raise ValidationError(_('Bad request: status code {}'.format(response.status_code)))
                events365 = json.loads((response.content.decode('utf-8')))
                for ev in events365.get('value'):
                    if ev.get('seriesMasterId') == event_id.office_id:
                        return ev.get('id')
            except Exception as error:
                _logger.error('Error {} - Event {}'.format(error, self.name))
                raise ValidationError(_('Error {} - Event {}'.format(error, self.name)))
        return event_id.office_id

    def request_get_event_id(self, headers, calendar_id):
        event_id = None
        url = 'https://graph.microsoft.com/v1.0/me/calendars/{}/calendarView?startDateTime={}&endDateTime={}'.format(
            calendar_id, self.start, self.stop)
        try:
            response = requests.get(url=url, headers=headers)
            if response.status_code != 200:
                raise ValidationError(_('Bad request: status code {}'.format(response.status_code)))
            events365 = json.loads((response.content.decode('utf-8')))
            for ev in events365.get('value'):
                if ev.get('seriesMasterId') == self.browse(self.recurrent_id).office_id:
                    event_id = ev.get('id')
                    break
        except Exception as error:
            _logger.error('Error {} - Event {}'.format(error, self.name))
        return event_id

    def requests_del_calendar_view(self, header, calendar_id):
        headers = header
        for meeting_view in self.search([('active', '=', False), ('recurrent_id', '=', self.id)]):
            event_id = meeting_view.request_get_event_id(headers, calendar_id)
            if event_id:
                url_del = 'https://graph.microsoft.com/v1.0/me/calendars/{}/events/{}'.format(calendar_id, event_id)
                response = requests.delete(url=url_del, headers=headers)
                if response.status_code == 204:
                    _logger.info(
                        'Successful deleted event {} from Office365 Calendar'.format(meeting_view.name))
                else:
                    _logger.info('Bad request: status code {}'.format(response.status_code))


class OfficeCalendarValue(models.Model):
    _name = 'office.calendar.value'

    user_id = fields.Many2one('res.users')
    value = fields.Text()

    @api.model
    def create_calendar_value_scheduler(self):
        res_users = self.env['office.sync'].get_users_connect_office_365()
        for user in res_users:
            if user.token:
                user.auto_generate_refresh_token()
                events = self.get_office_calendar_value(user, user.last_calender_import, datetime.now())
                if events:
                    office_calendar_value = self.sudo().create({'user_id': user.id, 'value': events})
                    self.with_delay().create_calender_sync_from_office_to_odoo(office_calendar_value, user)

    def get_office_calendar_value(self, user, from_date, to_date):
        if not from_date:
            from_date = datetime.now() - timedelta(days=365)
        try:
            url = 'https://graph.microsoft.com/v1.0/me/events'
            if from_date and to_date:
                url = '{}?$filter=lastModifiedDateTime ge {}&lastModifiedDateTime le {}'.format(url,
                                                                                                from_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                                                                to_date.strftime("%Y-%m-%dT%H:%M:%SZ"))
            headers = {
                'Host': 'outlook.office.com',
                'Authorization': 'Bearer {0}'.format(user.token),
                'Accept': 'application/json',
                'X-Target-URL': 'http://outlook.office.com',
                'connection': 'keep-Alive'
            }
            response = requests.get(url=url, headers=headers)
            events = json.loads((response.content.decode('utf-8'))).get('value', False)
            events = json.dumps(events)
            user.sudo().write({'last_calender_import': to_date})
            return events
        except Exception as e:
            _logger.info('Error Getting event values from Office365: {}'.format(e))
            return False

    def get_user_by_email(self, email):
        user = False
        users = self.env['res.users'].search([('office365_email', '=', email)])
        if users:
            return users[0]
        return user

    def check_calender_event_of_user(self, user, event):
        if event.get('organizer', False) and event['organizer'].get('emailAddress', False) and \
                event['organizer']['emailAddress'].get('address', False):
            author = self.get_user_by_email(event['organizer']['emailAddress']['address'])
            if author == user:
                return True
        return False

    def check_allow_create_calendar_sync(self, last_modified, office_id):
        already_sync_from_odoo = self.env['calendar.sync'].search([('last_modified', '>=', last_modified),
                                                                   ('office_id', '=', office_id),
                                                                   ('event_from', '=', 'odoo')])
        already_sync_from_365 = self.env['calendar.sync'].search([('last_modified', '>=', last_modified),
                                                                   ('office_id', '=', office_id),
                                                                   ('event_from', '=', 'outlook')])
        if already_sync_from_odoo or already_sync_from_365:
            return False
        return True

    def get_calender_sync_value_from_office(self, event):
        vals = {'event_from': 'outlook',
                'state': 'new',
                'value': json.dumps(event)}
        if event.get('subject', ''):
            vals['name'] = event['subject']
        if event.get('lastModifiedDateTime', False):
            modified = parse(event['lastModifiedDateTime']).strftime('%Y-%m-%d %H:%M:%S')
            vals['last_modified'] = modified
        if event.get('id', False):
            vals['office_id'] = event['id']
            event_ids = self.env['calendar.event'].search([('office_id', '=', event['id'])])
            if event_ids:
                if not isinstance(event_ids[0].id, (int)):
                    event_id = (str(event_ids[0].id)).split('-')[0]
                else:
                    event_id = event_ids[0].id
                vals['event_id'] = event_id
        return vals

    @job
    def create_calender_sync_from_office_to_odoo(self, office_calendar_value, user):
        events = json.loads(office_calendar_value.value)
        if events:
            for event in events:
                is_update_by_user = self.check_calender_event_of_user(user, event)
                if is_update_by_user:
                    vals = self.get_calender_sync_value_from_office(event)
                    if vals.get('last_modified', False) and vals.get('office_id', False):
                        if not self.check_allow_create_calendar_sync(vals['last_modified'], vals['office_id']):
                            continue
                    calendar_sync = self.env['calendar.sync'].sudo().create(vals)
                    calendar_sync.with_delay().sync_calendar_to_odoo(user)

    @api.model
    def auto_unlink_office_calendar_value(self):
        now = datetime.now()
        time_to_unlink = now - timedelta(days=30)
        res_to_delete = self.sudo().search([('create_date', '<=', time_to_unlink)])
        for res in res_to_delete:
            try:
                res.unlink()
            except Exception as e:
                continue
        return True


class CalendarSync(models.Model):
    _name = 'calendar.sync'
    _order = 'last_modified desc'

    event_from = fields.Selection([('odoo', 'Odoo'), ('outlook', 'Outlook')], string='Sync From')
    name = fields.Char()
    value = fields.Text('Value')
    last_modified = fields.Datetime('Last Modified')
    state = fields.Selection([('new', 'New'), ('fail', 'Fail'), ('done', 'Done'), ('cancel', 'Cancel')])
    office_id = fields.Char('Office Id')
    event_id = fields.Many2one('calendar.event')

    '''Sync calendar from odoo to outlook'''

    @job
    def sync_calendar_to_outlook_using_queue(self, user):
        user = user.sudo()
        self = self.sudo()
        calendar_id = user.get_calendar_id_office_365()
        if user.token:
            header = {
                'Authorization': 'Bearer {0}'.format(user.token),
                'Content-Type': 'application/json'
            }
            data = self.get_values_calendar()
            url = 'https://graph.microsoft.com/v1.0/me/calendars/{}/events'.format(calendar_id)
            try:
                if not self.office_id:
                    response = requests.post(url=url, headers=header, data=data).content
                    response = json.loads((response.decode('utf-8')))
                    if response.get('id'):
                        self.sudo().write({'office_id': response.get('id'), 'state': 'done'})
                        self.event_id.sudo().with_context(event_from_request_not_push_to_queue=True).write(
                            {'office_id': response.get('id')})
                    if response.get('recurrence'):
                        self.event_id.requests_del_calendar_view(header, calendar_id)
                else:
                    url = '{}/{}'.format(url, self.office_id)
                    response = requests.patch(url=url, headers=header, data=data).content
                    response = json.loads((response.decode('utf-8')))
                    if response.get('id'):
                        self.sudo().write({'office_id': response.get('id'), 'state': 'done'})
                self.env.cr.commit()
            except Exception as error:
                _logger.error(error)

    def get_category(self, category):
        categ = []
        for categ_id in category:
            event_type = self.env['calendar.event.type'].sudo().browse(categ_id)
            if event_type:
                categ.append(event_type.name)
        return categ

    def get_time(self, alarm_ids):
        alarm = self.env['calendar.alarm'].sudo().browse(alarm_ids[0])
        if alarm.interval == 'minutes':
            return alarm.duration
        elif alarm.interval == 'hours':
            return alarm.duration * 60
        elif alarm.interval == 'days':
            return alarm.duration * 60 * 24

    def get_attendees(self):
        attendee_list = []
        attendees = json.loads(self.value).get('partner_ids')
        attendees = attendees if isinstance(attendees, (list, tuple)) else (attendees, )
        for attendee in attendees:
            attendee = self.env['calendar.attendee'].sudo().search(
                [('event_id', '=', self.event_id.id), ('partner_id', '=', attendee)], limit=1)
            if attendee:
                attendee_list.append({
                    "status": {
                        "response": 'Accepted',
                        "time": datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
                    },
                    "type": "required",
                    "emailAddress": {
                        "address": attendee.email,
                        "name": attendee.display_name
                    }
                })
        return attendee_list

    def get_values_calendar(self):
        try:
            event_val = json.loads(self.value)
            start, stop = str(self.event_id.start), str(self.event_id.stop)
            if event_val.get('start'):
                start = parse(event_val.get('start')).strftime('%Y-%m-%d T %H:%M:%S')
            if event_val.get('stop'):
                stop = parse(event_val.get('stop')).strftime('%Y-%m-%d T %H:%M:%S')
        except Exception as error:
            self.with_context(dont_sync=True).write({'state': 'cancel'})
            _logger.error(error)
            return
        values = {}
        if event_val.get('name'):
            values.update({'subject': event_val.get('name')})
        if event_val.get('description'):
            values.update({'body': {'contentType': 'html', 'content': event_val.get('description')}})
        if event_val.get('categ_ids'):
            values.update({'categories': self.get_category(event_val.get('categ_ids'))})
        if event_val.get('partner_ids'):
            values.update({'attendees': self.get_attendees()})
        if event_val.get('start'):
            values.update({'start': {'dateTime': start, 'timeZone': 'UTC'}})
        if event_val.get('stop'):
            values.update({'end': {'dateTime': stop, 'timeZone': 'UTC'}})
        if event_val.get('show_as'):
            values.update({'showAs': event_val.get('show_as')})
        if event_val.get('location'):
            values.update({'location': {'displayName': event_val.get('location')}})
        if 'recurrency' in event_val.keys() and not event_val['recurrency']:
            values.update({'recurrence': None})
        else:
            if self.event_id.recurrency:
                start = parse(start)
                values.update({'recurrence': {
                    'pattern': {
                        'daysOfWeek': self.get_days(event_val),
                        'type': ('Absolute' if self.event_id.rrule_type not in ['weekly', 'daily'] else '')
                                + self.event_id.rrule_type,
                        'interval': self.event_id.interval or 1,
                        'month': start.month,
                        'dayOfMonth': start.day,
                        'firstDayOfWeek': 'sunday',
                        'index': 'first'
                    },
                    'range': {
                        'type': 'endDate',
                        'startDate': '{}-{}-{}'.format(start.year, start.month, start.day),
                        'endDate': str(self.event_id.final_date),
                        'recurrenceTimeZone': "UTC",
                        'numberOfOccurrences': self.event_id.count or 0,
                    }
                }})
        return json.dumps(values)

    def get_days(self, event_val):
        days = []
        if event_val.get('mo'):
            days.append("monday")
        if event_val.get('tu'):
            days.append("tuesday")
        if event_val.get('we'):
            days.append("wednesday")
        if event_val.get('th'):
            days.append("thursday")
        if event_val.get('fr'):
            days.append("friday")
        if event_val.get('sa'):
            days.append("saturday")
        if event_val.get('su'):
            days.append("sunday")
        return days

    def push_new_event_to_queue_using_cron_job(self, calendar_sync_id):
        calendar_sync = self.browse(calendar_sync_id)
        calendar_event = calendar_sync.event_id
        if not calendar_event:
            return False
        user = calendar_event.user_id
        if not user:
            return False
        user.auto_generate_refresh_token()
        calendar_sync.with_delay(eta=2).sync_calendar_to_outlook_using_queue(user)
        return True
    '''End sync calendar from odoo to outlook'''

    '''Sync calendar from outlook to odoo'''
    @job
    def sync_calendar_to_odoo(self, user):
        try:
            event = json.loads(self.value)
            self.update_calender_odoo(event, self.event_id, user)
            self.write({'state': 'done'})
        except:
            self.write({'state': 'fail'})
            self.env.cr.commit()

    def get_categ_id(self, event):
        categ_id = []
        for categ in event['categories']:
            categ_type_id = self.env['calendar.event.type'].search([('name', '=', categ.strip())])
            if categ_type_id:
                categ_id.append(categ_type_id[0].id)
            else:
                categ_type_id = categ_type_id.create({'name': categ.strip()})
                categ_id.append(categ_type_id[0].id)
        return categ_id

    def get_attendee_email_list_odoo_event(self, odoo_event):
        attendess_mail_list = []
        for attendee in odoo_event.attendee_ids:
            if attendee.email not in attendess_mail_list:
                attendess_mail_list.append(attendee.id)
        attendess_mail_list.sort()
        return attendess_mail_list

    def get_attendee_email_list_office_event(self, event):
        attendess_mail_list = []
        for attendee in event['attendees']:
            if attendee.get('emailAddress', False):
                if attendee['emailAddress'].get('address', False):
                    attendess_mail_list.append(attendee['emailAddress']['address'])
        attendess_mail_list.sort()
        return attendess_mail_list

    def get_event_value(self, event, odoo_event, user):
        categ_id = self.get_categ_id(event)
        value = {}
        office_id = event.get('id')
        name = event.get('subject')
        category_name = event.get('categories')[0] if event.get('categories') else False
        description = event['bodyPreview']
        location = (event['location'].get('displayName', ''))
        start = datetime.strptime(event['start']['dateTime'][:-8], '%Y-%m-%dT%H:%M:%S')
        stop = datetime.strptime(event['end']['dateTime'][:-8], '%Y-%m-%dT%H:%M:%S')
        allday = event.get('isAllDay')
        categ_ids = [(6, 0, categ_id)]
        show_as = event.get('showAs') if event.get('showAs') in ['free', 'busy'] else None
        recurrency = True if event.get('recurrence') else False
        end_type = 'end_date' if event.get('recurrence') else ''
        rrule_type = event['recurrence']['pattern']['type'].replace('absolute', '').lower() if event.get('recurrence') else ''
        count = event['recurrence']['range']['numberOfOccurrences'] if event.get('recurrence') else ''
        final_date = datetime.strptime(event.get('recurrence').get('range').get('endDate'), '%Y-%m-%d').\
            strftime('%Y-%m-%d') if event.get('recurrence') else None

        mo = True if event.get('recurrence') and 'daysOfWeek' in event.get('recurrence').get('pattern').keys() \
                     and 'monday' in event['recurrence']['pattern']['daysOfWeek'] else False

        tu = True if event['recurrence'] and 'daysOfWeek' in event['recurrence']['pattern'].keys() \
                     and 'tuesday' in event['recurrence']['pattern']['daysOfWeek'] else False

        we = True if event['recurrence'] and 'daysOfWeek' in event['recurrence']['pattern'].keys() \
                     and 'wednesday' in event['recurrence']['pattern']['daysOfWeek'] else False

        th = True if event['recurrence'] and 'daysOfWeek' in event['recurrence']['pattern'].keys() \
                     and 'thursday' in event['recurrence']['pattern']['daysOfWeek'] else False

        fr = True if event['recurrence'] and 'daysOfWeek' in event['recurrence']['pattern'].keys() \
                      and 'friday' in event['recurrence']['pattern']['daysOfWeek'] else False

        sa = True if event['recurrence'] and 'daysOfWeek' in event['recurrence']['pattern'].keys() \
                     and 'saturday' in event['recurrence']['pattern']['daysOfWeek'] else False

        su = True if event['recurrence'] and 'daysOfWeek' in event['recurrence']['pattern'].keys() \
                     and 'sunday' in event['recurrence']['pattern']['daysOfWeek'] else False
        if odoo_event:
            if odoo_event.office_id != office_id:
                value['office_id'] = office_id
            if odoo_event.name != name:
                value['name'] = name
            if odoo_event.category_name != category_name:
                value['category_name'] = category_name
            if odoo_event.description != description:
                value['description'] = description
            if odoo_event.location != location:
                value['location'] = location
            if odoo_event.start != start:
                value['start'] = start
            if odoo_event.stop != stop:
                value['stop'] = stop
            if odoo_event.allday != allday:
                value['allday'] = allday
            if list(odoo_event.categ_ids._ids) != categ_id:
                value['categ_ids'] = categ_ids
            if odoo_event.show_as != show_as:
                value['show_as'] = show_as
            if odoo_event.recurrency != recurrency:
                value['recurrency'] = recurrency
            if odoo_event.end_type != end_type:
                value['end_type'] = end_type
            if odoo_event.rrule_type != rrule_type:
                value['rrule_type'] = rrule_type
            if odoo_event.count != count:
                value['count'] = count
            if odoo_event.final_date:
                if odoo_event.final_date.strftime('%Y-%m-%d') != final_date:
                    value['final_date'] = final_date
            else:
                value['final_date'] = final_date
            if odoo_event.mo != mo:
                value['mo'] = mo
            if odoo_event.tu != tu:
                value['tu'] = tu
            if odoo_event.we != we:
                value['we'] = we
            if odoo_event.th != th:
                value['th'] = th
            if odoo_event.fr != fr:
                value['fr'] = fr
            if odoo_event.sa != sa:
                value['sa'] = sa
            if odoo_event.su != su:
                value['su'] = su
        else:
            value.update({
                'user_id': user.id,
                'office_id': office_id,
                'name': name,
                'category_name': category_name,
                "description": description,
                'location': location,
                'start': start,
                'stop': stop,
                'allday': allday,
                'categ_ids': categ_ids,
                'show_as': show_as,
                'recurrency': recurrency,
                'end_type': end_type,
                'rrule_type': rrule_type,
                'count': count,
                'final_date': final_date,
                'mo': mo,
                'tu': tu,
                'we': we,
                'th': th,
                'fr': fr,
                'sa': sa,
                'su': su,
            })
        return value

    def mapping_calendar_attendee(self, event, odoo_event, user):
        partner_ids = []
        attendee_ids = []
        attendess_mail_list = []
        remove_list = []
        for attendee in event['attendees']:
            partner = self.env['res.partner'].search([('email', "=", attendee['emailAddress']['address'])])
            attendess_mail_list.append(attendee['emailAddress']['address'])
            if not partner:
                continue
            odoo_attendee = self.env['calendar.attendee'].search([('event_id', '=', odoo_event.id),
                                                                  ('partner_id', 'in', partner._ids),
                                                                  ('email', '=', attendee['emailAddress']['address'])])
            if odoo_attendee:
                continue
            odoo_attendee_create = self.env['calendar.attendee'].create({
                'partner_id': partner[0].id,
                'event_id': odoo_event.id,
                'email': attendee['emailAddress']['address'],
                'common_name': attendee['emailAddress']['name'],
            })
            attendee_ids.append((4, odoo_attendee_create.id))
            partner_ids.append((4, partner[0].id))
        for attend in odoo_event.attendee_ids:
            if attend.email not in attendess_mail_list:
                remove_list.append(attend.id)
        if remove_list:
            remove_list_obj = self.env['calendar.attendee'].browse(remove_list)
            remove_list_obj.unlink()
        if not event['attendees']:
            odoo_attendee = self.env['calendar.attendee'].create({
                'partner_id': user.partner_id.id,
                'event_id': odoo_event.id,
                'email': user.partner_id.email,
                'common_name': user.partner_id.name,
            })
            odoo_event.with_context(not_push_event_to_queue=True).write({
                'attendee_ids': [(6, 0, [odoo_attendee.id])],
                'partner_ids': [(6, 0, [user.partner_id.id])],
            })
        else:
            odoo_event.with_context(not_push_event_to_queue=True).write({
                'attendee_ids': attendee_ids,
                'partner_ids': partner_ids
            })
        self.env.cr.commit()
        return

    def update_calender_odoo(self, event, odoo_event, user):
        if event['subject'] and event['body']:
            _logger.info('Office365: Getting event {} from Office365'.format(event['id']))
            vals = self.get_event_value(event, odoo_event, user)
            if vals:
                if odoo_event:
                    _logger.info('Office365: Updating event {} In Odoo'.format(event['id']))
                    odoo_event.with_context(not_push_event_to_queue=True).with_user(user).sudo().write(vals)
                else:
                    if not self.query_check_odoo_event(event['id']):
                        _logger.info('Office365: Creating event {} In Odoo'.format(event['id']))
                        odoo_event = self.env['calendar.event'].with_context(event_create_from_office=True).\
                            with_user(user).sudo().create(vals)
            if odoo_event:
                odoo_attendess_mail_list = self.get_attendee_email_list_odoo_event(odoo_event)
                office_attendess_mail_list = self.get_attendee_email_list_office_event(event)
                if odoo_attendess_mail_list != office_attendess_mail_list:
                    self.mapping_calendar_attendee(event, odoo_event, user)

    def query_check_odoo_event(self, office_id):
        query = "SELECT * FROM calendar_event WHERE active = true and office_id = '{}'".format(office_id)
        self._cr.execute(query)
        res = self.env.cr.fetchall()
        if res:
            return True
        return False

    @api.model
    def auto_unlink_calendar_sync(self):
        now = datetime.now()
        time_to_unlink = now - timedelta(days=30)
        res_to_delete = self.sudo().search([('create_date', '<=', time_to_unlink),
                                            ('state', 'not in', ('new', 'fail'))])
        for res in res_to_delete:
            try:
                res.unlink()
            except Exception as e:
                continue
        return True
