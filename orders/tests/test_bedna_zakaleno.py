from datetime import time

from django.contrib.auth.models import Permission
from django.contrib.messages import WARNING, get_messages
from django.urls import reverse
from django.utils import timezone

from orders.choices import RovnaniChoice, StavBednyChoice, TryskaniChoice, TypZarizeniChoice
from orders.models import Bedna, Sarze, SarzeKrok, SarzeKrokBedna, Zarizeni
from orders.tests.tests_views import ViewsTestBase


class BednaZakalenoTryskaniTests(ViewsTestBase):
    def setUp(self):
        super().setUp()
        self.bedna = self.b_eur_pr
        self.bedna.stav_bedny = StavBednyChoice.DO_ZPRACOVANI
        self.bedna.rovnat = RovnaniChoice.KRIVA
        self.bedna.save(update_fields=['stav_bedny', 'rovnat'])
        self.user.user_permissions.add(Permission.objects.get(codename='scan_mark_bedna_zakaleno'))
        self.url = reverse('bedna_scan_zakaleno', args=[self.bedna.cislo_bedny])
        self.pec = Zarizeni.objects.create(
            kod_zarizeni='PEC', nazev_zarizeni='Pec', zkraceny_nazev_zarizeni='Pec',
            typ_zarizeni=TypZarizeniChoice.VICEUCELOVKA,
        )
        self.tryskac = Zarizeni.objects.create(
            kod_zarizeni='TR', nazev_zarizeni='Tryskač', zkraceny_nazev_zarizeni='Tryskač',
            typ_zarizeni=TypZarizeniChoice.TRYSKAC,
        )

    def create_batch(self):
        sarze = Sarze.objects.create(datum_zalozeni=timezone.localdate())
        self.add_step(sarze, self.pec)
        return sarze

    def add_step(self, sarze, zarizeni, *, complete=True, bedna=None):
        krok = SarzeKrok.objects.create(
            sarze=sarze, zarizeni=zarizeni, zacatek=time(6),
            konec=time(7) if complete else None, operator='Test',
        )
        SarzeKrokBedna.objects.create(
            krok=krok, bedna=bedna or self.bedna, patro=1, procent_z_patra=100,
        )
        return krok

    def mark(self, stav):
        Bedna.objects.filter(pk=self.bedna.pk).update(tryskat=stav)
        response = self.client.post(self.url, {'action': 'mark_zakaleno'})
        self.assertRedirects(response, reverse('provozni_prehledy'), fetch_redirect_response=False)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZAKALENO)
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.KRIVA)
        return [str(message) for message in get_messages(response.wsgi_request) if message.level == WARNING]

    def preview(self, stav):
        Bedna.objects.filter(pk=self.bedna.pk).update(tryskat=stav)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Pokud všechny šarže této bedny zahájily tryskání')
        return response

    def reset_manufacturing_state(self):
        Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=StavBednyChoice.DO_ZPRACOVANI)

    def test_all_batches_completed_blasting_sets_blasted_and_saves_one_history_entry(self):
        for _ in range(2):
            sarze = self.create_batch()
            self.add_step(sarze, self.tryskac)
            # Repeated occurrences of the crate or batch must not change the result.
            self.add_step(sarze, self.pec)
        for state in TryskaniChoice:
            with self.subTest(state=state):
                self.reset_manufacturing_state()
                history_count = self.bedna.history.count()
                self.assertEqual(self.mark(state), [])
                self.assertEqual(self.bedna.tryskat, TryskaniChoice.OTRYSKANA)
                self.assertEqual(self.bedna.history.count(), history_count + 1)
                latest = self.bedna.history.order_by('-history_id').first()
                self.assertEqual(latest.stav_bedny, StavBednyChoice.ZAKALENO)
                self.assertEqual(latest.tryskat, TryskaniChoice.OTRYSKANA)

    def test_partial_blasting_of_dirty_crate_warns_with_only_unblasted_batches(self):
        blasted = self.create_batch()
        self.add_step(blasted, self.tryskac)
        missing = [self.create_batch(), self.create_batch()]
        # A second occurrence must not duplicate the batch in the warning.
        self.add_step(missing[0], self.pec)
        response = self.preview(TryskaniChoice.SPINAVA)
        self.assertContains(response, 'id="varovani-neuplne-tryskani"')
        self.assertContains(response, 'Nebyly otryskány všechny vruty')
        self.assertContains(response, 'Neotryskané šarže:')
        self.assertNotContains(response, str(blasted))
        for sarze in missing:
            self.assertContains(response, str(sarze), count=1)
        self.assertContains(response, 'name="action" value="mark_zakaleno"')
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.DO_ZPRACOVANI)
        warnings = self.mark(TryskaniChoice.SPINAVA)
        self.assertEqual(self.bedna.tryskat, TryskaniChoice.SPINAVA)
        self.assertEqual(warnings, [])

    def test_partial_blasting_in_other_states_preserves_state_without_warning(self):
        self.add_step(self.create_batch(), self.tryskac)
        self.create_batch()
        for state in TryskaniChoice:
            if state == TryskaniChoice.SPINAVA:
                continue
            with self.subTest(state=state):
                self.reset_manufacturing_state()
                self.assertNotContains(self.preview(state), 'id="varovani-neuplne-tryskani"')
                self.assertEqual(self.mark(state), [])
                self.assertEqual(self.bedna.tryskat, state)

    def test_no_blasting_preserves_every_state_without_warning(self):
        self.create_batch()
        for state in TryskaniChoice:
            with self.subTest(state=state):
                self.reset_manufacturing_state()
                self.assertNotContains(self.preview(state), 'id="varovani-neuplne-tryskani"')
                self.assertEqual(self.mark(state), [])
                self.assertEqual(self.bedna.tryskat, state)

    def test_no_batches_preserves_every_state_without_warning(self):
        for state in TryskaniChoice:
            with self.subTest(state=state):
                self.reset_manufacturing_state()
                self.assertNotContains(self.preview(state), 'id="varovani-neuplne-tryskani"')
                self.assertEqual(self.mark(state), [])
                self.assertEqual(self.bedna.tryskat, state)

    def test_open_blasting_step_counts_without_end_date_or_time(self):
        self.add_step(self.create_batch(), self.tryskac)
        krok = self.add_step(self.create_batch(), self.tryskac, complete=False)
        self.assertIsNone(krok.datum_konce)
        self.assertIsNone(krok.konec)
        self.assertNotContains(self.preview(TryskaniChoice.SPINAVA), 'id="varovani-neuplne-tryskani"')
        warnings = self.mark(TryskaniChoice.SPINAVA)
        self.assertEqual(warnings, [])
        self.assertEqual(self.bedna.tryskat, TryskaniChoice.OTRYSKANA)

    def test_blasting_other_crate_in_same_batch_does_not_count(self):
        self.add_step(self.create_batch(), self.tryskac)
        missing = self.create_batch()
        self.add_step(missing, self.tryskac, bedna=self.b_abc_ex)
        response = self.preview(TryskaniChoice.SPINAVA)
        self.assertContains(response, 'id="varovani-neuplne-tryskani"')
        self.assertContains(response, str(missing))
        warnings = self.mark(TryskaniChoice.SPINAVA)
        self.assertEqual(warnings, [])
        self.assertEqual(self.bedna.tryskat, TryskaniChoice.SPINAVA)

    def test_get_does_not_change_states_and_post_uses_current_steps(self):
        sarze = self.create_batch()
        Bedna.objects.filter(pk=self.bedna.pk).update(tryskat=TryskaniChoice.SPINAVA)
        history_count = self.bedna.history.count()
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.DO_ZPRACOVANI)
        self.assertEqual(self.bedna.tryskat, TryskaniChoice.SPINAVA)
        self.assertEqual(self.bedna.history.count(), history_count)
        self.add_step(sarze, self.tryskac, complete=False)
        self.assertEqual(self.mark(TryskaniChoice.SPINAVA), [])
        self.assertEqual(self.bedna.tryskat, TryskaniChoice.OTRYSKANA)
