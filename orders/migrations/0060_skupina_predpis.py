# Generated by Django 5.2.1 on 2025-06-19 13:03

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0059_alter_historicalzakaznik_pouze_komplet_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Skupina',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cislo', models.PositiveSmallIntegerField(unique=True, verbose_name='Skupina TZ')),
                ('popis', models.CharField(max_length=100, unique=True, verbose_name='Popis skupiny TZ')),
            ],
        ),
        migrations.CreateModel(
            name='Predpis',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nazev', models.CharField(max_length=20, unique=True, verbose_name='Název předpisu')),
                ('skupina', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='predpisy', to='orders.skupina', verbose_name='Skupina TZ')),
            ],
        ),
    ]
