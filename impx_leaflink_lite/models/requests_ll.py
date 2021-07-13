from odoo import _
from odoo.exceptions import ValidationError
from odoo.http import request
import requests
import json


def requests_ll(**kwargs):
    api_key = request.env.ref('base.main_company').leaf_link_api_key
    if not api_key:
        raise ValidationError(_("The field 'LeafLink API key' is missing, please check config again"))
    api_key = 'Token {}'.format(api_key)
    headers = {'Authorization': api_key, 'Content-Type': 'application/json'}
    try:
        resp = requests.request(
            method=kwargs.get('method'),
            url=kwargs.get('url'),
            headers=headers,
            params=kwargs.get('params'),
            data=kwargs.get('data'))
        content = json.loads(resp.content)
        if resp.ok and (200 <= resp.status_code < 400):
            return content
        raise ValidationError(_('Requests is fail. Status code {}.\n{}'.format(resp.status_code, content)))
    except ValueError as error:
        raise ValidationError(_('Bad requests: {}'.format(error)))


def get_url_ll(api_url):
    leaf_link_base_url = request.env.ref('base.main_company').leaf_link_base_url or ''
    if not leaf_link_base_url:
        raise ValidationError(_("The field 'LeafLink base URL' is missing, please check config again"))
    base_url = leaf_link_base_url.split('/')[2]
    return 'https://{}/api/v2/{}/'.format(base_url, api_url)


def get_data_from_ll(url, data_list, params):
    params.update({'offset': params.get('offset') + params.get('limit')})
    _master_data = requests_ll(method='GET', url=url, params=params)
    _orders_lst = _master_data.get('results')
    if not _orders_lst:
        return data_list
    data_list.extend(_orders_lst)
    if len(data_list) < _master_data.get('count'):
        return get_data_from_ll(data_list, params)
    return data_list


def get_all_data_from_ll(**kw):
    url, params = kw.get('url') or '', kw.get('params') or {}
    params.update({'limit': 500, 'offset': 0})
    master_data = requests_ll(method='GET', url=url, params=params)
    data_list = master_data.get('results')
    if not data_list:
        return False
    if len(data_list) == master_data.get('count'):
        return data_list
    return get_data_from_ll(url, data_list, params)
