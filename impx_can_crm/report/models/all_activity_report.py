# -*- coding: utf-8 -*-
import datetime

from odoo import fields, models, tools, api
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT


class ImpirixActivityReport(models.Model):
    """ CRM Lead, Res Partner Analysis """

    _name = "impirix.crm.activity.report"
    _auto = False
    _description = "Partner, CRM Activity Analysis"
    _rec_name = 'id'

    name = fields.Char(readonly=True)
    date = fields.Datetime('Completion Date', readonly=True)
    lead_create_date = fields.Datetime('Creation Date', readonly=True)
    date_conversion = fields.Datetime('Conversion Date', readonly=True)
    date_deadline = fields.Date('Expected Closing', readonly=True)
    date_closed = fields.Datetime('Closed Date', readonly=True)
    author_id = fields.Many2one('res.partner', 'Assigned To', readonly=True)
    user_id = fields.Many2one('res.users', 'Salesperson', readonly=True)
    team_id = fields.Many2one('crm.team', 'Sales Team', readonly=True)
    lead_id = fields.Many2one('crm.lead', "Opportunity", readonly=True)
    partner_id = fields.Many2one('res.partner', "Partner", readonly=True)
    body = fields.Html('Activity Description', readonly=True)
    subtype_id = fields.Many2one('mail.message.subtype', 'Subtype', readonly=True)
    mail_activity_type_id = fields.Many2one('mail.activity.type', 'Activity Type', readonly=True)
    country_id = fields.Many2one('res.country', 'Country', readonly=True)
    company_id = fields.Many2one('res.company', 'Company', readonly=True)
    stage_id = fields.Many2one('crm.stage', 'Lead stage', readonly=True)
    lead_type = fields.Selection(
        string='Source type',
        selection=[('lead', 'Lead'), ('opportunity', 'Opportunity'), ('partner', 'Partner')],
        help="Type is used to separate Leads, Opportunities and partner")
    active = fields.Boolean('Active', readonly=True)
    time_range = fields.Selection(
        [('to_day', 'To day'), ('yesterday', 'Yesterday'), ('this_week', 'This week'),
         ('last_week', 'Last week'), ('this_month', 'This month'), ('last_month', 'Last month'),
         ('this_quarter', 'This quarter'), ('last quarter', 'Last quarter'), ('this_year', 'This year'),
         ('last_year', 'Last year')], compute='_compute_search_range', search='_search_time_range')

    def _compute_search_range(self):
        pass

    def get_to_day_range(self):
        change_datetime = self.env['change.datetime']
        now = datetime.datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        end = now

        now = change_datetime.change_utc_to_local_datetime(now)
        now = datetime.datetime.strptime(now, DEFAULT_SERVER_DATETIME_FORMAT)
        start = now.strftime(DEFAULT_SERVER_DATE_FORMAT) + ' 00:00:00'
        start = change_datetime.change_local_datetime_to_utc(start)
        return start, end

    def get_yesterday_range(self):
        today_start, today_end = self.get_to_day_range()
        end = datetime.datetime.strptime(today_start, DEFAULT_SERVER_DATETIME_FORMAT) + datetime.timedelta(seconds=-1)
        start = end + datetime.timedelta(days=-1)
        end = end.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        start = start.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        return start, end

    def get_this_week_range(self):
        today_start, today_end = self.get_to_day_range()
        end = today_end

        change_datetime = self.env['change.datetime']
        start = change_datetime.change_utc_to_local_datetime(today_start)
        start = datetime.datetime.strptime(start, DEFAULT_SERVER_DATETIME_FORMAT)

        delta_day = start.weekday()
        start = start + datetime.timedelta(-delta_day)
        start = start.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        start = change_datetime.change_local_datetime_to_utc(start)

        return start, end

    def get_last_week_range(self):
        this_week_start, this_week_end = self.get_this_week_range()
        end = datetime.datetime.strptime(this_week_start, DEFAULT_SERVER_DATETIME_FORMAT)
        end = end + datetime.timedelta(seconds=-1)
        start = end + datetime.timedelta(days=-7)
        end = end.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        start = start.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        return start, end

    def get_this_month_range(self):
        today_start, today_end = self.get_to_day_range()
        end = today_end

        change_datetime = self.env['change.datetime']
        start = change_datetime.change_utc_to_local_datetime(today_start)
        start = datetime.datetime.strptime(start, DEFAULT_SERVER_DATETIME_FORMAT)

        delta_day = start.day - 1
        start = start + datetime.timedelta(-delta_day)
        start = start.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        start = change_datetime.change_local_datetime_to_utc(start)
        return start, end

    def get_last_month_range(self):
        this_month_start, this_month_end = self.get_this_month_range()

        change_datetime = self.env['change.datetime']
        end = this_month_start
        end = datetime.datetime.strptime(end, DEFAULT_SERVER_DATETIME_FORMAT)
        end = end + datetime.timedelta(seconds=-1)
        end = end.strftime(DEFAULT_SERVER_DATETIME_FORMAT)

        start = change_datetime.change_utc_to_local_datetime(end)
        start = datetime.datetime.strptime(start, DEFAULT_SERVER_DATETIME_FORMAT)
        delta_day = start.day
        start = start + datetime.timedelta(days=-delta_day)
        start = start + datetime.timedelta(seconds=1)

        start = start.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        start = change_datetime.change_local_datetime_to_utc(start)
        return start, end

    def subtract_month(self, source_datetime):
        res_datetime = '{}-{}-{} {}:{}:{}'.format(
            source_datetime.year, source_datetime.month-1,
            source_datetime.day, source_datetime.hour,
            source_datetime.minute, source_datetime.second)
        res_datetime = datetime.datetime.strptime(res_datetime, DEFAULT_SERVER_DATETIME_FORMAT)
        return res_datetime

    def get_this_quarter_range(self):
        this_month_start, this_month_end = self.get_this_month_range()
        this_quater_end = this_month_end

        this_quater_end_obj = datetime.datetime.strptime(this_quater_end, DEFAULT_SERVER_DATETIME_FORMAT)
        this_quarter_start = '{}-{}-01 00:00:00'.format(this_quater_end_obj.year, this_quater_end_obj.month)
        this_quarter_start = datetime.datetime.strptime(this_quarter_start, DEFAULT_SERVER_DATETIME_FORMAT)

        change_datetime = self.env['change.datetime']
        for index in range(0, 3):
            if this_quarter_start.month in (1, 4, 7, 10):
                break
            this_quarter_start = self.subtract_month(this_quarter_start)

        this_quarter_start = this_quarter_start.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        this_quarter_start = change_datetime.change_local_datetime_to_utc(this_quarter_start)
        return this_quarter_start, this_quater_end

    def get_last_quarter_range(self):
        this_quarter_start, this_quarter_end = self.get_this_quarter_range()
        end = this_quarter_start
        end = datetime.datetime.strptime(end, DEFAULT_SERVER_DATETIME_FORMAT)
        end_obj = end = end + datetime.timedelta(seconds=-1)
        end = end.strftime(DEFAULT_SERVER_DATETIME_FORMAT)

        change_datetime = self.env['change.datetime']
        start = '{}-{}-01 00:00:00'.format(end_obj.year, end_obj.month)
        start = datetime.datetime.strptime(start, DEFAULT_SERVER_DATETIME_FORMAT)

        for index in range(0, 3):
            if start.month in (1, 4, 7, 10):
                break
            start = self.subtract_month(start)

        start = start.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        start = change_datetime.change_local_datetime_to_utc(start)
        return start, end

    def get_this_year_range(self):
        this_quarter_start, this_quarter_end = self.get_this_quarter_range()
        end = this_quarter_end

        end_obj = datetime.datetime.strptime(end, DEFAULT_SERVER_DATETIME_FORMAT)
        year = end_obj.year
        start = '{}-01-01 00:00:00'.format(year)
        change_datetime = self.env['change.datetime']
        start = change_datetime.change_local_datetime_to_utc(start)
        return start, end

    def get_last_year_range(self):
        this_quarter_start, this_quarter_end = self.get_this_quarter_range()

        this_quarter_end_obj = datetime.datetime.strptime(this_quarter_end, DEFAULT_SERVER_DATETIME_FORMAT)
        year = this_quarter_end_obj.year - 1
        start = '{}-01-01 00:00:00'.format(year)
        end = '{}-12-31 23:59:59'.format(year)

        change_datetime = self.env['change.datetime']
        start = change_datetime.change_local_datetime_to_utc(start)
        end = change_datetime.change_local_datetime_to_utc(end)
        return start, end

    def get_start_end_time_range(self, value):
        function_dict = {
            'to_day': 'get_to_day_range',
            'yesterday': 'get_yesterday_range',
            'this_week': 'get_this_week_range',
            'last_week': 'get_last_week_range',
            'this_month': 'get_this_month_range',
            'last_month': 'get_last_month_range',
            'this_quarter': 'get_this_quarter_range',
            'last_quarter': 'get_last_quarter_range',
            'this_year': 'get_this_year_range',
            'last_year': 'get_last_year_range'
        }

        function = function_dict.get(value, False)
        return getattr(self, function)()

    def _search_time_range(self, operator, value):
        start, end = self.get_start_end_time_range(value)
        if operator in ('>', '>='):
            domain = [('date', operator, start)]
        else:
            domain = [('date', operator, end)]
        return domain

    def search(self, args, **kwargs):
        return super(ImpirixActivityReport, self).search(args, **kwargs)

    def _get_subtype(self):
        disccusion_subtype = self.env.ref('mail.mt_comment')
        mt_activities = self.env.ref('mail.mt_activities') #call
        mt_note = self.env.ref('mail.mt_note') #note
        res = []
        res.append(mt_activities.id)
        res.append(disccusion_subtype.id)
        res.append(mt_note.id)
        return res

    def _lead_select(self):
        return """
            SELECT
                m.id,
                l.name as name,
                l.create_date AS lead_create_date,
                l.date_conversion,
                l.date_deadline,
                l.date_closed,
                m.subtype_id,
                m.mail_activity_type_id,
                m.author_id,
                m.date,
                m.body,
                l.id as lead_id,
                l.user_id,
                l.team_id,
                l.country_id,
                l.company_id,
                l.stage_id,
                l.partner_id,
                l.type as lead_type,
                l.active
        """

    def _lead_from(self):
        return """
            FROM mail_message AS m
        """

    def _lead_join(self):
        return """
            JOIN crm_lead AS l ON m.res_id = l.id
        """

    def _lead_where(self):
        subtype_ids = self._get_subtype()
        subtype_clause = ','.join([str(subtype_id) for subtype_id in subtype_ids])
        return """
            WHERE
                m.model = 'crm.lead' AND (m.mail_activity_type_id IS NOT NULL OR m.subtype_id in ({}))
        """.format(subtype_clause)

    def _partner_select(self):
        return """
            SELECT
                m.id,
                p.name as name,
                p.create_date AS lead_create_date,
                null as date_conversion,
                null as date_deadline,
                null as date_closed,
                m.subtype_id,
                m.mail_activity_type_id,
                m.author_id,
                m.date,
                m.body,
                null as lead_id,
                p.user_id,
                p.team_id,
                p.country_id,
                p.company_id,
                null as stage_id,
                p.id as partner_id,
                'partner' as lead_type,
                p.active
        """

    def _partner_from(self):
        return """
            FROM mail_message AS m
        """

    def _partner_join(self):
        return """
            JOIN res_partner AS p ON m.res_id = p.id
        """

    def _partner_where(self):
        subtype_ids = self._get_subtype()
        subtype_clause = ','.join([str(subtype_id) for subtype_id in subtype_ids])
        return """
            WHERE
                m.model = 'res.partner' AND (m.mail_activity_type_id IS NOT NULL OR m.subtype_id in ({}))
        """.format(subtype_clause)

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                %s
                %s
                %s
                %s
                union 
                %s
                %s
                %s
                %s
            )
        """ % (self._table, self._lead_select(), self._lead_from(), self._lead_join(), self._lead_where(),
               self._partner_select(), self._partner_from(), self._partner_join(), self._partner_where())
        )
