from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.http import HttpResponse

from orders import actions
from orders.choices import StavBednyChoice, ZinkovaniChoice, STAV_BEDNY_ROZPRACOVANOST
from orders.models import Bedna, KontrolaBedny, Pozice, PoziceZakazkaOrder, Zakazka
from orders.services.history_service import update_queryset_with_history
from orders.tests.tests_actions import ActionsBase, DummyAdmin
from orders.views import dashboard_bedny_k_navezeni_view


class BulkHistoryAssertions:
    def history_before(self, bedny):
        return {
            bedna.pk: (bedna.history.first(), bedna.history.count())
            for bedna in bedny
        }

    def assert_audited_change(self, before, expected, reason):
        """Kontroluje snímek DB a následnou změnu provedenou jiným pracovníkem."""
        next_user = get_user_model().objects.create_user(username=f'dalsi-{get_user_model().objects.count()}')
        for pk, (previous, count) in before.items():
            with self.subTest(bedna=pk):
                bedna = Bedna.objects.get(pk=pk)
                current = bedna.history.first()
                self.assertEqual(bedna.history.count(), count + 1)
                self.assertEqual(current.history_type, '~')
                self.assertEqual(current.history_user_id, self.user.pk)
                self.assertEqual(current.history_change_reason, reason)
                for field in current.tracked_fields:
                    self.assertEqual(getattr(current, field.attname), getattr(bedna, field.attname))
                for name, value in expected.items():
                    self.assertEqual(getattr(bedna, name), value)
                expected_fields = {
                    Bedna._meta.get_field(name).name for name, value in expected.items()
                    if getattr(previous, name) != value
                }
                self.assertEqual(
                    {change.field for change in current.diff_against(previous).changes},
                    expected_fields,
                )

                # Nový snímek se nesmí připsat pozdějšímu autorovi poznámky.
                bedna.poznamka = f'Pouze poznámka dalšího pracovníka {next_user.pk}.'
                bedna._history_user = next_user
                bedna.save(update_fields=['poznamka'])
                following = bedna.history.first()
                self.assertEqual(following.history_user_id, next_user.pk)
                self.assertEqual(
                    {change.field for change in following.diff_against(current).changes},
                    {'poznamka'},
                )


