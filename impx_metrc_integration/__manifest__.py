{
    'name': 'Impirix Metrc Integration',
    'summary': 'Impirix Metrc Integration',
    'description': 'Impirix Metrc Integration',
    'category': 'Metrc',
    'version': '1.1',
    'depends': ['base_setup', 'product', 'impx_can_general', 'impx_can_sale', 'impx_can_inventory', 'purchase'],
    "external_dependencies": {"python": ["iso8601"]},
    'data': [
        'data/update_uom_metrc.xml',
        'data/item_schedule.xml',

        'security/ir.model.access.csv',

        'views/res_config_setting.xml',
        'views/uom_uom.xml',
        'views/product.xml',
        'views/stock_picking.xml',
        'views/transfer.xml',
        'views/settings.xml',
        'views/stock_production_lot_view.xml',
    ],
}
