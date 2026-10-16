from django.db import migrations


# Frozen copy of the customer settings at the time of this migration.
CUSTOMER_KKK_SETTINGS = {
    'EUR': (5, 5, 2, 'HPM - F 73c\nEurotec - F.3'),
    'ROT': (10, 5, 3, 'HPM - F XXX'),
    'SPX': (5, 3, 1, 'HPM - F XXX'),
    'SSH': (5, 5, 3, 'HPM - F 11b'),
    'HPM': (5, 5, 3, 'HPM - F 86a'),
    'SWG': (5, 5, 5, 'HPM - F XXX'),
    'FIS': (5, 25, 2, 'HPM - F XXX'),
}


def populate_customer_kkk_settings(apps, schema_editor):
    Customer = apps.get_model('orders', 'Zakaznik')
    for code, config in CUSTOMER_KKK_SETTINGS.items():
        Customer.objects.using(schema_editor.connection.alias).filter(zkratka=code).update(
            kkk_min_hodnot_mechanicke=config[0],
            kkk_min_hodnot_prohyb=config[1],
            kkk_min_hodnot_tvrdost=config[2],
            kkk_nazev_protokolu=config[3],
        )


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0239_zakaznik_nastaveni_kkk'),
    ]

    operations = [
        migrations.RunPython(populate_customer_kkk_settings, migrations.RunPython.noop),
    ]
