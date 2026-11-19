from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from unittest.mock import patch

from django.contrib import messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db import connections, transaction
from django.http import HttpResponse
from django.test import RequestFactory, TransactionTestCase, skipUnlessDBFeature

from orders import actions
from orders.admin import BednaAdmin
from orders.choices import StavBednyChoice, TypZkouskyChoice, ZinkovaniChoice
from orders.models import Bedna, Kamion, KontrolaBedny, MereniBedny, Pozice, PoziceZakazkaOrder, Zakazka
from orders.services.exceptions import ServiceValidationError
from orders.services.expedice_service import (
    expedice_beden_do_existujiciho_kamionu, expedice_beden_do_noveho_kamionu,
    expedice_zakazek_do_existujiciho_kamionu, expedice_zakazek_do_noveho_kamionu,
)
from orders.tests.tests_actions import ActionsBase


class ZincDispatchGuardTests(ActionsBase):
    def make_crate(self, release='UV', *, pending=False, atypical=False, reasons=None):
        crate = self._create_bedna_in_state(StavBednyChoice.ZKONTROLOVANO, zinkovat=ZinkovaniChoice.ZINKOVAT)
        if atypical:
            crate.atypicky_prubeh = True
            crate.save(update_fields=['atypicky_prubeh'])
        if release is not None:
            if reasons is None:
                reasons = ('neshoda_jine',) if release in ('NE', 'UO') else ()
            KontrolaBedny.objects.create(
                bedna=crate, cistota='OK', ulozeni='OK', uvolneni=release,
                vyzaduje_potvrzeni=pending, **{name: True for name in reasons},
                poznamka='Původní rozhodnutí.',
            )
        return crate

    def dispatch(self, crates):
        request = self.get_request('post')
        result = actions.odeslat_na_zinkovani_action(
            BednaAdmin(Bedna, self.site), request,
            Bedna.objects.filter(pk__in=[crate.pk for crate in crates]),
        )
        return result, [str(item) for item in request._messages]

    def assert_rejected(self, crates, message):
        counts = {crate.pk: crate.history.count() for crate in crates}
        expected = {crate.pk: crate.zinkovat for crate in crates}
        with patch('orders.actions.utilita_export_beden_zinkovani_csv') as export:
            result, feedback = self.dispatch(crates)
        self.assertIsNone(result)
        export.assert_not_called()
        self.assertTrue(any(message in text for text in feedback), feedback)
        for crate in crates:
            crate.refresh_from_db()
            self.assertEqual(crate.zinkovat, expected[crate.pk])
            self.assertEqual(crate.history.count(), counts[crate.pk])

    def assert_dispatched(self, crates):
        counts = {crate.pk: crate.history.count() for crate in crates}
        controls = KontrolaBedny.objects.filter(bedna__in=crates).order_by('pk')
        before = list(controls.values())
        control_history_counts = {control.pk: control.history.count() for control in controls}
        with patch('orders.actions.utilita_export_beden_zinkovani_csv', return_value=HttpResponse()) as export:
            result, _ = self.dispatch(crates)
        self.assertIsInstance(result, HttpResponse)
        self.assertEqual(set(export.call_args.args[0].values_list('pk', flat=True)), {crate.pk for crate in crates})
        self.assertEqual(list(controls.values()), before)
        for control in controls:
            self.assertEqual(control.history.count(), control_history_counts[control.pk])
        for crate in crates:
            crate.refresh_from_db()
            self.assertEqual(crate.zinkovat, ZinkovaniChoice.V_ZINKOVNE)
            self.assertEqual(crate.history.count(), counts[crate.pk] + 1)
            self.assertEqual(crate.history.first().history_user_id, self.user.pk)
            self.assertEqual(crate.history.first().history_change_reason, 'Odeslání do zinkovny a export dodacího listu.')

    def test_both_release_decisions_allow_dispatch_with_history(self):
        self.assert_dispatched([self.make_crate(release) for release in ('UV', 'UO')])

    def test_curvature_only_nonconformity_allows_dispatch_in_mixed_selection(self):
        curved = self.make_crate('NE', reasons=('neshoda_krivost',))
        curved.rovnat = 'KR'
        curved.save(update_fields=['rovnat'])
        self.assert_dispatched([
            self.make_crate(), self.make_crate('UO'), curved,
            self.make_crate('NE', atypical=True),
        ])
        self.assertEqual(curved.rovnat, 'KR')

    def test_atypical_nonconformity_allows_any_or_no_reasons(self):
        reasons = [(), *((field,) for field in KontrolaBedny.NESHODA_FIELDS), KontrolaBedny.NESHODA_FIELDS]
        crates = [self.make_crate('NE', atypical=True, reasons=names) for names in reasons]
        # Přezinkování může řešit i NOK čistotu nebo uložení atypické bedny.
        control = crates[-1].kontrola
        control.cistota = control.ulozeni = 'NOK'
        control.save()
        self.assert_dispatched(crates)

    def test_standard_nonconformity_with_other_reason_rejects_whole_selection(self):
        for field in KontrolaBedny.NESHODA_FIELDS:
            if field == 'neshoda_krivost':
                continue
            for reasons in ((field,), ('neshoda_krivost', field)):
                with self.subTest(reasons=reasons):
                    self.assert_rejected([
                        self.make_crate('NE', atypical=True),
                        self.make_crate('NE', reasons=('neshoda_krivost',)),
                        self.make_crate('NE', reasons=reasons),
                    ], 'Křivost')

    def test_standard_nonconformity_without_reason_rejects_whole_selection(self):
        self.assert_rejected([self.make_crate(), self.make_crate('NE', reasons=())], 'Křivost')

    def test_atypical_missing_or_undecided_control_rejects_whole_selection(self):
        for release in (None, '--'):
            with self.subTest(release=release):
                self.assert_rejected([
                    self.make_crate('NE', atypical=True),
                    self.make_crate(release, atypical=True),
                ], 'Uvolněno')

    def test_nonconformity_exceptions_still_require_measurement_confirmation(self):
        for atypical, reasons in ((True, ()), (False, ('neshoda_krivost',))):
            with self.subTest(atypical=atypical):
                self.assert_rejected([
                    self.make_crate(),
                    self.make_crate('NE', pending=True, atypical=atypical, reasons=reasons),
                ], 'po změně měření')

    def test_nonconformity_exceptions_preserve_state_and_pause_guards(self):
        for atypical, reasons in ((True, ()), (False, ('neshoda_krivost',))):
            for field, value, message in (
                ('stav_bedny', 'ZA', 'ZKONTROLOVANO'),
                ('zinkovat', 'NN', 'ZINKOVAT'),
                ('pozastaveno', True, 'pozastaven'),
            ):
                with self.subTest(atypical=atypical, field=field):
                    bad = self.make_crate('NE', atypical=atypical, reasons=reasons)
                    setattr(bad, field, value)
                    bad.save()
                    self.assert_rejected([self.make_crate(), bad], message)

    def test_missing_undecided_or_nonconforming_control_rejects_whole_selection(self):
        for release in (None, '--', 'NE'):
            with self.subTest(release=release):
                bad = self.make_crate(release)
                self.assert_rejected([self.make_crate(), bad], 'Uvolněno')

    def test_pending_measurements_reject_whole_selection(self):
        self.assert_rejected([self.make_crate(), self.make_crate(pending=True)], 'po změně měření')

    def test_wrong_production_state_zinc_state_or_pause_rejects_whole_selection(self):
        for field, value, message in (
            ('stav_bedny', 'ZA', 'ZKONTROLOVANO'),
            ('zinkovat', 'NN', 'ZINKOVAT'),
            ('pozastaveno', True, 'pozastaven'),
        ):
            with self.subTest(field=field):
                bad = self.make_crate()
                setattr(bad, field, value)
                bad.save()
                self.assert_rejected([self.make_crate(), bad], message)

    def test_customer_limit_change_does_not_revoke_saved_release(self):
        self.zakaznik.max_krivych_vrutu = 5
        self.zakaznik.save()
        crate = self.make_crate()
        MereniBedny.objects.create(
            kontrola=crate.kontrola, typ_zkousky=TypZkouskyChoice.PROHYB_PO_TZ,
            poradi=1, hodnota='0.1',
        )
        self.zakaznik.max_krivych_vrutu = 0
        self.zakaznik.save()
        with patch('orders.actions.utilita_export_beden_zinkovani_csv', return_value=HttpResponse()):
            result, _ = self.dispatch([crate])
        self.assertIsInstance(result, HttpResponse)
        crate.refresh_from_db()
        self.assertEqual(crate.zinkovat, ZinkovaniChoice.V_ZINKOVNE)

    def test_reprinting_existing_zinc_delivery_note_does_not_require_new_release(self):
        crate = self.make_crate('NE', pending=True)
        crate.zinkovat = ZinkovaniChoice.V_ZINKOVNE
        crate.save()
        count = crate.history.count()
        with patch('orders.actions.utilita_export_beden_zinkovani_csv', return_value=HttpResponse()):
            result = actions.export_na_zinkovani_action(
                BednaAdmin(Bedna, self.site), self.get_request('post'), Bedna.objects.filter(pk=crate.pk),
            )
        self.assertIsInstance(result, HttpResponse)
        self.assertEqual(crate.history.count(), count)


