# Generated by Django 5.2.1 on 2025-06-01 10:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0039_bedna_behalter_nr_historicalbedna_behalter_nr_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="historicalzakaznik",
            name="cisla_beden_auto",
        ),
        migrations.RemoveField(
            model_name="zakaznik",
            name="cisla_beden_auto",
        ),
        migrations.AddField(
            model_name="historicalzakaznik",
            name="ciselna_rada",
            field=models.PositiveIntegerField(
                default=100000,
                help_text="Číselná řada pro automatické číslování beden - např. 100000, 200000, 300000 atd.",
                verbose_name="Číselná řada",
            ),
        ),
        migrations.AddField(
            model_name="zakaznik",
            name="ciselna_rada",
            field=models.PositiveIntegerField(
                default=100000,
                help_text="Číselná řada pro automatické číslování beden - např. 100000, 200000, 300000 atd.",
                verbose_name="Číselná řada",
            ),
        ),
    ]
