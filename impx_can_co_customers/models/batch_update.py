from odoo import api, fields, models, _, tools
import urllib.request
from bs4 import BeautifulSoup
import datetime
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
import base64

from odoo.exceptions import ValidationError
from xlrd import open_workbook
import io
import requests
import logging
_logger = logging.getLogger(__name__)


class ColoradoPartner(models.Model):
    _name = 'colorado.partner'

    name = fields.Char('Name')
    license_number = fields.Char('License Number')
    dba = fields.Char('DBA')
    facility_type = fields.Char('Facility Type')
    city = fields.Char('City')
    zip_code = fields.Char('Zip Code')
    update_date = fields.Date('Update Date')
    type = fields.Selection([('med', 'Medical'), ('rec', 'Retail')])
    state = fields.Selection([('create', 'Create'), ('license_expired', 'License Expired')])
    partner_id = fields.Many2one('res.partner')
    batch_update_id = fields.Many2one('batch.update.customer')
    type_of_co_partner = fields.Selection([
        ('is_store', 'Stores'),
        ('is_testing_facility', 'Testing_Facility'),
        ('is_transporter', 'Transporter')
    ], string="Partner Type")


class CoStoresMedMappingFields(models.Model):
    _name = 'co.stores.med.mapping.field'

    partner_field = fields.Many2one('ir.model.fields', required=True, domain=[('model_id.model', '=', 'colorado.partner')])
    column_number = fields.Integer()
    note = fields.Char()
    config_id = fields.Many2one('batch.update.customer.config')


class CoStoresRecMappingFields(models.Model):
    _name = 'co.stores.rec.mapping.field'

    partner_field = fields.Many2one('ir.model.fields', required=True, domain=[('model_id.model', '=', 'colorado.partner')])
    column_number = fields.Integer()
    note = fields.Char()
    config_id = fields.Many2one('batch.update.customer.config')


class CoTestingFacilitiesMedMappingFields(models.Model):
    _name = 'co.testing.facilities.med.mapping.field'

    partner_field = fields.Many2one('ir.model.fields', required=True, domain=[('model_id.model', '=', 'colorado.partner')])
    column_number = fields.Integer()
    note = fields.Char()
    config_id = fields.Many2one('batch.update.customer.config')


class CoTestingFacilitiesRecMappingFields(models.Model):
    _name = 'co.testing.facilities.rec.mapping.field'

    partner_field = fields.Many2one('ir.model.fields', required=True, domain=[('model_id.model', '=', 'colorado.partner')])
    column_number = fields.Integer()
    note = fields.Char()
    config_id = fields.Many2one('batch.update.customer.config')


class CoTransportersMedMappingFields(models.Model):
    _name = 'co.transporters.med.mapping.field'

    partner_field = fields.Many2one('ir.model.fields', required=True, domain=[('model_id.model', '=', 'colorado.partner')])
    column_number = fields.Integer()
    note = fields.Char()
    config_id = fields.Many2one('batch.update.customer.config')


class CoTransportersRecMappingFields(models.Model):
    _name = 'co.transporters.rec.mapping.field'

    partner_field = fields.Many2one('ir.model.fields', required=True, domain=[('model_id.model', '=', 'colorado.partner')])
    column_number = fields.Integer()
    note = fields.Char()
    config_id = fields.Many2one('batch.update.customer.config')


class BatchUpdateConfig(models.Model):
    _name = 'batch.update.customer.config'

    co_url = fields.Char()
    co_menu_stores = fields.Char(default='Stores', required=True)
    co_menu_testing_facilities = fields.Char(default='Testing Facilities', required=True)
    co_menu_transporters = fields.Char(default='Transporters', required=True)

    co_stores_med_sheet_name = fields.Char(default='Medical')
    co_stores_rec_sheet_name = fields.Char(default='Retail')
    co_testing_facilities_med_sheet_name = fields.Char(default='Medical')
    co_testing_facilities_rec_sheet_name = fields.Char(default='Retail')
    co_transporters_med_sheet_name = fields.Char(default='Medical')
    co_transporters_rec_sheet_name = fields.Char(default='Retail')

    co_stores_med_file_start_read = fields.Integer(default=1)
    co_stores_rec_file_start_read = fields.Integer(default=1)
    co_testing_facilities_med_file_start_read = fields.Integer(default=1)
    co_testing_facilities_rec_file_start_read = fields.Integer(default=1)
    co_transporters_med_file_start_read = fields.Integer(default=1)
    co_transporters_rec_file_start_read = fields.Integer(default=1)

    notify_user_ids = fields.Many2many('res.users')

    co_stores_med_map_ids = fields.One2many('co.stores.med.mapping.field', 'config_id')
    co_stores_rec_map_ids = fields.One2many('co.stores.rec.mapping.field', 'config_id')
    co_testing_facilities_med_map_ids = fields.One2many('co.testing.facilities.med.mapping.field', 'config_id')
    co_testing_facilities_rec_map_ids = fields.One2many('co.testing.facilities.rec.mapping.field', 'config_id')
    co_transporters_med_map_ids = fields.One2many('co.transporters.med.mapping.field', 'config_id')
    co_transporters_rec_map_ids = fields.One2many('co.transporters.rec.mapping.field', 'config_id')

    def save_config(self):
        return True


