from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.admin.sites import AdminSite
from django.http import HttpResponse
from django.urls import reverse

from decimal import Decimal
from unittest.mock import patch
from datetime import date
import csv
import io
import json

from orders.models import (
    Zakaznik, Kamion, Zakazka, Bedna, Predpis, TypHlavy,
    Odberatel, Pozice
)
from orders.choices import KamionChoice, StavBednyChoice, RovnaniChoice, TryskaniChoice
from orders import actions
from orders.admin import BednaAdmin


class ActionsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.factory = RequestFactory()
        User = get_user_model()
        cls.user = User.objects.create_superuser('admin', 'a@example.com', 'pass')
        cls.site = AdminSite()
        cls.zakaznik = Zakaznik.objects.create(
            nazev='Test', zkraceny_nazev='T', zkratka='EUR', ciselna_rada=100000
        )
        cls.odberatel = Odberatel.objects.create(
            nazev='O1', zkraceny_nazev='O1', zkratka='OD1'
        )
        cls.kamion_prijem = Kamion.objects.create(zakaznik=cls.zakaznik, datum=date.today())
        cls.kamion_vydej = Kamion.objects.create(
            zakaznik=cls.zakaznik,
            datum=date.today(),
            prijem_vydej=KamionChoice.VYDEJ,
            odberatel=cls.odberatel
        )
        cls.predpis = Predpis.objects.create(nazev='Predpis', skupina=1, zakaznik=cls.zakaznik)
        cls.typ_hlavy = TypHlavy.objects.create(nazev='SK', popis='popis')
        cls.zakazka = Zakazka.objects.create(
            kamion_prijem=cls.kamion_prijem,
            artikl='A1', prumer=1, delka=1,
            predpis=cls.predpis, typ_hlavy=cls.typ_hlavy,
            popis='p'
        )
        cls.bedna = Bedna.objects.create(zakazka=cls.zakazka, hmotnost=Decimal(1), tara=Decimal(1), mnozstvi=1, stav_bedny=StavBednyChoice.PRIJATO)

    def get_request(self, method='get', data=None):
        req = getattr(self.factory, method)('/', data or {})
        req.user = self.user
        req.session = {}
        req._messages = FallbackStorage(req)
        return req
    

class DummyAdmin:
    def message_user(self, request, message, level=None):
        pass  # Dummy method to avoid errors in tests


