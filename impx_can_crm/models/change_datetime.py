# -*- encoding: utf-8 -*-

from odoo import api, fields, models, _
import datetime, pytz
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT


class ChangeDateTime(models.Model):
    _name = 'change.datetime'
    _description = 'Change Datetime'
    _auto = False

    def change_utc_to_local_datetime(self, source_date, option=DEFAULT_SERVER_DATETIME_FORMAT):
        user_tz = self.env.user.tz or False
        if user_tz:
            tz_now = datetime.datetime.now(pytz.timezone(user_tz))
            difference = tz_now.utcoffset().total_seconds() / 60 / 60
            difference = int(difference)
        else:
            difference = 10
        utc_date = datetime.datetime.strptime(source_date, '%Y-%m-%d %H:%M:%S')
        local_date = utc_date + datetime.timedelta(hours=difference)
        return local_date.strftime(option)

    def change_local_datetime_to_utc(self, source_date, option=DEFAULT_SERVER_DATETIME_FORMAT):
        user_tz = self.env.user.tz or False
        if user_tz:
            tz_now = datetime.datetime.now(pytz.timezone(user_tz))
            difference = tz_now.utcoffset().total_seconds() / 60 / 60
            difference = int(difference)
        else:
            difference = 10
        local_date = datetime.datetime.strptime(source_date,
                                                '%Y-%m-%d %H:%M:%S')
        utc_date = local_date + datetime.timedelta(hours=-difference)
        return utc_date.strftime(option)

