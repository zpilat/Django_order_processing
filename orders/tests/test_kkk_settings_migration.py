from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class CustomerKkkSettingsMigrationTests(TransactionTestCase):
    migrate_from = [('orders', '0238_historicalkontrolabedny_neshoda_vrstva_and_more')]
    migrate_to = [('orders', '0241_zakaznik_pole_bez_prefixu_kkk')]

    def restore_latest_schema(self):
        MigrationExecutor(connection).migrate(self.migrate_to)

    def test_existing_customers_receive_settings_without_changing_sample_size_or_history(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        self.addCleanup(self.restore_latest_schema)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        Customer = old_apps.get_model('orders', 'Zakaznik')
        History = old_apps.get_model('orders', 'HistoricalZakaznik')
        expected = {
            'EUR': (5, 5, 2, 'HPM - F 73c\nEurotec - F.3'),
            'ROT': (10, 5, 3, 'HPM - F XXX'),
            'SPX': (5, 3, 1, 'HPM - F XXX'),
            'SSH': (5, 5, 3, 'HPM - F 11b'),
            'HPM': (5, 5, 3, 'HPM - F 86a'),
            'SWG': (5, 5, 5, 'HPM - F XXX'),
            'FIS': (5, 25, 2, 'HPM - F XXX'),
            'TST': (None, None, None, ''),
        }
        for index, code in enumerate(expected, start=1):
            values = dict(
                nazev=code, zkraceny_nazev=code, zkratka=code, ciselna_rada=100000 * index,
                pocet_vrutu_pro_kontrolu_prohybu=32, max_krivych_vrutu=2,
            )
            customer = Customer.objects.create(**values)
            History.objects.create(id=customer.pk, history_date=timezone.now(), history_type='+', **values)

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps = executor.loader.project_state(self.migrate_to).apps
        Customer = apps.get_model('orders', 'Zakaznik')
        History = apps.get_model('orders', 'HistoricalZakaznik')
        for customer in Customer.objects.all():
            with self.subTest(customer=customer.zkratka):
                actual = tuple(getattr(customer, field) for field in (
                    'min_hodnot_mechanicke', 'min_hodnot_prohyb',
                    'min_hodnot_tvrdost', 'nazev_protokolu',
                ))
                self.assertEqual(actual, expected[customer.zkratka])
                self.assertEqual(customer.pocet_vrutu_pro_kontrolu_prohybu, 32)
                self.assertEqual(customer.max_krivych_vrutu, 2)
                history = History.objects.get(id=customer.pk)
                self.assertIsNone(history.min_hodnot_prohyb)
                self.assertEqual(history.nazev_protokolu, '')

    def test_rename_preserves_custom_settings_in_customer_and_history(self):
        migrate_from = [('orders', '0240_naplnit_nastaveni_kkk')]
        executor = MigrationExecutor(connection)
        executor.migrate(migrate_from)
        self.addCleanup(self.restore_latest_schema)
        old_apps = executor.loader.project_state(migrate_from).apps
        Customer = old_apps.get_model('orders', 'Zakaznik')
        History = old_apps.get_model('orders', 'HistoricalZakaznik')
        fields = ('min_hodnot_mechanicke', 'min_hodnot_prohyb', 'min_hodnot_tvrdost', 'nazev_protokolu')
        expected = (7, 8, 9, 'Vlastní protokol\nDruhý řádek')
        values = dict(
            nazev='EUR', zkraceny_nazev='EUR', zkratka='EUR', ciselna_rada=100000,
            pocet_vrutu_pro_kontrolu_prohybu=32, max_krivych_vrutu=2,
            **{f'kkk_{field}': value for field, value in zip(fields, expected)},
        )
        customer = Customer.objects.create(**values)
        History.objects.create(id=customer.pk, history_date=timezone.now(), history_type='+', **values)

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps = executor.loader.project_state(self.migrate_to).apps
        for model_name in ('Zakaznik', 'HistoricalZakaznik'):
            record = apps.get_model('orders', model_name).objects.get(id=customer.pk)
            self.assertEqual(tuple(getattr(record, field) for field in fields), expected)
            self.assertEqual(record.pocet_vrutu_pro_kontrolu_prohybu, 32)
            self.assertEqual(record.max_krivych_vrutu, 2)