class ActionsTests(ActionsBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = DummyAdmin()

    # Helpers for tests that need to assert messages
    def _messaging_admin(self):
        from django.contrib import messages as dj_messages

        class _Admin:
            def message_user(self, request, message, level=None):
                dj_messages.add_message(request, level or dj_messages.INFO, message)

        return _Admin()

    def _messages_texts(self, request):
        return [m.message for m in list(request._messages)]

    @patch('orders.actions.utilita_tisk_dokumentace')
    def test_tisk_karet_beden_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        req = self.get_request()
        qs = Bedna.objects.all()
        resp = actions.tisk_karet_beden_action(self.admin, req, qs)
        mock_util.assert_called_once_with(self.admin, req, qs,
                                          'orders/karta_bedny_eur.html', 'karty_beden_eur.pdf')
        self.assertIsInstance(resp, HttpResponse)

    def test_tisk_karet_beden_action_empty(self):
        resp = actions.tisk_karet_beden_action(self.admin, self.get_request(), Bedna.objects.none())
        self.assertIsNone(resp)

    @patch('orders.actions.utilita_tisk_dokumentace')
    def test_tisk_karet_kontroly_kvality_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        resp = actions.tisk_karet_kontroly_kvality_action(self.admin, self.get_request(), Bedna.objects.all())
        mock_util.assert_called_once()
        self.assertIsInstance(resp, HttpResponse)

    @patch('orders.actions.utilita_tisk_dokumentace_sablony')
    def test_tisk_karet_bedny_a_kontroly_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        req = self.get_request()
        qs = Bedna.objects.all()
        resp = actions.tisk_karet_bedny_a_kontroly_action(self.admin, req, qs)
        self.assertIsInstance(resp, HttpResponse)
        mock_util.assert_called_once_with(
            self.admin,
            req,
            qs,
            [
                'orders/karta_bedny_eur.html',
                'orders/karta_kontroly_kvality_eur.html',
            ],
            'karty_bedny_a_kontroly_eur.pdf',
        )

    @patch('orders.actions.utilita_expedice_zakazek')
    @patch('orders.actions.utilita_kontrola_zakazek')
    def test_expedice_zakazek_action(self, mock_kontrola, mock_expedice):
        data = {'apply': '1', 'odberatel': self.odberatel.id}
        req = self.get_request('post', data)
        with patch('orders.actions.Kamion.objects.create', return_value=self.kamion_vydej) as mock_create:
            resp = actions.expedice_zakazek_action(self.admin, req, Zakazka.objects.all())
        self.assertIsNone(resp)
        mock_create.assert_called()
        mock_expedice.assert_called()

    def test_expedice_zakazek_action_empty(self):
        resp = actions.expedice_zakazek_action(self.admin, self.get_request('post'), Zakazka.objects.none())
        self.assertIsNone(resp)

    @patch('orders.actions.utilita_expedice_zakazek')
    @patch('orders.actions.utilita_kontrola_zakazek')
    def test_expedice_zakazek_kamion_action(self, mock_kontrola, mock_expedice):
        data = {'apply': '1', 'kamion': self.kamion_vydej.id}
        req = self.get_request('post', data)
        qs = Zakazka.objects.all()
        resp = actions.expedice_zakazek_kamion_action(self.admin, req, qs)
        self.assertIsNone(resp)
        mock_expedice.assert_called_with(self.admin, req, qs, self.kamion_vydej)

    @patch('orders.actions.utilita_tisk_dokumentace')
    def test_tisk_karet_beden_zakazek_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        resp = actions.tisk_karet_beden_zakazek_action(self.admin, self.get_request(), Zakazka.objects.all())
        self.assertIsInstance(resp, HttpResponse)

    @patch('orders.actions.utilita_tisk_dokumentace')
    def test_tisk_karet_kontroly_kvality_zakazek_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        resp = actions.tisk_karet_kontroly_kvality_zakazek_action(self.admin, self.get_request(), Zakazka.objects.all())
        self.assertIsInstance(resp, HttpResponse)

    def test_vratit_zakazky_z_expedice_action(self):
        self.zakazka.expedovano = True
        self.zakazka.kamion_vydej = self.kamion_vydej
        self.zakazka.save()
        actions.vratit_zakazky_z_expedice_action(self.admin, self.get_request('post'), Zakazka.objects.all())
        self.zakazka.refresh_from_db()
        self.assertFalse(self.zakazka.expedovano)
        self.assertIsNone(self.zakazka.kamion_vydej)
        self.assertEqual(self.zakazka.bedny.first().stav_bedny, StavBednyChoice.K_EXPEDICI)

    def test_import_kamionu_action(self):
        kamion = Kamion.objects.create(zakaznik=self.zakaznik, datum=date.today())
        resp = actions.import_kamionu_action(self.site, self.get_request('post'), Kamion.objects.filter(id=kamion.id))
        self.assertIsNotNone(resp)

    def test_import_kamionu_action_multiple_selected_error(self):
        admin_obj = self._messaging_admin()
        k1 = Kamion.objects.create(zakaznik=self.zakaznik, datum=date.today())
        k2 = Kamion.objects.create(zakaznik=self.zakaznik, datum=date.today())
        req = self.get_request('post')
        resp = actions.import_kamionu_action(admin_obj, req, Kamion.objects.filter(id__in=[k1.id, k2.id]))
        self.assertIsNone(resp)
        msgs = self._messages_texts(req)
        self.assertTrue(any('Vyber pouze jeden kamion' in m for m in msgs))

    def test_import_kamionu_action_not_prijem_error(self):
        admin_obj = self._messaging_admin()
        req = self.get_request('post')
        resp = actions.import_kamionu_action(admin_obj, req, Kamion.objects.filter(id=self.kamion_vydej.id))
        self.assertIsNone(resp)
        msgs = self._messages_texts(req)
        self.assertTrue(any('Import je možný pouze pro kamiony příjem' in m for m in msgs))

    def test_import_kamionu_action_has_orders_error(self):
        admin_obj = self._messaging_admin()
        req = self.get_request('post')
        resp = actions.import_kamionu_action(admin_obj, req, Kamion.objects.filter(id=self.kamion_prijem.id))
        self.assertIsNone(resp)
        msgs = self._messages_texts(req)
        self.assertTrue(any('Kamion již obsahuje zakázky' in m for m in msgs))

    @patch('orders.actions.utilita_tisk_dl_a_proforma_faktury')
    def test_tisk_dodaciho_listu_kamionu_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        resp = actions.tisk_dodaciho_listu_kamionu_action(self.site, self.get_request(), Kamion.objects.filter(id=self.kamion_vydej.id))
        self.assertIsInstance(resp, HttpResponse)

    def test_tisk_dodaciho_listu_kamionu_action_not_vydej_error(self):
        admin_obj = self._messaging_admin()
        req = self.get_request('get')
        resp = actions.tisk_dodaciho_listu_kamionu_action(admin_obj, req, Kamion.objects.filter(id=self.kamion_prijem.id))
        self.assertIsNone(resp)
        msgs = self._messages_texts(req)
        self.assertTrue(any('Tisk DL je možný pouze pro kamiony výdej' in m for m in msgs))

    @patch('orders.actions.utilita_tisk_dl_a_proforma_faktury')
    def test_tisk_proforma_faktury_kamionu_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        resp = actions.tisk_proforma_faktury_kamionu_action(self.site, self.get_request(), Kamion.objects.filter(id=self.kamion_vydej.id))
        self.assertIsInstance(resp, HttpResponse)

    def test_tisk_proforma_faktury_kamionu_action_not_vydej_error(self):
        admin_obj = self._messaging_admin()
        req = self.get_request('get')
        resp = actions.tisk_proforma_faktury_kamionu_action(admin_obj, req, Kamion.objects.filter(id=self.kamion_prijem.id))
        self.assertIsNone(resp)
        msgs = self._messages_texts(req)
        self.assertTrue(any('Tisk proforma faktury je možný pouze pro kamiony výdej' in m for m in msgs))

    @patch('orders.actions.utilita_tisk_dokumentace')
    def test_tisk_karet_beden_kamionu_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        resp = actions.tisk_karet_beden_kamionu_action(self.admin, self.get_request(), Kamion.objects.filter(id=self.kamion_prijem.id))
        self.assertIsInstance(resp, HttpResponse)

    def test_tisk_karet_beden_kamionu_action_wrong_direction_error(self):
        admin_obj = self._messaging_admin()
        req = self.get_request('get')
        resp = actions.tisk_karet_beden_kamionu_action(admin_obj, req, Kamion.objects.filter(id=self.kamion_vydej.id))
        self.assertIsNone(resp)
        msgs = self._messages_texts(req)
        self.assertTrue(any('Tisk karet beden je možný pouze pro kamiony příjem' in m for m in msgs))

    def test_tisk_karet_beden_kamionu_action_no_bedny_error(self):
        admin_obj = self._messaging_admin()
        empty_k = Kamion.objects.create(zakaznik=self.zakaznik, datum=date.today())
        req = self.get_request('get')
        resp = actions.tisk_karet_beden_kamionu_action(admin_obj, req, Kamion.objects.filter(id=empty_k.id))
        self.assertIsNone(resp)
        msgs = self._messages_texts(req)
        self.assertTrue(any('V označeném kamionu nejsou žádné bedny' in m for m in msgs))

    @patch('orders.actions.utilita_tisk_dokumentace')
    def test_tisk_karet_kontroly_kvality_kamionu_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        resp = actions.tisk_karet_kontroly_kvality_kamionu_action(self.admin, self.get_request(), Kamion.objects.filter(id=self.kamion_prijem.id))
        self.assertIsInstance(resp, HttpResponse)

    def test_tisk_karet_kontroly_kvality_kamionu_action_wrong_direction_error(self):
        admin_obj = self._messaging_admin()
        req = self.get_request('get')
        resp = actions.tisk_karet_kontroly_kvality_kamionu_action(admin_obj, req, Kamion.objects.filter(id=self.kamion_vydej.id))
        self.assertIsNone(resp)
        msgs = self._messages_texts(req)
        self.assertTrue(any('Tisk karet beden je možný pouze pro kamiony příjem' in m for m in msgs))

    def test_tisk_karet_kontroly_kvality_kamionu_action_no_bedny_error(self):
        admin_obj = self._messaging_admin()
        empty_k = Kamion.objects.create(zakaznik=self.zakaznik, datum=date.today())
        req = self.get_request('get')
        resp = actions.tisk_karet_kontroly_kvality_kamionu_action(admin_obj, req, Kamion.objects.filter(id=empty_k.id))
        self.assertIsNone(resp)
        msgs = self._messages_texts(req)
        self.assertTrue(any('V označeném kamionu nejsou žádné bedny' in m for m in msgs))

    def test_expedice_zakazek_kamion_action_multiple_customers_error(self):
        admin_obj = self._messaging_admin()
        z2 = Zakaznik.objects.create(nazev='Z2', zkraceny_nazev='Z2', zkratka='E2', ciselna_rada=200000)
        k2 = Kamion.objects.create(zakaznik=z2, datum=date.today())
        predpis2 = Predpis.objects.create(nazev='P2', skupina=1, zakaznik=z2)
        zak2 = Zakazka.objects.create(
            kamion_prijem=k2, artikl='B1', prumer=1, delka=1,
            predpis=predpis2, typ_hlavy=self.typ_hlavy, popis='p2'
        )
        req = self.get_request('post')
        qs = Zakazka.objects.filter(id__in=[self.zakazka.id, zak2.id])
        resp = actions.expedice_zakazek_kamion_action(admin_obj, req, qs)
        self.assertIsNone(resp)
        msgs = self._messages_texts(req)
        self.assertTrue(any('Všechny vybrané zakázky musí patřit jednomu zákazníkovi' in m for m in msgs))


class ExportBednyCsvActionTests(ActionsBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

    def setUp(self):
        super().setUp()
        self.bedna_admin = BednaAdmin(Bedna, self.site)

    def test_export_bedny_to_csv_action_generates_expected_rows(self):
        bedna = self.bedna
        bedna.stav_bedny = StavBednyChoice.K_EXPEDICI
        bedna.rovnat = RovnaniChoice.ROVNA
        bedna.tryskat = TryskaniChoice.CISTA
        bedna.poznamka = 'Pozn'
        bedna.behalter_nr = 42
        bedna.save()

        self.zakazka.celozavit = True
        self.zakazka.popis = 'Plny popis'
        self.zakazka.save()

        Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal('2.5'),
            tara=Decimal('1.0'),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.DO_ZPRACOVANI,
        )

        request = self.get_request('post', data={'select_across': '1', 'action': 'export_bedny_to_csv_action'})
        response = actions.export_bedny_to_csv_action(self.bedna_admin, request, Bedna.objects.all())

        self.assertIsInstance(response, HttpResponse)
        content = response.content.decode('utf-8-sig')
        rows = list(csv.reader(io.StringIO(content), delimiter=';'))

        self.assertGreaterEqual(len(rows), 2)
        expected_header = [
            'Zákazník', 'Zakázka', 'Číslo bedny', 'Č.b. zák.', 'Navezené', 'Rozměr', 'Do zprac.',
            'Zakal.', 'Kontrol.', 'Křivost', 'Čistota', 'K expedici', 'Hmotnost', 'Poznámka',
            'Hlava + závit', 'Název', 'Skupina',
        ]
        self.assertEqual(rows[0], expected_header)

        expected_row = [
            'T',
            'A1',
            str(bedna.cislo_bedny),
            '42',
            '',
            '1 x 1',
            'x',
            'x',
            'x',
            'x',
            'x',
            '0',
            '1',
            'Pozn',
            'SK + VG',
            'Plny popis',
            '1',
        ]
        self.assertEqual(rows[1], expected_row)


class BednaAdminPollingTests(ActionsBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

    def setUp(self):
        super().setUp()
        self.bedna_admin = BednaAdmin(Bedna, self.site)

    def test_poll_changes_view_without_since(self):
        request = self.get_request('get')
        response = self.bedna_admin.poll_changes_view(request)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertIn('timestamp', payload)
        self.assertIn('changed', payload)
        self.assertFalse(payload['changed'])

    def test_poll_changes_view_detects_updates(self):
        initial_request = self.get_request('get')
        initial_payload = json.loads(
            self.bedna_admin.poll_changes_view(initial_request).content.decode('utf-8')
        )
        baseline_timestamp = initial_payload.get('timestamp')
        self.assertIsNotNone(baseline_timestamp)

        # Provede změnu na bedně, aby vznikl nový historický záznam
        self.bedna.poznamka = 'Změna pro polling'
        self.bedna.save()

        request = self.get_request('get', data={'since': baseline_timestamp})
        response = self.bedna_admin.poll_changes_view(request)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertIn('timestamp', payload)
        self.assertTrue(payload['changed'])
        self.assertIsNotNone(payload['timestamp'])

class KNavezeniActionTests(ActionsBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Vytvoří výchozí skladovou pozici
        cls.pozice_A = Pozice.objects.create(kod='A', kapacita=10)

    def _minimal_admin(self):
        # Minimální stub s atributy používanými renderem akce
        class _Site:
            def each_context(self, request):
                return {}

        class _Admin:
            admin_site = _Site()
            model = Bedna

            def message_user(self, request, message, level=None):
                # žádná akce pro testy
                return None

        return _Admin()

    def test_get_renders_formset(self):
        # Přidá druhou bednu ve stavu PRIJATO
        Bedna.objects.create(zakazka=self.zakazka, hmotnost=Decimal(2), tara=Decimal(1), mnozstvi=1, stav_bedny=StavBednyChoice.PRIJATO)
        req = self.get_request('get')
        admin_obj = self._minimal_admin()
        qs = Bedna.objects.all().order_by('id')
        resp = actions.oznacit_k_navezeni_action(admin_obj, req, qs)
        # Měl by vrátit TemplateResponse s formsetem pro obě bedny
        from django.template.response import TemplateResponse
        self.assertIsInstance(resp, TemplateResponse)
        self.assertIn('formset', resp.context_data)
        formset = resp.context_data['formset']
        self.assertEqual(len(formset.forms), qs.count())

    def test_post_success_updates_bedny(self):
        admin_obj = self._minimal_admin()
        qs = Bedna.objects.all().order_by('id')
        from django.contrib import admin as dj_admin
        data = {
            'apply': '1',
            'ozn-TOTAL_FORMS': str(qs.count()),
            'ozn-INITIAL_FORMS': str(qs.count()),
            'ozn-MIN_NUM_FORMS': '0',
            'ozn-MAX_NUM_FORMS': '1000',
        }
        for i, b in enumerate(qs):
            data[f'ozn-{i}-bedna_id'] = str(b.id)
            data[f'ozn-{i}-pozice'] = str(self.pozice_A.id)
            data[f'ozn-{i}-poznamka_k_navezeni'] = 'pozn'
        for b in qs:
            data.setdefault(dj_admin.helpers.ACTION_CHECKBOX_NAME, [])
            data[dj_admin.helpers.ACTION_CHECKBOX_NAME].append(str(b.id))

        req = self.get_request('post', data)
        resp = actions.oznacit_k_navezeni_action(admin_obj, req, qs)
        self.assertIsNone(resp)
        for b in qs:
            b.refresh_from_db()
            self.assertEqual(b.stav_bedny, StavBednyChoice.K_NAVEZENI)
            self.assertEqual(b.pozice_id, self.pozice_A.id)
            self.assertEqual(b.poznamka_k_navezeni, 'pozn')

    def test_post_redirects_to_dashboard_when_requested(self):
        admin_obj = self._minimal_admin()
        qs = Bedna.objects.all().order_by('id')
        from django.contrib import admin as dj_admin
        data = {
            'apply_open_dashboard': '1',
            'ozn-TOTAL_FORMS': str(qs.count()),
            'ozn-INITIAL_FORMS': str(qs.count()),
            'ozn-MIN_NUM_FORMS': '0',
            'ozn-MAX_NUM_FORMS': '1000',
        }
        for i, b in enumerate(qs):
            data[f'ozn-{i}-bedna_id'] = str(b.id)
            data[f'ozn-{i}-pozice'] = str(self.pozice_A.id)
            data[f'ozn-{i}-poznamka_k_navezeni'] = 'pozn'
        for b in qs:
            data.setdefault(dj_admin.helpers.ACTION_CHECKBOX_NAME, [])
            data[dj_admin.helpers.ACTION_CHECKBOX_NAME].append(str(b.id))

        req = self.get_request('post', data)
        resp = actions.oznacit_k_navezeni_action(admin_obj, req, qs)
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], reverse('dashboard_bedny_k_navezeni'))
        for b in qs:
            b.refresh_from_db()
            self.assertEqual(b.stav_bedny, StavBednyChoice.K_NAVEZENI)

    def test_post_invalid_form_returns_template(self):
        admin_obj = self._minimal_admin()
        qs = Bedna.objects.all()[:1]
        from django.contrib import admin as dj_admin
        data = {
            'apply': '1',
            'ozn-TOTAL_FORMS': '1',
            'ozn-INITIAL_FORMS': '1',
            'ozn-MIN_NUM_FORMS': '0',
            'ozn-MAX_NUM_FORMS': '1000',
            'ozn-0-bedna_id': str(qs[0].id),
            'ozn-0-pozice': '',  # invalid (required)
            'ozn-0-poznamka': '',
            dj_admin.helpers.ACTION_CHECKBOX_NAME: [str(qs[0].id)],
        }
        req = self.get_request('post', data)
        resp = actions.oznacit_k_navezeni_action(admin_obj, req, qs)
        from django.template.response import TemplateResponse
        self.assertIsInstance(resp, TemplateResponse)


class StatusChangeActionsTests(ActionsBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

    def _messaging_admin(self):
        from django.contrib import messages as dj_messages

        class _Admin:
            def message_user(self, request, message, level=None):
                dj_messages.add_message(request, level or dj_messages.INFO, message)

        return _Admin()

    def _messages_texts(self, request):
        return [m.message for m in list(request._messages)]

    def test_abort_if_paused_bedny_blocks_queryset(self):
        admin_obj = self._messaging_admin()
        self.bedna.stav_bedny = StavBednyChoice.NEPRIJATO
        self.bedna.pozastaveno = True
        self.bedna.save()
        req = self.get_request('post')
        result = actions._abort_if_paused_bedny(admin_obj, req, Bedna.objects.all(), "Test akce")
        self.assertTrue(result)
        msgs = self._messages_texts(req)
        self.assertTrue(any('pozastavených beden' in m for m in msgs))

    def test_abort_if_paused_bedny_allows_clean_queryset(self):
        admin_obj = self._messaging_admin()
        self.bedna.stav_bedny = StavBednyChoice.NEPRIJATO
        self.bedna.pozastaveno = False
        self.bedna.save()
        req = self.get_request('post')
        result = actions._abort_if_paused_bedny(admin_obj, req, Bedna.objects.all(), "Test akce")
        self.assertFalse(result)
        self.assertEqual(self._messages_texts(req), [])

    def test_abort_if_paused_bedny_handles_iterable_without_filter(self):
        admin_obj = self._messaging_admin()
        self.bedna.pozastaveno = True
        self.bedna.save()
        req = self.get_request('post')
        class _Broken(list):
            def filter(self, *args, **kwargs):
                raise TypeError("no filter on plain iterable")
        broken = _Broken([self.bedna])
        result = actions._abort_if_paused_bedny(admin_obj, req, broken, "Test akce")
        self.assertTrue(result)
        msgs = self._messages_texts(req)
        self.assertTrue(any('pozastavených beden' in m for m in msgs))

    def test_abort_if_zakazky_maji_pozastavene_bedny_blocks(self):
        admin_obj = self._messaging_admin()
        self.bedna.pozastaveno = True
        self.bedna.save()
        req = self.get_request('post')
        result = actions._abort_if_zakazky_maji_pozastavene_bedny(
            admin_obj,
            req,
            Zakazka.objects.filter(id=self.zakazka.id),
            "Test akce",
        )
        self.assertTrue(result)
        msgs = self._messages_texts(req)
        self.assertTrue(any('pozastavených beden' in m for m in msgs))

    def test_abort_if_zakazky_maji_pozastavene_bedny_allows_clean(self):
        admin_obj = self._messaging_admin()
        self.bedna.pozastaveno = False
        self.bedna.save()
        req = self.get_request('post')
        result = actions._abort_if_zakazky_maji_pozastavene_bedny(
            admin_obj,
            req,
            Zakazka.objects.filter(id=self.zakazka.id),
            "Test akce",
        )
        self.assertFalse(result)
        self.assertEqual(self._messages_texts(req), [])

    def test_abort_if_kamiony_maji_pozastavene_bedny_blocks(self):
        admin_obj = self._messaging_admin()
        self.bedna.pozastaveno = True
        self.bedna.save()
        req = self.get_request('post')
        result = actions._abort_if_kamiony_maji_pozastavene_bedny(
            admin_obj,
            req,
            Kamion.objects.filter(id=self.kamion_prijem.id),
            "Test akce",
        )
        self.assertTrue(result)
        msgs = self._messages_texts(req)
        self.assertTrue(any('pozastavených beden' in m for m in msgs))

    def test_abort_if_kamiony_maji_pozastavene_bedny_allows_clean(self):
        admin_obj = self._messaging_admin()
        self.bedna.pozastaveno = False
        self.bedna.save()
        req = self.get_request('post')
        result = actions._abort_if_kamiony_maji_pozastavene_bedny(
            admin_obj,
            req,
            Kamion.objects.filter(id=self.kamion_prijem.id),
            "Test akce",
        )
        self.assertFalse(result)
        self.assertEqual(self._messages_texts(req), [])

    def test_oznacit_navezeno_action_wrong_state(self):
        # připraví bednu, která není v K_NAVEZENI
        admin_obj = self._messaging_admin()
        self.bedna.stav_bedny = StavBednyChoice.PRIJATO
        self.bedna.save()
        req = self.get_request('post')
        resp = actions.oznacit_navezeno_action(admin_obj, req, Bedna.objects.filter(id=self.bedna.id))
        self.assertIsNone(resp)
        msgs = self._messages_texts(req)
        self.assertTrue(any('nejsou ve stavu K NAVEZENÍ' in m for m in msgs))

    def test_oznacit_navezeno_action_success(self):
        admin_obj = self._messaging_admin()
        # nastaví správný počáteční stav
        self.bedna.stav_bedny = StavBednyChoice.K_NAVEZENI
        self.bedna.save()
        req = self.get_request('post')
        resp = actions.oznacit_navezeno_action(admin_obj, req, Bedna.objects.filter(id=self.bedna.id))
        self.assertIsNone(resp)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.NAVEZENO)

    def test_prijmout_bedny_action_blocked_by_paused(self):
        admin_obj = self._messaging_admin()
        self.bedna.stav_bedny = StavBednyChoice.NEPRIJATO
        self.bedna.pozastaveno = True
        self.bedna.save()
        req = self.get_request('post')
        resp = actions.prijmout_bedny_action(admin_obj, req, Bedna.objects.filter(id=self.bedna.id))
        self.assertIsNone(resp)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.NEPRIJATO)
        msgs = self._messages_texts(req)
        self.assertTrue(any('pozastavených beden' in m for m in msgs))

    def test_prijmout_zakazku_action_blocked_by_paused_bedna(self):
        admin_obj = self._messaging_admin()
        self.bedna.stav_bedny = StavBednyChoice.NEPRIJATO
        self.bedna.pozastaveno = True
        self.bedna.save()
        req = self.get_request('post')
        resp = actions.prijmout_zakazku_action(admin_obj, req, Zakazka.objects.filter(id=self.zakazka.id))
        self.assertIsNone(resp)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.NEPRIJATO)
        msgs = self._messages_texts(req)
        self.assertTrue(any('pozastavených beden' in m for m in msgs))

    @patch('orders.actions.utilita_kontrola_zakazek')
    def test_expedice_zakazek_action_blocked_by_paused_bedna(self, mock_kontrola):
        admin_obj = self._messaging_admin()
        self.bedna.pozastaveno = True
        self.bedna.save()
        req = self.get_request('get')
        resp = actions.expedice_zakazek_action(admin_obj, req, Zakazka.objects.filter(id=self.zakazka.id))
        self.assertIsNone(resp)
        mock_kontrola.assert_not_called()
        msgs = self._messages_texts(req)
        self.assertTrue(any('pozastavených beden' in m for m in msgs))

    @patch('orders.actions.utilita_kontrola_zakazek')
    def test_expedice_zakazek_kamion_action_blocked_by_paused_bedna(self, mock_kontrola):
        admin_obj = self._messaging_admin()
        self.bedna.pozastaveno = True
        self.bedna.save()
        req = self.get_request('get')
        resp = actions.expedice_zakazek_kamion_action(admin_obj, req, Zakazka.objects.filter(id=self.zakazka.id))
        self.assertIsNone(resp)
        mock_kontrola.assert_not_called()
        msgs = self._messages_texts(req)
        self.assertTrue(any('pozastavených beden' in m for m in msgs))

    def test_prijmout_kamion_action_blocked_by_paused_bedna(self):
        admin_obj = self._messaging_admin()
        self.bedna.stav_bedny = StavBednyChoice.NEPRIJATO
        self.bedna.pozastaveno = True
        self.bedna.save()
        req = self.get_request('post')
        resp = actions.prijmout_kamion_action(admin_obj, req, Kamion.objects.filter(id=self.kamion_prijem.id))
        self.assertIsNone(resp)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.NEPRIJATO)
        msgs = self._messages_texts(req)
        self.assertTrue(any('pozastavených beden' in m for m in msgs))

    def test_prijmout_kamion_action_success(self):
        admin_obj = self._messaging_admin()
        # vytvoří NEPRIJATO bednu s platnými daty pro přechod do PRIJATO
        from decimal import Decimal
        b = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal('1'),
            tara=Decimal('1'),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.NEPRIJATO,
        )
        req = self.get_request('post')
        resp = actions.prijmout_kamion_action(admin_obj, req, Kamion.objects.filter(id=self.kamion_prijem.id))
        self.assertIsNone(resp)
        b.refresh_from_db()
        self.assertEqual(b.stav_bedny, StavBednyChoice.PRIJATO)

    def test_prijmout_kamion_action_validation_error(self):
        admin_obj = self._messaging_admin()
        # vytvoří NEPRIJATO bednu bez hmotnosti/tary/mnozstvi (validní pro NEPRIJATO, neprojde validací při přechodu)
        b = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=None,
            tara=None,
            mnozstvi=None,
            stav_bedny=StavBednyChoice.NEPRIJATO,
        )
        req = self.get_request('post')
        resp = actions.prijmout_kamion_action(admin_obj, req, Kamion.objects.filter(id=self.kamion_prijem.id))
        self.assertIsNone(resp)
        msgs = self._messages_texts(req)
        self.assertTrue(any('neprošla validací' in m for m in msgs))
        b.refresh_from_db()
        self.assertEqual(b.stav_bedny, StavBednyChoice.NEPRIJATO)

    def test_oznacit_k_expedici_action_invalid_conditions(self):
        admin_obj = self._messaging_admin()
        # nastaví stav tak, aby nesplňoval podmínku rovnání
        self.bedna.stav_bedny = StavBednyChoice.NAVEZENO
        self.bedna.rovnat = RovnaniChoice.NEZADANO
        self.bedna.tryskat = TryskaniChoice.CISTA
        self.bedna.save()
        req = self.get_request('post')
        resp = actions.oznacit_k_expedici_action(admin_obj, req, Bedna.objects.filter(id=self.bedna.id))
        self.assertIsNone(resp)
        msgs = self._messages_texts(req)
        self.assertTrue(any("'K expedici'" in m for m in msgs))

    def test_oznacit_k_expedici_action_success(self):
        admin_obj = self._messaging_admin()
        # splní podmínky: stav v rozpracovanosti + rovnání a tryskání v povolených hodnotách
        self.bedna.stav_bedny = StavBednyChoice.ZKONTROLOVANO
        self.bedna.rovnat = RovnaniChoice.ROVNA
        self.bedna.tryskat = TryskaniChoice.CISTA
        self.bedna.save()
        req = self.get_request('post')
        resp = actions.oznacit_k_expedici_action(admin_obj, req, Bedna.objects.filter(id=self.bedna.id))
        self.assertIsNone(resp)
        self.bedna.refresh_from_db()
        self.assertEqual(self.bedna.stav_bedny, StavBednyChoice.K_EXPEDICI)