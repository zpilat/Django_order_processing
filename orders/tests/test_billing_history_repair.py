from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection
from django.db.migrations.recorder import MigrationRecorder
from django.test import TestCase

from orders.models import Bedna, Kamion, Predpis, TypHlavy, Zakazka, Zakaznik
from orders.services.billing_history_repair_service import (
    ATYPICAL_REASON, DATA_MIGRATION, FLAGS, REPAIR_REASON, SCHEMA_MIGRATION,
    build_billing_history_repair_plan, repair_billing_history,
)
from orders.services.exceptions import ServiceValidationError


class BillingHistoryRepairTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.start = datetime(2026, 11, 13, 12, 3, 32, tzinfo=dt_timezone.utc)
        cls.end = cls.start + timedelta(seconds=2)
        cls.before = cls.start - timedelta(hours=1)
        cls.after = cls.end + timedelta(hours=1)
        for name, timestamp in ((SCHEMA_MIGRATION, cls.start), (DATA_MIGRATION, cls.end)):
            MigrationRecorder.Migration.objects.filter(app='orders', name=name).update(applied=timestamp)
        cls.user = get_user_model().objects.create_user(username='history-worker')
        with patch('django.utils.timezone.now', return_value=cls.before):
            cls.customer = Zakaznik.objects.create(
                nazev='Historie fakturace', zkraceny_nazev='HF', zkratka='EUR', ciselna_rada=100000,
                fakturovat_rovnani=False, fakturovat_tryskani=True,
            )
            cls.truck = Kamion.objects.create(zakaznik=cls.customer, datum=cls.before.date())
            specification = Predpis.objects.create(zakaznik=cls.customer, nazev='Historie')
            head = TypHlavy.objects.create(nazev='Historie')
            cls.order = Zakazka.objects.create(
                kamion_prijem=cls.truck, predpis=specification, typ_hlavy=head,
                artikl='H1', prumer=1, delka=1,
            )
            crates = [Bedna.objects.create(
                zakazka=cls.order, stav_bedny='PR', hmotnost=10, tara=1, mnozstvi=100,
                **{name: True for name in FLAGS},
            ) for _ in range(2)]
        cls.saved_pk, cls.not_saved_pk = [crate.pk for crate in crates]
        cls.expected = (True, False, True, False)
        # Napodobí přesně mezeru 0250: aktuální volby změněné bez historie.
        Bedna.objects.filter(pk__in=[crate.pk for crate in crates]).update(**dict(zip(FLAGS, cls.expected)))
        with patch('django.utils.timezone.now', return_value=cls.after):
            saved = Bedna.objects.get(pk=cls.saved_pk)
            saved.stav_bedny = 'ZA'
            saved.poznamka = 'Skutečná práce po migraci.'
            saved._history_user = cls.user
            saved.save()

    def markers(self):
        return Bedna.history.filter(history_change_reason__startswith=REPAIR_REASON)

    def live_values(self):
        return {model: list(model.objects.order_by('pk').values()) for model in (Bedna, Zakazka, Kamion, Zakaznik)}

    def history_values(self, record):
        return {item.attname: getattr(record, item.attname) for item in record._meta.concrete_fields}

    def test_preview_has_no_writes_and_reconstructs_both_missing_records(self):
        live = self.live_values()
        history = list(Bedna.history.order_by('history_id').values())
        plan = repair_billing_history()
        self.assertEqual(plan.issues, [])
        self.assertEqual(len(plan.records), 2)
        self.assertEqual((plan.first_saved, plan.not_saved), (1, 1))
        self.assertTrue(all(tuple(getattr(row, name) for name in FLAGS) == self.expected for row in plan.records))
        self.assertEqual(self.live_values(), live)
        self.assertEqual(list(Bedna.history.order_by('history_id').values()), history)

    def test_apply_preserves_current_data_original_history_and_real_worker_changes(self):
        live = self.live_values()
        original = {row.history_id: row for row in Bedna.history.all()}
        first = Bedna.history.filter(id=self.saved_pk).first()
        previous = Bedna.history.filter(id=self.saved_pk, history_date__lt=self.start).first()
        repair_billing_history(apply=True)
        self.assertEqual(self.live_values(), live)
        self.assertEqual(self.markers().count(), 2)
        for pk, old in original.items():
            self.assertEqual(Bedna.history.filter(history_id=pk).values().get(), self.history_values(old))
        marker = self.markers().get(id=self.saved_pk)
        self.assertEqual(marker.history_date, self.end)
        self.assertIsNone(marker.history_user_id)
        first.refresh_from_db()
        self.assertEqual(first.history_user_id, self.user.pk)
        self.assertEqual(first.prev_record.history_id, marker.history_id)
        before = {change.field: (change.old, change.new) for change in first.diff_against(previous).changes}
        after = {change.field: (change.old, change.new) for change in first.diff_against(marker).changes}
        self.assertEqual(after, {name: value for name, value in before.items() if name not in FLAGS})
        self.assertEqual(set(after), {'stav_bedny', 'poznamka'})

    def test_first_future_save_does_not_attribute_migration_to_worker(self):
        repair_billing_history(apply=True)
        crate = Bedna.objects.get(pk=self.not_saved_pk)
        migration = crate.history.first()
        with patch('django.utils.timezone.now', return_value=self.after + timedelta(hours=1)):
            crate.poznamka = 'Pouze nová poznámka.'
            crate._history_user = self.user
            crate.save(update_fields=['poznamka'])
        first = crate.history.first()
        self.assertEqual(first.history_user_id, self.user.pk)
        self.assertEqual({change.field for change in first.diff_against(migration).changes}, {'poznamka'})

    def test_second_apply_is_a_noop(self):
        repair_billing_history(apply=True)
        count = Bedna.history.count()
        plan = repair_billing_history(apply=True)
        self.assertEqual(len(plan.records), 0)
        self.assertEqual(plan.already_recorded, 2)
        self.assertEqual(Bedna.history.count(), count)

    def test_rehearsal_rolls_back_rows_and_does_not_advance_sequence(self):
        history_model = Bedna.history.model
        def sequence_value():
            with connection.cursor() as cursor:
                cursor.execute(
                    'SELECT pg_sequence_last_value(pg_get_serial_sequence(%s, %s)::regclass)',
                    [history_model._meta.db_table, 'history_id'],
                )
                return cursor.fetchone()[0]
        before_sequence = sequence_value()
        live = self.live_values()
        original = list(Bedna.history.order_by('history_id').values())
        plan = repair_billing_history(rollback=True)
        self.assertEqual(len(plan.records), 2)
        self.assertEqual(list(Bedna.history.order_by('history_id').values()), original)
        self.assertEqual(self.live_values(), live)
        self.assertEqual(sequence_value(), before_sequence)

    def test_later_manual_billing_override_remains_untouched(self):
        with patch('django.utils.timezone.now', return_value=self.after + timedelta(minutes=1)):
            crate = Bedna.objects.get(pk=self.saved_pk)
            crate.fakturovat_rovnani = True
            crate.fakturovat = False
            crate.save(update_fields=['fakturovat_rovnani', 'fakturovat'])
        before = self.live_values()
        manual = crate.history.first()
        repair_billing_history(apply=True)
        self.assertEqual(self.live_values(), before)
        self.assertEqual(Bedna.history.filter(history_id=manual.history_id).values().get(), self.history_values(manual))

    def test_customer_changes_after_migration_do_not_change_reconstruction(self):
        with patch('django.utils.timezone.now', return_value=self.after):
            self.customer.fakturovat_rovnani = True
            self.customer.fakturovat_tryskani = False
            self.customer.save()
            new = Bedna.objects.create(zakazka=self.order)
        plan = repair_billing_history()
        self.assertEqual(plan.issues, [])
        self.assertEqual(len(plan.records), 2)
        self.assertNotIn(new.pk, [row.id for row in plan.records])
        self.assertTrue(all(tuple(getattr(row, name) for name in FLAGS) == self.expected for row in plan.records))

    def test_first_post_migration_atypical_conversion_keeps_its_real_changes(self):
        with patch('django.utils.timezone.now', return_value=self.after):
            crate = Bedna.objects.get(pk=self.not_saved_pk)
            crate.atypicky_prubeh = True
            crate.fakturovat = False
            for name in FLAGS:
                setattr(crate, name, False)
            crate._change_reason = ATYPICAL_REASON
            crate._history_user = self.user
            crate.save()
        conversion = crate.history.first()
        repair_billing_history(apply=True)
        marker = self.markers().get(id=crate.pk)
        changes = {change.field for change in conversion.diff_against(marker).changes}
        self.assertEqual(changes, {'atypicky_prubeh', 'fakturovat', 'fakturovat_kaleni', 'fakturovat_tryskani'})
        self.assertEqual(Bedna.objects.get(pk=crate.pk).fakturovat, False)
        self.assertEqual(conversion.history_user_id, self.user.pk)

    def test_existing_atypical_crate_is_reconstructed_as_nonbillable(self):
        with patch('django.utils.timezone.now', return_value=self.before):
            crate = Bedna.objects.create(
                zakazka=self.order, atypicky_prubeh=True, fakturovat=False,
                **{name: True for name in FLAGS},
            )
        Bedna.objects.filter(pk=crate.pk).update(**{name: False for name in FLAGS})
        repair_billing_history(apply=True)
        marker = self.markers().get(id=crate.pk)
        self.assertEqual(tuple(getattr(marker, name) for name in FLAGS), (False,) * 4)
        self.assertFalse(marker.fakturovat)

    def test_first_unexpected_snapshot_blocks_entire_write(self):
        Bedna.history.filter(id=self.saved_pk, history_date=self.after).update(fakturovat_rovnani=True)
        self.assert_blocked('První pozdější snímek')

    def test_unrecorded_current_override_blocks_entire_write(self):
        Bedna.objects.filter(pk=self.not_saved_pk).update(fakturovat_kaleni=False)
        self.assert_blocked('současný stav')

    def test_missing_historical_customer_chain_blocks_write(self):
        Zakaznik.history.all().delete()
        self.assert_blocked('Chybí tehdejší historie')

    def test_history_inside_migration_window_blocks_write(self):
        historical = Bedna.history.filter(id=self.not_saved_pk).first()
        historical.history_date = self.start + timedelta(seconds=1)
        historical.save(update_fields=['history_date'])
        self.assert_blocked('časovém okně migrace')

    def test_invalid_existing_marker_blocks_write(self):
        repair_billing_history(apply=True)
        self.markers().filter(id=self.saved_pk).update(fakturovat_kaleni=False)
        self.assert_blocked('Existující záznam opravy')

    def assert_blocked(self, message):
        before = list(Bedna.history.order_by('history_id').values())
        with self.assertRaisesMessage(ServiceValidationError, message):
            repair_billing_history(apply=True)
        self.assertEqual(list(Bedna.history.order_by('history_id').values()), before)

    def test_insert_failure_rolls_back_all_inserted_markers(self):
        manager = Bedna.history.model.objects
        original_bulk_create = manager.bulk_create
        def fail_after_first(records, **kwargs):
            original_bulk_create(records[:1])
            raise IntegrityError('Simulovaná chyba zápisu.')
        count = Bedna.history.count()
        with patch.object(manager, 'bulk_create', side_effect=fail_after_first):
            with self.assertRaises(IntegrityError):
                repair_billing_history(apply=True)
        self.assertEqual(Bedna.history.count(), count)
        self.assertFalse(self.markers().exists())

    def test_command_preview_csv_and_rehearsal(self):
        with TemporaryDirectory() as directory:
            output = StringIO()
            path = Path(directory) / 'navrh.csv'
            call_command('doplnit_historii_fakturace', csv=path, stdout=output)
            self.assertIn('NÁHLED BEZ ZÁPISU', output.getvalue())
            self.assertIn('fakturovat_kaleni_po', path.read_text(encoding='utf-8-sig'))
            self.assertFalse(self.markers().exists())
            call_command('doplnit_historii_fakturace', rollback=True, stdout=StringIO())
            self.assertFalse(self.markers().exists())

    def test_command_apply_and_idempotence(self):
        call_command('doplnit_historii_fakturace', apply=True, stdout=StringIO())
        call_command('doplnit_historii_fakturace', apply=True, stdout=StringIO())
        self.assertEqual(self.markers().count(), 2)

    def test_csv_failure_rolls_back_apply(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(CommandError):
                call_command(
                    'doplnit_historii_fakturace', apply=True,
                    csv=Path(directory) / 'missing' / 'navrh.csv', stdout=StringIO(),
                )
        self.assertFalse(self.markers().exists())
