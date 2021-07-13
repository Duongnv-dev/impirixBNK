{
    'name': 'Impirix Cannabis Custom Manufacturing',
    'summary': 'Impirix Cannabis Custom Manufacturing',
    'description': 'Impirix Cannabis Custom Manufacturing',
    'category': 'Manufacturing',
    'version': '1.0',
    'depends': ['mrp', 'impx_can_inventory', 'mrp_workorder'],
    'data': [
        'views/stock_production_lot.xml',
        'views/mrp_workorder_views.xml',
        'views/mrp_product_produce.xml',
        'views/mrp_production.xml',
    ],
    'application': True,
    'qweb': [],
}