from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0207_historicalsarze_cislo_pracoviste_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='sarzekrokbedna',
            options={
                'ordering': ['krok_id', 'patro', 'pk'],
                'permissions': (
                    ('delete_sarzekrokbedna_patro', 'Může smazat celé patro v kroku šarže'),
                ),
                'verbose_name': 'Bedna v kroku šarže',
                'verbose_name_plural': 'deník',
            },
        ),
    ]
