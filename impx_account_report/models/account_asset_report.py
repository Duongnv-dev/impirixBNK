# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.tools import format_date
import copy
import binascii
import struct
import time
import itertools
from collections import defaultdict

MAX_NAME_LENGTH = 50


class assets_report(models.AbstractModel):
    _inherit = 'account.assets.report'

    filter_analytic_accounts = []
    filter_analytic_tags = []

    @api.model
    def _get_options(self, previous_options=None):
        """override base function to add analytic, analytic_tags, journals, analytic_accounts to previous_options
        (if not already exist) purpose is show input conditions on search view of report

        :param previous_options:
        :return: previous_options
        """
        res = super(assets_report, self)._get_options(previous_options=previous_options)

        if res.get('analytic') == None:
            res['analytic'] = True

        if res.get('analytic_tags') == None:
            res['analytic_tags'] = []

        if not res.get('journals', []):
            # journals = self.env['account.journal'].search([]).read(['name', 'code', 'type'])
            journals = self._get_filter_journals().read(['name', 'code', 'type'])
            res['journals'] = journals

        if res.get('analytic_accounts') == None:
            res['analytic_accounts'] = []
        return res

    def get_where_asset(self, options):
        """New method Using on _get_assets_lines to build SQL where clause

        :param options:
        process to get some param: journal_ids, analytic_accounts, analytic_tags in options (is search input from user)
        build where_assets (SQL where clause) from params above
        :return: where_assets
        """
        where_assets = ""

        journal_ids = []
        journals = options['journals']

        for journal in journals:
            if not journal.get('selected', False):
                continue

            if journal.get('ids', False):
                journal_ids.extend(journal['ids'])
                continue

            journal_ids.append(journal['id'])

        if journal_ids:
            where_assets += " AND asset.journal_id in ({})".format(
                ','.join([str(journal_id) for journal_id in journal_ids]))

        analytic_accounts = options.get('analytic_accounts', [])
        if analytic_accounts:
            where_assets += " AND asset.account_analytic_id in ({})".format(
                ','.join([str(analytic_account) for analytic_account in analytic_accounts]))

        analytic_tags = options.get('analytic_tags', [])
        if analytic_tags:
            where_assets += " AND asset.id in (select account_asset_id " \
                            "from account_analytic_tag_account_asset_rel " \
                            "where account_analytic_tag_id in ({}))".format(
                ','.join([str(analytic_tag) for analytic_tag in analytic_tags]))

        return where_assets

    def _get_assets_lines(self, options):
        """override base method to add assets condition to sql query

        :param options:
        get where_assets (SQL where clause) from method get_where_asset method
        add this clause to sql query to filter by some more conditions from user input
        :return: results
        """
        where_account_move = ""
        if options.get('all_entries') is False:
            where_account_move += " AND state = 'posted'"

        where_asset = self.get_where_asset(options)

        sql = """
                SELECT asset.id as asset_id,
                       asset.parent_id as parent_id,
                       asset.name as asset_name,
                       asset.value_residual as asset_value,
                       asset.original_value as asset_original_value,
                       asset.first_depreciation_date as asset_date,
                       max_date_before.date as max_date_before,
                       asset.disposal_date as asset_disposal_date,
                       asset.acquisition_date as asset_acquisition_date,
                       asset.method as asset_method,
                       (SELECT COUNT(*) FROM account_move WHERE asset_id = asset.id AND asset_value_change != 't') as asset_method_number,
                       asset.method_period as asset_method_period,
                       asset.method_progress_factor as asset_method_progress_factor,
                       asset.state as asset_state,
                       account.code as account_code,
                       account.name as account_name,
                       account.id as account_id,
                       COALESCE(first_move.asset_depreciated_value, move_before.asset_depreciated_value, 0.0) as depreciated_start,
                       COALESCE(first_move.asset_remaining_value, move_before.asset_remaining_value, 0.0) as remaining_start,
                       COALESCE(last_move.asset_depreciated_value, move_before.asset_depreciated_value, 0.0) as depreciated_end,
                       COALESCE(last_move.asset_remaining_value, move_before.asset_remaining_value, 0.0) as remaining_end,
                       COALESCE(first_move.amount_total, 0.0) as depreciation
                FROM account_asset as asset
                LEFT JOIN account_account as account ON asset.account_asset_id = account.id
                LEFT OUTER JOIN (SELECT MIN(date) as date, asset_id FROM account_move WHERE date >= %(date_from)s AND date <= %(date_to)s {where_account_move} GROUP BY asset_id) min_date_in ON min_date_in.asset_id = asset.id
                LEFT OUTER JOIN (SELECT MAX(date) as date, asset_id FROM account_move WHERE date >= %(date_from)s AND date <= %(date_to)s {where_account_move} GROUP BY asset_id) max_date_in ON max_date_in.asset_id = asset.id
                LEFT OUTER JOIN (SELECT MAX(date) as date, asset_id FROM account_move WHERE date <= %(date_from)s {where_account_move} GROUP BY asset_id) max_date_before ON max_date_before.asset_id = asset.id
                LEFT OUTER JOIN account_move as first_move ON first_move.id = (SELECT m.id FROM account_move m WHERE m.asset_id = asset.id AND m.date = min_date_in.date ORDER BY m.id ASC LIMIT 1)
                LEFT OUTER JOIN account_move as last_move ON last_move.id = (SELECT m.id FROM account_move m WHERE m.asset_id = asset.id AND m.date = max_date_in.date ORDER BY m.id DESC LIMIT 1)
                LEFT OUTER JOIN account_move as move_before ON move_before.id = (SELECT m.id FROM account_move m WHERE m.asset_id = asset.id AND m.date = max_date_before.date ORDER BY m.id DESC LIMIT 1)
                WHERE asset.company_id in %(company_ids)s
                AND asset.acquisition_date <= %(date_to)s
                AND (asset.disposal_date >= %(date_from)s OR asset.disposal_date IS NULL)
                AND asset.state not in ('model', 'draft')
                AND asset.asset_type = 'purchase'
                {where_asset}

                ORDER BY account.code;
            """.format(where_account_move=where_account_move, where_asset=where_asset)

        date_to = options['date']['date_to']
        date_from = options['date']['date_from']
        company_ids = tuple(t['id'] for t in self._get_options_companies(options))

        self.flush()
        self.env.cr.execute(sql, {'date_to': date_to, 'date_from': date_from, 'company_ids': company_ids})
        results = self.env.cr.dictfetchall()
        return results

    @api.model
    def _init_filter_journals(self, options, previous_options=None):
        """override base method to set journal for options

        :param options: filter report options return to client
        :param previous_options: init filter report options
        process set journals of options is copied of previous_options
        :return:
        """
        previous_options = previous_options or {}
        options['journals'] = previous_options.get('journals', [])
