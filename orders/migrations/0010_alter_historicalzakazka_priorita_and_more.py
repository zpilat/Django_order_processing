# Generated by Django 5.2.1 on 2025-05-18 11:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0009_alter_kamion_options_alter_zakazka_options_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="historicalzakazka",
            name="priorita",
            field=models.CharField(
                choices=[("-", "Nízká"), ("P2", "Střední P2"), ("P1", "Vysoká P1")],
                max_length=5,
                verbose_name="Priorita",
            ),
        ),
        migrations.AlterField(
            model_name="zakazka",
            name="priorita",
            field=models.CharField(
                choices=[("-", "Nízká"), ("P2", "Střední P2"), ("P1", "Vysoká P1")],
                max_length=5,
                verbose_name="Priorita",
            ),
        ),
    ]
