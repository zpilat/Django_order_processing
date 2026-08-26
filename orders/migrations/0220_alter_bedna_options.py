from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0219_bedna_obsah_ca_bedna_obsah_p_bedna_obsah_zn'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='bedna',
            options={
                'ordering': ['id'],
                'permissions': (
                    ('change_expedovana_bedna', 'Může upravovat expedované bedny'),
                    ('change_pozastavena_bedna', 'Může upravovat a uvolnit pozastavené bedny'),
                    ('change_neprijata_bedna', 'Může upravovat bedny ve stavu NEPŘIJATO'),
                    ('change_poznamka_neprijata_bedna', 'Může upravovat poznámku u bedny ve stavu NEPŘIJATO'),
                    ('mark_bedna_navezeno', 'Může označit bednu jako navezenou a vrátit ji zpět na příjem'),
                    ('mark_bedna_zakaleno', 'Může označit bednu jako zakalenou přímo z příjmu (např. při reklamaci)'),
                    ('scan_mark_bedna_zakaleno', 'Může označit bednu jako zakalenou přes skenování'),
                    ('mark_bedna_zkontrolovano', 'Může označit bednu jako zkontrolovanou přes skenování'),
                    ('filter_chemistry_bedna', 'Filtr chemie a export chemických údajů beden'),
                ),
                'verbose_name': 'Bedna',
                'verbose_name_plural': 'bedny',
            },
        ),
    ]
