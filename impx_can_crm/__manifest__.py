{
    'name': 'Impirix Cannabis CRM',
    'summary': 'Impirix Cannabis CRM',
    'description': 'Impirix Cannabis CRM',
    'category': 'CRM',
    'version': '1.1',
    'depends': ['crm'],
    'data': [
        'security/ir.model.access.csv',
        'views/crm_lead_view.xml',
        'views/res_partner_view.xml',
        'report/views/impirix_activity_report.xml',
        'views/mail_templates.xml',
    ],
    'application': True,
    'qweb': [
        'static/src/xml/activity.xml',
        'static/src/xml/thread.xml',
    ],
}
