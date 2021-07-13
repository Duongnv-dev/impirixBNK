{
    'name': 'Impirix Cannabis Custom Inventory',
    'summary': 'Impirix Cannabis Custom Inventory',
    'description': 'Impirix Cannabis Custom Inventory',
    'category': 'Inventory',
    'version': '1.0',
    'depends': ['base', 'stock', 'analytic', 'impx_can_general'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_warehouse.xml',
        'views/package_tags.xml',
        'views/stock_production_lot_view.xml',
        'views/stock_picking.xml',
        'views/stock_quant_view.xml',
        'views/stock_location.xml',
        'views/stock_move_line.xml',

        'wizard/views/wizard_split_package.xml',
    ],
    'application': True,
    'qweb': [],
}