class LoadingConfirmationGuardTests(ActionsBase):
    def setUp(self):
        self.position = Pozice.objects.create(kod='A', kapacita=10)

    def confirmation(self, selected, form_ids=None):
        form_ids = selected if form_ids is None else form_ids
        data = {
            'apply': '1', '_selected_action': [str(pk) for pk in selected],
            'ozn-TOTAL_FORMS': str(len(form_ids)), 'ozn-INITIAL_FORMS': str(len(form_ids)),
            'ozn-MIN_NUM_FORMS': '0', 'ozn-MAX_NUM_FORMS': '1000',
        }
        for index, pk in enumerate(form_ids):
            data[f'ozn-{index}-bedna_id'] = str(pk)
            data[f'ozn-{index}-pozice'] = str(self.position.pk)
            data[f'ozn-{index}-poznamka_k_navezeni'] = 'Požadavek.'
        return data

    def assert_rejected(self, data, queryset, crates):
        counts = {crate.pk: crate.history.count() for crate in crates}
        states = {crate.pk: (crate.stav_bedny, crate.pozice_id) for crate in crates}
        request = self.get_request('post', data)
        result = actions.oznacit_k_navezeni_action(BednaAdmin(Bedna, self.site), request, queryset)
        self.assertIsNone(result)
        self.assertTrue(any(item.level == messages.ERROR for item in request._messages))
        self.assertFalse(PoziceZakazkaOrder.objects.exists())
        for crate in crates:
            crate.refresh_from_db()
            self.assertEqual((crate.stav_bedny, crate.pozice_id), states[crate.pk])
            self.assertEqual(crate.history.count(), counts[crate.pk])

    def test_stale_confirmation_cannot_restore_already_checked_crate(self):
        crate = self._create_bedna_in_state(StavBednyChoice.ZKONTROLOVANO)
        self.assert_rejected(
            self.confirmation([crate.pk]), Bedna.objects.filter(pk=crate.pk, stav_bedny='PR'), [crate],
        )

    def test_substituted_omitted_or_duplicate_form_ids_reject_whole_selection(self):
        second = self._create_bedna_in_state(StavBednyChoice.PRIJATO)
        foreign = self._create_bedna_in_state(StavBednyChoice.PRIJATO)
        ids = [self.bedna.pk, second.pk]
        for form_ids in ([self.bedna.pk, foreign.pk], [self.bedna.pk], [self.bedna.pk, self.bedna.pk], []):
            with self.subTest(form_ids=form_ids):
                self.assert_rejected(
                    self.confirmation(ids, form_ids), Bedna.objects.filter(pk__in=ids),
                    [self.bedna, second, foreign],
                )

    def test_checkbox_selection_must_match_current_action_queryset(self):
        foreign = self._create_bedna_in_state(StavBednyChoice.PRIJATO)
        self.assert_rejected(
            self.confirmation([foreign.pk]), Bedna.objects.filter(pk=self.bedna.pk), [self.bedna, foreign],
        )

    def test_missing_or_malformed_checkbox_selection_is_rejected(self):
        for selected in ([], ['invalid']):
            with self.subTest(selected=selected):
                data = self.confirmation([self.bedna.pk])
                data['_selected_action'] = selected
                self.assert_rejected(data, Bedna.objects.filter(pk=self.bedna.pk), [self.bedna])

    def test_deleted_selected_crate_rejects_surviving_crates(self):
        # Opravený příjem mohl být mezitím vrácen do Nepřijato a smazán.
        deleted = self._create_bedna_in_state(StavBednyChoice.NEPRIJATO)
        data = self.confirmation([self.bedna.pk, deleted.pk])
        deleted.delete()
        self.assert_rejected(data, Bedna.objects.all(), [self.bedna])


