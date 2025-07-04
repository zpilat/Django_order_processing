# Generated by Django 5.2.1 on 2025-06-26 08:14

import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0089_cena_historicalcena'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TypHlavy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nazev', models.CharField(max_length=10, unique=True, verbose_name='Typ hlavy')),
                ('popis', models.CharField(blank=True, max_length=50, null=True, verbose_name='Popis')),
            ],
            options={
                'verbose_name': 'Typ hlavy',
                'verbose_name_plural': 'typy hlav',
                'ordering': ['nazev'],
            },
        ),
        migrations.CreateModel(
            name='HistoricalTypHlavy',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('nazev', models.CharField(db_index=True, max_length=10, verbose_name='Typ hlavy')),
                ('popis', models.CharField(blank=True, max_length=50, null=True, verbose_name='Popis')),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical Typ hlavy',
                'verbose_name_plural': 'historical typy hlav',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
    ]
