from decimal import Decimal
from unittest.mock import patch

from django import forms
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from orders.choices import StavBednyChoice, TypZkouskyChoice
from orders.models import Bedna, KontrolaBedny, MereniBedny, ZaznamNeshody
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class KontrolaUnsavedTests(KontrolaBednyTestBase):
    def setUp(self):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        customer.zkratka = 'ROT'
        customer.max_krivych_vrutu = 0
        customer.save()
        Bedna.objects.filter(pk=self.bedna.pk).update(
            stav_bedny='ZK', rovnat='RO', tryskat='CI', hmotnost=10, tara=1, mnozstvi=100,
        )
        self.kontrola = KontrolaBedny.objects.create(
            bedna=self.bedna, cistota='OK', ulozeni='OK', uvolneni='UV',
        )
        MereniBedny.objects.create(
            kontrola=self.kontrola, typ_zkousky=TypZkouskyChoice.PROHYB_PO_TZ,
            poradi=1, hodnota=Decimal('0.1'),
        )
        self.user.user_permissions.add(Permission.objects.get(codename='mark_bedna_zkontrolovano'))
        self.client.force_login(self.user)
        self.url = reverse('bedna_kontrola', args=[self.bedna.cislo_bedny])

    def control_payload(self, response, **changes):
        data = {'snapshot': response.context['snapshot']}
        for name, field in response.context['form'].fields.items():
            value = response.context['form'][name].value()
            if isinstance(field.widget, forms.CheckboxInput):
                if value:
                    data[name] = 'on'
            else:
                data[name] = '' if value is None else value
        data.update(changes)
        return data

    def save_measurements(self, kind, rows, *, stale=False):
        url = reverse('bedna_mereni_zkousky', args=[self.bedna.cislo_bedny, kind])
        response = self.client.get(url)
        data = {
            'snapshot': 'stale' if stale else response.context['snapshot'],
            'mereni-TOTAL_FORMS': str(len(rows)),
            'mereni-INITIAL_FORMS': str(len(response.context['formset'].measurements)),
        }
        for index, row in enumerate(rows):
            data.update({f'mereni-{index}-{key}': str(value) for key, value in row.items()})
        return self.client.post(url, data)

    def confirm(self):
        response = self.client.get(self.url)
        self.assertRedirects(self.client.post(self.url, self.control_payload(response)), self.url)
        self.kontrola.refresh_from_db()
        self.assertFalse(self.kontrola.vyzaduje_potvrzeni)

    def test_database_baseline_is_captured_before_automatic_defaults(self):
        MereniBedny.objects.filter(kontrola=self.kontrola).update(hodnota=Decimal('0.9'))
        history = self.kontrola.history.count()
        response = self.client.get(self.url)
        saved = response.context['ochrana_kontroly']['ulozene_hodnoty']
        self.assertEqual(saved['uvolneni'], 'UV')
        self.assertFalse(saved['neshoda_krivost'])
        self.assertEqual(response.context['form']['uvolneni'].value(), 'NE')
        self.assertTrue(response.context['form']['neshoda_krivost'].value())
        self.assertTrue(response.context['ochrana_kontroly']['stavy_nepotvrzeny'])
        self.kontrola.refresh_from_db()
        self.assertEqual(self.kontrola.uvolneni, 'UV')
        self.assertEqual(self.kontrola.history.count(), history)

    def test_add_edit_delete_require_confirmation_but_unchanged_save_does_not(self):
        kind = TypZkouskyChoice.KRUT
        history = self.kontrola.history.count()
        self.assertRedirects(self.save_measurements(kind, [{'hodnota': '7'}]), self.url)
        self.kontrola.refresh_from_db()
        self.assertTrue(self.kontrola.vyzaduje_potvrzeni)
        self.assertEqual(self.kontrola.history.count(), history)
        self.confirm()
        item = MereniBedny.objects.get(kontrola=self.kontrola, typ_zkousky=kind)
        self.assertRedirects(self.save_measurements(kind, [{'id': item.pk, 'hodnota': '7.0000'}]), self.url)
        self.kontrola.refresh_from_db()
        self.assertFalse(self.kontrola.vyzaduje_potvrzeni)
        self.assertRedirects(self.save_measurements(kind, [{'id': item.pk, 'hodnota': '8'}]), self.url)
        self.kontrola.refresh_from_db()
        self.assertTrue(self.kontrola.vyzaduje_potvrzeni)
        self.confirm()
        self.assertRedirects(self.save_measurements(kind, [{'id': item.pk, 'hodnota': '8', 'DELETE': 'on'}]), self.url)
        self.kontrola.refresh_from_db()
        self.assertTrue(self.kontrola.vyzaduje_potvrzeni)
        self.assertFalse(MereniBedny.objects.filter(pk=item.pk).exists())

    def test_pending_confirmation_survives_another_browser_and_noop_measurement_save(self):
        self.save_measurements(TypZkouskyChoice.KRUT, [{'hodnota': '7'}])
        other = Client()
        other.force_login(self.user)
        response = other.get(self.url)
        self.assertTrue(response.context['ochrana_kontroly']['ceka_na_potvrzeni'])
        self.assertContains(response, 'id="kontrola-neulozene"')
        item = MereniBedny.objects.get(kontrola=self.kontrola, typ_zkousky=TypZkouskyChoice.KRUT)
        self.save_measurements(TypZkouskyChoice.KRUT, [{'id': item.pk, 'hodnota': '7'}])
        self.kontrola.refresh_from_db()
        self.assertTrue(self.kontrola.vyzaduje_potvrzeni)
        self.confirm()
        self.assertFalse(other.get(self.url).context['ochrana_kontroly']['ceka_na_potvrzeni'])

    def test_invalid_or_stale_control_does_not_clear_confirmation(self):
        self.save_measurements(TypZkouskyChoice.KRUT, [{'hodnota': '7'}])
        for stale in (False, True):
            with self.subTest(stale=stale):
                response = self.client.get(self.url)
                data = self.control_payload(response, poznamka='Draft', cistota='OK' if stale else 'NOK')
                if stale:
                    data['snapshot'] = 'stale'
                result = self.client.post(self.url, data)
                self.assertEqual(result.status_code, 200)
                self.assertTrue(result.context['form'].errors)
                self.assertEqual(result.context['ochrana_kontroly']['ulozene_hodnoty']['poznamka'], '')
                self.assertTrue(result.context['ochrana_kontroly']['is_bound'])
                self.kontrola.refresh_from_db()
                self.assertTrue(self.kontrola.vyzaduje_potvrzeni)
                self.assertEqual(self.kontrola.poznamka, '')

    def test_invalid_or_stale_measurements_do_not_request_confirmation(self):
        for stale in (False, True):
            with self.subTest(stale=stale):
                response = self.save_measurements(TypZkouskyChoice.KRUT, [
                    {'hodnota': '7' if stale else 'invalid'},
                ], stale=stale)
                self.assertEqual(response.status_code, 200)
                self.kontrola.refresh_from_db()
                self.assertFalse(self.kontrola.vyzaduje_potvrzeni)
                self.assertFalse(MereniBedny.objects.filter(typ_zkousky=TypZkouskyChoice.KRUT).exists())

    def test_confirmation_rolls_back_with_crate_control_and_nonconformity(self):
        self.save_measurements(TypZkouskyChoice.PROHYB_PO_ROVNANI, [{'hodnota': '0.1'}])
        response = self.client.get(self.url)
        history = self.kontrola.history.count()
        with patch.object(Bedna, 'save', side_effect=RuntimeError('Fail crate save')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, self.control_payload(response, cistota='NOK', uvolneni='NE'))
        self.kontrola.refresh_from_db()
        self.assertTrue(self.kontrola.vyzaduje_potvrzeni)
        self.assertEqual(self.kontrola.cistota, 'OK')
        self.assertEqual(self.kontrola.history.count(), history)
        self.assertFalse(ZaznamNeshody.objects.exists())

    def test_initial_completion_requires_saving_control_after_measurements(self):
        Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=StavBednyChoice.ZAKALENO)
        self.save_measurements(TypZkouskyChoice.KRUT, [{'hodnota': '7'}])
        finish = reverse('bedna_scan_zkontrolovano', args=[self.bedna.cislo_bedny])
        response = self.client.get(self.url)
        self.assertFalse(response.context['can_mark_zkontrolovano'])
        self.assertRedirects(self.client.post(finish, {'action': 'mark_zkontrolovano'}), self.url)
        self.confirm()
        self.assertRedirects(self.client.post(finish, {'action': 'mark_zkontrolovano'}), self.url)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZKONTROLOVANO)

    def test_first_measurement_creates_pending_control_with_unchanged_default_baseline(self):
        Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny=StavBednyChoice.ZAKALENO)
        self.kontrola.delete()
        before = self.client.get(self.url)
        self.assertFalse(before.context['ochrana_kontroly']['kontrola_existuje'])
        self.assertRedirects(self.save_measurements(TypZkouskyChoice.PROHYB_PO_TZ, [{'hodnota': '0.1'}]), self.url)
        after = self.client.get(self.url)
        self.assertTrue(after.context['ochrana_kontroly']['kontrola_existuje'])
        self.assertTrue(after.context['ochrana_kontroly']['ceka_na_potvrzeni'])
        self.assertEqual(before.context['ochrana_kontroly']['ulozene_hodnoty'],
                         after.context['ochrana_kontroly']['ulozene_hodnoty'])
        self.assertNotEqual(before.context['snapshot'], after.context['snapshot'])
