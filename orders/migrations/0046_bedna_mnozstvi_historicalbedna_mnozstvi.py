# Generated by Django 5.2.1 on 2025-06-04 08:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0045_rename_zakazka_id_bedna_zakazka_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='bedna',
            name='mnozstvi',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Mn. ks'),
        ),
        migrations.AddField(
            model_name='historicalbedna',
            name='mnozstvi',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Mn. ks'),
        ),
    ]
