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
        self.configure_curvature_customer(code='EUR')
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
        if values['cistota'] == VysledekKontrolyChoice.NOK or values['ulozeni'] == VysledekKontrolyChoice.NOK:
            values['uvolneni'] = UvolneniKontrolyChoice.NESHODA
        values.setdefault('neshoda_cistota', values['cistota'] == VysledekKontrolyChoice.NOK)
        if values['ulozeni'] == VysledekKontrolyChoice.NOK:
            values.update(neshoda_jine=True, poznamka='Nesprávné uložení')
        if values.get('neshoda_krivost') and 'uvolneni' not in overrides:
            values['uvolneni'] = UvolneniKontrolyChoice.NESHODA
        if values['uvolneni'] in (UvolneniKontrolyChoice.NESHODA, UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU):
            values.setdefault('neshoda_krut_nizky', True)
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna, **values)
        self.create_curvature_measurement(kontrola, value='0.9' if values.get('neshoda_krivost') else '0.1')
        self.create_required_mechanical_measurements(kontrola)
        return kontrola

    def test_missing_or_undecided_release_hides_button_and_blocks_get_and_post(self):
        state = StavBednyChoice.ZAKALENO
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
                self.assertContains(overview, 'id="blokace-zkontrolovano"')
                self.assertContains(overview, (
                    'Vyberte a uložte rozhodnutí o uvolnění.' if has_control
                    else 'Nejprve vyplňte a uložte výstupní kontrolu'
                ))
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

    def test_every_decided_release_allows_initial_completion(self):
        state = StavBednyChoice.ZAKALENO
        for release in (
            UvolneniKontrolyChoice.UVOLNENO, UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU,
            UvolneniKontrolyChoice.NESHODA,
        ):
            with self.subTest(state=state, release=release):
                kontrola, _ = KontrolaBedny.objects.update_or_create(
                    bedna=self.bedna, defaults={
                        'uvolneni': release, 'neshoda_cistota': False,
                        'neshoda_krut_nizky': release != UvolneniKontrolyChoice.UVOLNENO,
                        'cistota': VysledekKontrolyChoice.OK, 'ulozeni': VysledekKontrolyChoice.OK,
                    },
                )
                self.create_curvature_measurement(kontrola, value='0.1')
                self.create_required_mechanical_measurements(kontrola)
                Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=state)
                overview = self.client.get(self.control_url)
                self.assertContains(overview, self.url)
                self.assertNotContains(overview, 'id="blokace-zkontrolovano"')
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
            if state == StavBednyChoice.ZAKALENO:
                continue
            with self.subTest(state=state):
                Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=state)
                overview = self.client.get(self.control_url)
                if state == StavBednyChoice.ZKONTROLOVANO:
                    self.assertNotContains(overview, 'id="blokace-zkontrolovano"')
                else:
                    self.assertContains(overview, 'id="blokace-zkontrolovano"')
                    self.assertContains(overview, f'Bedna je ve stavu {state.label}.')
                self.assertNotContains(overview, self.url)
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
        self.assertContains(response, 'Bedna je pozastavená. Nejprve je nutné zrušit pozastavení.')
        self.assertRedirects(self.client.post(self.url, self.payload), self.control_url)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZAKALENO)

    def test_missing_mark_permission_is_explained_on_readonly_control(self):
        self.create_control()
        self.user.user_permissions.clear()
        self.user.user_permissions.add(Permission.objects.get(codename='view_bedna'))
        response = self.client.get(self.control_url)
        self.assertContains(response, 'Nemáte oprávnění označit bednu jako zkontrolovanou.')
        self.assertContains(response, 'id="blokace-zkontrolovano"')
        self.assertNotContains(response, self.url)
        self.assertEqual(self.client.post(self.url, self.payload).status_code, 403)

    def test_state_and_control_are_rechecked_after_acquiring_bedna_lock(self):
        kontrola = self.create_control()
        self.create_curvature_measurement(kontrola, value='0.9')
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
        state = StavBednyChoice.ZAKALENO
        for missing in cases:
            with self.subTest(state=state, missing=missing):
                KontrolaBedny.objects.filter(bedna=self.bedna).delete()
                kontrola = self.create_control(**missing)
                Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=state)
                history_count = self.bedna.history.count()
                overview = self.client.get(self.control_url)
                self.assertFalse(overview.context['can_mark_zkontrolovano'])
                self.assertNotContains(overview, self.url)
                self.assertContains(overview, 'id="blokace-zkontrolovano"')
                reasons = ' '.join(overview.context['blokace_zkontrolovano'])
                if 'cistota' in missing:
                    self.assertIn('Čistotu (OK nebo NOK)', reasons)
                if 'ulozeni' in missing:
                    self.assertIn('Uložení (OK nebo NOK)', reasons)
                if missing.get('neshoda_krivost'):
                    if len(missing) == 1:
                        self.assertEqual(overview.context['blokace_zkontrolovano'], [
                            'Při důvodu Křivost doplňte a uložte oba počty křivých.',
                        ])
                    else:
                        for field, label in (
                            ('pocet_krivych_vrutu_prvni_mereni', 'Počet křivých 1. měření'),
                            ('pocet_krivych_vrutu_druhe_mereni', 'Počet křivých 2. měření'),
                        ):
                            self.assertEqual(label in reasons, missing.get(field) is None)
                for method in ('get', 'post'):
                    response = getattr(self.client, method)(self.url, self.payload if method == 'post' else {})
                    self.assertRedirects(response, self.control_url, fetch_redirect_response=False)
                    message_text = ' '.join(str(message) for message in response.wsgi_request._messages)
                    for reason in overview.context['blokace_zkontrolovano']:
                        self.assertIn(reason, message_text)
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
                overview = self.client.get(self.control_url)
                self.assertContains(overview, self.url)
                self.assertNotContains(overview, 'id="blokace-zkontrolovano"')
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
        return MereniBedny.objects.update_or_create(
            kontrola=kontrola, typ_zkousky=kind, poradi=1,
            defaults={'hodnota': Decimal(value)},
        )[0]

    def test_orange_heat_treatment_allows_marking_without_counts_or_straightening(self):
        self.configure_curvature_customer()
        for release in (
            UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU,
            UvolneniKontrolyChoice.NESHODA,
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
                self.assertEqual(self.bedna.rovnat, RovnaniChoice.ROVNA)
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

    def test_cleanliness_sets_blasting_and_post_ignores_forged_states(self):
        kontrola = self.create_control(uvolneni=UvolneniKontrolyChoice.NESHODA)
        for cleanliness in (VysledekKontrolyChoice.OK, VysledekKontrolyChoice.NOK):
            for previous in TryskaniChoice:
                with self.subTest(cleanliness=cleanliness, previous=previous):
                    KontrolaBedny.objects.filter(pk=kontrola.pk).update(
                        cistota=cleanliness, neshoda_cistota=cleanliness == VysledekKontrolyChoice.NOK,
                    )
                    Bedna.objects.filter(pk=self.bedna.pk).update(
                        stav_bedny=StavBednyChoice.ZAKALENO, tryskat=previous,
                        rovnat=RovnaniChoice.KRIVA,
                    )
                    if cleanliness == VysledekKontrolyChoice.NOK:
                        expected = TryskaniChoice.SPINAVA
                    elif previous in (TryskaniChoice.SPINAVA, TryskaniChoice.OTRYSKANA):
                        expected = TryskaniChoice.OTRYSKANA
                    else:
                        expected = TryskaniChoice.CISTA
                    history_count = self.bedna.history.count()
                    control_history_count = kontrola.history.count()
                    preview = self.client.get(self.url)
                    self.assertEqual(preview.status_code, 200)
                    self.assertEqual(preview.context['stavy_po_kontrole']['tryskat'], expected)
                    self.assertContains(preview, expected.label)
                    self.assertNotContains(preview, '<select')
                    self.assertEqual(self.bedna.history.count(), history_count)
                    response = self.client.post(self.url, {
                        'action': 'mark_zkontrolovano', 'rovnat': 'forged', 'tryskat': 'forged',
                    })
                    self.assertRedirects(response, self.control_url)
                    self.bedna.refresh_from_db()
                    self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZKONTROLOVANO)
                    self.assertEqual(self.bedna.tryskat, expected)
                    self.assertEqual(self.bedna.rovnat, RovnaniChoice.ROVNA)
                    self.assertEqual(self.bedna.history.count(), history_count + 1)
                    self.assertEqual(kontrola.history.count(), control_history_count)

    def test_straightening_uses_decisive_phase_and_sample_tolerance(self):
        self.configure_curvature_customer()
        kontrola = self.create_control(
            uvolneni=UvolneniKontrolyChoice.NESHODA,
            pocet_krivych_vrutu_prvni_mereni=0, pocet_krivych_vrutu_druhe_mereni=0,
        )
        for tz, after, maximum, expected, curvature_reason in (
            ('0.4', None, 0, RovnaniChoice.ROVNA, False),
            ('0.6', None, 0, RovnaniChoice.ROVNA, True),
            ('0.6001', None, 0, RovnaniChoice.KRIVA, True),
            ('0.9', '0.4', 0, RovnaniChoice.VYROVNANA, False),
            ('0.1', '0.4001', 0, RovnaniChoice.KRIVA, True),
            ('0.9', '0.5', 0, RovnaniChoice.KRIVA, True),
            ('0.9', '0.9', 1, RovnaniChoice.VYROVNANA, False),
            ('0.9', None, 1, RovnaniChoice.ROVNA, False),
        ):
            with self.subTest(tz=tz, after=after, maximum=maximum):
                self.configure_curvature_customer(maximum=maximum)
                Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=StavBednyChoice.ZAKALENO)
                MereniBedny.objects.filter(kontrola=kontrola).delete()
                self.create_curvature_measurement(kontrola, value=tz)
                self.create_required_mechanical_measurements(kontrola)
                if after is not None:
                    self.create_curvature_measurement(kontrola, value=after, kind=TypZkouskyChoice.PROHYB_PO_ROVNANI)
                # Koulení se pro rozhodující fázi nepoužívá.
                self.create_curvature_measurement(kontrola, value='9', kind=TypZkouskyChoice.PROHYB_PO_KOULENI)
                KontrolaBedny.objects.filter(pk=kontrola.pk).update(neshoda_krivost=curvature_reason)
                preview = self.client.get(self.url)
                self.assertEqual(preview.context['stavy_po_kontrole']['rovnat'], expected)
                self.assertRedirects(self.client.post(self.url, {'action': 'mark_zkontrolovano'}), self.control_url)
                self.bedna.refresh_from_db()
                self.assertEqual(self.bedna.rovnat, expected)

    def test_missing_curvature_inputs_block_button_and_direct_requests_without_saving(self):
        kontrola = self.create_control()
        for missing, text in (
            ('tz', 'Změřte a uložte Prohyb po TZ.'),
            ('limit', 'standardní maximum prohybu'),
            ('maximum', 'maximální povolený počet křivých'),
        ):
            with self.subTest(missing=missing):
                self.configure_curvature_customer(code='TST' if missing == 'limit' else 'EUR',
                                                  maximum=None if missing == 'maximum' else 0)
                MereniBedny.objects.filter(kontrola=kontrola).delete()
                self.create_required_mechanical_measurements(kontrola)
                if missing != 'tz':
                    self.create_curvature_measurement(kontrola, value='0.1')
                # Ani měření po rovnání nenahrazuje povinné měření po TZ.
                self.create_curvature_measurement(kontrola, value='0.1', kind=TypZkouskyChoice.PROHYB_PO_ROVNANI)
                history_count = self.bedna.history.count()
                overview = self.client.get(self.control_url)
                self.assertFalse(overview.context['can_mark_zkontrolovano'])
                self.assertContains(overview, text)
                for method in ('get', 'post'):
                    response = getattr(self.client, method)(self.url, self.payload if method == 'post' else {})
                    self.assertRedirects(response, self.control_url, fetch_redirect_response=False)
                    self.assertTrue(any(text in str(message) for message in response.wsgi_request._messages))
                self.bedna.refresh_from_db()
                self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZAKALENO)
                self.assertEqual(self.bedna.history.count(), history_count)

    def test_curvature_inputs_and_result_are_rechecked_under_bedna_lock(self):
        kontrola = self.create_control(uvolneni=UvolneniKontrolyChoice.NESHODA)
        for change in ('tz', 'maximum', 'result'):
            with self.subTest(change=change):
                self.configure_curvature_customer(code='EUR')
                self.create_required_mechanical_measurements(kontrola)
                self.create_curvature_measurement(kontrola, value='0.1')
                Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=StavBednyChoice.ZAKALENO)
                loads = 0

                def load_with_change(*args, **kwargs):
                    nonlocal loads
                    loads += 1
                    if loads == 2:
                        if change == 'tz':
                            MereniBedny.objects.filter(
                                kontrola=kontrola, typ_zkousky=TypZkouskyChoice.PROHYB_PO_TZ,
                            ).delete()
                        elif change == 'maximum':
                            customer = self.bedna.zakazka.kamion_prijem.zakaznik
                            type(customer).objects.filter(pk=customer.pk).update(max_krivych_vrutu=None)
                        else:
                            MereniBedny.objects.filter(
                                kontrola=kontrola, typ_zkousky=TypZkouskyChoice.PROHYB_PO_TZ,
                            ).update(hodnota=Decimal('0.9'))
                    return get_object_or_404(*args, **kwargs)

                with patch('orders.views.get_object_or_404', side_effect=load_with_change):
                    response = self.client.post(self.url, {'action': 'mark_zkontrolovano'})
                self.assertEqual(loads, 2)
                self.assertRedirects(response, self.control_url, fetch_redirect_response=False)
                self.bedna.refresh_from_db()
                self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZAKALENO)
