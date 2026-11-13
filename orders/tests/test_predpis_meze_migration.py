from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from orders.models import Predpis


class PredpisMezeMigrationTests(TransactionTestCase):
    def restore_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_schema_and_conversion_preserve_original_history_and_texts(self):
        self.addCleanup(self.restore_schema)
        before = [('orders', '0246_bedna_fauf_historicalbedna_fauf')]
        after = [('orders', '0247_predpis_ciselne_meze_zkousek')]
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        apps = executor.loader.project_state(before).apps
        Customer = apps.get_model('orders', 'Zakaznik')
        Spec = apps.get_model('orders', 'Predpis')
        History = apps.get_model('orders', 'HistoricalPredpis')
        customer = Customer.objects.create(nazev='Migration test', zkraceny_nazev='MIG', zkratka='MIG', ciselna_rada=900000)
        item = Spec.objects.create(nazev='Old specification', zakaznik_id=customer.pk, krut='25,3 – 31,0 Nm', vrstva='CHD 550 HV0,3', vrstva_2='0,1 – 0,3 mm')
        History.objects.create(**{field.attname: getattr(item, field.attname) for field in Spec._meta.fields}, history_date=timezone.now(), history_type='+')
        MigrationExecutor(connection).migrate(after)
        # Runtime command uses today's models, including newer customer columns.
        # First exercise the historical schema path, then restore the current schema.
        self.restore_schema()
        converted = Predpis.objects.get(pk=item.pk)
        self.assertIsNone(converted.krut_min)
        call_command('doplnit_meze_predpisu', apply=True, stdout=StringIO())
        converted.refresh_from_db()
        self.assertEqual((converted.krut_min, converted.krut_max), (Decimal('25.3'), Decimal('31')))
        self.assertEqual(converted.vrstva_min, Decimal('0.1'))
        self.assertEqual(converted.krut, item.krut)
        self.assertEqual(converted.history.count(), 2)
        original, filled = list(converted.history.order_by('history_id'))
        self.assertIsNone(original.krut_min)
        self.assertIsNone(original.vrstva_min)
        self.assertEqual(filled.krut_min, Decimal('25.3'))
        call_command('doplnit_meze_predpisu', apply=True, stdout=StringIO())
        self.assertEqual(converted.history.count(), 2)
