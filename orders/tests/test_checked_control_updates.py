from decimal import Decimal
from unittest.mock import patch

from django import forms
from django.contrib.auth.models import Permission
from django.urls import reverse

from orders.choices import (
    RovnaniChoice, StavBednyChoice, TryskaniChoice, TypZkouskyChoice,
    UvolneniKontrolyChoice, VysledekKontrolyChoice,
)
from orders.models import Bedna, KontrolaBedny, MereniBedny, ZaznamNeshody
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class CheckedControlUpdatesTests(KontrolaBednyTestBase):
    def setUp(self):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        customer.zkratka = 'ROT'
        customer.max_krivych_vrutu = 0
        customer.save()
        self.customer = customer
        self.bedna.stav_bedny = StavBednyChoice.ZKONTROLOVANO
        self.bedna.hmotnost = Decimal('10')
        self.bedna.tara = Decimal('1')
        self.bedna.mnozstvi = 100
        self.bedna.rovnat = RovnaniChoice.KRIVA
        self.bedna.tryskat = TryskaniChoice.SPINAVA
        self.bedna.save()
        self.kontrola = KontrolaBedny.objects.create(
            bedna=self.bedna, cistota=VysledekKontrolyChoice.NOK,
            ulozeni=VysledekKontrolyChoice.OK, uvolneni=UvolneniKontrolyChoice.NESHODA,
            neshoda_cistota=True, neshoda_krivost=True,
            pocet_krivych_vrutu_prvni_mereni=0, pocet_krivych_vrutu_druhe_mereni=0,
        )
        self.measurement(TypZkouskyChoice.PROHYB_PO_TZ, '0.9')
        self.user.user_permissions.add(Permission.objects.get(codename='mark_bedna_zkontrolovano'))
        self.client.force_login(self.user)
        self.url = reverse('bedna_kontrola', args=[self.bedna.cislo_bedny])

    def measurement(self, kind, value):
        return MereniBedny.objects.update_or_create(
            kontrola=self.kontrola, typ_zkousky=kind, poradi=1,
            defaults={'hodnota': Decimal(value)},
        )[0]

    def payload(self, response, **overrides):
        form = response.context['form']
        data = {'snapshot': response.context['snapshot']}
        for name, field in form.fields.items():
            value = form[name].value()
            if isinstance(field.widget, forms.CheckboxInput):
                if value:
                    data[name] = 'on'
            else:
                data[name] = '' if value is None else value
        data.update(overrides)
        return data

    def test_corrected_control_updates_both_states_and_records_author(self):
        self.measurement(TypZkouskyChoice.PROHYB_PO_ROVNANI, '0.4')
        response = self.client.get(self.url)
        count = self.bedna.history.count()
        result = self.client.post(self.url, self.payload(
            response, cistota='OK', uvolneni='UV', rovnat='KR', tryskat='SP',
        ))
        self.assertRedirects(result, self.url)
        self.bedna.refresh_from_db()
        self.kontrola.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZKONTROLOVANO)
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.VYROVNANA)
        self.assertEqual(self.bedna.tryskat, TryskaniChoice.OTRYSKANA)
        self.assertEqual(self.kontrola.uvolneni, UvolneniKontrolyChoice.UVOLNENO)
        self.assertEqual(self.kontrola.uvolneni_zmenil, self.user)
        self.assertFalse(self.kontrola.neshoda_krivost)
        self.assertFalse(self.kontrola.neshoda_cistota)
        self.assertEqual(self.bedna.history.count(), count + 1)
        self.assertEqual(self.bedna.history.first().history_user, self.user)
        messages = ' '.join(str(item) for item in result.wsgi_request._messages)
        self.assertIn('Rovnání: Vyrovnaná', messages)
        self.assertIn('Tryskání: Otryskaná', messages)

    def test_qs_release_uses_heat_treatment_deviation_without_straightening(self):
        self.measurement(TypZkouskyChoice.PROHYB_PO_TZ, '0.5')
        result = self.client.post(self.url, self.payload(
            self.client.get(self.url), cistota='OK', uvolneni='UO',
        ))
        self.assertRedirects(result, self.url)
        self.bedna.refresh_from_db()
        self.kontrola.refresh_from_db()
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.ROVNA)
        self.assertEqual(self.bedna.tryskat, TryskaniChoice.OTRYSKANA)
        self.assertTrue(self.kontrola.neshoda_krivost)

    def test_unfinished_control_leaves_technological_states_for_completion(self):
        Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=StavBednyChoice.ZAKALENO)
        self.measurement(TypZkouskyChoice.PROHYB_PO_ROVNANI, '0.1')
        count = self.bedna.history.count()
        result = self.client.post(self.url, self.payload(
            self.client.get(self.url), cistota='OK', uvolneni='UV',
        ))
        self.assertRedirects(result, self.url)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZAKALENO)
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.KRIVA)
        self.assertEqual(self.bedna.tryskat, TryskaniChoice.SPINAVA)
        self.assertEqual(self.bedna.history.count(), count)

    def test_unchanged_release_still_updates_cleanliness_and_straightening(self):
        self.measurement(TypZkouskyChoice.PROHYB_PO_ROVNANI, '0.1')
        result = self.client.post(self.url, self.payload(
            self.client.get(self.url), cistota='OK', neshoda_krut_nizky='on',
        ))
        self.assertRedirects(result, self.url)
        self.bedna.refresh_from_db()
        self.kontrola.refresh_from_db()
        self.assertEqual(self.kontrola.uvolneni, UvolneniKontrolyChoice.NESHODA)
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.VYROVNANA)
        self.assertEqual(self.bedna.tryskat, TryskaniChoice.OTRYSKANA)

    def test_unchanged_form_recalculates_from_measurements_without_duplicate_history(self):
        KontrolaBedny.objects.filter(pk=self.kontrola.pk).update(
            cistota='OK', neshoda_cistota=False, neshoda_krivost=False, neshoda_krut_nizky=True,
        )
        self.measurement(TypZkouskyChoice.PROHYB_PO_ROVNANI, '0.1')
        control_history = self.kontrola.history.count()
        bedna_history = self.bedna.history.count()
        for _ in range(2):
            response = self.client.get(self.url)
            self.assertRedirects(self.client.post(self.url, self.payload(response)), self.url)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.VYROVNANA)
        self.assertEqual(self.bedna.tryskat, TryskaniChoice.OTRYSKANA)
        self.assertEqual(self.kontrola.history.count(), control_history)
        self.assertEqual(self.bedna.history.count(), bedna_history + 1)

    def test_worsened_results_set_dirty_and_bent_and_create_nonconformity(self):
        self.measurement(TypZkouskyChoice.PROHYB_PO_TZ, '0.1')
        self.measurement(TypZkouskyChoice.PROHYB_PO_ROVNANI, '0.4001')
        Bedna.objects.filter(pk=self.bedna.pk).update(rovnat='VY', tryskat='OT')
        KontrolaBedny.objects.filter(pk=self.kontrola.pk).update(
            cistota='OK', uvolneni='UV', neshoda_cistota=False, neshoda_krivost=False,
        )
        result = self.client.post(self.url, self.payload(
            self.client.get(self.url), cistota='NOK', uvolneni='NE',
        ))
        self.assertRedirects(result, self.url)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.KRIVA)
        self.assertEqual(self.bedna.tryskat, TryskaniChoice.SPINAVA)
        self.assertEqual(ZaznamNeshody.objects.count(), 1)

    def test_invalid_or_stale_control_does_not_change_states_or_history(self):
        self.measurement(TypZkouskyChoice.PROHYB_PO_ROVNANI, '0.1')
        for stale in (False, True):
            with self.subTest(stale=stale):
                response = self.client.get(self.url)
                data = self.payload(response, cistota='OK' if stale else 'NOK', uvolneni='UV')
                if stale:
                    data['snapshot'] = 'outdated'
                history = (self.bedna.history.count(), self.kontrola.history.count())
                result = self.client.post(self.url, data)
                self.assertEqual(result.status_code, 200)
                self.assertTrue(result.context['form'].errors)
                self.bedna.refresh_from_db()
                self.kontrola.refresh_from_db()
                self.assertEqual(self.bedna.rovnat, RovnaniChoice.KRIVA)
                self.assertEqual(self.bedna.tryskat, TryskaniChoice.SPINAVA)
                self.assertEqual(self.kontrola.cistota, VysledekKontrolyChoice.NOK)
                self.assertEqual((self.bedna.history.count(), self.kontrola.history.count()), history)

    def test_missing_evaluation_inputs_reject_entire_save_with_explanation(self):
        for missing, explanation in (
            ('tz', 'Změřte a uložte Prohyb po TZ.'),
            ('limit', 'Pro zákazníka není nastavené standardní maximum prohybu.'),
            ('maximum', 'U zákazníka nastavte maximální povolený počet křivých ve vzorku.'),
            ('cleanliness', 'Vyplňte a uložte Čistotu (OK nebo NOK).'),
        ):
            with self.subTest(missing=missing):
                self.customer.zkratka = 'TST' if missing == 'limit' else 'ROT'
                self.customer.max_krivych_vrutu = None if missing == 'maximum' else 0
                self.customer.save()
                MereniBedny.objects.filter(kontrola=self.kontrola).delete()
                if missing != 'tz':
                    self.measurement(TypZkouskyChoice.PROHYB_PO_TZ, '0.1')
                response = self.client.get(self.url)
                history = (self.bedna.history.count(), self.kontrola.history.count())
                result = self.client.post(self.url, self.payload(
                    response, poznamka='Uncommitted correction', neshoda_krut_nizky='on',
                    cistota=VysledekKontrolyChoice.NEZADANO if missing == 'cleanliness' else 'NOK',
                ))
                self.assertEqual(result.status_code, 200)
                self.assertTrue(result.context['form'].non_field_errors())
                self.assertContains(result, explanation)
                self.kontrola.refresh_from_db()
                self.assertEqual(self.kontrola.poznamka, '')
                self.assertEqual((self.bedna.history.count(), self.kontrola.history.count()), history)

    def test_crate_save_failure_rolls_back_control_snapshot_and_history(self):
        self.measurement(TypZkouskyChoice.PROHYB_PO_ROVNANI, '0.1')
        data = self.payload(self.client.get(self.url), cistota='OK', neshoda_krut_nizky='on')
        history = (self.bedna.history.count(), self.kontrola.history.count())
        with patch.object(Bedna, 'save', side_effect=RuntimeError('Save failed')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, data)
        self.kontrola.refresh_from_db()
        self.assertEqual(self.kontrola.cistota, VysledekKontrolyChoice.NOK)
        self.assertFalse(self.kontrola.neshoda_krut_nizky)
        self.assertFalse(ZaznamNeshody.objects.exists())
        self.assertEqual((self.bedna.history.count(), self.kontrola.history.count()), history)
