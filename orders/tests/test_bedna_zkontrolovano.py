from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.shortcuts import get_object_or_404
from django.urls import reverse

from orders.choices import RovnaniChoice, StavBednyChoice, TryskaniChoice, UvolneniKontrolyChoice
from orders.models import Bedna, KontrolaBedny
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

    def test_missing_or_undecided_release_hides_button_and_blocks_get_and_post(self):
        for state in (StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO):
            for has_control in (False, True):
                with self.subTest(state=state, has_control=has_control):
                    KontrolaBedny.objects.filter(bedna=self.bedna).delete()
                    if has_control:
                        KontrolaBedny.objects.create(bedna=self.bedna)
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
                        bedna=self.bedna, defaults={'uvolneni': release, 'neshoda_cistota': True},
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
        KontrolaBedny.objects.create(bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.UVOLNENO)
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
        KontrolaBedny.objects.create(bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.UVOLNENO)
        Bedna.objects.filter(pk=self.bedna.pk).update(pozastaveno=True)
        self.user.user_permissions.add(Permission.objects.get(codename='change_pozastavena_bedna'))
        response = self.client.get(self.control_url)
        self.assertTrue(response.context['can_edit'])
        self.assertFalse(response.context['can_mark_zkontrolovano'])
        self.assertRedirects(self.client.post(self.url, self.payload), self.control_url)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZAKALENO)

    def test_state_and_release_are_rechecked_after_acquiring_bedna_lock(self):
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.UVOLNENO)
        for change in ('state', 'release'):
            with self.subTest(change=change):
                Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=StavBednyChoice.ZAKALENO)
                KontrolaBedny.objects.filter(pk=kontrola.pk).update(uvolneni=UvolneniKontrolyChoice.UVOLNENO)
                history_count = self.bedna.history.count()
                loads = 0

                def load_with_change(*args, **kwargs):
                    nonlocal loads
                    loads += 1
                    if loads == 2:
                        if change == 'state':
                            Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=StavBednyChoice.K_EXPEDICI)
                        else:
                            KontrolaBedny.objects.filter(pk=kontrola.pk).update(
                                uvolneni=UvolneniKontrolyChoice.NEROZHODNUTO,
                            )
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
