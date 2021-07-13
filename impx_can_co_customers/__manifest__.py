{
    'name': 'Impirix Get Customers Automatically from Colorado',
    'summary': 'Impirix Get Customers Automatically from Colorado',
    'description': 'Impirix Get Customers Automatically from Colorado',
    'category': 'CRM',
    'version': '1.1',
    'depends': ['impx_can_crm'],
    'data': [
        'security/ir.model.access.csv',
        'data/data.xml',
        'data/mail_template.xml',
        'views/batch_update_view.xml',
        'views/res_config_setting_view.xml',
    ],
    'external_dependencies': {
            'python': ['bs4', 'googledrivedownloader', 'xlrd'],
        },
    'application': True,
    'qweb': [],
}