class ShippingServiceGuardTests(ActionsBase):
    def calls(self, ids, *, orders=False):
        services = (
            (expedice_zakazek_do_existujiciho_kamionu, expedice_zakazek_do_noveho_kamionu)
            if orders else (expedice_beden_do_existujiciho_kamionu, expedice_beden_do_noveho_kamionu)
        )
        for service in services:
            kwargs = (
                {'zakazky_qs': Zakazka.objects.filter(pk=self.zakazka.pk)}
                if orders else {'bedny_qs': Bedna.objects.filter(pk__in=ids)}
            )
            if 'noveho' in service.__name__:
                kwargs.update(zakaznici=[self.zakaznik], odberatel=self.odberatel)
            else:
                kwargs['kamion_vydej'] = self.kamion_vydej
            yield service, kwargs

    def assert_rejected(self, crates, message, *, orders=False):
        before = {model: (model.objects.count(), model.history.count()) for model in (Bedna, Kamion, Zakazka)}
        states = {crate.pk: (crate.stav_bedny, crate.zakazka_id) for crate in crates}
        for service, kwargs in self.calls(list(states), orders=orders):
            with self.subTest(service=service.__name__):
                with self.assertRaisesMessage(ServiceValidationError, message):
                    service(**kwargs)
                for model, counts in before.items():
                    self.assertEqual((model.objects.count(), model.history.count()), counts)
                for crate in crates:
                    crate.refresh_from_db()
                    self.assertEqual((crate.stav_bedny, crate.zakazka_id), states[crate.pk])

    def test_crate_services_reject_every_source_state_other_than_ready(self):
        ready = self._create_bedna_in_state(StavBednyChoice.K_EXPEDICI)
        for state in StavBednyChoice:
            if state == StavBednyChoice.K_EXPEDICI:
                continue
            with self.subTest(state=state):
                other = self._create_bedna_in_state(state)
                self.assert_rejected([ready, other], 'K_EXPEDICI')

    def test_all_services_reject_bad_technological_states(self):
        crate = self._create_bedna_in_state(StavBednyChoice.K_EXPEDICI)
        for field, value, valid in (
            ('rovnat', 'KR', 'RO'), ('tryskat', 'SP', 'CI'), ('zinkovat', 'PZ', 'NN'),
        ):
            with self.subTest(field=field):
                setattr(crate, field, value)
                crate.save()
                self.assert_rejected([crate], 'Pro expedici musí')
                self.assert_rejected([crate], 'Pro expedici musí', orders=True)
                setattr(crate, field, valid)
                crate.save()

    def test_all_services_reject_paused_selected_crates(self):
        crate = self._create_bedna_in_state(StavBednyChoice.K_EXPEDICI)
        crate.pozastaveno = True
        crate.save()
        self.assert_rejected([crate], 'pozastaven')
        self.assert_rejected([crate], 'pozastaven', orders=True)

    def test_order_services_reject_pause_in_the_unshipped_remainder(self):
        ready = self._create_bedna_in_state(StavBednyChoice.K_EXPEDICI)
        self.bedna.pozastaveno = True
        self.bedna.save()
        self.assert_rejected([ready], 'pozastaven', orders=True)

    def test_crate_service_can_leave_unselected_paused_crate_in_production(self):
        self.bedna.pozastaveno = True
        self.bedna.save()
        ready = self._create_bedna_in_state(StavBednyChoice.K_EXPEDICI)
        result = expedice_beden_do_existujiciho_kamionu(
            bedny_qs=Bedna.objects.filter(pk=ready.pk), kamion_vydej=self.kamion_vydej,
        )
        self.assertEqual(result.moved_bedny_count, 1)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.PRIJATO)

    def test_legacy_crates_without_explicit_release_still_ship(self):
        for orders in (False, True):
            for index in range(2):
                for new_truck in (False, True):
                    with self.subTest(orders=orders, has_control=index, new_truck=new_truck):
                        crate = self._create_bedna_in_state(StavBednyChoice.K_EXPEDICI)
                        if index:
                            KontrolaBedny.objects.create(bedna=crate)
                        calls = list(self.calls([crate.pk], orders=orders))
                        service, kwargs = calls[int(new_truck)]
                        result = service(**kwargs)
                        self.assertEqual(result.moved_bedny_count, 1)
                        crate.refresh_from_db()
                        self.assertEqual(crate.stav_bedny, StavBednyChoice.EXPEDOVANO)


