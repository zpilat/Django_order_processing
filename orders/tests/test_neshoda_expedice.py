from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import date
from threading import Event

from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.db import connections, transaction
from django.forms import modelform_factory
from django.test import RequestFactory, TransactionTestCase, skipUnlessDBFeature

from orders import actions
from orders.admin import BednaAdmin
from orders.choices import StavBednyChoice, UvolneniKontrolyChoice, RovnaniChoice, TryskaniChoice
from orders.forms import BednaAdminForm
from orders.models import Bedna, Kamion, KontrolaBedny, Zakazka, Zakaznik, Predpis, TypHlavy
from orders.services.exceptions import ServiceValidationError
from orders.services.expedice_service import (
    expedice_beden_do_existujiciho_kamionu,
    expedice_beden_do_noveho_kamionu,
    expedice_zakazek_do_existujiciho_kamionu,
    expedice_zakazek_do_noveho_kamionu,
    validate_expedice_preconditions,
)
from orders.tests.tests_actions import ActionsBase


class NeshodaExpediceTests(ActionsBase):
    def setUp(self):
        self.admin = BednaAdmin(Bedna, self.site)

    def create_control(self, bedna, status=UvolneniKontrolyChoice.NESHODA):
        return KontrolaBedny.objects.create(bedna=bedna, uvolneni=status)

    def test_model_rejects_nonconformity_in_both_shipping_states(self):
        bedna = self._create_bedna_in_state(StavBednyChoice.ZKONTROLOVANO)
        self.create_control(bedna)
        for state in (StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO):
            with self.subTest(state=state):
                bedna.stav_bedny = state
                with self.assertRaisesMessage(ValidationError, str(Bedna.NESHODA_EXPEDICE_MESSAGE)):
                    bedna.full_clean()
        bedna.stav_bedny = StavBednyChoice.ZKONTROLOVANO
        bedna.full_clean()

    def test_model_allows_missing_control_and_all_other_release_decisions(self):
        bedna = self._create_bedna_in_state(StavBednyChoice.K_EXPEDICI)
        # A cached missing reverse relation must not conceal a subsequently saved control.
        self.assertFalse(hasattr(bedna, 'kontrola'))
        for state in (StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO):
            bedna.stav_bedny = state
            bedna.full_clean()
        kontrola = self.create_control(bedna)
        with self.assertRaises(ValidationError):
            bedna.full_clean()
        for status in UvolneniKontrolyChoice:
            if status == UvolneniKontrolyChoice.NESHODA:
                continue
            kontrola.uvolneni = status
            kontrola.save()
            for state in (StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO):
                with self.subTest(state=state, status=status):
                    bedna.stav_bedny = state
                    bedna.full_clean()

    def test_mark_ready_rejects_entire_selection_and_identifies_bad_crate(self):
        good = self._create_bedna_in_state(StavBednyChoice.ZKONTROLOVANO)
        bad = self._create_bedna_in_state(StavBednyChoice.ZKONTROLOVANO)
        self.create_control(bad)
        request = self.get_request('post')
        actions.oznacit_k_expedici_action(
            self.admin, request, Bedna.objects.filter(pk__in=[good.pk, bad.pk]),
        )
        for bedna in (good, bad):
            bedna.refresh_from_db()
            self.assertEqual(bedna.stav_bedny, StavBednyChoice.ZKONTROLOVANO)
        self.assertTrue(any(str(bad.cislo_bedny) in str(m) and 'Neshoda' in str(m) for m in request._messages))

    def test_mark_ready_allows_missing_control_and_other_release_decisions(self):
        ids = [self._create_bedna_in_state(StavBednyChoice.ZKONTROLOVANO).pk]
        for status in UvolneniKontrolyChoice:
            if status != UvolneniKontrolyChoice.NESHODA:
                bedna = self._create_bedna_in_state(StavBednyChoice.ZKONTROLOVANO)
                self.create_control(bedna, status)
                ids.append(bedna.pk)
        actions.oznacit_k_expedici_action(self.admin, self.get_request('post'), Bedna.objects.filter(pk__in=ids))
        self.assertEqual(Bedna.objects.filter(pk__in=ids, stav_bedny=StavBednyChoice.K_EXPEDICI).count(), len(ids))

    def test_all_shipping_actions_reject_nonconformity_without_side_effects(self):
        good = self._create_bedna_in_state(StavBednyChoice.K_EXPEDICI)
        bad = self._create_bedna_in_state(StavBednyChoice.K_EXPEDICI)
        self.create_control(bad)
        for action, qs in (
            (actions.expedice_beden_action, Bedna.objects.filter(pk__in=[good.pk, bad.pk])),
            (actions.expedice_beden_kamion_action, Bedna.objects.filter(pk__in=[good.pk, bad.pk])),
            (actions.expedice_zakazek_action, Zakazka.objects.filter(pk=self.zakazka.pk)),
            (actions.expedice_zakazek_kamion_action, Zakazka.objects.filter(pk=self.zakazka.pk)),
        ):
            with self.subTest(action=action.__name__):
                before = (Kamion.objects.count(), Zakazka.objects.count())
                request = self.get_request('post', {
                    'apply': '1', 'odberatel': self.odberatel.pk, 'kamion': self.kamion_vydej.pk,
                })
                action(self.admin, request, qs)
                self.assertEqual((Kamion.objects.count(), Zakazka.objects.count()), before)
                self.assertEqual(Bedna.objects.filter(pk__in=[good.pk, bad.pk], stav_bedny=StavBednyChoice.K_EXPEDICI).count(), 2)
                self.zakazka.refresh_from_db()
                self.assertFalse(self.zakazka.expedovano)
                self.assertIsNone(self.zakazka.kamion_vydej_id)
                self.assertTrue(any('Neshoda' in str(m) for m in request._messages))

    def test_direct_shipping_services_reject_nonconformity_and_roll_back(self):
        good = self._create_bedna_in_state(StavBednyChoice.K_EXPEDICI)
        bad = self._create_bedna_in_state(StavBednyChoice.K_EXPEDICI)
        self.create_control(bad)
        for service, selection in (
            (expedice_beden_do_existujiciho_kamionu, {'bedny_qs': Bedna.objects.filter(pk__in=[good.pk, bad.pk])}),
            (expedice_zakazek_do_existujiciho_kamionu, {'zakazky_qs': Zakazka.objects.filter(pk=self.zakazka.pk)}),
            (expedice_beden_do_noveho_kamionu, {'bedny_qs': Bedna.objects.filter(pk__in=[good.pk, bad.pk])}),
            (expedice_zakazek_do_noveho_kamionu, {'zakazky_qs': Zakazka.objects.filter(pk=self.zakazka.pk)}),
        ):
            with self.subTest(service=service.__name__):
                before = (Kamion.objects.count(), Zakazka.objects.count())
                kwargs = dict(selection)
                if 'noveho' in service.__name__:
                    kwargs.update(zakaznici=[self.zakaznik], odberatel=self.odberatel)
                else:
                    kwargs['kamion_vydej'] = self.kamion_vydej
                with self.assertRaisesMessage(ServiceValidationError, 'Neshoda'):
                    service(**kwargs)
                self.assertEqual((Kamion.objects.count(), Zakazka.objects.count()), before)
                self.assertEqual(Bedna.objects.filter(pk__in=[good.pk, bad.pk], stav_bedny=StavBednyChoice.K_EXPEDICI).count(), 2)
                self.zakazka.refresh_from_db()
                self.assertFalse(self.zakazka.expedovano)
                self.assertIsNone(self.zakazka.kamion_vydej_id)

    def test_order_shipping_ignores_nonconformity_of_crates_that_stay_in_production(self):
        self.create_control(self.bedna)
        ready = self._create_bedna_in_state(StavBednyChoice.K_EXPEDICI)
        result = expedice_zakazek_do_existujiciho_kamionu(
            zakazky_qs=Zakazka.objects.filter(pk=self.zakazka.pk), kamion_vydej=self.kamion_vydej,
        )
        self.assertEqual(result.moved_bedny_count, 1)
        ready.refresh_from_db()
        self.assertEqual(ready.stav_bedny, StavBednyChoice.EXPEDOVANO)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.PRIJATO)

    def test_service_preconditions_report_nonconformity(self):
        bad = self._create_bedna_in_state(StavBednyChoice.K_EXPEDICI)
        self.create_control(bad)
        self.assertTrue(any('Neshoda' in error for error in validate_expedice_preconditions(
            bedny_qs=Bedna.objects.filter(pk=bad.pk),
        )))

    def test_return_from_shipping_rejects_legacy_nonconformity_in_both_branches(self):
        Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=StavBednyChoice.EXPEDOVANO)
        bad = self._create_bedna_in_state(StavBednyChoice.EXPEDOVANO)
        self.create_control(bad)
        original = Zakazka.objects.create(
            kamion_prijem=self.kamion_prijem, predpis=self.predpis, typ_hlavy=self.typ_hlavy,
            artikl='ORIGINAL', prumer=1, delka=1, popis='Original',
        )
        for parent in (None, original):
            with self.subTest(parent=parent):
                self.zakazka.expedovano = True
                self.zakazka.kamion_vydej = self.kamion_vydej
                self.zakazka.puvodni_zakazka = parent
                self.zakazka.save()
                request = self.get_request('post')
                actions.vratit_zakazky_z_expedice_action(
                    self.admin, request, Zakazka.objects.filter(pk=self.zakazka.pk),
                )
                self.zakazka.refresh_from_db()
                bad.refresh_from_db()
                self.assertTrue(self.zakazka.expedovano)
                self.assertEqual(self.zakazka.kamion_vydej_id, self.kamion_vydej.pk)
                self.assertEqual(bad.stav_bedny, StavBednyChoice.EXPEDOVANO)
                self.assertEqual(bad.zakazka_id, self.zakazka.pk)
                self.assertTrue(any('Neshoda' in str(m) for m in request._messages))


