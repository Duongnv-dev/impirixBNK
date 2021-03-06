{
    'name': 'Impirix Leaf Link',
    'summary': 'Impirix Leaf Link',
    'description': 'Impirix Leaf Link',
    'category': 'LeafLink',
    'version': '1.1',
    'depends': ['impx_can_crm', 'impx_can_general', 'impx_can_sale', 'sale_management'],
    'data': [
        'security/ir.model.access.csv',
        'views/template.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_view_form.xml',
        'views/batch_update_leaf_link_view.xml',
        'data/ir_cron_leaf_link_cron_job.xml',
        'data/mail_template_leaf_link.xml',
        'views/product_product_views.xml',
        'views/sale_order_views.xml',
        'views/product_images_views.xml',
        'views/product_categories_leaflink.xml',
        'views/leaflink_logs_views.xml',
        'wizard/views/sync_general_to_odoo_views.xml',
        'wizard/views/sync_product_to_odoo_views.xml',
        'wizard/views/sync_sale_order_to_odoo_views.xml',
        'wizard/views/sync_all_to_odoo.xml',
        'wizard/views/sync_contacts_to_odoo_views.xml',
        'wizard/views/sync_company_staff_to_odoo_views.xml',
        'wizard/views/menuitem.xml',
    ],
    'external_dependencies': {
        'python': ['html2text']
    },
}
