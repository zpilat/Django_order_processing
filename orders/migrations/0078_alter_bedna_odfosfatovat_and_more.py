# Generated by Django 5.2.1 on 2025-06-23 10:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0077_alter_bedna_odfosfatovat_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bedna',
            name='odfosfatovat',
            field=models.BooleanField(default=False, verbose_name='Odfosfátovat'),
        ),
        migrations.AlterField(
            model_name='historicalbedna',
            name='odfosfatovat',
            field=models.BooleanField(default=False, verbose_name='Odfosfátovat'),
        ),
    ]