@skipUnlessDBFeature('has_select_for_update')
class WorkflowGuardConcurrencyTests(TransactionTestCase):
    def setUp(self):
        # Stejné malé fixture jako u přímých akcí, ale commitnuté pro druhé spojení.
        ActionsBase.setUpTestData.__func__(type(self))
        self.admin = BednaAdmin(Bedna, self.site)
        self.position = Pozice.objects.create(kod='A', kapacita=10)

    def request(self, data=None):
        request = RequestFactory().post('/', data or {})
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def after_concurrent_change(self, change, operation):
        started = Event()
        def worker():
            try:
                started.set()
                return operation()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                crate = Bedna.objects.select_for_update().get(pk=self.bedna.pk)
                change(crate)
                future = executor.submit(worker)
                self.assertTrue(started.wait(timeout=5))
                with self.assertRaises(TimeoutError):
                    future.result(timeout=0.3)
            return future.result(timeout=10)

    def test_zinc_dispatch_waits_and_rejects_new_nonconformity(self):
        Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny='ZK', zinkovat='KZ')
        def change(crate):
            KontrolaBedny.objects.create(bedna=crate, cistota='OK', ulozeni='OK', uvolneni='NE')
        def operation():
            with patch('orders.actions.utilita_export_beden_zinkovani_csv') as export:
                request = self.request()
                actions.odeslat_na_zinkovani_action(self.admin, request, Bedna.objects.filter(pk=self.bedna.pk))
                self.assertFalse(export.called)
                return [str(item) for item in request._messages]
        feedback = self.after_concurrent_change(change, operation)
        self.assertTrue(any('Uvolněno' in text for text in feedback))
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.zinkovat, ZinkovaniChoice.ZINKOVAT)

    def test_loading_confirmation_waits_and_rejects_new_pause(self):
        def change(crate):
            crate.pozastaveno = True
            crate.save()
        feedback = self.after_concurrent_change(change, self.confirm_loading)
        self.assertTrue(any('pozastaven' in text for text in feedback))
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.PRIJATO)
        self.assertFalse(PoziceZakazkaOrder.objects.exists())

    def test_loading_confirmation_waits_and_rejects_new_source_state(self):
        def change(crate):
            crate.stav_bedny = StavBednyChoice.NAVEZENO
            crate.pozice = self.position
            crate.save()
        feedback = self.after_concurrent_change(change, self.confirm_loading)
        self.assertTrue(feedback)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.NAVEZENO)
        self.assertFalse(PoziceZakazkaOrder.objects.exists())

    def confirm_loading(self):
        request = self.request({
            'apply': '1', '_selected_action': [str(self.bedna.pk)],
            'ozn-TOTAL_FORMS': '1', 'ozn-INITIAL_FORMS': '1',
            'ozn-MIN_NUM_FORMS': '0', 'ozn-MAX_NUM_FORMS': '1000',
            'ozn-0-bedna_id': str(self.bedna.pk), 'ozn-0-pozice': str(self.position.pk),
        })
        actions.oznacit_k_navezeni_action(
            self.admin, request, Bedna.objects.filter(pk=self.bedna.pk, stav_bedny=StavBednyChoice.PRIJATO),
        )
        return [str(item) for item in request._messages]

    def test_shipping_service_waits_and_rejects_new_bad_technological_state(self):
        Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny='KE', rovnat='RO', tryskat='CI', zinkovat='NN')
        def change(crate):
            crate.tryskat = 'SP'
            crate.save()
        def operation():
            try:
                expedice_beden_do_existujiciho_kamionu(
                    bedny_qs=Bedna.objects.filter(pk=self.bedna.pk), kamion_vydej=self.kamion_vydej,
                )
            except ServiceValidationError as error:
                return str(error)
            self.fail('Expedice přijala nově nevyhovující technologický stav.')
        feedback = self.after_concurrent_change(change, operation)
        self.assertIn('Pro expedici musí', feedback)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.K_EXPEDICI)
