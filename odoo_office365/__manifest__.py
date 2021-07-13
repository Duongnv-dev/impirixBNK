# -*- coding: utf-8 -*-
{
    'name': "odoo office 365",

    'summary': """
                Odoo Office365 Connector provides the opportunity to sync calendar, contacts, tasks and mails between ODOO and Office365.
            """,

    'description': """
	Odoo is a fully integrated suite of business modules that encompass the traditional ERP functionality. Odoo office 365 Connector 		provides the opportunity to sync calendar, contacts,task and mail between ODOO and office 365.
    """,
    'author': "Techloyce",
    'website': "http://www.techloyce.com",
    'category': 'sale',
    'price': 499,
    'currency': 'EUR',
    'version': '12.0.0.2.2',
    'license' : 'OPL-1',
    'depends': ['base', 'calendar', 'crm', 'queue_job'],
    'images': [
        'static/description/banner.png',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/views.xml',
        'data/scheduler.xml',
        'data/data.xml',
        'wizard/message_wizard.xml',
        'views/template.xml',
        'views/office365_sync.xml',
        'views/res_users.xml',
        'views/office365_mail.xml',
        'views/calendar_sync.xml',
        'wizard/wizard_assign_mail.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        # 'demo/demo.xml',
    ],
}