class BulkActionHistoryTests(BulkHistoryAssertions, ActionsBase):
    def create_bedny(self, state, **kwargs):
        bedny = [self._create_bedna_in_state(state, **kwargs) for _ in range(2)]
        for bedna in bedny:
            # Ruční fakturace se při technologických operacích nesmí změnit.
            bedna.fakturovat_kaleni = False
            bedna.fakturovat_rovnani = True
            bedna.fakturovat_tryskani = False
            bedna.fakturovat_zinkovani = True
            bedna.save()
        return bedny

    def test_return_from_preparation_records_author_reason_and_clears_position(self):
        cases = (
            (StavBednyChoice.K_NAVEZENI,
             actions.vratit_bedny_ze_stavu_k_navezeni_do_stavu_prijato_action,
             'Vrácení z K navezení do Přijato.'),
            (StavBednyChoice.NAVEZENO,
             actions.vratit_bedny_ze_stavu_navezeno_do_stavu_prijato_action,
             'Vrácení z Navezeno do Přijato.'),
        )
        for state, action, reason in cases:
            with self.subTest(state=state):
                bedny = self.create_bedny(state)
                before = self.history_before(bedny)
                action(DummyAdmin(), self.get_request('post'), Bedna.objects.filter(pk__in=before))
                self.assert_audited_change(
                    before, {'stav_bedny': StavBednyChoice.PRIJATO, 'pozice_id': None}, reason,
                )

    def test_return_from_each_work_in_progress_state_records_history(self):
        for state in STAV_BEDNY_ROZPRACOVANOST:
            with self.subTest(state=state):
                before = self.history_before(self.create_bedny(state))
                actions.vratit_bedny_z_rozpracovanosti_do_stavu_prijato_action(
                    DummyAdmin(), self.get_request('post'), Bedna.objects.filter(pk__in=before),
                )
                self.assert_audited_change(
                    before, {'stav_bedny': StavBednyChoice.PRIJATO, 'pozice_id': None},
                    'Vrácení z rozpracovanosti do Přijato.',
                )

    def test_ready_for_shipment_records_history_for_checked_crates(self):
        before = self.history_before(self.create_bedny(StavBednyChoice.ZKONTROLOVANO))
        actions.oznacit_k_expedici_action(
            DummyAdmin(), self.get_request('post'), Bedna.objects.filter(pk__in=before),
        )
        self.assert_audited_change(
            before, {'stav_bedny': StavBednyChoice.K_EXPEDICI, 'pozice_id': None},
            'Hromadné označení K expedici.',
        )

    def test_zinc_dispatch_records_history_even_when_original_filter_no_longer_matches(self):
        bedny = self.create_bedny(StavBednyChoice.ZKONTROLOVANO, zinkovat=ZinkovaniChoice.ZINKOVAT)
        for bedna in bedny:
            KontrolaBedny.objects.create(bedna=bedna, cistota='OK', ulozeni='OK', uvolneni='UV')
        before = self.history_before(bedny)
        queryset = Bedna.objects.filter(pk__in=before, zinkovat=ZinkovaniChoice.ZINKOVAT)
        with patch('orders.actions.utilita_export_beden_zinkovani_csv', return_value=HttpResponse()) as export:
            actions.odeslat_na_zinkovani_action(DummyAdmin(), self.get_request('post'), queryset)
        self.assertEqual(set(export.call_args.args[0].values_list('pk', flat=True)), set(before))
        self.assert_audited_change(
            before, {'zinkovat': ZinkovaniChoice.V_ZINKOVNE},
            'Odeslání do zinkovny a export dodacího listu.',
        )

    def prepare_shipped_order(self):
        order = Zakazka.objects.get(pk=self.zakazka.pk)
        order.expedovano = True
        order.kamion_vydej = self.kamion_vydej
        order.save()
        # Vracení pracuje s celou zakázkou, tedy také s výchozí bednou fixture.
        bedny = list(Bedna.objects.filter(zakazka=order))
        for bedna in bedny:
            bedna.stav_bedny = StavBednyChoice.EXPEDOVANO
            bedna.save()
        bedny.extend(self.create_bedny(StavBednyChoice.EXPEDOVANO))
        return order, bedny

    def test_shipment_return_restores_order_and_records_crate_and_order_author(self):
        for original_expedovano in (None, True):
            with self.subTest(original_expedovano=original_expedovano):
                order, bedny = self.prepare_shipped_order()
                if original_expedovano is not None:
                    original = Zakazka.objects.create(
                        kamion_prijem=self.kamion_prijem, predpis=self.predpis,
                        typ_hlavy=self.typ_hlavy, artikl='Original',
                        prumer=1, delka=1, expedovano=original_expedovano,
                    )
                    order.puvodni_zakazka = original
                    order.save()
                before = self.history_before(bedny)
                actions.vratit_zakazky_z_expedice_action(
                    DummyAdmin(), self.get_request('post'), Zakazka.objects.filter(pk=order.pk),
                )
                self.assert_audited_change(
                    before, {'stav_bedny': StavBednyChoice.K_EXPEDICI, 'pozice_id': None},
                    'Vrácení zakázky z expedice: bedna K expedici.',
                )
                order.refresh_from_db()
                self.assertFalse(order.expedovano)
                self.assertIsNone(order.kamion_vydej_id)
                self.assertEqual(order.history.first().history_user_id, self.user.pk)
                self.assertEqual(order.history.first().history_change_reason, 'Vrácení zakázky z expedice.')

    def test_shipment_return_to_original_records_both_state_and_order_before_deletion(self):
        original = Zakazka.objects.create(
            kamion_prijem=self.kamion_prijem, predpis=self.predpis,
            typ_hlavy=self.typ_hlavy, artikl='Original', prumer=1, delka=1,
        )
        order, bedny = self.prepare_shipped_order()
        order.puvodni_zakazka = original
        order.save()
        before = self.history_before(bedny)
        actions.vratit_zakazky_z_expedice_action(
            DummyAdmin(), self.get_request('post'), Zakazka.objects.filter(pk=order.pk),
        )
        self.assertFalse(Zakazka.objects.filter(pk=order.pk).exists())
        deletion = Zakazka.history.filter(id=order.pk).first()
        self.assertEqual(deletion.history_type, '-')
        self.assertEqual(deletion.history_user_id, self.user.pk)
        self.assertEqual(deletion.history_change_reason, 'Vrácení beden do původní zakázky po expedici.')
        self.assert_audited_change(
            before, {'stav_bedny': StavBednyChoice.K_EXPEDICI, 'zakazka_id': original.pk, 'pozice_id': None},
            f'Vrácení z expedice do původní zakázky (ID {original.pk}).',
        )

    def test_rejected_action_does_not_change_data_or_history(self):
        before = self.history_before([Bedna.objects.get(pk=self.bedna.pk)])
        actions.vratit_bedny_ze_stavu_navezeno_do_stavu_prijato_action(
            DummyAdmin(), self.get_request('post'), Bedna.objects.filter(pk__in=before),
        )
        for pk, (record, count) in before.items():
            bedna = Bedna.objects.get(pk=pk)
            self.assertEqual(bedna.stav_bedny, record.stav_bedny)
            self.assertEqual(bedna.history.count(), count)

    def test_history_failure_rolls_back_all_crates(self):
        before = self.history_before(self.create_bedny(StavBednyChoice.ZAKALENO))
        with patch('simple_history.manager.HistoryManager.bulk_history_create', side_effect=IntegrityError('history')):
            with self.assertRaises(IntegrityError):
                actions.vratit_bedny_z_rozpracovanosti_do_stavu_prijato_action(
                    DummyAdmin(), self.get_request('post'), Bedna.objects.filter(pk__in=before),
                )
        for pk, (record, count) in before.items():
            bedna = Bedna.objects.get(pk=pk)
            self.assertEqual(bedna.stav_bedny, record.stav_bedny)
            self.assertEqual(bedna.history.count(), count)

    def test_bulk_action_preserves_bypass_of_model_save_and_validation(self):
        before = self.history_before(self.create_bedny(StavBednyChoice.ZAKALENO))
        with (
            patch.object(Bedna, 'save', side_effect=AssertionError('save must not be called')),
            patch.object(Bedna, 'clean', side_effect=AssertionError('clean must not be called')),
            patch.object(Bedna, 'full_clean', side_effect=AssertionError('full_clean must not be called')),
        ):
            actions.vratit_bedny_z_rozpracovanosti_do_stavu_prijato_action(
                DummyAdmin(), self.get_request('post'), Bedna.objects.filter(pk__in=before),
            )
        self.assert_audited_change(
            before, {'stav_bedny': StavBednyChoice.PRIJATO, 'pozice_id': None},
            'Vrácení z rozpracovanosti do Přijato.',
        )

    def test_shipment_return_history_failure_rolls_back_order_and_crates(self):
        order, bedny = self.prepare_shipped_order()
        before = self.history_before(bedny)
        order_count = order.history.count()
        with patch('simple_history.manager.HistoryManager.bulk_history_create', side_effect=IntegrityError('history')):
            actions.vratit_zakazky_z_expedice_action(
                DummyAdmin(), self.get_request('post'), Zakazka.objects.filter(pk=order.pk),
            )
        order.refresh_from_db()
        self.assertTrue(order.expedovano)
        self.assertEqual(order.kamion_vydej_id, self.kamion_vydej.pk)
        self.assertEqual(order.history.count(), order_count)
        for pk, (record, count) in before.items():
            bedna = Bedna.objects.get(pk=pk)
            self.assertEqual(bedna.stav_bedny, record.stav_bedny)
            self.assertEqual(bedna.history.count(), count)

    def test_evaluated_queryset_does_not_use_stale_billing_flags_for_history(self):
        bedna = self.create_bedny(StavBednyChoice.ZAKALENO)[0]
        queryset = Bedna.objects.filter(pk=bedna.pk)
        list(queryset)
        bedna.fakturovat_kaleni = True
        bedna.save(update_fields=['fakturovat_kaleni'])
        before = self.history_before([bedna])
        update_queryset_with_history(
            queryset, user=self.user, change_reason='Test čerstvých hodnot.',
            stav_bedny=StavBednyChoice.PRIJATO,
        )
        self.assert_audited_change(
            before, {'stav_bedny': StavBednyChoice.PRIJATO}, 'Test čerstvých hodnot.',
        )

    def test_empty_selection_does_not_create_history(self):
        count = Bedna.history.count()
        self.assertEqual(update_queryset_with_history(
            Bedna.objects.none(), user=self.user, change_reason='Prázdný výběr.',
            stav_bedny=StavBednyChoice.PRIJATO,
        ), 0)
        self.assertEqual(Bedna.history.count(), count)


