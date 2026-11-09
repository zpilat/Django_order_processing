from decimal import Decimal
from unittest.mock import patch

from django import forms
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.forms import modelform_factory
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from orders import actions
from orders.admin import BednaAdmin
from orders.choices import KamionChoice, TypZkouskyChoice, ZinkovaniChoice
from orders.forms import BednaAdminForm, BednaChangeListForm
from orders.models import Bedna, Kamion, KontrolaBedny, MereniBedny, Odberatel, ZaznamNeshody, Zakazka
from orders.services.exceptions import ServiceValidationError
from orders.services.expedice_service import (
    expedice_beden_do_existujiciho_kamionu, expedice_beden_do_noveho_kamionu,
    expedice_zakazek_do_existujiciho_kamionu, expedice_zakazek_do_noveho_kamionu,
    validate_expedice_preconditions,
)
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class KontrolaConsistencyTests(KontrolaBednyTestBase):
    def setUp(self):
        self.customer = self.bedna.zakazka.kamion_prijem.zakaznik
        self.customer.zkratka = 'ROT'
        self.customer.max_krivych_vrutu = 0
        self.customer.save()
        Bedna.objects.filter(pk=self.bedna.pk).update(
            stav_bedny='ZK', rovnat='RO', tryskat='CI', zinkovat=ZinkovaniChoice.NEZINKOVAT,
            hmotnost=10, tara=1, mnozstvi=100,
        )
        self.bedna.refresh_from_db()
        self.kontrola = KontrolaBedny.objects.create(
            bedna=self.bedna, cistota='OK', ulozeni='OK', uvolneni='UV',
        )
        self.item = MereniBedny.objects.create(
            kontrola=self.kontrola, typ_zkousky=TypZkouskyChoice.PROHYB_PO_TZ,
            poradi=1, hodnota=Decimal('0.1'),
        )
        self.create_required_mechanical_measurements(self.kontrola)
        self.user.user_permissions.add(*Permission.objects.filter(
            codename__in=['mark_bedna_zkontrolovano', 'change_bedna'],
        ))
        self.client.force_login(self.user)
        self.url = reverse('bedna_kontrola', args=[self.bedna.cislo_bedny])
        self.finish_url = reverse('bedna_scan_zkontrolovano', args=[self.bedna.cislo_bedny])
        self.admin = BednaAdmin(Bedna, AdminSite())

    def payload(self, response, **changes):
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

    def request(self, data=None):
        request = RequestFactory().post('/', data or {})
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def change_measurement(self, value='0.9', *, expect_confirmation=True):
        url = reverse('bedna_mereni_zkousky', args=[self.bedna.cislo_bedny, TypZkouskyChoice.PROHYB_PO_TZ])
        response = self.client.post(url, {
            'snapshot': self.client.get(url).context['snapshot'],
            'mereni-TOTAL_FORMS': '1', 'mereni-INITIAL_FORMS': '1',
            'mereni-0-id': str(self.item.pk), 'mereni-0-hodnota': value,
        })
        self.assertRedirects(response, self.url)
        self.kontrola.refresh_from_db()
        self.assertEqual(self.kontrola.vyzaduje_potvrzeni, expect_confirmation)

    def admin_form(self, form_class=BednaAdminForm, **changes):
        bedna = Bedna.objects.get(pk=self.bedna.pk)
        form_type = modelform_factory(Bedna, form=form_class, fields=('stav_bedny', 'zakazka'))
        return form_type({'stav_bedny': 'ZK', 'zakazka': bedna.zakazka_id, **changes}, instance=bedna)

    def test_pending_measurement_blocks_readiness_and_both_model_shipping_states(self):
        self.change_measurement()
        request = self.request()
        actions.oznacit_k_expedici_action(self.admin, request, Bedna.objects.filter(pk=self.bedna.pk))
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, 'ZK')
        self.assertTrue(any(str(self.bedna.cislo_bedny) in str(message) for message in request._messages))
        for state in ('KE', 'EX'):
            with self.subTest(state=state):
                self.bedna.stav_bedny = state
                with self.assertRaisesMessage(ValidationError, 'Po změně měření'.lower()):
                    self.bedna.full_clean()

    def test_all_shipping_paths_reject_pending_control_without_side_effects(self):
        self.change_measurement()
        # I starší bedna již K expedici s nepotvrzeným měřením musí zůstat zablokovaná.
        Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny='KE')
        receiver = Odberatel.objects.create(nazev='Consistency', zkraceny_nazev='CON', zkratka='CON')
        truck = Kamion.objects.create(
            zakaznik=self.customer, odberatel=receiver, prijem_vydej=KamionChoice.VYDEJ,
            datum=timezone.localdate(),
        )
        crates = Bedna.objects.filter(pk=self.bedna.pk)
        orders = Zakazka.objects.filter(pk=self.bedna.zakazka_id)
        self.assertTrue(validate_expedice_preconditions(bedny_qs=crates))
        for service, selection in (
            (expedice_beden_do_existujiciho_kamionu, {'bedny_qs': crates}),
            (expedice_zakazek_do_existujiciho_kamionu, {'zakazky_qs': orders}),
            (expedice_beden_do_noveho_kamionu, {'bedny_qs': crates}),
            (expedice_zakazek_do_noveho_kamionu, {'zakazky_qs': orders}),
        ):
            with self.subTest(service=service.__name__):
                counts = (Kamion.objects.count(), Zakazka.objects.count())
                kwargs = dict(selection)
                if 'existujiciho' in service.__name__:
                    kwargs['kamion_vydej'] = truck
                else:
                    kwargs.update(odberatel=receiver, zakaznici=[self.customer])
                with self.assertRaisesMessage(ServiceValidationError, 'po změně měření'):
                    service(**kwargs)
                self.bedna.refresh_from_db()
                self.assertEqual(self.bedna.stav_bedny, 'KE')
                self.assertEqual((Kamion.objects.count(), Zakazka.objects.count()), counts)

    def test_successful_confirmation_unblocks_readiness(self):
        Bedna.objects.filter(pk=self.bedna.pk).update(rovnat='KR')
        self.change_measurement('0.2')
        response = self.client.get(self.url)
        self.assertRedirects(self.client.post(self.url, self.payload(response)), self.url)
        actions.oznacit_k_expedici_action(self.admin, self.request(), Bedna.objects.filter(pk=self.bedna.pk))
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, 'KE')

    def test_checked_control_cannot_clear_required_decisions_or_confirmation(self):
        Bedna.objects.filter(pk=self.bedna.pk).update(rovnat='KR')
        self.change_measurement('0.2')
        for field in ('cistota', 'ulozeni', 'uvolneni'):
            with self.subTest(field=field):
                response = self.client.get(self.url)
                history = (self.kontrola.history.count(), self.bedna.history.count())
                result = self.client.post(self.url, self.payload(response, **{field: '--'}))
                self.assertEqual(result.status_code, 200)
                self.assertTrue(result.context['form'].errors)
                self.kontrola.refresh_from_db()
                self.assertEqual(getattr(self.kontrola, field), 'UV' if field == 'uvolneni' else 'OK')
                self.assertTrue(self.kontrola.vyzaduje_potvrzeni)
                self.assertEqual((self.kontrola.history.count(), self.bedna.history.count()), history)

    def test_red_curvature_requires_both_counts_on_checked_control(self):
        self.change_measurement()
        page = self.client.get(self.url)
        result = self.client.post(self.url, self.payload(page, uvolneni='NE'))
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, 'doplňte a uložte oba počty křivých')
        self.kontrola.refresh_from_db()
        self.assertTrue(self.kontrola.vyzaduje_potvrzeni)
        self.assertFalse(ZaznamNeshody.objects.exists())
        result = self.client.post(self.url, self.payload(
            page, uvolneni='NE', pocet_krivych_vrutu_prvni_mereni='0', pocet_krivych_vrutu_druhe_mereni='0',
        ))
        self.assertRedirects(result, self.url)
        self.kontrola.refresh_from_db()
        self.assertFalse(self.kontrola.vyzaduje_potvrzeni)

    def test_orange_tz_still_allows_qs_without_bent_counts(self):
        self.change_measurement('0.5')
        result = self.client.post(self.url, self.payload(self.client.get(self.url), uvolneni='UO'))
        self.assertRedirects(result, self.url)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.rovnat, 'RO')

    def test_snapshot_contains_final_states_on_entry_and_added_reason(self):
        self.change_measurement()
        for changes in ({'cistota': 'NOK'}, {'neshoda_krut_nizky': 'on'}):
            result = self.client.post(self.url, self.payload(
                self.client.get(self.url), uvolneni='NE',
                pocet_krivych_vrutu_prvni_mereni='0', pocet_krivych_vrutu_druhe_mereni='0', **changes,
            ))
            self.assertRedirects(result, self.url)
            self.bedna.refresh_from_db()
            snapshot = ZaznamNeshody.objects.filter(bedna=self.bedna).latest('pk').snapshot
            self.assertEqual(snapshot['bedna']['tryskani'], self.bedna.get_tryskat_display())
            self.assertEqual(snapshot['bedna']['rovnani'], self.bedna.get_rovnat_display())
        self.assertEqual(ZaznamNeshody.objects.filter(bedna=self.bedna).count(), 2)

    def test_snapshot_failure_rolls_back_control_states_and_confirmation(self):
        Bedna.objects.filter(pk=self.bedna.pk).update(rovnat='KR')
        self.change_measurement('0.2')
        history = (self.kontrola.history.count(), self.bedna.history.count())
        with patch('orders.views.zaznamenat_neshodu', side_effect=RuntimeError('Snapshot failed')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, self.payload(self.client.get(self.url), cistota='NOK', uvolneni='NE'))
        self.bedna.refresh_from_db()
        self.kontrola.refresh_from_db()
        self.assertEqual(self.bedna.tryskat, 'CI')
        self.assertEqual(self.kontrola.uvolneni, 'UV')
        self.assertTrue(self.kontrola.vyzaduje_potvrzeni)
        self.assertEqual((self.kontrola.history.count(), self.bedna.history.count()), history)

    def test_changed_customer_rules_block_completion_and_admin_until_control_saved(self):
        self.customer.max_krivych_vrutu = 1
        self.customer.save()
        MereniBedny.objects.filter(pk=self.item.pk).update(hodnota=Decimal('0.9'))
        Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny='ZA')
        self.customer.max_krivych_vrutu = 0
        self.customer.save()
        page = self.client.get(self.url)
        self.assertFalse(page.context['can_mark_zkontrolovano'])
        self.client.post(self.finish_url, {'action': 'mark_zkontrolovano'})
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, 'ZA')
        for form_class in (BednaAdminForm, BednaChangeListForm):
            self.assertFalse(self.admin_form(form_class).is_valid())
        result = self.client.post(self.url, self.payload(
            page, uvolneni='NE', pocet_krivych_vrutu_prvni_mereni='0', pocet_krivych_vrutu_druhe_mereni='0',
        ))
        self.assertRedirects(result, self.url)
        self.assertTrue(self.client.get(self.url).context['can_mark_zkontrolovano'])
        self.client.post(self.finish_url, {'action': 'mark_zkontrolovano'})
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, 'ZK')
        self.assertEqual(self.bedna.rovnat, 'KR')

    def test_admin_rejects_missing_control_and_pending_measurements(self):
        Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny='ZA')
        for form_class in (BednaAdminForm, BednaChangeListForm):
            KontrolaBedny.objects.filter(pk=self.kontrola.pk).update(vyzaduje_potvrzeni=True)
            form = self.admin_form(form_class)
            self.assertFalse(form.is_valid())
            self.assertIn('stav_bedny', form.errors)
        self.kontrola.delete()
        self.assertFalse(self.admin_form().is_valid())

    def test_admin_completion_uses_the_same_automatic_states(self):
        Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny='ZA', rovnat='KR', tryskat='SP')
        for form_class in (BednaAdminForm, BednaChangeListForm):
            with self.subTest(form_class=form_class.__name__):
                form = self.admin_form(form_class)
                self.assertTrue(form.is_valid(), form.errors)
                saved = form.save()
                self.assertEqual(saved.rovnat, 'RO')
                self.assertEqual(saved.tryskat, 'OT')
                Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny='ZA', rovnat='KR', tryskat='SP')

    def test_admin_cannot_complete_paused_crate(self):
        Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny='ZA', pozastaveno=True)
        form = self.admin_form()
        self.assertFalse(form.is_valid())
        self.assertIn('pozastavená', str(form.errors))

    def test_actual_admin_list_completion_validates_and_saves_automatic_states(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        url = reverse('admin:orders_bedna_changelist') + '?stav_bedny=ZA'
        for complete in (False, True):
            with self.subTest(complete=complete):
                Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny='ZA', rovnat='KR', tryskat='SP')
                KontrolaBedny.objects.filter(pk=self.kontrola.pk).update(ulozeni='OK' if complete else '--')
                page = self.client.get(url)
                formset = page.context['cl'].formset
                data = {'_save': 'Uložit'}
                for field in formset.management_form:
                    data[field.html_name] = field.value()
                for form in formset.forms:
                    for field in form:
                        data[field.html_name] = '' if field.value() is None else field.value()
                    data[f'{form.prefix}-stav_bedny'] = 'ZK'
                result = self.client.post(url, data)
                self.bedna.refresh_from_db()
                self.assertEqual(self.bedna.stav_bedny, 'ZK' if complete else 'ZA')
                if complete:
                    self.assertEqual(result.status_code, 302)
                    self.assertEqual(self.bedna.rovnat, 'RO')
                    self.assertEqual(self.bedna.tryskat, 'OT')
                else:
                    self.assertEqual(result.status_code, 200)
                    self.assertContains(result, 'Vyplňte a uložte Uložení')

    def test_bulk_completion_is_removed_for_get_and_post(self):
        self.assertFalse(hasattr(actions, 'oznacit_zkontrolovano_action'))
        for request in (RequestFactory().get('/', {'stav_bedny': 'RO'}), self.request()):
            request.user = self.user
            self.assertNotIn('oznacit_zkontrolovano_action', self.admin.get_actions(request))

    def test_legacy_paper_inspection_allows_readiness_after_unrelated_measurement(self):
        self.kontrola.delete()
        url = reverse('bedna_mereni_zkousky', args=[self.bedna.cislo_bedny, TypZkouskyChoice.VRSTVA])
        page = self.client.get(url)
        result = self.client.post(url, {
            'snapshot': page.context['snapshot'], 'mereni-TOTAL_FORMS': '1', 'mereni-INITIAL_FORMS': '0',
            'mereni-0-hodnota': '7',
        })
        self.assertRedirects(result, self.url)
        kontrola = KontrolaBedny.objects.get(bedna=self.bedna)
        self.assertEqual(kontrola.uvolneni, '--')
        self.assertFalse(kontrola.vyzaduje_potvrzeni)
        self.assertFalse(self.client.get(self.url).context['ochrana_kontroly']['ceka_na_potvrzeni'])
        actions.oznacit_k_expedici_action(self.admin, self.request(), Bedna.objects.filter(pk=self.bedna.pk))
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, 'KE')

    def test_missing_bending_or_torsion_blocks_button_finish_and_admin(self):
        Bedna.objects.filter(pk=self.bedna.pk).update(stav_bedny='ZA')
        other = Bedna.objects.create(zakazka=self.bedna.zakazka)
        self.create_required_mechanical_measurements(KontrolaBedny.objects.create(bedna=other))
        for missing in (
            (TypZkouskyChoice.OHYB,), (TypZkouskyChoice.KRUT,),
            (TypZkouskyChoice.OHYB, TypZkouskyChoice.KRUT),
        ):
            with self.subTest(missing=missing):
                self.create_required_mechanical_measurements(self.kontrola)
                MereniBedny.objects.filter(kontrola=self.kontrola, typ_zkousky__in=missing).delete()
                history = self.bedna.history.count()
                page = self.client.get(self.url)
                self.assertFalse(page.context['can_mark_zkontrolovano'])
                for kind in missing:
                    self.assertContains(page, f'Změřte a uložte {kind.label}.')
                for method in ('get', 'post'):
                    result = getattr(self.client, method)(self.finish_url, {'action': 'mark_zkontrolovano'})
                    self.assertRedirects(result, self.url, fetch_redirect_response=False)
                for form_class in (BednaAdminForm, BednaChangeListForm):
                    form = self.admin_form(form_class)
                    self.assertFalse(form.is_valid())
                    for kind in missing:
                        self.assertIn(f'Změřte a uložte {kind.label}.', str(form.errors))
                # Rozpracovaná kontrola ve stavu Zakaleno se smí dál ukládat.
                self.assertRedirects(self.client.post(self.url, self.payload(page)), self.url)
                self.bedna.refresh_from_db()
                self.assertEqual(self.bedna.stav_bedny, 'ZA')
                self.assertEqual(self.bedna.history.count(), history)

        self.create_required_mechanical_measurements(self.kontrola)
        self.assertTrue(self.client.get(self.url).context['can_mark_zkontrolovano'])
        self.assertRedirects(self.client.post(self.finish_url, {'action': 'mark_zkontrolovano'}), self.url)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, 'ZK')

    def test_checked_control_cannot_confirm_missing_mechanical_measurements(self):
        Bedna.objects.filter(pk=self.bedna.pk).update(rovnat='KR')
        self.change_measurement('0.2')
        for missing in (TypZkouskyChoice.OHYB, TypZkouskyChoice.KRUT):
            with self.subTest(missing=missing):
                self.create_required_mechanical_measurements(self.kontrola)
                MereniBedny.objects.filter(kontrola=self.kontrola, typ_zkousky=missing).delete()
                page = self.client.get(self.url)
                history = (self.kontrola.history.count(), self.bedna.history.count())
                result = self.client.post(self.url, self.payload(page, poznamka='Neúplná oprava'))
                self.assertEqual(result.status_code, 200)
                self.assertContains(result, f'Změřte a uložte {missing.label}.')
                self.kontrola.refresh_from_db()
                self.assertTrue(self.kontrola.vyzaduje_potvrzeni)
                self.assertEqual(self.kontrola.poznamka, '')
                self.assertEqual((self.kontrola.history.count(), self.bedna.history.count()), history)
