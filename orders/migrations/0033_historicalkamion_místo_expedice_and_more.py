# Generated by Django 5.2.1 on 2025-05-28 06:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0032_alter_bedna_stav_bedny_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalkamion',
            name='místo_expedice',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Místo expedice'),
        ),
        migrations.AddField(
            model_name='kamion',
            name='místo_expedice',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Místo expedice'),
        ),
    ]
