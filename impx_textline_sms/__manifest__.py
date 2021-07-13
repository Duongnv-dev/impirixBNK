# -*- coding: utf-8 -*-
{
    'name': "Impirix TextLine SMS",
    'summary': "Impirix TextLine SMS",
    'description': "Impirix TextLine SMS",
    'category': 'SMS',
    'version': '1.1',
    'depends': ['base', 'contacts', 'sms', 'crm', 'impx_can_crm', 'crm_sms'],
    'data': [
        # 'security/ir.model.access.csv',
        'views/sms_textline_views.xml',
        'views/sms_textline_config_view.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
}
