# Generated by Django 5.2.1 on 2025-06-23 12:12

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0079_alter_bedna_odfosfatovat_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='zakazka',
            name='predpis',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='zakazky', to='orders.predpis', verbose_name='Předpis / Výkres'),
        ),
    ]
