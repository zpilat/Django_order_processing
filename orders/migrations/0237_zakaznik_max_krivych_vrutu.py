from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0236_historicalzakaznik_max_pocet_krivych_vrutu_pro_kontrolu_prohybu_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='historicalzakaznik',
            old_name='max_pocet_krivych_vrutu_pro_kontrolu_prohybu',
            new_name='max_krivych_vrutu',
        ),
        migrations.RenameField(
            model_name='zakaznik',
            old_name='max_pocet_krivych_vrutu_pro_kontrolu_prohybu',
            new_name='max_krivych_vrutu',
        ),
    ]