class BatchUpdateCustomerLog(models.Model):
    _name = 'batch.update.customer.log'
    _order = 'id DESC'

    log_time = fields.Datetime()
    message = fields.Text()
    batch_id = fields.Many2one('batch.update.customer')


class PartnerUpdateChange(models.Model):
    _name = 'partner.update.change'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one('res.partner', ondelete='cascade')
    regulatory_license_type = fields.Selection(related='partner_id.regulatory_license_type', readonly=True)
    regulatory_license = fields.Char(related='partner_id.regulatory_license', readonly=True)
    user_id = fields.Many2one(related='partner_id.user_id', readonly=True)

    def open_partner(self):
        if self.partner_id:
            return {
                'view_mode': 'form',
                'view_id': self.env.ref('base.view_partner_form').id,
                'res_model': 'res.partner',
                'type': 'ir.actions.act_window',
                'target': 'new',
                'res_id': self.partner_id.id,
                'flags': {'mode': 'edit'}
            }
        else:
            return False


class BatchUpdateCustomer(models.Model):
    _name = 'batch.update.customer'
    _order = 'id DESC'
    _description = 'Batch Update Customer'

    name = fields.Char()
    run_date = fields.Datetime(default=datetime.datetime.now())
    log_ids = fields.One2many('batch.update.customer.log', 'batch_id')
    url = fields.Char()
    new_customer_ids = fields.Many2many('partner.update.change', 'new_customer_partner_update_rel')
    license_expired_customer_ids = fields.Many2many('partner.update.change', 'license_expired_customer_partner_update_rel')
    batch_url = fields.Char(compute='_compute_batch_url', store=True)
    stores_file = fields.Binary(attachment=True)
    stores_file_name = fields.Char()
    testing_facilities_file = fields.Binary(attachment=True)
    testing_facilities_file_name = fields.Char()
    transporters_file = fields.Binary(attachment=True)
    transporters_file_name = fields.Char()
    state = fields.Selection([('new', 'Draft'), ('in_progress', 'In Progress'),
                              ('done', 'Done'), ('fail', 'Fail')], default='new')
    create_colorado_partner_ids = fields.One2many('colorado.partner', 'batch_update_id',
                                                  domain=[('state', '=', 'create')])
    license_expired_colorado_partner_ids = fields.One2many('colorado.partner', 'batch_update_id',
                                                    domain=[('state', '=', 'license_expired')])
    hide_validation = fields.Boolean(default=True)
    hide_suggest = fields.Boolean(default=True)
    readonly_file = fields.Boolean(default=False)

    @api.onchange('stores_file', 'testing_facilities_file', 'transporters_file')
    def onchange_file(self):
        for rec in self:
            rec.hide_validation = True
            rec.hide_suggest = True
            rec.create_colorado_partner_ids = None
            rec.license_expired_colorado_partner_ids = None
            rec.state = 'in_progress'
            if rec.stores_file and rec.testing_facilities_file and rec.transporters_file:
                rec.hide_suggest = False
                rec.readonly_file = True
            if not rec.stores_file and not rec.testing_facilities_file and not rec.transporters_file:
                rec.state = 'new'

    def _compute_batch_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        action_id = self.env.ref('impx_can_co_customers.batch_update_customer_action').id
        menu_id = self.env.ref('impx_can_co_customers.menu_crm_batch_update_customer').id
        for s in self:
            if not base_url or not action_id or not menu_id:
                s.batch_url = False
            else:
                s.batch_url = '{}/web#action={}&id={}&menu_id={}&model=batch.update.customer&view_type=form'.format(base_url,action_id,s.id, menu_id)

    def get_link_download(self, url, message_list):
        try:
            html_page = urllib.request.urlopen(url)
        except Exception:
            message = 'URL invalid. Please check the url again.'
            message_list.append(message)
            return False, message_list
        soup = BeautifulSoup(html_page, features="lxml")
        table = soup.find('table')
        if not table:
            message = 'Can not find link to download file.Please check the url again.'
            message_list.append(message)
            return False, message_list
        rows = table.findAll('tr')
        file_id_dict = {}
        config = self.env['batch.update.customer.config'].search([], limit=1)
        for tr in rows:
            cols = tr.findAll('td')
            if config.co_menu_stores in cols[0].text:
                link = cols[0].find('a').get('href')
                link_list = link.split('edit')
                file_id = '{}export?format=xlsx'.format(link_list[0])
                file_id_dict['Stores'] = file_id
            if config.co_menu_testing_facilities in cols[0].text:
                link = cols[0].find('a').get('href')
                link_list = link.split('edit')
                file_id = '{}export?format=xlsx'.format(link_list[0])
                file_id_dict['Testing Facilities'] = file_id
            if config.co_menu_transporters in cols[0].text:
                link = cols[0].find('a').get('href')
                link_list = link.split('edit')
                file_id = '{}export?format=xlsx'.format(link_list[0])
                file_id_dict['Transporters'] = file_id
        return file_id_dict, message_list

    def get_file(self, url, message_list):
        file_id_dict, message_list = self.get_link_download(url, message_list)
        if not file_id_dict:
            self.state = 'fail'
            return message_list
        today = datetime.datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        today_str = self.env['change.datetime'].change_utc_to_local_datetime(today, '%Y%m%d_%H%M%S')
        if file_id_dict:
            self.state = 'in_progress'
            try:
                for key in file_id_dict:
                    if key == 'Stores' and requests.get(file_id_dict[key]).status_code == 200:
                        self.stores_file = base64.b64encode(requests.get(file_id_dict[key]).content)
                        self.stores_file_name = '{}_{}.xlsx'.format(key, today_str)
                    if key == 'Testing Facilities' and requests.get(file_id_dict[key]).status_code == 200:
                        self.testing_facilities_file = base64.b64encode(requests.get(file_id_dict[key]).content)
                        self.testing_facilities_file_name = '{}_{}.xlsx'.format(key, today_str)
                    if key == 'Transporters' and requests.get(file_id_dict[key]).status_code == 200:
                        self.transporters_file = base64.b64encode(requests.get(file_id_dict[key]).content)
                        self.transporters_file_name = '{}_{}.xlsx'.format(key, today_str)
            except Exception:
                message = 'Cannot download file from website.'
                message_list.append(message)
                self.state = 'fail'
        return message_list

    def get_config_info(self, file_name=False):
        config = self.env['batch.update.customer.config'].search([], limit=1)
        result = {}
        if config:
            url = config.co_url or False
            user_ids = config.notify_user_ids
            notify_partner_ids = [user.partner_id.id for user in user_ids]
            result = {
                'url': url,
                'notify_partner_ids': notify_partner_ids,
            }
            if file_name == config.co_menu_stores:
                med = config.co_stores_med_map_ids
                rec = config.co_stores_rec_map_ids
                result.update({'med_file_start_read': config.co_stores_med_file_start_read})
                result.update({'rec_file_start_read': config.co_stores_rec_file_start_read})
            elif file_name == config.co_menu_testing_facilities:
                med = config.co_testing_facilities_med_map_ids
                rec = config.co_testing_facilities_rec_map_ids
                result.update({'med_file_start_read': config.co_testing_facilities_med_file_start_read})
                result.update({'rec_file_start_read': config.co_testing_facilities_rec_file_start_read})
            elif file_name == config.co_menu_transporters:
                med = config.co_transporters_med_map_ids
                rec = config.co_transporters_rec_map_ids
                result.update({'med_file_start_read': config.co_transporters_med_file_start_read})
                result.update({'rec_file_start_read': config.co_transporters_rec_file_start_read})
            else:
                return result
            med_map_field_dict = {}
            rec_map_field_dict = {}
            for line_med in med:
                med_map_field_dict[line_med.partner_field.name] = line_med.column_number
            result['med_map_field_dict'] = med_map_field_dict
            for line_rec in rec:
                rec_map_field_dict[line_rec.partner_field.name] = line_rec.column_number
            result['rec_map_field_dict'] = rec_map_field_dict
        return result

    def get_data_from_file(self, file):
        medical_res_dict = {}
        retail_res_dict = {}
        config = self.env['batch.update.customer.config'].search([], limit=1)
        try:
            inputx = io.BytesIO()
            inputx.write(base64.decodebytes(file))
            book = open_workbook(file_contents=inputx.getvalue())
            worksheets = book.sheets()
            medical_res_stores = []
            retail_res_stores = []
            medical_res_testing_facilities = []
            retail_res_testing_facilities = []
            medical_res_transporters = []
            retail_res_transporters = []
            for worksheet in worksheets:
                num_rows = worksheet.nrows - 1
                num_cells = worksheet.ncols - 1
                curr_row = -1
                while curr_row < num_rows:
                    curr_row += 1
                    row = []
                    curr_cell = -1
                    while curr_cell < num_cells:
                        curr_cell += 1
                        row.append(worksheet.cell_value(curr_row, curr_cell))
                    if worksheet.name == config.co_stores_med_sheet_name:
                        medical_res_stores.append(row)
                    if worksheet.name == config.co_stores_rec_sheet_name:
                        retail_res_stores.append(row)
                    if worksheet.name == config.co_testing_facilities_med_sheet_name:
                        medical_res_testing_facilities.append(row)
                    if worksheet.name == config.co_testing_facilities_rec_sheet_name:
                        retail_res_testing_facilities.append(row)
                    if worksheet.name == config.co_transporters_med_sheet_name:
                        medical_res_transporters.append(row)
                    if worksheet.name == config.co_transporters_rec_sheet_name:
                        retail_res_transporters.append(row)
            if file == self.stores_file:
                medical_res_dict.update({'Stores_Med': medical_res_stores})
                retail_res_dict.update({'Stores_Rec':  retail_res_stores})
            if file == self.testing_facilities_file:
                medical_res_dict.update({'Testing Facilities_Med': medical_res_testing_facilities})
                retail_res_dict.update({'Testing Facilities_Rec': retail_res_testing_facilities})
            if file == self.transporters_file:
                medical_res_dict.update({'Transporters_Med': medical_res_transporters})
                retail_res_dict.update({'Transporters_Rec': retail_res_transporters})
            return medical_res_dict, retail_res_dict
        except Exception as error:
            _logger.info('ERROR: {}'.format(error))
            self.state = 'fail'
            self.create_log([str(error)])
            return medical_res_dict, retail_res_dict
        
    def get_all_data_from_file(self):
        all_data_tuple = ()
        if self.stores_file:
            all_data_tuple += self.get_data_from_file(self.stores_file)
        if self.testing_facilities_file:
            all_data_tuple += self.get_data_from_file(self.testing_facilities_file)
        if self.transporters_file:
            all_data_tuple += self.get_data_from_file(self.transporters_file)
        return all_data_tuple

    def get_category_tag(self, stage):
        prev = 'MEDList'
        if stage == 'license_expired':
            prev = u'License Expired'
        today = datetime.datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        today_str = self.env['change.datetime'].change_utc_to_local_datetime(today, '%Y-%m')
        name = prev + today_str
        category = self.env['res.partner.category'].sudo().search([('name', '=', name)])
        if category:
            category_id = category[0]
        else:
            category_id = self.env['res.partner.category'].sudo().create({'name': name})
        return category_id.id

    def get_state_country(self):
        states = self.env['res.country.state'].search([('name', '=', 'Colorado')])
        if states:
            state_id = states[0].id
        else:
            state_id = False
        countries = self.env['res.country'].search([('name', '=', 'United States')])
        if countries:
            country_id = countries[0].id
        else:
            country_id = False
        return state_id, country_id

    def get_db_partner(self, license_type):
        domain = [('regulatory_license_type', '=', license_type), ('is_company', '=', True), ('license_expired', '=', False)]
        partners = self.env['res.partner'].sudo().search_read(domain, ['regulatory_license'])
        partners_dict = dict((row['regulatory_license'], row['id']) for row in partners)
        regulatory_license_list = [partner['regulatory_license'] for partner in partners]
        return partners_dict, regulatory_license_list

    def import_data(self, config, message_list):
        create_ids = []
        excel_list_total = []
        license_expired_ids = []
        if not self.stores_file and not self.testing_facilities_file and not self.transporters_file:
            message_list.append('The file is missing. Please check the file')
            return create_ids, license_expired_ids, message_list
        all_data_tuple = self.get_all_data_from_file()
        for data_dict in all_data_tuple:
            for key in data_dict:
                regulatory_type = 'med' if 'Med' in key else 'rec'
                type_of_co_partner = False
                if "Stores" in key:
                    config = self.sudo().get_config_info(file_name="Stores")
                    type_of_co_partner = 'is_store'
                elif "Testing Facilities" in key:
                    config = self.sudo().get_config_info(file_name="Testing Facilities")
                    type_of_co_partner = 'is_testing_facility'
                elif "Transporters" in key:
                    config = self.sudo().get_config_info(file_name="Transporters")
                    type_of_co_partner = 'is_transporter'
                if not type_of_co_partner:
                    continue
                data = data_dict[key]
                try:
                    record_ids = self.import_file_to_colorado_partner(
                        data, config, regulatory_type, type_of_co_partner, message_list)
                    if record_ids:
                        create_ids.extend(record_ids[0])
                        excel_list_total.extend(record_ids[1])
                        message_list.extend(record_ids[2])
                except Exception as e:
                    raise ValidationError(_('{}{}'.format('File excel format is invalid.\nDetail:  ', e)))
        license_expired_ids = self.import_license_expired_customer(all_data_tuple, excel_list_total)
        return create_ids, license_expired_ids, message_list

    def import_license_expired_customer(self, all_data_tuple, excel_list_total):
        license_expired_ids = []
        license_expired_partner_values = []
        colorado_partner = self.env['colorado.partner'].sudo()
        res_partner = self.env['res.partner'].sudo()
        for data_dict in all_data_tuple:
            for key in data_dict:
                regulatory_type = 'med' if 'Med' in key else 'rec'
                partners_dict, regulatory_license_list = self.get_db_partner(regulatory_type)
                for regulatory_license in regulatory_license_list:
                    if regulatory_license not in excel_list_total:
                        partner = res_partner.browse(partners_dict.get(regulatory_license))
                        item_val = {'license_number': partner.regulatory_license, 'name': partner.name,
                                    'dba': partner.doing_business_as, 'city': partner.city, 'zip_code': partner.zip,
                                    'type': partner.regulatory_license_type,
                                    'state': 'license_expired', 'partner_id': partner.id}
                        if self.build_value_colorado_partner(item_val) not in license_expired_partner_values:
                            license_expired_partner_values.append(self.build_value_colorado_partner(item_val))
        try:
            colorado_partner_license_expired = colorado_partner.create(license_expired_partner_values)
            license_expired_ids.extend(colorado_partner_license_expired)
        except Exception as e:
            raise ValidationError(_('{}{}'.format('File excel format is invalid.\nDetail:  ', e)))
        return license_expired_ids

    def build_value_colorado_partner(self, file_val):
        return {
            'name': file_val.get('name'),
            'license_number': file_val.get('license_number'),
            'dba': file_val.get('dba'),
            'facility_type': file_val.get('facility_type'),
            'city': file_val.get('city'),
            'zip_code': file_val.get('zip_code'),
            'update_date': file_val.get('update_date'),
            'type': file_val.get('type'),
            'state': file_val.get('state'),
            'partner_id': file_val.get('partner_id'),
            'type_of_co_partner': file_val.get('type_of_co_partner'),
            'batch_update_id': self.id,
        }

    def get_value_create_colorado_partner(self, line, map_field_dict, regulatory_type, type_of_co_partner, res_partner, excel_license):
        if not excel_license:
            return {}
        partner = res_partner.search([('regulatory_license', '=', excel_license)], limit=1)
        line_val = {'name': excel_license,
                    'license_number': excel_license,
                    'type': regulatory_type,
                    'type_of_co_partner': type_of_co_partner,
                    'state': 'create',
                    'partner_id': partner.id if partner else None}
        name_index = map_field_dict.get('name')
        if isinstance(name_index, int):
            name = line[name_index] or excel_license
            line_val['name'] = name
        dba_index = map_field_dict.get('dba')
        if isinstance(dba_index, int):
            line_val['dba'] = line[dba_index]
        facility_type_index = map_field_dict.get('facility_type')
        if isinstance(facility_type_index, int):
            line_val['facility_type'] = line[facility_type_index]
        city_index = map_field_dict.get('city')
        if isinstance(city_index, int):
            line_val['city'] = line[city_index]
        zip_code_index = map_field_dict.get('zip_code')
        if isinstance(zip_code_index, int):
            line_val['zip_code'] = line[zip_code_index]
        update_date_index = map_field_dict.get('update_date')
        if isinstance(update_date_index, int):
            line_val['update_date'] = line[update_date_index]
        return line_val

    def checkout_config(self, data, start_index, map_field_dict, regulatory_type, message_list):
        if start_index > len(data) or start_index < 0:
            message_list.append(
                'Read file starting from line number ({}) invalid. Please check the configuration'.format(
                    regulatory_type, ''))
            self.state = 'fail'
            return False, message_list
        if 'license_number' not in map_field_dict:
            message_list.append(
                'The regulatory_license field is not in the configuration ({}). Please check the configuration'.format(
                    regulatory_type, ''))
            self.state = 'fail'
            return False, message_list
        return True, message_list

    def import_file_to_colorado_partner(self, data, config, regulatory_type, type_of_co_partner, message_list):
        create_ids = []
        partners_dict, regulatory_license_list = self.get_db_partner(regulatory_type)
        start_index, map_field_dict = config.get('med_file_start_read'), config.get('med_map_field_dict')
        if regulatory_type == 'rec':
            start_index, map_field_dict = config.get('rec_file_start_read'), config.get('rec_map_field_dict')
        if not self.checkout_config(data, start_index, map_field_dict, regulatory_type, message_list)[0]:
            return create_ids, license_expired_ids, message_list
        colorado_partner = self.env['colorado.partner'].sudo()
        res_partner = self.env['res.partner'].sudo()
        excel_list = []
        create_partner_values = []
        for line in data[start_index:]:
            if 'license_number' not in map_field_dict.keys():
                break
            excel_license = str(line[map_field_dict['license_number']])
            if not excel_license:
                continue
            if excel_license not in excel_list:
                excel_list.append(excel_license)
            if excel_license not in regulatory_license_list:
                line_val = self.get_value_create_colorado_partner(line, map_field_dict, regulatory_type, type_of_co_partner, res_partner, excel_license)
                if line_val:
                    create_partner_values.append(self.build_value_colorado_partner(line_val))
        colorado_partner_new = colorado_partner.create(create_partner_values)
        create_ids.extend(colorado_partner_new.ids)
        return create_ids, excel_list, message_list

    def create_log(self, message_list):
        if not message_list:
            return False
        mess = '\n'.join(set(message_list))
        vals = {
            'batch_id': self.id,
            'log_time': datetime.datetime.now(),
            'message':  mess
        }
        return self.env['batch.update.customer.log'].create(vals)

    def create_partner_update_change(self, partners):
        partner_update_list = []
        for partner in partners:
            val = {
                'partner_id': partner
            }
            partner_update = self.env['partner.update.change'].sudo().create(val)
            partner_update_list.append(partner_update.id)
        return partner_update_list

    def set_to_draft(self):
        self.state = 'new'
        self.stores_file = None
        self.testing_facilities_file = None
        self.transporters_file = None
        self.create_colorado_partner_ids = None
        self.license_expired_colorado_partner_ids = None
        self.create_log(['Set to draft'])
        self.hide_suggest = True
        self.hide_validation = True

    def manual_download_file(self):
        config = self.get_config_info()
        if not config.get('url', False):
            self.create_log(['There is no URL. Please check the configuration'])
            return False
        self.sudo().write({'url': config.get('url')})
        if not self.stores_file and not self.testing_facilities_file and not self.transporters_file:
            message_list = self.get_file(config.get('url'), message_list=[])
        else:
            return False
        if not message_list:
            message_list.append('Download successful.')
            self.state = 'in_progress'
        self.create_log(message_list)
        self.hide_validation = True
        self.hide_suggest = False
        self.readonly_file = True
        self.create_colorado_partner_ids = None
        self.license_expired_colorado_partner_ids = None
        return True

    def manual_suggest_file(self):
        message_list = []
        self.create_colorado_partner_ids = None
        self.license_expired_colorado_partner_ids = None
        config = self.get_config_info()
        create_ids, license_expired_ids, message_list = self.sudo().import_data(config, message_list)
        if not message_list:
            message_list.append('Prepare data successful.')
            self.state = 'in_progress'
        self.create_log(message_list)
        self.hide_suggest = True
        self.hide_validation = False

    def manual_validation_file(self):
        self.sudo().write({'run_date': datetime.datetime.now()})
        message_list = []
        partner_update = self.import_prepare_data_to_res_partner()
        partner_update_create = self.sudo().create_partner_update_change(partner_update[0])
        partner_update_deactivate = self.sudo().create_partner_update_change(partner_update[1])
        self.sudo().write({'new_customer_ids': [(6, 0, partner_update_create)]})
        self.sudo().write({'license_expired_customer_ids': [(6, 0, partner_update_deactivate)]})
        if not message_list:
            message_list.append('Validation successful.')
            self.state = 'done'
        self.create_log(message_list)
        self.hide_suggest = True
        self.hide_validation = True
        return True

    def import_prepare_data_to_res_partner(self):
        license_expired_partner = ()
        for partner in self.license_expired_colorado_partner_ids:
            category_id = self.get_category_tag(partner.state)
            partner.partner_id.write({'license_expired': True, 'category_id': [(4, category_id)]})
            license_expired_partner += (partner.partner_id.id, )
        res_partner = self.env['res.partner'].sudo()
        vals_partner = []
        state_id, country_id = self.get_state_country()
        for colorado_partner in self.create_colorado_partner_ids:
            type_of_co_partner = colorado_partner.type_of_co_partner
            regulatory_license = colorado_partner.license_number
            category_id = self.get_category_tag(colorado_partner.state)
            val = {
                'name': colorado_partner.name or regulatory_license or 'Unknown',
                'regulatory_license': regulatory_license,
                'regulatory_license_type': colorado_partner.type,
                'doing_business_as': colorado_partner.dba,
                'city': colorado_partner.city,
                'state_id': state_id,
                'zip': colorado_partner.zip_code,
                'country_id': country_id,
                'is_company': True,
                'category_id': [(4, category_id)],
            }
            if type_of_co_partner == 'is_testing_facility':
                val.update({
                    'is_transporter': False,
                    'is_testing_facility': True,
                })
            elif type_of_co_partner == 'is_transporter':
                val.update({
                    'is_transporter': True,
                    'is_testing_facility': False,
                    'transporter_type': colorado_partner.facility_type or ''
                })
            vals_partner.append(val)
        create_partner = res_partner.create(vals_partner)
        return create_partner._ids, license_expired_partner

    @api.depends('name')
    def action_send_notify_mail(self, partner_ids):
        ir_model_data = self.env['ir.model.data'].sudo()
        try:
            template_id = ir_model_data.get_object_reference('impx_can_co_customers', 'notify_batch_update_need_to_confirm_email_template')[1]
        except ValueError:
            template_id = False
        ctx = {
            'default_model': 'batch.update.customer',
            'default_res_id': self.ids[0],
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_partner_ids': [(6, 0, partner_ids)],
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True,
            'proforma': self.env.context.get('proforma', False),
            'force_email': True
        }
        message = self.env['mail.compose.message'].sudo().with_context(**ctx).create({})
        message.onchange_template_id_wrapper()
        message.send_mail()
        return True

    def _auto_update_customer(self):
        today = datetime.datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        today_str = self.env['change.datetime'].change_utc_to_local_datetime(today, '%Y%m%d')
        vals = {
            'name': 'Update: {}'.format(today_str),
            'run_date': datetime.datetime.now(),
            'hide_validation': False,
            'hide_suggest': True,
            'readonly_file': True,
        }
        batch = self.sudo().create(vals)
        config = batch.get_config_info()
        message_list = []
        if not config.get('url'):
            message = 'There is no URL. Please check the configuration'
            message_list.append(message)
            batch.sudo().create_log(message_list)
            batch.state = 'fail'
            return False
        batch.sudo().write({'url': config.get('url')})
        batch.sudo()._compute_batch_url()
        message_list = batch.sudo().get_file(config.get('url'), message_list)
        create_ids, license_expired_ids, message_list = batch.sudo().import_data(config, message_list)
        if not message_list:
            message_list.append('Ready update')
            batch.state = 'in_progress'
        if config.get('notify_partner_ids'):
            try:
                batch.sudo().action_send_notify_mail(config['notify_partner_ids'])
            except Exception as error:
                message_list.append(error)
                batch.sudo().create_log(message_list)
                batch.state = 'fail'
                return False
        else:
            message_list.append("Warning: Can't find notify email")
        batch.sudo().create_log(message_list)
        return True
