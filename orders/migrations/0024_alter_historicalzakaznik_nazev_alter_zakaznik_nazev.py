# Generated by Django 5.2.1 on 2025-05-22 19:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0023_alter_bedna_cislo_bedny_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="historicalzakaznik",
            name="nazev",
            field=models.CharField(db_index=True, max_length=100, verbose_name="Název"),
        ),
        migrations.AlterField(
            model_name="zakaznik",
            name="nazev",
            field=models.CharField(max_length=100, unique=True, verbose_name="Název"),
        ),
    ]