@skipUnlessDBFeature('has_select_for_update')
class NeshodaExpediceConcurrencyTests(TransactionTestCase):
    def setUp(self):
        customer = Zakaznik.objects.create(nazev='Souběh', zkraceny_nazev='SOU', zkratka='SOU', ciselna_rada=100000)
        truck = Kamion.objects.create(zakaznik=customer, datum=date.today())
        rule = Predpis.objects.create(nazev='Souběh', zakaznik=customer)
        head = TypHlavy.objects.create(nazev='Souběh')
        order = Zakazka.objects.create(
            kamion_prijem=truck, predpis=rule, typ_hlavy=head, artikl='A1', prumer=1, delka=1, popis='Souběh',
        )
        self.bedna = Bedna.objects.create(
            zakazka=order, hmotnost=1, tara=1, mnozstvi=1,
            stav_bedny=StavBednyChoice.ZKONTROLOVANO, rovnat=RovnaniChoice.ROVNA, tryskat=TryskaniChoice.CISTA,
        )
        self.user = get_user_model().objects.create_superuser('souběh', 'test@example.com', 'test')

    def assert_waits_for_control_commit(self, operation):
        started = Event()

        def worker():
            try:
                started.set()
                return operation()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                Bedna.objects.select_for_update().get(pk=self.bedna.pk)
                KontrolaBedny.objects.create(bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.NESHODA)
                future = executor.submit(worker)
                self.assertTrue(started.wait(timeout=5))
                # The uncommitted control cannot be seen until the crate lock is released.
                with self.assertRaises(TimeoutError):
                    future.result(timeout=0.3)
            result = future.result(timeout=10)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZKONTROLOVANO)
        return result

    def test_mark_ready_waits_for_control_and_rejects_new_nonconformity(self):
        def mark_ready():
            request = RequestFactory().post('/')
            request.user = self.user
            request.session = {}
            request._messages = FallbackStorage(request)
            actions.oznacit_k_expedici_action(
                BednaAdmin(Bedna, AdminSite()), request, Bedna.objects.filter(pk=self.bedna.pk),
            )
            return [str(message) for message in request._messages]

        messages = self.assert_waits_for_control_commit(mark_ready)
        self.assertTrue(any('Neshoda' in message for message in messages))

    def test_admin_form_waits_for_control_and_rejects_new_nonconformity(self):
        def save_form():
            with transaction.atomic():
                form_class = modelform_factory(Bedna, form=BednaAdminForm, fields=['stav_bedny'])
                form = form_class(
                    {'stav_bedny': StavBednyChoice.K_EXPEDICI}, instance=Bedna.objects.get(pk=self.bedna.pk),
                )
                valid = form.is_valid()
                if valid:
                    form.save()
                return valid, str(form.errors)

        valid, errors = self.assert_waits_for_control_commit(save_form)
        self.assertFalse(valid)
        self.assertIn('Neshoda', errors)