class BulkPositionHistoryTests(BulkHistoryAssertions, ActionsBase):
    def check_position_move(self, direction):
        position_a = Pozice.objects.create(kod='A', kapacita=10)
        position_b = Pozice.objects.create(kod='B', kapacita=10)
        source, target = (position_a, position_b) if direction == 'down' else (position_b, position_a)
        bedny = [Bedna.objects.create(
            zakazka=self.zakazka, stav_bedny=StavBednyChoice.K_NAVEZENI,
            pozice=source, hmotnost=1, tara=1, mnozstvi=1,
        ) for _ in range(2)]
        untouched = Bedna.objects.create(
            zakazka=self.zakazka, stav_bedny=StavBednyChoice.K_NAVEZENI,
            pozice=target, hmotnost=1, tara=1, mnozstvi=1,
        )
        untouched_count = untouched.history.count()
        PoziceZakazkaOrder.objects.create(pozice=source, zakazka=self.zakazka, poradi=1)
        PoziceZakazkaOrder.objects.create(pozice=target, zakazka=self.zakazka, poradi=1)
        before = self.history_before(bedny)
        response = dashboard_bedny_k_navezeni_view(self.get_request('post', {
            'pozice_id': source.pk, 'zakazka_id': self.zakazka.pk, 'move': direction,
        }))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PoziceZakazkaOrder.objects.filter(pozice=source, zakazka=self.zakazka).exists())
        self.assertEqual(PoziceZakazkaOrder.objects.filter(pozice=target, zakazka=self.zakazka).count(), 1)
        self.assertEqual(untouched.history.count(), untouched_count)
        self.assert_audited_change(
            before, {'pozice_id': target.pk},
            f'Přesun v přehledu K navezení: pozice {source.kod} → {target.kod}.',
        )

    def test_move_down_records_position_history_for_each_moved_crate(self):
        self.check_position_move('down')

    def test_move_up_records_position_history_for_each_moved_crate(self):
        self.check_position_move('up')

    def test_ordering_failure_rolls_back_position_and_already_created_history(self):
        source = Pozice.objects.create(kod='A', kapacita=10)
        target = Pozice.objects.create(kod='B', kapacita=10)
        bedna = Bedna.objects.create(
            zakazka=self.zakazka, stav_bedny=StavBednyChoice.K_NAVEZENI,
            pozice=source, hmotnost=1, tara=1, mnozstvi=1,
        )
        source_order = PoziceZakazkaOrder.objects.create(pozice=source, zakazka=self.zakazka, poradi=1)
        count = bedna.history.count()

        def fail_rebuild(*args, **kwargs):
            self.assertEqual(Bedna.objects.get(pk=bedna.pk).pozice_id, target.pk)
            self.assertEqual(bedna.history.count(), count + 1)
            raise IntegrityError('ordering')

        with patch.object(PoziceZakazkaOrder.objects, 'bulk_create', side_effect=fail_rebuild):
            with self.assertRaises(IntegrityError):
                dashboard_bedny_k_navezeni_view(self.get_request('post', {
                    'pozice_id': source.pk, 'zakazka_id': self.zakazka.pk, 'move': 'down',
                }))

        bedna.refresh_from_db()
        self.assertEqual(bedna.pozice_id, source.pk)
        self.assertEqual(bedna.history.count(), count)
        self.assertTrue(PoziceZakazkaOrder.objects.filter(pk=source_order.pk).exists())
        self.assertFalse(PoziceZakazkaOrder.objects.filter(pozice=target).exists())
