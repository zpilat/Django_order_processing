# Generated by Django 5.2.1 on 2025-06-25 09:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0087_rename_cislo_dl_historicalkamion_cislo_dl_zakaznika_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalkamion',
            name='poradove_cislo',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Pořadové číslo'),
        ),
        migrations.AddField(
            model_name='kamion',
            name='poradove_cislo',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Pořadové číslo'),
        ),
    ]
