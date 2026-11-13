from decimal import Decimal
from html.parser import HTMLParser
from unittest.mock import patch

from django import forms
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.forms import modelform_factory
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

from orders.choices import KamionChoice, RovnaniChoice, StavBednyChoice, TryskaniChoice, TypZkouskyChoice, UvolneniKontrolyChoice, ZinkovaniChoice
from orders.actions import _validate_proforma_pricing
from orders import actions
from orders.forms import BednaAdminForm
from orders.models import Bedna, Cena, Kamion, KontrolaBedny, MereniBedny, Rozpracovanost, Zakazka
from orders.services.atypicky_prubeh_service import prevest_na_atypicky_prubeh
from orders.services.expedice_service import expedice_beden_do_existujiciho_kamionu, validate_bedny_pro_expedici
from orders.services.exceptions import ServiceValidationError
from orders.services.stav_bedny_service import duvody_neuplne_kontroly
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class InvoiceTableRows(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


class AtypickyPrubehTests(KontrolaBednyTestBase):
    def setUp(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        self.bedna.stav_bedny = StavBednyChoice.PRIJATO
        self.bedna.hmotnost = Decimal('10')
        self.bedna.tara = Decimal('1')
        self.bedna.mnozstvi = 100
        self.bedna.tryskat = TryskaniChoice.SPINAVA
        self.bedna.save()
        self.qs = Bedna.objects.filter(pk=self.bedna.pk)
        self.url = reverse('bedna_kontrola', args=[self.bedna.cislo_bedny])

    def start(self):
        prevest_na_atypicky_prubeh(self.qs, user=self.user)
        self.bedna.refresh_from_db()

    def configure_curvature(self, code='EUR'):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        customer.zkratka = code
        customer.max_krivych_vrutu = 0
        customer.save()

    def save_control(self, **changes):
        page = self.client.get(self.url)
        form = page.context['form']
        data = {'snapshot': page.context['snapshot']}
        for name, field in form.fields.items():
            value = form[name].value()
            if isinstance(field.widget, forms.CheckboxInput):
                if value:
                    data[name] = 'on'
            else:
                data[name] = '' if value is None else value
        data.update(cistota='OK', ulozeni='OK')
        data.update(changes)
        return self.client.post(self.url, data)

    def measure(self, kind, value):
        url = reverse('bedna_mereni_zkousky', args=[self.bedna.cislo_bedny, kind])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        response = self.client.post(url, {
            'snapshot': page.context['snapshot'],
            'mereni-TOTAL_FORMS': '1', 'mereni-INITIAL_FORMS': '0',
            'mereni-0-hodnota': value,
        })
        self.assertRedirects(response, self.url, fetch_redirect_response=False)

    def admin_payload(self, form):
        data = {}
        for field in form:
            value = field.value()
            if isinstance(field.field.widget, forms.CheckboxInput):
                if value:
                    data[field.html_name] = 'on'
            else:
                data[field.html_name] = '' if value is None else value
        return data

    def edit_admin_list_field(self, crate, name, value):
        url = reverse('admin:orders_bedna_changelist') + '?stav_bedny=ZK'
        page = self.client.get(url)
        formset = page.context['cl'].formset
        data = {'_save': 'Uložit', '_touched_enabled': '1'}
        data.update(self.admin_payload(formset.management_form))
        for form in formset.forms:
            data.update(self.admin_payload(form))
            if form.instance.pk == crate.pk:
                key = f'{form.prefix}-{name}'
                data[key] = value
                data['_touched_field'] = [key]
        return self.client.post(url, data)

    def test_admin_detail_can_change_blasting_of_unfinished_atypical_nonconformity(self):
        self.start()
        control = self.bedna.kontrola
        control_history = control.history.count()
        url = reverse('admin:orders_bedna_change', args=[self.bedna.pk])
        page = self.client.get(url)
        data = self.admin_payload(page.context['adminform'].form)
        response = self.client.post(url, {**data, 'tryskat': 'SP', '_save': 'Uložit'})
        self.assertEqual(response.status_code, 302)
        self.bedna.refresh_from_db()
        control.refresh_from_db()
        self.assertEqual(self.bedna.tryskat, TryskaniChoice.SPINAVA)
        self.assertEqual((control.cistota, control.ulozeni, control.uvolneni), ('--', '--', 'NE'))
        self.assertEqual(control.history.count(), control_history)

    def test_unchanged_incomplete_rows_do_not_block_other_rows_but_changed_standard_rows_are_validated(self):
        self.start()
        self.configure_curvature()
        normal = Bedna.objects.create(
            zakazka=self.bedna.zakazka, stav_bedny='ZK', hmotnost=10, tara=1, mnozstvi=100,
        )
        complete = KontrolaBedny.objects.create(bedna=normal, cistota='OK', ulozeni='OK', uvolneni='UV')
        self.create_required_mechanical_measurements(complete)
        MereniBedny.objects.create(kontrola=complete, typ_zkousky=TypZkouskyChoice.PROHYB_PO_TZ, hodnota='0.1', poradi=1)
        legacy = Bedna.objects.create(
            zakazka=self.bedna.zakazka, stav_bedny='ZK', hmotnost=10, tara=1, mnozstvi=100,
        )
        original_history = (self.bedna.history.count(), legacy.history.count())
        result = self.edit_admin_list_field(normal, 'poznamka', 'Změna jiné bedny')
        self.assertEqual(result.status_code, 302)
        normal.refresh_from_db()
        self.assertEqual(normal.poznamka, 'Změna jiné bedny')
        self.assertEqual((self.bedna.history.count(), legacy.history.count()), original_history)
        result = self.edit_admin_list_field(self.bedna, 'tryskat', 'SP')
        self.assertEqual(result.status_code, 302)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.tryskat, TryskaniChoice.SPINAVA)
        result = self.edit_admin_list_field(legacy, 'poznamka', 'Nelze potvrdit neúplnou běžnou kontrolu')
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, 'Nejprve vyplňte a uložte výstupní kontrolu')
        legacy.refresh_from_db()
        self.assertFalse(legacy.poznamka)

    def test_operational_edit_does_not_confirm_measurements(self):
        self.start()
        self.configure_curvature()
        self.measure(TypZkouskyChoice.PROHYB_PO_ROVNANI, '0.1')
        form_type = modelform_factory(Bedna, form=BednaAdminForm, fields=('tryskat',))
        form = form_type({'tryskat': 'SP'}, instance=Bedna.objects.get(pk=self.bedna.pk))
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.NEZADANO)
        self.assertTrue(self.bedna.kontrola.vyzaduje_potvrzeni)

    def test_partial_nonconformity_control_preserves_blasting_but_release_requires_final_checks(self):
        self.start()
        self.qs.update(tryskat=TryskaniChoice.SPINAVA)
        response = self.save_control(cistota='--', ulozeni='--', poznamka='Průběžná poznámka')
        self.assertEqual(response.status_code, 302)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.tryskat, TryskaniChoice.SPINAVA)
        self.assertEqual(self.bedna.kontrola.cistota, '--')
        for release in ('UV', 'UO'):
            with self.subTest(release=release):
                changes = {'neshoda_jine': 'on', 'poznamka': 'Odchylka'} if release == 'UO' else {}
                response = self.save_control(cistota='--', ulozeni='--', uvolneni=release, **changes)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Vyplňte a uložte Čistotu')
                self.assertContains(response, 'Vyplňte a uložte Uložení')
                self.bedna.refresh_from_db()
                self.assertEqual(self.bedna.kontrola.uvolneni, 'NE')
        with self.assertRaises(ServiceValidationError):
            validate_bedny_pro_expedici(self.qs)

    def test_admin_action_requires_confirmation_then_resets_states_and_billing(self):
        url = reverse('admin:orders_bedna_changelist')
        data = {'action': 'prevest_na_atypicky_prubeh_action', '_selected_action': [self.bedna.pk]}
        preview = self.client.post(url, data)
        self.assertContains(preview, 'confirm_atypicky_prubeh')
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.PRIJATO)
        saved = self.client.post(url, {**data, 'confirm_atypicky_prubeh': 'yes'})
        self.assertEqual(saved.status_code, 302)
        self.bedna.refresh_from_db()
        self.assertTrue(self.bedna.atypicky_prubeh)
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.ZKONTROLOVANO)
        self.assertEqual((self.bedna.rovnat, self.bedna.tryskat, self.bedna.zinkovat), ('--', '--', '--'))
        self.assertFalse(self.bedna.fakturovat)
        for operation in ('kaleni', 'rovnani', 'tryskani', 'zinkovani'):
            self.assertTrue(getattr(self.bedna, f'nefakturovat_{operation}'))
        self.assertEqual(self.bedna.history.first().history_user, self.user)
        self.assertEqual(self.bedna.kontrola.uvolneni, UvolneniKontrolyChoice.NESHODA)
        snapshot = self.bedna.zaznamy_neshod.get()
        self.assertEqual(snapshot.duvody, [])
        self.assertEqual(snapshot.zjistil, self.user)
        self.assertFalse(MereniBedny.objects.filter(kontrola__bedna=self.bedna).exists())
        with self.assertRaises(ServiceValidationError):
            validate_bedny_pro_expedici(self.qs)

    def test_action_requires_control_permission(self):
        self.user.is_superuser = False
        self.user.save()
        self.user.user_permissions.add(Permission.objects.get(codename='change_bedna'))
        response = self.client.post(reverse('admin:orders_bedna_changelist'), {
            'action': 'prevest_na_atypicky_prubeh_action', '_selected_action': [self.bedna.pk],
            'confirm_atypicky_prubeh': 'yes',
        })
        self.bedna.refresh_from_db()
        self.assertFalse(self.bedna.atypicky_prubeh)
        self.assertFalse(KontrolaBedny.objects.exists())

    def test_paused_crate_is_not_converted(self):
        self.bedna.pozastaveno = True
        self.bedna.save()
        with self.assertRaises(ValidationError):
            self.start()
        self.assertFalse(KontrolaBedny.objects.exists())

    def test_mixed_selection_and_existing_control_are_not_overwritten(self):
        other = Bedna.objects.create(zakazka=self.bedna.zakazka)
        with self.assertRaises(ValidationError):
            prevest_na_atypicky_prubeh(Bedna.objects.filter(pk__in=[self.bedna.pk, other.pk]), user=self.user)
        self.bedna.refresh_from_db()
        self.assertFalse(self.bedna.atypicky_prubeh)
        control = KontrolaBedny.objects.create(bedna=self.bedna)
        item = MereniBedny.objects.create(kontrola=control, typ_zkousky=TypZkouskyChoice.OHYB, hodnota=45, poradi=1)
        with self.assertRaises(ValidationError):
            self.start()
        self.assertEqual(MereniBedny.objects.get(pk=item.pk).hodnota, 45)

    def test_action_rolls_back_states_and_history_if_snapshot_fails(self):
        history_count = self.bedna.history.count()
        with patch('orders.services.atypicky_prubeh_service.zaznamenat_neshodu', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                self.start()
        self.bedna.refresh_from_db()
        self.assertFalse(self.bedna.atypicky_prubeh)
        self.assertEqual(self.bedna.history.count(), history_count)
        self.assertFalse(KontrolaBedny.objects.exists())

    def test_no_measurements_or_limits_required_but_qs_and_other_still_require_reason(self):
        self.start()
        self.assertEqual(self.save_control().status_code, 302)  # Neshoda bez důvodu.
        response = self.save_control(uvolneni=UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU)
        self.assertIn('uvolneni', response.context['form'].errors)
        response = self.save_control(neshoda_jine='on', poznamka='')
        self.assertIn('poznamka', response.context['form'].errors)
        self.assertEqual(self.save_control(uvolneni=UvolneniKontrolyChoice.UVOLNENO).status_code, 302)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.NEZADANO)
        self.assertEqual(self.bedna.tryskat, TryskaniChoice.CISTA)
        self.assertEqual(self.bedna.zinkovat, ZinkovaniChoice.NEZADANO)
        self.assertEqual(duvody_neuplne_kontroly(self.bedna), [])
        self.bedna.stav_bedny = StavBednyChoice.K_EXPEDICI
        with self.assertRaises(ValidationError):
            self.bedna.full_clean()  # Nezadáno stále není způsobilý technologický stav.
        self.bedna.rovnat = RovnaniChoice.ROVNA
        self.bedna.zinkovat = ZinkovaniChoice.NEZINKOVAT
        self.bedna.full_clean()
        validate_bedny_pro_expedici(self.qs)

    def test_post_straightening_is_available_without_heat_treatment_and_confirms_states(self):
        self.start()
        self.configure_curvature()
        page = self.client.get(self.url)
        self.assertIn(TypZkouskyChoice.PROHYB_PO_ROVNANI, [item['typ'] for item in page.context['zkousky']])
        self.measure(TypZkouskyChoice.PROHYB_PO_ROVNANI, '0.1')
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.NEZADANO)
        self.assertTrue(self.bedna.kontrola.vyzaduje_potvrzeni)
        self.assertEqual(self.save_control(uvolneni='UV').status_code, 302)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.VYROVNANA)
        self.assertEqual(self.bedna.zinkovat, ZinkovaniChoice.NEZADANO)
        self.assertFalse(self.bedna.kontrola.vyzaduje_potvrzeni)
        self.assertFalse(self.bedna.fakturovat)
        self.assertEqual(MereniBedny.objects.filter(kontrola__bedna=self.bedna).count(), 1)

    def test_heat_treatment_failure_sets_reason_and_kriva_when_control_is_saved(self):
        self.start()
        self.configure_curvature()
        self.measure(TypZkouskyChoice.PROHYB_PO_TZ, '10')
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.NEZADANO)
        self.assertEqual(self.save_control().status_code, 302)
        self.bedna.refresh_from_db()
        self.assertTrue(self.bedna.kontrola.neshoda_krivost)
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.KRIVA)
        self.assertEqual(self.bedna.zaznamy_neshod.count(), 2)
        rejected = self.save_control(uvolneni='UV')
        self.assertIn('uvolneni', rejected.context['form'].errors)
        self.measure(TypZkouskyChoice.PROHYB_PO_ROVNANI, '0.1')
        self.assertEqual(self.save_control(uvolneni='UV').status_code, 302)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.VYROVNANA)

    def test_passing_heat_treatment_sets_rovna_only_after_saving_control(self):
        self.start()
        self.configure_curvature()
        self.qs.update(rovnat=RovnaniChoice.KRIVA)
        self.measure(TypZkouskyChoice.PROHYB_PO_TZ, '0.1')
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.KRIVA)
        self.assertTrue(self.bedna.kontrola.vyzaduje_potvrzeni)
        self.assertEqual(self.save_control(uvolneni='UV').status_code, 302)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.ROVNA)

    def test_orange_heat_treatment_sets_rovna_on_qs_release(self):
        self.start()
        self.configure_curvature(code='ROT')
        self.measure(TypZkouskyChoice.PROHYB_PO_TZ, '0.5')
        self.assertEqual(self.save_control(uvolneni='UO').status_code, 302)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.ROVNA)
        self.assertTrue(self.bedna.kontrola.neshoda_krivost)

    def test_failed_post_straightening_sets_kriva_and_cannot_release(self):
        self.start()
        self.configure_curvature()
        self.measure(TypZkouskyChoice.PROHYB_PO_TZ, '0.1')
        self.assertEqual(self.save_control().status_code, 302)
        self.measure(TypZkouskyChoice.PROHYB_PO_ROVNANI, '10')
        self.assertEqual(self.save_control().status_code, 302)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.KRIVA)
        self.assertIsNone(self.bedna.kontrola.pocet_krivych_vrutu_prvni_mereni)
        self.assertEqual(self.bedna.kontrola.uvolneni, 'NE')

    def test_present_measurement_requires_limits_and_nok_still_blocks_release(self):
        self.start()
        self.measure(TypZkouskyChoice.PROHYB_PO_ROVNANI, '0.1')
        response = self.save_control(uvolneni='UV')
        self.assertContains(response, 'standardní maximum prohybu')
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.NEZADANO)
        self.assertTrue(self.bedna.kontrola.vyzaduje_potvrzeni)
        self.configure_curvature()
        response = self.save_control(cistota='NOK', uvolneni='UV')
        self.assertIn('uvolneni', response.context['form'].errors)
        self.assertEqual(self.save_control(cistota='NOK').status_code, 302)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.tryskat, TryskaniChoice.SPINAVA)

    def test_standard_bedna_keeps_mandatory_measurements(self):
        self.start()
        self.save_control(uvolneni='UV')
        self.bedna.refresh_from_db()
        self.bedna.atypicky_prubeh = False
        reasons = duvody_neuplne_kontroly(self.bedna)
        self.assertIn('Změřte a uložte Ohyb.', reasons)
        self.assertIn('Změřte a uložte Krut.', reasons)
        self.assertIn('Změřte a uložte Prohyb po TZ.', reasons)

    def test_manual_states_and_billing_are_preserved_on_control_save(self):
        self.start()
        self.qs.update(rovnat=RovnaniChoice.ROVNA, zinkovat=ZinkovaniChoice.ZINKOVAT,
                       fakturovat=True, nefakturovat_rovnani=False)
        self.assertEqual(self.save_control(uvolneni='UV').status_code, 302)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.rovnat, RovnaniChoice.ROVNA)
        self.assertEqual(self.bedna.zinkovat, ZinkovaniChoice.ZINKOVAT)
        self.assertTrue(self.bedna.fakturovat)
        self.assertFalse(self.bedna.nefakturovat_rovnani)

    def test_admin_form_uses_atypical_rules_but_cannot_disable_them_on_incomplete_control(self):
        self.start()
        self.save_control(uvolneni='UV')
        form_type = modelform_factory(Bedna, form=BednaAdminForm, fields=('stav_bedny', 'atypicky_prubeh'))
        valid = form_type({'stav_bedny': 'ZK', 'atypicky_prubeh': 'on'}, instance=Bedna.objects.get(pk=self.bedna.pk))
        self.assertTrue(valid.is_valid(), valid.errors)
        invalid = form_type({'stav_bedny': 'ZK'}, instance=Bedna.objects.get(pk=self.bedna.pk))
        self.assertFalse(invalid.is_valid())

    def test_atypical_crate_requires_explicit_release_but_legacy_standard_crate_does_not(self):
        self.bedna.rovnat = RovnaniChoice.ROVNA
        self.bedna.tryskat = TryskaniChoice.CISTA
        self.bedna.zinkovat = ZinkovaniChoice.NEZINKOVAT
        self.bedna.stav_bedny = StavBednyChoice.K_EXPEDICI
        self.bedna.full_clean()
        self.bedna.atypicky_prubeh = True  # Změna ve formuláři ještě není v DB.
        with self.assertRaisesMessage(ValidationError, 'rozhodnutí o uvolnění'):
            self.bedna.full_clean()
        self.qs.update(atypicky_prubeh=True)
        with self.assertRaises(ServiceValidationError):
            validate_bedny_pro_expedici(self.qs)

    def test_released_crate_can_be_shipped_without_measurements(self):
        self.start()
        self.save_control(uvolneni='UV')
        self.qs.update(rovnat=RovnaniChoice.ROVNA, zinkovat=ZinkovaniChoice.NEZINKOVAT)
        self.client.post(reverse('admin:orders_bedna_changelist'), {
            'action': 'oznacit_k_expedici_action', '_selected_action': [self.bedna.pk],
        })
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.K_EXPEDICI)
        truck = Kamion.objects.create(
            zakaznik=self.bedna.zakazka.kamion_prijem.zakaznik,
            datum=self.bedna.zakazka.kamion_prijem.datum, prijem_vydej=KamionChoice.VYDEJ,
        )
        expedice_beden_do_existujiciho_kamionu(bedny_qs=self.qs, kamion_vydej=truck, actor=self.user)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.EXPEDOVANO)
        self.assertFalse(MereniBedny.objects.filter(kontrola__bedna=self.bedna).exists())

    def test_billing_exclusions_affect_prices_weights_and_proforma_totals(self):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        customer.fakturovat_rovnani = customer.fakturovat_tryskani = True
        customer.save()
        price = Cena.objects.create(
            zakaznik=customer, popis='Test', delka_min=0, delka_max=1000,
            cena_za_kg=3, cena_rovnani_za_kg=2, cena_tryskani_za_kg=1,
        )
        price.predpis.add(self.bedna.zakazka.predpis)
        truck = Kamion.objects.create(zakaznik=customer, datum=self.bedna.zakazka.kamion_prijem.datum, prijem_vydej=KamionChoice.VYDEJ)
        order = self.bedna.zakazka
        order.kamion_vydej = truck
        order.save()
        self.bedna.rovnat = RovnaniChoice.VYROVNANA
        self.bedna.tryskat = TryskaniChoice.OTRYSKANA
        self.bedna.nefakturovat_kaleni = True
        self.bedna.nefakturovat_tryskani = True
        self.bedna.save()
        page = self.client.get(reverse('admin:orders_bedna_change', args=[self.bedna.pk]))
        self.assertContains(page, 'Fakturovat rovnání')
        self.assertNotContains(page, 'Nefakturovat rovnání')
        self.assertContains(page, 'orders/js/admin_bedna_billing.js')
        billing_fields = ('fakturovat', 'nefakturovat_kaleni', 'nefakturovat_rovnani', 'nefakturovat_tryskani', 'nefakturovat_zinkovani')
        form_type = modelform_factory(Bedna, form=BednaAdminForm, fields=billing_fields)
        rendered = form_type(instance=self.bedna).as_p()
        self.assertIn('Fakturovat rovnání', rendered)
        self.assertNotIn('Nefakturovat rovnání', rendered)
        for enabled in (False, True):
            # Při vypnutém hlavním přepínači odešle browser hodnoty přes skrytá pole.
            data = {name: str(getattr(self.bedna, name)) for name in billing_fields}
            data['fakturovat'] = str(enabled)
            form = form_type(data=data, instance=self.bedna)
            self.assertTrue(form.is_valid(), form.errors)
            form.save()
            self.bedna.refresh_from_db()
            self.assertTrue(self.bedna.nefakturovat_kaleni)
            self.assertFalse(self.bedna.nefakturovat_rovnani)
            self.assertTrue(self.bedna.nefakturovat_tryskani)
            self.assertEqual(self.bedna.cena_rovnani_za_bednu, 20 if enabled else 0)
        self.assertEqual(self.bedna.cena_za_bednu, 0)
        self.assertEqual(self.bedna.cena_rovnani_za_bednu, 20)
        self.assertEqual(self.bedna.cena_tryskani_za_bednu, 0)
        self.assertEqual(order.cena_za_zakazku, 0)
        self.assertEqual(order.cena_rovnani_za_zakazku, 20)
        self.assertEqual(order.hmotnost_fakturovaneho_kaleni, 0)
        self.assertEqual(truck.hmotnost_fakturovaneho_kaleni, 0)
        self.assertEqual(truck.hmotnost_otryskanych_beden, 0)
        self.assertEqual(truck.hmotnost_vyrovnanych_beden, 10)
        self.assertEqual(order.pocet_otryskanych_beden, 0)
        self.assertEqual(truck.pocet_otryskanych_beden, 0)
        for template in ('proforma_faktura_po_zakazkach', 'proforma_faktura_po_bednach'):
            html = render_to_string(f'orders/{template}.html', {'kamion': truck})
            self.assertIn('20,00', html)
            self.assertNotIn('30,00', html)
        snapshot = Rozpracovanost.objects.create()
        snapshot.bedny.add(self.bedna, through_defaults={
            'stav_bedny': self.bedna.stav_bedny, 'rovnat': self.bedna.rovnat,
            'tryskat': self.bedna.tryskat, 'zinkovat': self.bedna.zinkovat,
        })
        request = RequestFactory().get('/')
        request.user = self.user
        with patch('orders.actions.render_to_string', return_value='') as render, \
                patch('orders.actions.HTML') as html, patch('orders.actions.finders.find', return_value=None):
            html.return_value.write_pdf.return_value = b'pdf'
            actions.tisk_rozpracovanost_action(None, request, Rozpracovanost.objects.filter(pk=snapshot.pk))
        section = render.call_args.args[1]['sections'][0]
        self.assertEqual(section['sum_cena_netto'], 0)
        self.assertEqual(section['sum_tryskani_cena_netto'], 0)
        self.assertEqual(section['sum_rovnani_cena_netto'], 20)
        price.cena_za_kg = 0
        price.cena_tryskani_za_kg = None
        price.save()
        self.assertEqual(_validate_proforma_pricing(truck), [])
        self.bedna.nefakturovat_rovnani = True
        self.bedna.save()
        self.assertEqual(order.hmotnost_vyrovnanych_beden, 0)
        self.assertEqual(truck.pocet_vyrovnanych_beden, 0)
        self.bedna.nefakturovat_rovnani = False
        self.bedna.fakturovat = False
        self.assertEqual(self.bedna.cena_rovnani_za_bednu, 0)

    def test_billing_enabled_requires_at_least_one_selected_operation(self):
        fields = tuple(f'nefakturovat_{operation}' for operation in ('kaleni', 'rovnani', 'tryskani', 'zinkovani'))
        for name in fields:
            setattr(self.bedna, name, True)
        message = 'vyberte alespoň jednu operaci'
        with self.assertRaisesMessage(ValidationError, message):
            self.bedna.full_clean()
        form_type = modelform_factory(Bedna, form=BednaAdminForm, fields=('fakturovat', *fields))
        data = {'fakturovat': 'True', **dict.fromkeys(fields, 'True')}
        form = form_type(data=data, instance=self.bedna)
        self.assertFalse(form.is_valid())
        self.assertIn(message, str(form.non_field_errors()))
        for selected in fields:
            with self.subTest(operation=selected):
                allowed = form_type(data={**data, selected: 'False'}, instance=Bedna.objects.get(pk=self.bedna.pk))
                self.assertTrue(allowed.is_valid(), allowed.errors)
        disabled = form_type(data={**data, 'fakturovat': 'False'}, instance=Bedna.objects.get(pk=self.bedna.pk))
        self.assertTrue(disabled.is_valid(), disabled.errors)

    def create_billing_fixture(self):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        customer.fakturovat_rovnani = customer.fakturovat_tryskani = True
        customer.save()
        price = Cena.objects.create(
            zakaznik=customer, popis='Test fakturace', delka_min=0, delka_max=1000,
            cena_za_kg=3, cena_rovnani_za_kg=2, cena_tryskani_za_kg=1,
        )
        price.predpis.add(self.bedna.zakazka.predpis)
        truck = Kamion.objects.create(
            zakaznik=customer, datum=self.bedna.zakazka.kamion_prijem.datum,
            prijem_vydej=KamionChoice.VYDEJ,
        )
        order = self.bedna.zakazka
        order.kamion_vydej = truck
        order.save()
        return truck, price

    def stock_report_context(self, snapshot):
        request = RequestFactory().get('/')
        request.user = self.user
        with patch('orders.actions.render_to_string', return_value='') as render, \
                patch('orders.actions.HTML') as html, patch('orders.actions.finders.find', return_value=None):
            html.return_value.write_pdf.return_value = b'pdf'
            actions.tisk_rozpracovanost_action(None, request, Rozpracovanost.objects.filter(pk=snapshot.pk))
        return render.call_args.args[1]

    def test_admin_shows_hardness_of_atypical_crate_outside_standard_sampling(self):
        self.bedna = Bedna.objects.create(
            zakazka=self.bedna.zakazka, stav_bedny='PR', hmotnost=10, tara=1, mnozstvi=100,
        )
        self.qs = Bedna.objects.filter(pk=self.bedna.pk)
        self.start()
        self.assertFalse(self.bedna.bedna_k_mereni_tvrdosti_a_povrchu)
        predpis = self.bedna.zakazka.predpis
        predpis.povrch, predpis.jadro = '550-650 HV', '300-400 HV'
        predpis.save(update_fields=['povrch', 'jadro'])
        for kind, value in (
            (TypZkouskyChoice.TVRDOST_POVRCHU, 613), (TypZkouskyChoice.TVRDOST_JADRA, 387),
        ):
            MereniBedny.objects.create(kontrola=self.bedna.kontrola, typ_zkousky=kind, hodnota=value, poradi=1)
        response = self.client.get(reverse('admin:orders_bedna_change', args=[self.bedna.pk]))
        for text in ('Tvrdost povrchu', 'Tvrdost jádra', '613', '387', '550-650 HV', '300-400 HV'):
            self.assertContains(response, text)

    def test_grouped_invoice_counts_only_crates_with_billable_hardening(self):
        truck, _ = self.create_billing_fixture()
        self.qs.update(rovnat='VY', nefakturovat_kaleni=True, nefakturovat_tryskani=True)
        html = render_to_string('orders/proforma_faktura_po_zakazkach.html', {'kamion': truck})
        rows = InvoiceTableRows(html).rows
        row = next(row for row in rows if row and row[0] == self.bedna.zakazka.artikl)
        self.assertEqual(row[4:8], ['0', '0,0', '3,00', '0,00'])
        self.assertEqual(row[8:12], ['1', '10,0', '2,00', '20,00'])
        total = rows[-1]
        self.assertEqual(total[1], '0 ks')

        Bedna.objects.create(zakazka=self.bedna.zakazka, hmotnost=5)
        Bedna.objects.create(zakazka=self.bedna.zakazka, hmotnost=7, fakturovat=False)
        order = self.bedna.zakazka
        self.assertEqual(order.pocet_beden_fakturovanych, 2)
        self.assertEqual(truck.pocet_beden_expedovano_fakturovanych, 2)
        for container in (order, truck, order.kamion_prijem):
            self.assertEqual(container.pocet_beden_fakturovaneho_kaleni, 1)
            self.assertEqual(container.hmotnost_fakturovaneho_kaleni, 5)

    def test_grouped_invoice_omits_nonbillable_orders_and_keeps_straightening_only(self):
        truck, _ = self.create_billing_fixture()
        self.qs.update(fakturovat=False)
        order = self.bedna.zakazka
        other = Zakazka.objects.create(
            kamion_prijem=order.kamion_prijem, kamion_vydej=truck, predpis=order.predpis,
            typ_hlavy=order.typ_hlavy, artikl='PLACENE_ROVNANI', prumer=order.prumer,
            delka=order.delka, popis=order.popis,
        )
        Bedna.objects.create(zakazka=other, hmotnost=10, rovnat='VY', nefakturovat_kaleni=True)
        for template in ('proforma_faktura_po_zakazkach', 'proforma_faktura_po_bednach'):
            with self.subTest(template=template):
                html = render_to_string(f'orders/{template}.html', {'kamion': truck})
                rows = InvoiceTableRows(html).rows
                order_cells = [cell for row in rows for cell in row]
                self.assertNotIn(order.artikl, order_cells)
                self.assertIn(other.artikl, order_cells)
                self.assertIn('20,00', html)

    def test_stock_report_prices_only_operations_billed_in_the_selected_crates(self):
        truck, price = self.create_billing_fixture()
        self.qs.update(rovnat='VY', nefakturovat_kaleni=True, nefakturovat_tryskani=True)
        self.bedna.refresh_from_db()
        price.cena_za_kg = 0
        price.cena_tryskani_za_kg = None
        price.save()
        self.assertEqual(_validate_proforma_pricing(truck), [])
        # Další bedna téže zakázky se do tohoto reportu nejprve nezahrne.
        other = Bedna.objects.create(zakazka=self.bedna.zakazka, hmotnost=5)
        snapshot = Rozpracovanost.objects.create()
        snapshot.bedny.add(self.bedna)
        context = self.stock_report_context(snapshot)
        self.assertEqual(context['pricing_warnings'], [])
        section = context['sections'][0]
        self.assertEqual(section['sum_beden'], 0)
        self.assertEqual(section['zakazky'][0]['pocet_beden'], 0)
        self.assertEqual(section['sum_rovnani_beden'], 1)
        self.assertEqual(section['sum_rovnani_cena_netto'], 20)

        # Chybějící cena kalení se ohlásí, jakmile se zahrne i druhá bedna.
        snapshot.bedny.add(other)
        context = self.stock_report_context(snapshot)
        self.assertEqual(len(context['pricing_warnings']), 1)
        self.assertIn('cena kalení <= 0', context['pricing_warnings'][0])
        self.assertNotIn('cena tryskání', context['pricing_warnings'][0])
        self.assertEqual(context['sections'][0]['sum_beden'], 1)
        self.assertEqual(context['sections'][0]['sum_hmotnost'], 5)

        price.cena_rovnani_za_kg = None
        price.save()
        context = self.stock_report_context(snapshot)
        self.assertEqual(len(context['pricing_warnings']), 1)
        self.assertIn('cena rovnání <= 0', context['pricing_warnings'][0])

    def test_stock_report_does_not_require_prices_for_operations_disabled_by_customer(self):
        truck, price = self.create_billing_fixture()
        self.qs.update(rovnat='VY', tryskat='OT', nefakturovat_kaleni=True)
        customer = truck.zakaznik
        customer.fakturovat_rovnani = customer.fakturovat_tryskani = False
        customer.save()
        price.cena_za_kg = 0
        price.cena_rovnani_za_kg = price.cena_tryskani_za_kg = None
        price.save()
        snapshot = Rozpracovanost.objects.create()
        snapshot.bedny.add(self.bedna)
        context = self.stock_report_context(snapshot)
        self.assertEqual(context['pricing_warnings'], [])
