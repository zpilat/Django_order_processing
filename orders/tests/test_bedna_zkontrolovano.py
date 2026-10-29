from decimal import Decimal
from unittest.mock import PropertyMock, patch

from django.contrib.auth.models import Permission
from django.shortcuts import get_object_or_404
from django.urls import reverse

from orders.choices import RovnaniChoice, StavBednyChoice, TryskaniChoice, TypZkouskyChoice, UvolneniKontrolyChoice, VysledekKontrolyChoice
from orders.models import Bedna, KontrolaBedny, MereniBedny
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class BednaZkontrolovanoTests(KontrolaBednyTestBase):
    def setUp(self):
        self.bedna.stav_bedny = StavBednyChoice.ZAKALENO
        self.bedna.hmotnost = 10
        self.bedna.tara = 1
        self.bedna.mnozstvi = 100
        self.bedna.save(update_fields=['stav_bedny', 'hmotnost', 'tara', 'mnozstvi'])
        self.user.user_permissions.add(Permission.objects.get(codename='mark_bedna_zkontrolovano'))
        self.client.force_login(self.user)
        self.url = reverse('bedna_scan_zkontrolovano', args=[self.bedna.cislo_bedny])
        self.control_url = reverse('bedna_kontrola', args=[self.bedna.cislo_bedny])
        self.payload = {
            'action': 'mark_zkontrolovano',
            'rovnat': RovnaniChoice.ROVNA,
            'tryskat': TryskaniChoice.CISTA,
        }

    def create_control(self, **overrides):
        values = {
            'cistota': VysledekKontrolyChoice.OK,
            'ulozeni': VysledekKontrolyChoice.OK,
            'uvolneni': UvolneniKontrolyChoice.UVOLNENO,
        }
        values.update(overrides)
        return KontrolaBedny.objects.create(bedna=self.bedna, **values)

    def test_missing_or_undecided_release_hides_button_and_blocks_get_and_post(self):
        for state in (StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO):
            for has_control in (False, True):
                with self.subTest(state=state, has_control=has_control):
                    KontrolaBedny.objects.filter(bedna=self.bedna).delete()
                    if has_control:
                        self.create_control(uvolneni=UvolneniKontrolyChoice.NEROZHODNUTO)
                    Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=state)
                    history_count = self.bedna.history.count()
                    overview = self.client.get(self.control_url)
                    self.assertFalse(overview.context['can_mark_zkontrolovano'])
                    self.assertNotContains(overview, self.url)
                    for method in ('get', 'post'):
                        response = getattr(self.client, method)(self.url, self.payload if method == 'post' else {})
                        self.assertRedirects(response, self.control_url, fetch_redirect_response=False)
                        self.assertTrue(any(
                            'rozhodnutí o uvolnění' in str(message)
                            for message in response.wsgi_request._messages
                        ))
                    self.bedna.refresh_from_db()
                    self.assertEqual(self.bedna.stav_bedny, state)
                    self.assertEqual(self.bedna.history.count(), history_count)
                    self.assertEqual(KontrolaBedny.objects.filter(bedna=self.bedna).count(), int(has_control))

    def test_every_decided_release_allows_marking_from_both_allowed_states(self):
        for state in (StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO):
            for release in (
                UvolneniKontrolyChoice.UVOLNENO, UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU,
                UvolneniKontrolyChoice.NESHODA,
            ):
                with self.subTest(state=state, release=release):
                    kontrola, _ = KontrolaBedny.objects.update_or_create(
                        bedna=self.bedna, defaults={
                            'uvolneni': release, 'neshoda_cistota': True,
                            'cistota': VysledekKontrolyChoice.OK, 'ulozeni': VysledekKontrolyChoice.OK,
                        },
                    )
                    Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=state)
                    self.assertContains(self.client.get(self.control_url), self.url)
                    self.assertEqual(self.client.get(self.url).status_code, 200)
                    response = self.client.post(self.url, self.payload)
                    self.assertRedirects(response, self.control_url)
                    self.bedna.refresh_from_db()
                    kontrola.refresh_from_db()
                    self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZKONTROLOVANO)
                    self.assertEqual(kontrola.uvolneni, release)

    def test_other_manufacturing_states_block_direct_get_and_post(self):
        self.create_control()
        for state in StavBednyChoice:
            if state in (StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO):
                continue
            with self.subTest(state=state):
                Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=state)
                history_count = self.bedna.history.count()
                for method in ('get', 'post'):
                    response = getattr(self.client, method)(self.url, self.payload if method == 'post' else {})
                    self.assertRedirects(response, self.control_url, fetch_redirect_response=False)
                self.bedna.refresh_from_db()
                self.assertEqual(self.bedna.stav_bedny, state)
                self.assertEqual(self.bedna.history.count(), history_count)

    def test_paused_bedna_cannot_be_marked_even_with_special_permission(self):
        self.create_control()
        Bedna.objects.filter(pk=self.bedna.pk).update(pozastaveno=True)
        self.user.user_permissions.add(Permission.objects.get(codename='change_pozastavena_bedna'))
        response = self.client.get(self.control_url)
        self.assertTrue(response.context['can_edit'])
        self.assertFalse(response.context['can_mark_zkontrolovano'])
        self.assertRedirects(self.client.post(self.url, self.payload), self.control_url)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZAKALENO)

    def test_state_and_control_are_rechecked_after_acquiring_bedna_lock(self):
        kontrola = self.create_control()
        control_changes = {
            'release': {'uvolneni': UvolneniKontrolyChoice.NEROZHODNUTO},
            'cistota': {'cistota': VysledekKontrolyChoice.NEZADANO},
            'ulozeni': {'ulozeni': VysledekKontrolyChoice.NEZADANO},
            'first_count': {'pocet_krivych_vrutu_prvni_mereni': None},
            'second_count': {'pocet_krivych_vrutu_druhe_mereni': None},
        }
        for change in ('state', *control_changes):
            with self.subTest(change=change):
                Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=StavBednyChoice.ZAKALENO)
                KontrolaBedny.objects.filter(pk=kontrola.pk).update(
                    uvolneni=UvolneniKontrolyChoice.NESHODA,
                    cistota=VysledekKontrolyChoice.OK, ulozeni=VysledekKontrolyChoice.OK,
                    neshoda_krivost=True,
                    pocet_krivych_vrutu_prvni_mereni=0, pocet_krivych_vrutu_druhe_mereni=0,
                )
                history_count = self.bedna.history.count()
                loads = 0

                def load_with_change(*args, **kwargs):
                    nonlocal loads
                    loads += 1
                    if loads == 2:
                        if change == 'state':
                            Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=StavBednyChoice.K_EXPEDICI)
                        else:
                            KontrolaBedny.objects.filter(pk=kontrola.pk).update(**control_changes[change])
                    return get_object_or_404(*args, **kwargs)

                with patch('orders.views.get_object_or_404', side_effect=load_with_change):
                    response = self.client.post(self.url, self.payload)
                self.assertEqual(loads, 2)
                self.assertRedirects(response, self.control_url, fetch_redirect_response=False)
                self.bedna.refresh_from_db()
                self.assertEqual(self.bedna.stav_bedny, (
                    StavBednyChoice.K_EXPEDICI if change == 'state' else StavBednyChoice.ZAKALENO
                ))
                self.assertEqual(self.bedna.history.count(), history_count)

    def test_incomplete_control_hides_button_and_blocks_direct_get_and_post(self):
        cases = (
            {'cistota': VysledekKontrolyChoice.NEZADANO},
            {'ulozeni': VysledekKontrolyChoice.NEZADANO},
            {'neshoda_krivost': True},
            {'neshoda_krivost': True, 'pocet_krivych_vrutu_prvni_mereni': 0},
            {'neshoda_krivost': True, 'pocet_krivych_vrutu_druhe_mereni': 0},
        )
        for state in (StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO):
            for missing in cases:
                with self.subTest(state=state, missing=missing):
                    KontrolaBedny.objects.filter(bedna=self.bedna).delete()
                    kontrola = self.create_control(**missing)
                    Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=state)
                    history_count = self.bedna.history.count()
                    overview = self.client.get(self.control_url)
                    self.assertFalse(overview.context['can_mark_zkontrolovano'])
                    self.assertNotContains(overview, self.url)
                    for method in ('get', 'post'):
                        response = getattr(self.client, method)(self.url, self.payload if method == 'post' else {})
                        self.assertRedirects(response, self.control_url, fetch_redirect_response=False)
                        self.assertTrue(any(
                            'čistotu, uložení' in str(message) and 'oba počty křivých' in str(message)
                            for message in response.wsgi_request._messages
                        ))
                    self.bedna.refresh_from_db()
                    self.assertEqual(self.bedna.stav_bedny, state)
                    self.assertEqual(self.bedna.history.count(), history_count)
                    self.assertEqual(kontrola.history.count(), 1)

    def test_curvature_with_both_counts_including_zero_allows_marking(self):
        for first, second in ((0, 0), (0, 2), (2, 0), (2, 3)):
            with self.subTest(first=first, second=second):
                KontrolaBedny.objects.filter(bedna=self.bedna).delete()
                self.create_control(
                    uvolneni=UvolneniKontrolyChoice.NESHODA, neshoda_krivost=True,
                    pocet_krivych_vrutu_prvni_mereni=first, pocet_krivych_vrutu_druhe_mereni=second,
                )
                Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=StavBednyChoice.ZAKALENO)
                self.assertContains(self.client.get(self.control_url), self.url)
                self.assertEqual(self.client.get(self.url).status_code, 200)
                self.assertRedirects(self.client.post(self.url, self.payload), self.control_url)
                self.bedna.refresh_from_db()
                self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZKONTROLOVANO)

    def test_nok_is_a_completed_result_for_cleanliness_and_storage(self):
        for cleanliness, storage in (
            (VysledekKontrolyChoice.NOK, VysledekKontrolyChoice.OK),
            (VysledekKontrolyChoice.OK, VysledekKontrolyChoice.NOK),
            (VysledekKontrolyChoice.NOK, VysledekKontrolyChoice.NOK),
        ):
            with self.subTest(cleanliness=cleanliness, storage=storage):
                KontrolaBedny.objects.filter(bedna=self.bedna).delete()
                self.create_control(cistota=cleanliness, ulozeni=storage)
                Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=StavBednyChoice.ZAKALENO)
                self.assertContains(self.client.get(self.control_url), self.url)
                self.assertRedirects(self.client.post(self.url, self.payload), self.control_url)

    def configure_curvature_customer(self, code='ROT', maximum=0):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        customer.zkratka = code
        customer.max_krivych_vrutu = maximum
        customer.save(update_fields=['zkratka', 'max_krivych_vrutu'])

    def create_curvature_measurement(self, kontrola, value='0.5', kind=TypZkouskyChoice.PROHYB_PO_TZ):
        return MereniBedny.objects.create(
            kontrola=kontrola, typ_zkousky=kind, hodnota=Decimal(value), poradi=1,
        )

    def test_orange_heat_treatment_allows_marking_without_counts_or_straightening(self):
        self.configure_curvature_customer()
        for release in (
            UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU,
            UvolneniKontrolyChoice.NESHODA,
            UvolneniKontrolyChoice.UVOLNENO,
        ):
            with self.subTest(release=release):
                KontrolaBedny.objects.filter(bedna=self.bedna).delete()
                kontrola = self.create_control(
                    uvolneni=release, neshoda_krivost=True, neshoda_krut_nizky=True,
                )
                self.create_curvature_measurement(kontrola)
                Bedna.objects.filter(pk=self.bedna.pk).update(
                    stav_bedny=StavBednyChoice.ZAKALENO, rovnat=RovnaniChoice.KRIVA,
                )
                self.assertContains(self.client.get(self.control_url), self.url)
                self.assertEqual(self.client.get(self.url).status_code, 200)
                response = self.client.post(self.url, {**self.payload, 'rovnat': RovnaniChoice.KRIVA})
                self.assertRedirects(response, self.control_url)
                self.bedna.refresh_from_db()
                kontrola.refresh_from_db()
                self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZKONTROLOVANO)
                self.assertEqual(self.bedna.rovnat, RovnaniChoice.KRIVA)
                self.assertEqual(kontrola.uvolneni, release)
                self.assertIsNone(kontrola.pocet_krivych_vrutu_prvni_mereni)
                self.assertIsNone(kontrola.pocet_krivych_vrutu_druhe_mereni)
                self.assertFalse(kontrola.mereni.filter(typ_zkousky=TypZkouskyChoice.PROHYB_PO_ROVNANI).exists())

    def test_orange_exception_uses_qs_limits_for_any_customer(self):
        self.configure_curvature_customer(code='TST')
        kontrola = self.create_control(uvolneni=UvolneniKontrolyChoice.NESHODA, neshoda_krivost=True)
        self.create_curvature_measurement(kontrola, value='0.6')
        with patch.object(Bedna, 'limity_prohybu', new_callable=PropertyMock, return_value={
            'bezny': Decimal('0.4'), 'pro_uvolneni_s_odchylkou': Decimal('0.6'),
        }):
            self.assertContains(self.client.get(self.control_url), self.url)
            self.assertRedirects(self.client.post(self.url, self.payload), self.control_url)

    def test_orange_exception_preserves_other_control_requirements_and_measurement_limits(self):
        cases = (
            {'value': '0.6001'},
            {'value': '0.4'},
            {'code': 'EUR', 'value': '0.7'},
            {'maximum': None},
            {'value': None},
            {'after_straightening': True},
            {'cistota': VysledekKontrolyChoice.NEZADANO},
            {'ulozeni': VysledekKontrolyChoice.NEZADANO},
            {'uvolneni': UvolneniKontrolyChoice.NEROZHODNUTO},
        )
        for case in cases:
            with self.subTest(case=case):
                self.configure_curvature_customer(code=case.get('code', 'ROT'), maximum=case.get('maximum', 0))
                KontrolaBedny.objects.filter(bedna=self.bedna).delete()
                kontrola = self.create_control(**{
                    'uvolneni': UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU, 'neshoda_krivost': True,
                    **{key: case[key] for key in ('cistota', 'ulozeni', 'uvolneni') if key in case},
                })
                if case.get('value', '0.5') is not None:
                    self.create_curvature_measurement(kontrola, value=case.get('value', '0.5'))
                if case.get('after_straightening'):
                    self.create_curvature_measurement(kontrola, kind=TypZkouskyChoice.PROHYB_PO_ROVNANI)
                self.assertNotContains(self.client.get(self.control_url), self.url)
                for method in ('get', 'post'):
                    self.assertRedirects(
                        getattr(self.client, method)(self.url, self.payload if method == 'post' else {}),
                        self.control_url, fetch_redirect_response=False,
                    )
                self.bedna.refresh_from_db()
                self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZAKALENO)

    def test_orange_measurement_is_rechecked_after_acquiring_bedna_lock(self):
        self.configure_curvature_customer()
        kontrola = self.create_control(uvolneni=UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU, neshoda_krivost=True)
        measurement = self.create_curvature_measurement(kontrola)
        loads = 0

        def load_with_change(*args, **kwargs):
            nonlocal loads
            loads += 1
            if loads == 2:
                MereniBedny.objects.filter(pk=measurement.pk).update(hodnota=Decimal('0.7'))
            return get_object_or_404(*args, **kwargs)

        with patch('orders.views.get_object_or_404', side_effect=load_with_change):
            response = self.client.post(self.url, self.payload)
        self.assertEqual(loads, 2)
        self.assertRedirects(response, self.control_url, fetch_redirect_response=False)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZAKALENO)
