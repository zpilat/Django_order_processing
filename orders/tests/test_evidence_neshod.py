from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from orders.choices import StavBednyChoice, TypZkouskyChoice, UvolneniKontrolyChoice
from orders.models import KontrolaBedny, MereniBedny, ZaznamNeshody
from orders.services.evidence_neshod_service import zaznamenat_neshodu
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class EvidenceNeshodTests(KontrolaBednyTestBase):
    def setUp(self):
        self.bedna.stav_bedny = StavBednyChoice.ZAKALENO
        self.bedna.hmotnost, self.bedna.tara, self.bedna.mnozstvi = 10, 1, 100
        self.bedna.save()
        self.user.is_staff = True
        self.user.save()
        self.user.user_permissions.add(
            Permission.objects.get(codename='mark_bedna_zkontrolovano'),
            Permission.objects.get(codename='view_zaznamneshody'),
        )
        self.client.force_login(self.user)
        self.control_url = reverse('bedna_kontrola', args=[self.bedna.cislo_bedny])
        self.list_url = reverse('admin:orders_zaznamneshody_changelist')

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

    def save_decision(self, status, **overrides):
        response = self.client.get(self.control_url)
        return self.client.post(self.control_url, self.payload(response, uvolneni=status, **overrides))

    def create_case(self):
        result = self.save_decision(UvolneniKontrolyChoice.NESHODA, neshoda_krut_nizky='on', poznamka='Původní nález')
        self.assertRedirects(result, self.control_url)
        return ZaznamNeshody.objects.get()

    def test_first_nonconformity_copies_identity_all_measurements_requirements_and_limits(self):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        customer.zkratka = 'ROT'
        customer.min_hodnot_mechanicke = 3
        customer.pocet_vrutu_pro_kontrolu_prohybu = 25
        customer.save()
        predpis = self.bedna.zakazka.predpis
        predpis.ohyb, predpis.popis_ohyb = '45 stupňů', 'Původní požadavek'
        predpis.save()
        self.bedna.sarze = 'MATERIAL-01'
        self.bedna.save()
        self.user.first_name, self.user.last_name = 'Jan', 'Novák'
        self.user.save()
        control = KontrolaBedny.objects.create(bedna=self.bedna)
        for order in range(1, 13):
            MereniBedny.objects.create(
                kontrola=control, typ_zkousky=TypZkouskyChoice.OHYB,
                hodnota=Decimal('0') if order == 1 else Decimal('45.1234'),
                poradi=order, zmeril=self.user,
            )
        MereniBedny.objects.create(
            kontrola=control, typ_zkousky=TypZkouskyChoice.PROHYB_PO_KOULENI,
            hodnota=Decimal('0.5'), poradi=1, zmeril=self.user,
        )
        result = self.save_decision(
            UvolneniKontrolyChoice.NESHODA,
            neshoda_krut_nizky='on', neshoda_krivost='on',
            pocet_krivych_vrutu_prvni_mereni=0, pocet_krivych_vrutu_druhe_mereni=2,
            poznamka='Krut a křivost',
        )
        self.assertRedirects(result, self.control_url)
        case = ZaznamNeshody.objects.get()
        control.refresh_from_db()
        self.assertEqual(case.bedna, self.bedna)
        self.assertEqual(case.zjistil, self.user)
        self.assertEqual(case.zjistil_jmeno, 'Jan Novák')
        self.assertEqual(case.zjisteno_at, control.uvolneni_zmeneno_at)
        self.assertEqual(case.zakaznik_zkratka, 'ROT')
        self.assertEqual(case.zakazka, self.bedna.zakazka.artikl)
        self.assertEqual(case.oznaceni_bedny, str(self.bedna.cislo_bedny))
        self.assertEqual(case.sarze_materialu, 'MATERIAL-01')
        self.assertEqual(case.popis_duvodu, 'Krut nízký, Křivost')
        self.assertEqual(case.snapshot['kontrola']['pocet_krivych_vrutu_prvni_mereni'], 0)
        groups = {group['typ']: group for group in case.snapshot['zkousky']}
        bend = groups[TypZkouskyChoice.OHYB]
        self.assertEqual(len(bend['mereni']), 12)
        self.assertEqual(Decimal(bend['mereni'][0]['hodnota']), 0)
        self.assertEqual(bend['mereni'][1]['hodnota'], '45.1234')
        self.assertEqual(bend['mereni'][0]['zmeril'], 'Jan Novák')
        self.assertEqual(bend['pozadavek']['hodnota'], '45 stupňů')
        self.assertEqual(bend['pozadavek']['popisy'], ['Původní požadavek'])
        self.assertEqual(bend['rozsah_mereni'], 'Min. 3 vzorky')
        rolling = groups[TypZkouskyChoice.PROHYB_PO_KOULENI]
        self.assertEqual(len(rolling['mereni']), 1)
        self.assertEqual(Decimal(rolling['limity_prohybu']['bezny']), Decimal('0.4'))
        self.assertEqual(Decimal(rolling['limity_prohybu']['pro_uvolneni_s_odchylkou']), Decimal('0.6'))
        self.assertEqual(case.zdroj_historie_id, control.history.first().history_id)
        detail = self.client.get(case.get_absolute_url())
        self.assertTemplateUsed(detail, 'admin/orders/zaznamneshody/change_form.html')
        self.assertContains(detail, 'Identifikace při zjištění')
        self.assertContains(detail, 'Neshoda a výsledky kontroly')
        self.assertNotContains(detail, 'name="snapshot"')
        self.assertContains(detail, 'Původní požadavek')
        self.assertContains(detail, '45,1234', count=11)
        self.assertContains(detail, 'Mez QS s odchylkou: 0,6 mm')

    def test_case_stays_unchanged_after_repair_release_and_source_changes(self):
        control = KontrolaBedny.objects.create(bedna=self.bedna)
        measurement = MereniBedny.objects.create(
            kontrola=control, typ_zkousky=TypZkouskyChoice.OHYB,
            hodnota=Decimal('1.25'), poradi=1, zmeril=self.user,
        )
        case = self.create_case()
        frozen = deepcopy(case.snapshot)
        measurement.hodnota = Decimal('8.75')
        measurement.save()
        measurement.delete()
        self.bedna.zakazka.artikl = 'NEW-ARTICLE'
        self.bedna.zakazka.save()
        self.bedna.zakazka.predpis.nazev = 'NEW-PRESCRIPTION'
        self.bedna.zakazka.predpis.save()
        self.bedna.sarze = 'NEW-MATERIAL'
        self.bedna.save()
        self.user.first_name = 'Změněné jméno'
        self.user.save()
        result = self.save_decision(
            UvolneniKontrolyChoice.NESHODA, neshoda_krivost='on', poznamka='Další zjištění',
        )
        self.assertRedirects(result, self.control_url)
        result = self.save_decision(
            UvolneniKontrolyChoice.UVOLNENO, neshoda_krut_nizky='', neshoda_krivost='', poznamka='',
        )
        self.assertRedirects(result, self.control_url)
        case.refresh_from_db()
        self.assertEqual(ZaznamNeshody.objects.count(), 1)
        self.assertEqual(case.snapshot, frozen)
        self.assertEqual(case.popis, 'Původní nález')
        self.assertEqual(case.popis_duvodu, 'Krut nízký')
        self.assertEqual(case.zakazka, 'A1')
        response = self.client.get(case.get_absolute_url())
        self.assertContains(response, 'Původní nález')
        self.assertContains(response, '1,25')
        self.assertNotContains(response, 'NEW-ARTICLE')
        self.assertNotContains(response, 'NEW-PRESCRIPTION')
        overview = self.client.get(reverse('neshody_prehled'))
        self.assertEqual(overview.context['items'], [])
        self.assertContains(self.client.get(self.list_url), case.get_absolute_url())
        self.assertContains(self.client.get(self.control_url), case.get_absolute_url())
        case.popis = 'Přepsaný nález'
        with self.assertRaises(ValidationError):
            case.save()

    def test_new_transition_creates_new_case_without_duplicate_saves(self):
        first = self.create_case()
        self.assertRedirects(self.save_decision(UvolneniKontrolyChoice.NESHODA), self.control_url)
        control = KontrolaBedny.objects.get(bedna=self.bedna)
        repeated = zaznamenat_neshodu(control, previous_status=UvolneniKontrolyChoice.NEROZHODNUTO, user=self.user)
        self.assertEqual(repeated.pk, first.pk)
        self.assertEqual(ZaznamNeshody.objects.count(), 1)
        self.assertRedirects(self.save_decision(UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU), self.control_url)
        self.assertEqual(ZaznamNeshody.objects.count(), 1)
        self.assertRedirects(self.save_decision(UvolneniKontrolyChoice.NESHODA), self.control_url)
        self.assertEqual(ZaznamNeshody.objects.count(), 2)
        self.assertEqual(ZaznamNeshody.objects.values('zdroj_historie_id').distinct().count(), 2)

    def test_invalid_and_stale_submissions_do_not_create_cases(self):
        response = self.client.get(self.control_url)
        invalid = self.client.post(self.control_url, self.payload(response, uvolneni=UvolneniKontrolyChoice.NESHODA))
        self.assertIn('uvolneni', invalid.context['form'].errors)
        self.assertFalse(ZaznamNeshody.objects.exists())
        self.create_case()
        stale = self.client.post(self.control_url, self.payload(
            response, uvolneni=UvolneniKontrolyChoice.NESHODA, neshoda_cistota='on',
        ))
        self.assertTrue(stale.context['form'].non_field_errors())
        self.assertEqual(ZaznamNeshody.objects.count(), 1)

    def test_prefilled_bending_nonconformity_saves_a_real_status_transition(self):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        customer.zkratka = 'ROT'
        customer.max_krivych_vrutu = 0
        customer.save()
        control = KontrolaBedny.objects.create(bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.UVOLNENO)
        MereniBedny.objects.create(
            kontrola=control, typ_zkousky=TypZkouskyChoice.PROHYB_PO_TZ,
            hodnota=Decimal('0.7'), poradi=1, zmeril=self.user,
        )
        response = self.client.get(self.control_url)
        self.assertEqual(response.context['form']['uvolneni'].value(), UvolneniKontrolyChoice.NESHODA)
        self.assertTrue(response.context['form']['neshoda_krivost'].value())
        result = self.client.post(self.control_url, self.payload(response))
        self.assertRedirects(result, self.control_url)
        control.refresh_from_db()
        self.assertEqual(control.uvolneni, UvolneniKontrolyChoice.NESHODA)
        self.assertEqual(ZaznamNeshody.objects.count(), 1)
        self.assertEqual(ZaznamNeshody.objects.get().popis_duvodu, 'Křivost')

    def test_case_failure_rolls_back_inspection_and_its_history(self):
        with patch('orders.views.zaznamenat_neshodu', side_effect=RuntimeError('Snapshot failed')):
            with self.assertRaises(RuntimeError):
                self.save_decision(UvolneniKontrolyChoice.NESHODA, neshoda_cistota='on')
        self.assertFalse(KontrolaBedny.objects.exists())
        self.assertFalse(KontrolaBedny.history.exists())
        self.assertFalse(ZaznamNeshody.objects.exists())

    def test_admin_requires_staff_and_ledger_permission_and_protects_control_links(self):
        case = self.create_case()
        self.client.logout()
        for url in (self.list_url, case.get_absolute_url()):
            self.assertEqual(self.client.get(url).status_code, 302)
        reader = get_user_model().objects.create_user(username='ledger-reader')
        self.client.force_login(reader)
        for url in (self.list_url, case.get_absolute_url()):
            self.assertEqual(self.client.get(url).status_code, 302)
        reader.user_permissions.add(Permission.objects.get(codename='view_zaznamneshody'))
        self.assertEqual(self.client.get(self.list_url).status_code, 302)
        reader.is_staff = True
        reader.save()
        self.assertEqual(self.client.get(self.list_url).status_code, 200)
        detail = self.client.get(case.get_absolute_url())
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, self.control_url)
        self.assertEqual(self.client.post(case.get_absolute_url()).status_code, 403)
        reader.user_permissions.clear()
        for url in (self.list_url, case.get_absolute_url()):
            self.assertEqual(self.client.get(url).status_code, 403)
        reader.user_permissions.add(Permission.objects.get(codename='mark_bedna_zkontrolovano'))
        control_page = self.client.get(self.control_url)
        self.assertNotContains(control_page, case.get_absolute_url())
        self.assertNotContains(control_page, self.list_url)
        reader.user_permissions.add(Permission.objects.get(codename='view_zaznamneshody'))
        control_page = self.client.get(self.control_url)
        self.assertContains(control_page, case.get_absolute_url())
        self.assertContains(control_page, self.list_url)
        self.assertEqual(self.client.get('/evidence-neshod/').status_code, 404)
        self.assertEqual(self.client.get(f'/evidence-neshod/{case.pk}/').status_code, 404)

    def test_admin_cannot_edit_or_delete_snapshots(self):
        case = self.create_case()
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        change_url = reverse('admin:orders_zaznamneshody_change', args=[case.pk])
        self.assertEqual(self.client.get(change_url).status_code, 200)
        self.assertEqual(self.client.post(change_url, {'popis': 'changed'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:orders_zaznamneshody_add')).status_code, 403)
        self.assertEqual(self.client.post(reverse('admin:orders_zaznamneshody_delete', args=[case.pk])).status_code, 403)
        self.assertContains(self.client.get(reverse('admin:index')), self.list_url)

    def test_filters_use_frozen_data_and_inclusive_local_dates(self):
        first = self.create_case()
        other = ZaznamNeshody.objects.create(
            skupina_dilu=ZaznamNeshody.SkupinaDilu.OSTATNI,
            zakaznik='Kovárna', zakaznik_zkratka='KOV', oznaceni_bedny='004/A1',
            zjisteno_at=timezone.make_aware(datetime(2026, 10, 29, 23, 59)),
            duvody=[{'kod': 'neshoda_krivost', 'nazev': 'Křivost'}],
        )
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        customer.zkratka = 'NEW'
        customer.save(update_fields=['zkratka'])
        response = self.client.get(self.list_url)
        self.assertEqual([spec.title for spec in response.context['cl'].filter_specs], [
            'Skupina dílů: Vše', 'Zákazník: Vše', 'Důvod neshody: Vše', 'Datum zjištění: Vše',
        ])
        for params, expected in (
            ({'q': first.oznaceni_bedny}, [first]),
            ({'zakaznik_zkratka__exact': 'TST'}, [first]),
            ({'duvod': 'neshoda_krut_nizky'}, [first]),
            ({'skupina_dilu__exact': 'ostatni'}, [other]),
            ({
                'zjisteno_at__gte': timezone.make_aware(datetime(2026, 10, 29)).isoformat(),
                'zjisteno_at__lt': timezone.make_aware(datetime(2026, 10, 30)).isoformat(),
                'zakaznik_zkratka__exact': 'KOV',
            }, [other]),
        ):
            with self.subTest(params=params):
                response = self.client.get(self.list_url, params)
                self.assertEqual(list(response.context['cl'].result_list), expected)
                for parameter, title in (
                    ('zakaznik_zkratka__exact', 'Zákazník: TST'),
                    ('duvod', 'Důvod neshody: Krut nízký'),
                    ('skupina_dilu__exact', 'Skupina dílů: Ostatní'),
                ):
                    if parameter in params and 'zjisteno_at__gte' not in params:
                        self.assertContains(response, title)
        self.assertEqual(self.client.get(other.get_absolute_url()).status_code, 200)

    @timezone.override('Europe/Prague')
    def test_dynamic_date_filter_uses_local_boundaries_and_replaces_date_hierarchy(self):
        dates = {
            'today': datetime(2026, 12, 31),
            'yesterday': datetime(2026, 12, 30, 23, 59),
            'week_start': datetime(2026, 12, 24),
            'before_week': datetime(2026, 12, 23, 23, 59),
            'month_start': datetime(2026, 12, 1),
            'before_month': datetime(2026, 11, 30, 23, 59),
            'year_start': datetime(2026, 1, 1),
            'before_year': datetime(2025, 12, 31, 23, 59),
            'tomorrow': datetime(2027, 1, 1),
        }
        records = {
            key: ZaznamNeshody.objects.create(zjisteno_at=timezone.make_aware(date))
            for key, date in dates.items()
        }
        now = timezone.make_aware(datetime(2026, 12, 31, 12))
        with patch('orders.filters.timezone', wraps=timezone) as filter_timezone:
            filter_timezone.now.return_value = now
            for value, label, keys in (
                ('dnes', 'Dnes', ('today',)),
                ('7_dni', 'Posledních 7 dní', ('today', 'yesterday', 'week_start')),
                ('mesic', 'Tento měsíc', ('today', 'yesterday', 'week_start', 'before_week', 'month_start')),
                ('rok', 'Tento rok', ('today', 'yesterday', 'week_start', 'before_week', 'month_start', 'before_month', 'year_start')),
            ):
                with self.subTest(value=value):
                    response = self.client.get(self.list_url, {'datum_zjisteni': value})
                    self.assertEqual(
                        set(response.context['cl'].result_list), {records[key] for key in keys},
                    )
                    self.assertContains(response, f'Datum zjištění: {label}')

            response = self.client.get(self.list_url, {
                'zjisteno_at__year': '2026', 'zjisteno_at__month': '11', 'q': 'A1',
            })
            date_filter = next(
                spec for spec in response.context['cl'].filter_specs if spec.parameter_name == 'datum_zjisteni'
            )
            for choice in date_filter.choices(response.context['cl']):
                params = parse_qs(urlsplit(choice['query_string']).query)
                self.assertFalse(any(key.startswith('zjisteno_at__') for key in params))
                self.assertEqual(params['q'], ['A1'])

    def test_pagination_preserves_filters_and_snapshot_text_is_escaped(self):
        ZaznamNeshody.objects.bulk_create([
            ZaznamNeshody(zakazka='A & B', oznaceni_bedny=str(index), popis='<script>alert(1)</script>')
            for index in range(51)
        ])
        response = self.client.get(self.list_url, {'q': 'A & B'})
        self.assertEqual(len(response.context['cl'].result_list), 50)
        self.assertEqual(response.context['cl'].result_count, 51)
        self.assertContains(response, 'q=A+%26+B')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertEqual(len(self.client.get(self.list_url, {'q': 'A & B', 'p': 2}).context['cl'].result_list), 1)
