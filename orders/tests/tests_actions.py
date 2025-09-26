from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.admin.sites import AdminSite
from django.http import HttpResponse

from decimal import Decimal
from unittest.mock import patch
from datetime import date

from orders.models import (
    Zakaznik, Kamion, Zakazka, Bedna, Predpis, TypHlavy,
    Odberatel, Pozice
)
from orders.choices import KamionChoice, StavBednyChoice
from orders import actions


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
        cls.bedna = Bedna.objects.create(zakazka=cls.zakazka, hmotnost=Decimal(1), tara=Decimal(1), mnozstvi=1)

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
                                          'orders/karta_bedny_eur.html', 'karty_beden.pdf')
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
        Bedna.objects.create(zakazka=self.zakazka, hmotnost=Decimal(2), tara=Decimal(1), mnozstvi=1)
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
        # Vytvoří platný formset POST
        from django.contrib import admin as dj_admin
        data = {
            'apply': '1',
            # management form
            'ozn-TOTAL_FORMS': str(qs.count()),
            'ozn-INITIAL_FORMS': str(qs.count()),
            'ozn-MIN_NUM_FORMS': '0',
            'ozn-MAX_NUM_FORMS': '1000',
        }
        for i, b in enumerate(qs):
            data[f'ozn-{i}-bedna_id'] = str(b.id)
            data[f'ozn-{i}-pozice'] = str(self.pozice_A.id)
            data[f'ozn-{i}-poznamka_k_navezeni'] = 'pozn'
        # Označení vybraných ID pomocí názvu zaškrtávacího políčka akce
        for b in qs:
            data.setdefault(dj_admin.helpers.ACTION_CHECKBOX_NAME, [])
            data[dj_admin.helpers.ACTION_CHECKBOX_NAME].append(str(b.id))

        req = self.get_request('post', data)
        resp = actions.oznacit_k_navezeni_action(admin_obj, req, qs)
        self.assertIsNone(resp)
        # Ověření aktualizací
        for b in qs:
            b.refresh_from_db()
            self.assertEqual(b.stav_bedny, StavBednyChoice.K_NAVEZENI)
            self.assertEqual(b.pozice_id, self.pozice_A.id)
            self.assertEqual(b.poznamka_k_navezeni, 'pozn')

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