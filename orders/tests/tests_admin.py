from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.urls import reverse

from decimal import Decimal
from datetime import date, time
from django.utils import timezone
from unittest.mock import patch
from types import SimpleNamespace

from orders.admin import KamionAdmin, ZakazkaAdmin, BednaAdmin, BednaInline, NotificationAdmin, SarzeAdmin, SarzeKrokAdmin, SarzeKrokBednaAdmin, SarzeKrokBednaInline, SarzeKrokInline, PredpisAdmin, CenaAdmin
from orders.actions import vytvorit_dalsi_krok_sarze_action, vytvorit_novy_krok_z_kroku_sarze_action
from orders.forms import ImportZakazekForm
from orders.models import Zakaznik, Kamion, Zakazka, Bedna, Predpis, TypHlavy, Odberatel, Cena, Notification, PriorityNotificationRecipient, Zarizeni, Sarze, SarzeKrok, SarzeKrokBedna
from orders.choices import StavBednyChoice, SklademZakazkyChoice, PrijemVydejChoice, KamionChoice, ZinkovaniChoice, PrioritaChoice
from orders.filters import DelkaFilter


class DummySession(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.modified = False


class AdminBase(TestCase):
    """
    Základní třída pro testy admin rozhraní.
    Obsahuje společné metody a nastavení pro testy admin tříd.
    """
    @classmethod
    def setUpTestData(cls):
        cls.factory = RequestFactory()
        User = get_user_model()
        cls.user = User.objects.create_superuser('admin', 'a@example.com', 'pass')
        cls.site = AdminSite()
        cls.zakaznik = Zakaznik.objects.create(
            nazev='Test', zkraceny_nazev='T', zkratka='EUR', ciselna_rada=100000
        )
        cls.kamion = Kamion.objects.create(zakaznik=cls.zakaznik, datum=date.today())
        cls.predpis = Predpis.objects.create(nazev='Test Predpis', skupina=1, zakaznik=cls.zakaznik,)
        cls.typ_hlavy = TypHlavy.objects.create(nazev='SK', popis='Zápustná hlava')

    def with_session_and_messages(self, request):
        request.session = DummySession()
        request._messages = FallbackStorage(request)
        return request


class KamionAdminTests(AdminBase):
    """
    Testy pro KamionAdmin třídu.
    Testuje metody pro získání inlinů, polí a readonly polí.
    """
    def setUp(self):
        self.admin = KamionAdmin(Kamion, self.site)

    def get_request(self, method='get', path='/', data=None, **extra):
        req = getattr(self.factory, method)(path, data=data or {}, **extra)
        req.user = self.user
        return self.with_session_and_messages(req)

    def _create_vydej_kamion_with_order(self):
        kamion_vydej = Kamion.objects.create(
            zakaznik=self.zakaznik,
            datum=date.today(),
            prijem_vydej=KamionChoice.VYDEJ,
        )
        zakazka = Zakazka.objects.create(
            kamion_prijem=self.kamion,
            kamion_vydej=kamion_vydej,
            artikl='ART1',
            prumer=Decimal('10.0'),
            delka=Decimal('50.0'),
            predpis=self.predpis,
            typ_hlavy=self.typ_hlavy,
            popis='Test zakázka',
        )
        return kamion_vydej, zakazka

    def test_get_inlines(self):
        add_inlines = self.admin.get_inlines(self.get_request(), None)
        self.assertEqual(add_inlines, [])
        
        self.kamion.prijem_vydej = 'P'        
        add_inlines = self.admin.get_inlines(self.get_request(), self.kamion)
        self.assertEqual(add_inlines[0].__name__, 'ZakazkaAutomatizovanyPrijemInline')

        zakazka = Zakazka.objects.create(
            kamion_prijem=self.kamion,
            artikl='A1',
            prumer=10,
            delka=200,
            predpis=self.predpis,
            typ_hlavy=self.typ_hlavy,
            popis='Test Zakázka',
        )
        inlines = self.admin.get_inlines(self.get_request(), self.kamion)
        self.assertEqual(inlines[0].__name__, 'ZakazkaKamionPrijemInline')

        self.kamion.prijem_vydej = 'V'
        inlines = self.admin.get_inlines(self.get_request(), self.kamion)
        self.assertEqual(inlines[0].__name__, 'ZakazkaKamionVydejInline')

    def test_get_fields_and_readonly(self):
        fields_add = self.admin.get_fields(self.get_request(), None)
        self.assertNotIn('prijem_vydej', fields_add)
        self.assertNotIn('odberatel', fields_add)

        self.kamion.prijem_vydej = 'P'
        fields_edit = self.admin.get_fields(self.get_request(), self.kamion)
        self.assertNotIn('odberatel', fields_edit)
        self.assertIn('prijem_vydej', fields_edit)

        self.kamion.prijem_vydej = 'V'
        fields_edit = self.admin.get_fields(self.get_request(), self.kamion)
        self.assertIn('odberatel', fields_edit)

        rof_add = self.admin.get_readonly_fields(self.get_request(), None)
        self.assertEqual(rof_add, ['prijem_vydej', 'poradove_cislo', 'get_struktura_kamionu'])
        rof_edit = self.admin.get_readonly_fields(self.get_request(), self.kamion)
        self.assertIn('zakaznik', rof_edit)

    def test_import_view_valid_and_invalid(self):
        url = f'/admin/orders/kamion/import-zakazek/?kamion={self.kamion.pk}'
        get_req = self.get_request('get', path=url)
        resp = self.admin.import_view(get_req)
        self.assertEqual(resp.status_code, 200)

        post_req = self.get_request('post', data={}, path=url)
        resp = self.admin.import_view(post_req)
        self.assertEqual(resp.status_code, 200)

        # Prepare required objects for a successful import
        predpis_import = Predpis.objects.create(
            nazev='00123_Ø10', skupina=1, zakaznik=self.zakaznik
        )
        typ_hlavy_import = TypHlavy.objects.create(nazev='TK', popis='Test')

        predpis_column_name = 'n. Zg. / \n' 'as drg'
        df_data = {
            'Abhol- datum': ['2024-01-01', '2024-01-01'],
            'Unnamed: 7': ['10 x 50', '10 x 50'],
            'Bezeichnung': ['desc 1', 'desc 2'],
            'Sonder / Zusatzinfo': ['', ''],
            'Artikel- nummer': ['A1', 'A1'],
            predpis_column_name: ['123', '123'],
            'Material- charge': ['M1', 'M2'],
            'Material': ['steel', 'steel'],
            'Ober- fläche': ['ZP', 'ZP'],
            'Gewicht in kg': [1, 1],
            'Gew.': [1, 1],
            'Tara kg': [1, 1],
            'Behälter-Nr.:': [1, 2],
            'Lief.': ['L1', 'L1'],
            'Fertigungs- auftrags Nr.': ['F1', 'F2'],
            'Unnamed: 6': ['TK', 'TK'],
        }
        import pandas as pandas_mod
        df = pandas_mod.DataFrame(df_data)
        file_mock = SimpleUploadedFile('f.xlsx', b'fakecontent', content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        valid_req = self.get_request('post', data={'file': file_mock}, path=url)
        valid_req.FILES['file'] = file_mock

        # Mockni _messages storage
        valid_req.session = DummySession()
        valid_req._messages = FallbackStorage(valid_req)

        self.assertTrue(ImportZakazekForm(valid_req.POST, valid_req.FILES).is_valid())

        with patch.object(self.admin, '_render_import', wraps=self.admin._render_import) as render_mock, patch('orders.admin.pd.read_excel', side_effect=lambda *args, **kwargs: df.copy()):
            zak_before = Zakazka.objects.count()
            bedna_before = Bedna.objects.count()
            preview_resp = self.admin.import_view(valid_req)

        self.assertEqual(preview_resp.status_code, 200)
        tmp_token = next(iter(valid_req.session.get('import_tmp_files', {})), None)
        self.assertTrue(tmp_token)

        import_req = self.get_request('post', data={'tmp_token': tmp_token}, path=url)
        import_req.session = valid_req.session
        import_req._messages = FallbackStorage(import_req)

        with patch('orders.admin.pd.read_excel', side_effect=lambda *args, **kwargs: df.copy()):
            resp = self.admin.import_view(import_req)

        if resp.status_code != 302:
            context = getattr(resp, 'context_data', {}) or {}
            form_errors = context.get('form').errors if context.get('form') else {}
            delta_zak = Zakazka.objects.count() - zak_before
            delta_bedna = Bedna.objects.count() - bedna_before
            self.fail(
                "Import neprovedl redirect (status {status}); chyby: {errors}; form_errors: {form_errors}; "
                "delta_zak: {delta_zak}; delta_bedna: {delta_bedna}".format(
                    status=resp.status_code,
                    errors=context.get('errors'),
                    form_errors=form_errors,
                    delta_zak=delta_zak,
                    delta_bedna=delta_bedna,
                )
            )
        self.assertEqual(Zakazka.objects.count(), zak_before + 2)
        self.assertEqual(Bedna.objects.count(), bedna_before + 2)

        # cleanup created objects
        Zakazka.objects.all().delete()
        Bedna.objects.all().delete()
        predpis_import.delete()

    def test_import_view_eur_prefers_active_predpis_when_duplicate_name(self):
        url = f'/admin/orders/kamion/import-zakazek/?kamion={self.kamion.pk}'

        predpis_name = '00123_Ø10'
        inactive_predpis = Predpis.objects.create(
            nazev=predpis_name,
            skupina=1,
            zakaznik=self.zakaznik,
            aktivni=False,
        )
        active_predpis = Predpis.objects.create(
            nazev=predpis_name,
            skupina=1,
            zakaznik=self.zakaznik,
            aktivni=True,
        )
        TypHlavy.objects.create(nazev='TK', popis='Test')

        predpis_column_name = 'n. Zg. / \n' 'as drg'
        df_data = {
            'Abhol- datum': ['2024-01-01'],
            'Unnamed: 7': ['10 x 50'],
            'Bezeichnung': ['desc 1'],
            'Sonder / Zusatzinfo': [''],
            'Artikel- nummer': ['A1'],
            predpis_column_name: ['123'],
            'Material- charge': ['M1'],
            'Material': ['steel'],
            'Ober- fläche': ['ZP'],
            'Gewicht in kg': [1],
            'Gew.': [1],
            'Tara kg': [1],
            'Behälter-Nr.:': [1],
            'Lief.': ['L1'],
            'Fertigungs- auftrags Nr.': ['F1'],
            'Unnamed: 6': ['TK'],
        }

        import pandas as pandas_mod
        df = pandas_mod.DataFrame(df_data)
        file_mock = SimpleUploadedFile('f.xlsx', b'fakecontent', content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        preview_req = self.get_request('post', data={'file': file_mock}, path=url)
        preview_req.FILES['file'] = file_mock
        preview_req.session = DummySession()
        preview_req._messages = FallbackStorage(preview_req)

        with patch.object(self.admin, '_render_import', wraps=self.admin._render_import), patch('orders.admin.pd.read_excel', side_effect=lambda *args, **kwargs: df.copy()):
            preview_resp = self.admin.import_view(preview_req)

        self.assertEqual(preview_resp.status_code, 200)
        tmp_token = next(iter(preview_req.session.get('import_tmp_files', {})), None)
        self.assertTrue(tmp_token)

        import_req = self.get_request('post', data={'tmp_token': tmp_token}, path=url)
        import_req.session = preview_req.session
        import_req._messages = FallbackStorage(import_req)

        with patch('orders.admin.pd.read_excel', side_effect=lambda *args, **kwargs: df.copy()):
            resp = self.admin.import_view(import_req)

        self.assertEqual(resp.status_code, 302)
        created_zakazka = Zakazka.objects.filter(artikl='A1', kamion_prijem=self.kamion).latest('id')
        self.assertEqual(created_zakazka.predpis_id, active_predpis.id)
        self.assertNotEqual(created_zakazka.predpis_id, inactive_predpis.id)
 
    def test_import_view_eur_same_artikl_sarze_diff_surface_creates_new_order(self):
        url = f'/admin/orders/kamion/import-zakazek/?kamion={self.kamion.pk}'

        # Prepare required objects for a successful import
        predpis_import = Predpis.objects.create(
            nazev='00123_Ø10', skupina=1, zakaznik=self.zakaznik
        )
        typ_hlavy_import = TypHlavy.objects.create(nazev='TK', popis='Test')

        predpis_column_name = 'n. Zg. / \n' 'as drg'
        df_data = {
            'Abhol- datum': ['2024-01-01', '2024-01-01'],
            'Unnamed: 7': ['10 x 50', '10 x 50'],
            'Bezeichnung': ['desc 1', 'desc 2'],
            'Sonder / Zusatzinfo': ['', ''],
            'Artikel- nummer': ['A1', 'A1'],
            predpis_column_name: ['123', '123'],
            'Material- charge': ['M1', 'M1'],
            'Material': ['steel', 'steel'],
            'Ober- fläche': ['ZP', 'ZN'],
            'Be-schich-tung': ['L1', 'L2'],
            'Gewicht in kg': [1, 1],
            'Gew.': [1, 1],
            'Tara kg': [1, 1],
            'Behälter-Nr.:': [1, 2],
            'Lief.': ['L1', 'L1'],
            'Fertigungs- auftrags Nr.': ['F1', 'F2'],
            'Unnamed: 6': ['TK', 'TK'],
        }
        import pandas as pandas_mod
        df = pandas_mod.DataFrame(df_data)
        file_mock = SimpleUploadedFile('f.xlsx', b'fakecontent', content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        valid_req = self.get_request('post', data={'file': file_mock}, path=url)
        valid_req.FILES['file'] = file_mock

        # Mockni _messages storage
        valid_req.session = DummySession()
        valid_req._messages = FallbackStorage(valid_req)

        self.assertTrue(ImportZakazekForm(valid_req.POST, valid_req.FILES).is_valid())

        with patch.object(self.admin, '_render_import', wraps=self.admin._render_import) as render_mock, patch('orders.admin.pd.read_excel', side_effect=lambda *args, **kwargs: df.copy()):
            zak_before = Zakazka.objects.count()
            bedna_before = Bedna.objects.count()
            preview_resp = self.admin.import_view(valid_req)

        self.assertEqual(preview_resp.status_code, 200)
        tmp_token = next(iter(valid_req.session.get('import_tmp_files', {})), None)
        self.assertTrue(tmp_token)

        import_req = self.get_request('post', data={'tmp_token': tmp_token}, path=url)
        import_req.session = valid_req.session
        import_req._messages = FallbackStorage(import_req)

        with patch('orders.admin.pd.read_excel', side_effect=lambda *args, **kwargs: df.copy()):
            resp = self.admin.import_view(import_req)

        if resp.status_code != 302:
            context = getattr(resp, 'context_data', {}) or {}
            form_errors = context.get('form').errors if context.get('form') else {}
            delta_zak = Zakazka.objects.count() - zak_before
            delta_bedna = Bedna.objects.count() - bedna_before
            self.fail(
                "Import neprovedl redirect (status {status}); chyby: {errors}; form_errors: {form_errors}; "
                "delta_zak: {delta_zak}; delta_bedna: {delta_bedna}".format(
                    status=resp.status_code,
                    errors=context.get('errors'),
                    form_errors=form_errors,
                    delta_zak=delta_zak,
                    delta_bedna=delta_bedna,
                )
            )
        self.assertEqual(Zakazka.objects.count(), zak_before + 2)
        self.assertEqual(Bedna.objects.count(), bedna_before + 2)

        # cleanup created objects
        Zakazka.objects.all().delete()
        Bedna.objects.all().delete()
        predpis_import.delete()
        typ_hlavy_import.delete()

    def test_import_view_spx_strategy(self):
        spx = Zakaznik.objects.create(
            nazev='SPX',
            zkraceny_nazev='SPX',
            zkratka='SPX',
            ciselna_rada=300000,
        )
        kamion_spx = Kamion.objects.create(zakaznik=spx, datum=date.today())
        Predpis.objects.create(nazev='SPAX-3 Ø6_SK', skupina=1, zakaznik=spx)
        Predpis.objects.create(nazev='SPAX-3 Ø5_SK', skupina=1, zakaznik=spx)

        url = f'/admin/orders/kamion/import-zakazek/?kamion={kamion_spx.pk}'
        file_mock = SimpleUploadedFile('spx.xlsx', b'fakecontent', content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        valid_req = self.get_request('post', data={'file': file_mock}, path=url)
        valid_req.FILES['file'] = file_mock
        valid_req.session = DummySession()
        valid_req._messages = FallbackStorage(valid_req)

        import pandas as pandas_mod
        df = pandas_mod.DataFrame([
            {
                'Bestellnr.': 'WO-1',
                'Material': 'SPX-1',
                'Kurztext': 'SPAX-3 SMK vrut',
                'Menge': '12',
                'ME Gewicht': '24,0',
                'GE': '30,0',
            },
            {
                'Bestellnr.': 'SARZE-A',
                'Material': 'SPX-1',
                'Kurztext': '6,0*160,0',
                'Menge': '',
                'ME Gewicht': '',
                'GE': '',
            },
            {
                'Bestellnr.': 'WO-1',
                'Material': 'SPX-1',
                'Kurztext': 'SPAX-3 SMK vrut 2',
                'Menge': '6',
                'ME Gewicht': '12,0',
                'GE': '15,0',
            },
            {
                'Bestellnr.': 'SARZE-B',
                'Material': 'SPX-1',
                'Kurztext': '5,0*120,0',
                'Menge': '',
                'ME Gewicht': '',
                'GE': '',
            },
        ])

        with patch.object(self.admin, '_render_import', wraps=self.admin._render_import) as render_mock, patch('orders.admin.pd.read_excel', side_effect=lambda *args, **kwargs: df.copy()):
            zak_before = Zakazka.objects.count()
            bedna_before = Bedna.objects.count()
            preview_resp = self.admin.import_view(valid_req)

        self.assertEqual(preview_resp.status_code, 200)
        tmp_token = next(iter(valid_req.session.get('import_tmp_files', {})), None)
        self.assertTrue(tmp_token)

        import_req = self.get_request('post', data={'tmp_token': tmp_token}, path=url)
        import_req.session = valid_req.session
        import_req._messages = FallbackStorage(import_req)

        with patch('orders.admin.pd.read_excel', side_effect=lambda *args, **kwargs: df.copy()):
            resp = self.admin.import_view(import_req)

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Zakazka.objects.count(), zak_before + 2)
        self.assertEqual(Bedna.objects.count(), bedna_before + 2)
        self.assertCountEqual(
            list(Bedna.objects.values_list('sarze', flat=True)),
            ['SARZE-A', 'SARZE-B'],
        )

    def test_import_view_spx_groups_orders_by_artikl_and_sarze(self):
        spx = Zakaznik.objects.create(
            nazev='SPX',
            zkraceny_nazev='SPX',
            zkratka='SPX',
            ciselna_rada=300000,
        )
        kamion_spx = Kamion.objects.create(zakaznik=spx, datum=date.today())
        Predpis.objects.create(nazev='SPAX-3 Ø6_SK', skupina=1, zakaznik=spx)
        Predpis.objects.create(nazev='SPAX-3 Ø5_SK', skupina=1, zakaznik=spx)

        url = f'/admin/orders/kamion/import-zakazek/?kamion={kamion_spx.pk}'
        file_mock = SimpleUploadedFile('spx.xlsx', b'fakecontent', content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        valid_req = self.get_request('post', data={'file': file_mock}, path=url)
        valid_req.FILES['file'] = file_mock
        valid_req.session = DummySession()
        valid_req._messages = FallbackStorage(valid_req)

        import pandas as pandas_mod
        df = pandas_mod.DataFrame([
            {
                'Bestellnr.': 'WO-1',
                'Material': 'SPX-1',
                'Kurztext': 'SPAX-3 SMK vrut A',
                'Menge': '10',
                'ME Gewicht': '20,0',
                'GE': '25,0',
            },
            {
                'Bestellnr.': 'SARZE-X',
                'Material': 'SPX-1',
                'Kurztext': '6,0*160,0',
                'Menge': '',
                'ME Gewicht': '',
                'GE': '',
            },
            {
                'Bestellnr.': 'WO-2',
                'Material': 'SPX-1',
                'Kurztext': 'SPAX-3 SMK vrut B',
                'Menge': '8',
                'ME Gewicht': '16,0',
                'GE': '20,0',
            },
            {
                'Bestellnr.': 'SARZE-X',
                'Material': 'SPX-1',
                'Kurztext': '6,0*140,0',
                'Menge': '',
                'ME Gewicht': '',
                'GE': '',
            },
            {
                'Bestellnr.': 'WO-3',
                'Material': 'SPX-1',
                'Kurztext': 'SPAX-3 SMK vrut C',
                'Menge': '6',
                'ME Gewicht': '12,0',
                'GE': '15,0',
            },
            {
                'Bestellnr.': 'SARZE-Y',
                'Material': 'SPX-1',
                'Kurztext': '5,0*120,0',
                'Menge': '',
                'ME Gewicht': '',
                'GE': '',
            },
        ])

        with patch.object(self.admin, '_render_import', wraps=self.admin._render_import), patch('orders.admin.pd.read_excel', side_effect=lambda *args, **kwargs: df.copy()):
            zak_before = Zakazka.objects.count()
            bedna_before = Bedna.objects.count()
            preview_resp = self.admin.import_view(valid_req)

        self.assertEqual(preview_resp.status_code, 200)
        tmp_token = next(iter(valid_req.session.get('import_tmp_files', {})), None)
        self.assertTrue(tmp_token)

        import_req = self.get_request('post', data={'tmp_token': tmp_token}, path=url)
        import_req.session = valid_req.session
        import_req._messages = FallbackStorage(import_req)

        with patch('orders.admin.pd.read_excel', side_effect=lambda *args, **kwargs: df.copy()):
            resp = self.admin.import_view(import_req)

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Zakazka.objects.count(), zak_before + 2)
        self.assertEqual(Bedna.objects.count(), bedna_before + 3)
        self.assertCountEqual(
            list(Bedna.objects.values_list('sarze', flat=True)),
            ['SARZE-X', 'SARZE-X', 'SARZE-Y'],
        )

    def test_import_view_spx_keeps_bedny_of_same_order_together(self):
        spx = Zakaznik.objects.create(
            nazev='SPX2',
            zkraceny_nazev='SPX2',
            zkratka='SPX',
            ciselna_rada=300001,
        )
        kamion_spx = Kamion.objects.create(zakaznik=spx, datum=date.today())
        Predpis.objects.create(nazev='SPAX-3 Ø6_SK', skupina=1, zakaznik=spx)

        url = f'/admin/orders/kamion/import-zakazek/?kamion={kamion_spx.pk}'
        file_mock = SimpleUploadedFile('spx_alt.xlsx', b'fakecontent', content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        valid_req = self.get_request('post', data={'file': file_mock}, path=url)
        valid_req.FILES['file'] = file_mock
        valid_req.session = DummySession()
        valid_req._messages = FallbackStorage(valid_req)

        import pandas as pandas_mod
        # Záměrně střídání šarží A, B, A při stejném artiklu/průměru/délce.
        df = pandas_mod.DataFrame([
            {
                'Bestellnr.': 'WO-1',
                'Material': 'SPX-ALT',
                'Kurztext': 'SPAX-3 SMK vrut 1',
                'Menge': '10',
                'ME Gewicht': '20,0',
                'GE': '25,0',
            },
            {
                'Bestellnr.': 'SARZE-A',
                'Material': 'SPX-ALT',
                'Kurztext': '6,0*160,0',
                'Menge': '',
                'ME Gewicht': '',
                'GE': '',
            },
            {
                'Bestellnr.': 'WO-2',
                'Material': 'SPX-ALT',
                'Kurztext': 'SPAX-3 SMK vrut 2',
                'Menge': '8',
                'ME Gewicht': '16,0',
                'GE': '20,0',
            },
            {
                'Bestellnr.': 'SARZE-B',
                'Material': 'SPX-ALT',
                'Kurztext': '6,0*160,0',
                'Menge': '',
                'ME Gewicht': '',
                'GE': '',
            },
            {
                'Bestellnr.': 'WO-3',
                'Material': 'SPX-ALT',
                'Kurztext': 'SPAX-3 SMK vrut 3',
                'Menge': '6',
                'ME Gewicht': '12,0',
                'GE': '15,0',
            },
            {
                'Bestellnr.': 'SARZE-A',
                'Material': 'SPX-ALT',
                'Kurztext': '6,0*160,0',
                'Menge': '',
                'ME Gewicht': '',
                'GE': '',
            },
        ])

        with patch.object(self.admin, '_render_import', wraps=self.admin._render_import), patch('orders.admin.pd.read_excel', side_effect=lambda *args, **kwargs: df.copy()):
            preview_resp = self.admin.import_view(valid_req)

        self.assertEqual(preview_resp.status_code, 200)
        tmp_token = next(iter(valid_req.session.get('import_tmp_files', {})), None)
        self.assertTrue(tmp_token)

        import_req = self.get_request('post', data={'tmp_token': tmp_token}, path=url)
        import_req.session = valid_req.session
        import_req._messages = FallbackStorage(import_req)

        existing_bedna_ids = set(Bedna.objects.values_list('id', flat=True))
        with patch('orders.admin.pd.read_excel', side_effect=lambda *args, **kwargs: df.copy()):
            resp = self.admin.import_view(import_req)

        self.assertEqual(resp.status_code, 302)

        new_bedny = list(
            Bedna.objects.exclude(id__in=existing_bedna_ids)
            .select_related('zakazka')
            .order_by('id')
        )
        self.assertEqual(len(new_bedny), 3)

        zakazka_sequence = [bedna.zakazka_id for bedna in new_bedny]
        # Očekáváme blokové pořadí stejné zakázky: A, A, B (ne A, B, A).
        self.assertEqual(zakazka_sequence[0], zakazka_sequence[1])
        self.assertNotEqual(zakazka_sequence[1], zakazka_sequence[2])

        sarze_sequence = [bedna.sarze for bedna in new_bedny]
        self.assertEqual(sarze_sequence[:2], ['SARZE-A', 'SARZE-A'])
        self.assertEqual(sarze_sequence[2], 'SARZE-B')

    def test_import_view_eur_orders_bedny_sorted_by_numeric_behalter(self):
        url = f'/admin/orders/kamion/import-zakazek/?kamion={self.kamion.pk}'
        file_mock = SimpleUploadedFile('eur.xlsx', b'fake', content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        valid_req = self.get_request('post', data={'file': file_mock}, path=url)
        valid_req.FILES['file'] = file_mock
        valid_req.session = DummySession()
        valid_req._messages = FallbackStorage(valid_req)

        # Předpoklady pro EUR strategii
        predpis_column_name = 'n. Zg. / \n' 'as drg'
        predpis_import = Predpis.objects.create(nazev='00123_Ø10', skupina=1, zakaznik=self.zakaznik)
        TypHlavy.objects.get_or_create(nazev='TK', defaults={'popis': 'Test'})

        import pandas as pandas_mod
        df = pandas_mod.DataFrame({
            'Abhol- datum': ['2024-01-01'] * 5,
            'Unnamed: 7': ['10 x 50'] * 5,
            'Bezeichnung': [f'desc {i}' for i in range(5)],
            'Sonder / Zusatzinfo': [''] * 5,
            'Artikel- nummer': ['A1'] * 5,
            predpis_column_name: ['123'] * 5,
            'Material- charge': ['M1'] * 5,
            'Material': ['steel'] * 5,
            'Ober- fläche': ['ZP'] * 5,
            'Gewicht in kg': [1] * 5,
            'Gew.': [1] * 5,
            'Tara kg': [1] * 5,
            'Behälter-Nr.:': [157, '304-B', '27', '505A', '754'],
            'Lief.': ['L1'] * 5,
            'Fertigungs- auftrags Nr.': [f'F{i}' for i in range(5)],
            'Unnamed: 6': ['TK'] * 5,
        })

        existing_ids = set(Bedna.objects.values_list('id', flat=True))

        with patch.object(self.admin, '_render_import', wraps=self.admin._render_import) as render_mock, patch('orders.admin.pd.read_excel', side_effect=lambda *args, **kwargs: df.copy()):
            resp = self.admin.import_view(valid_req)

        self.assertEqual(resp.status_code, 200)
        tmp_token = next(iter(valid_req.session.get('import_tmp_files', {})), None)
        self.assertTrue(tmp_token)

        import_req = self.get_request('post', data={'tmp_token': tmp_token}, path=url)
        import_req.session = valid_req.session
        import_req._messages = FallbackStorage(import_req)

        with patch('orders.admin.pd.read_excel', side_effect=lambda *args, **kwargs: df.copy()):
            resp = self.admin.import_view(import_req)

        self.assertEqual(resp.status_code, 302)

        new_bedny = list(
            Bedna.objects.exclude(id__in=existing_ids)
            .order_by('id')
            .values_list('behalter_nr', flat=True)
        )
        self.assertEqual(new_bedny, ['27', '157', '304-B', '505A', '754'])

    def test_save_formset_creates_bedny(self):
        admin_form = type('F', (), {'instance': self.kamion})()

        zak = Zakazka(
            artikl='A1', prumer=1, delka=1,
            predpis=self.predpis, typ_hlavy=self.typ_hlavy,
            popis='p'
        )

        class DummyForm:
            def __init__(self):
                self.cleaned_data = {'celkova_hmotnost': 2, 'pocet_beden': 2, 'tara': 1}

        class DummyFormset:
            def __init__(self):
                self.forms = [DummyForm()]
            def save(self, commit=True):
                if commit:
                    return []
                return [zak]

        fs = DummyFormset()
        self.admin.save_formset(self.get_request(), admin_form, fs, False)
        self.assertEqual(Zakazka.objects.count(), 1)
        self.assertEqual(Bedna.objects.count(), 2)

    def test_save_formset_propagates_sarze_to_created_bedny(self):
        admin_form = type('F', (), {'instance': self.kamion})()

        zak = Zakazka(
            artikl='A1', prumer=1, delka=1,
            predpis=self.predpis, typ_hlavy=self.typ_hlavy,
            popis='p'
        )

        class DummyForm:
            def __init__(self):
                self.cleaned_data = {
                    'celkova_hmotnost': 2,
                    'pocet_beden': 2,
                    'tara': 1,
                    'material': '42CrMo4',
                    'sarze': 'S-2026-05',
                }

        class DummyFormset:
            def __init__(self):
                self.forms = [DummyForm()]

            def save(self, commit=True):
                if commit:
                    return []
                return [zak]

        fs = DummyFormset()
        self.admin.save_formset(self.get_request(), admin_form, fs, False)

        self.assertEqual(Bedna.objects.count(), 2)
        self.assertEqual(Bedna.objects.filter(material='42CrMo4').count(), 2)
        self.assertEqual(Bedna.objects.filter(sarze='S-2026-05').count(), 2)

    def test_save_formset_leaves_sarze_null_when_missing_in_form_data(self):
        admin_form = type('F', (), {'instance': self.kamion})()

        zak = Zakazka(
            artikl='A1', prumer=1, delka=1,
            predpis=self.predpis, typ_hlavy=self.typ_hlavy,
            popis='p'
        )

        class DummyForm:
            def __init__(self):
                self.cleaned_data = {
                    'celkova_hmotnost': 2,
                    'pocet_beden': 2,
                    'tara': 1,
                    'material': '42CrMo4',
                }

        class DummyFormset:
            def __init__(self):
                self.forms = [DummyForm()]

            def save(self, commit=True):
                if commit:
                    return []
                return [zak]

        fs = DummyFormset()
        self.admin.save_formset(self.get_request(), admin_form, fs, False)

        self.assertEqual(Bedna.objects.count(), 2)
        self.assertEqual(Bedna.objects.filter(material='42CrMo4').count(), 2)
        self.assertEqual(Bedna.objects.filter(sarze__isnull=True).count(), 2)

    def test_save_formset_change_doesnt_create_bedny(self):
        """
        Testuje, že při změně kamionu se nevytvoří nové bedny.
        Při změně kamionu by se měly pouze aktualizovat existující zakázky a bedny,
        ale neměly by se vytvářet nové záznamy.
        """
        kamion = Kamion.objects.create(zakaznik=self.zakaznik, datum=date.today())
        zakazka = Zakazka.objects.create(
            kamion_prijem=kamion,
            artikl='A1', prumer=1, delka=1,
            predpis=self.predpis, typ_hlavy=self.typ_hlavy,
            popis='p',
        )
        Bedna.objects.create(zakazka=zakazka, hmotnost=Decimal(2), tara=Decimal(1), mnozstvi=1)

        admin_form = type('F', (), {'instance': kamion})()

        class DummyFormset:
            def __init__(self):
                self.instance = kamion
                self.forms = []
                self.saved = False

            def save(self, commit=True):
                self.saved = True
                return []

        fs = DummyFormset()
        self.admin.save_formset(self.get_request(), admin_form, fs, True)
        self.assertTrue(fs.saved)
        self.assertEqual(Bedna.objects.count(), 1)

    def test_zadat_mereni_action_requires_permission(self):
        kamion_vydej, _ = self._create_vydej_kamion_with_order()
        User = get_user_model()
        user = User.objects.create_user('staff_no_perm', 'noperm@example.com', 'pass', is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename='change_kamion'))

        request = self.factory.post('/')
        request.user = user
        request.session = DummySession()
        request._messages = FallbackStorage(request)

        queryset = Kamion.objects.filter(pk=kamion_vydej.pk)
        response = self.admin.zadat_mereni_action(request, queryset)

        self.assertIsNone(response)
        messages = [m.message for m in list(request._messages)]
        self.assertTrue(any("Nemáte oprávnění" in msg for msg in messages))

    def test_zadat_mereni_action_redirects_with_permission(self):
        kamion_vydej, _ = self._create_vydej_kamion_with_order()
        User = get_user_model()
        user = User.objects.create_user('staff_perm', 'perm@example.com', 'pass', is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename='change_kamion'))
        user.user_permissions.add(Permission.objects.get(codename='change_mereni_zakazky'))
        user = User.objects.get(pk=user.pk)

        request = self.factory.post('/')
        request.user = user
        request.session = DummySession()
        request._messages = FallbackStorage(request)

        queryset = Kamion.objects.filter(pk=kamion_vydej.pk)
        response = self.admin.zadat_mereni_action(request, queryset)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('admin:orders_kamion_zadani_mereni', args=[kamion_vydej.pk]))

    def test_get_actions_toggle_measurement_action_by_permission(self):
        User = get_user_model()
        user = User.objects.create_user('actions_user', 'actions@example.com', 'pass', is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename='change_kamion'))

        request = self.factory.get('/')
        request.user = user
        actions_without = self.admin.get_actions(request)
        self.assertNotIn('zadat_mereni_action', actions_without)

        user.user_permissions.add(Permission.objects.get(codename='change_mereni_zakazky'))
        request = self.factory.get('/')
        request.user = User.objects.get(pk=user.pk)
        actions_with = self.admin.get_actions(request)
        self.assertIn('zadat_mereni_action', actions_with)

    def test_get_actions_prijem_neprijaty_keeps_print_card_actions(self):
        request = self.get_request('get', '/', {'prijem_vydej': PrijemVydejChoice.PRIJEM_NEPRIJATY})
        actions_filtered = self.admin.get_actions(request)

        self.assertIn('tisk_karet_beden_kamionu_action', actions_filtered)
        self.assertIn('tisk_karet_bedny_a_kontroly_kamionu_action', actions_filtered)
        self.assertIn('tisk_karet_kontroly_kvality_kamionu_action', actions_filtered)
        self.assertNotIn('import_kamionu_action', actions_filtered)

    def test_get_actions_combined_card_action_matches_bedna_card_visibility(self):
        visible_filters = [None, PrijemVydejChoice.PRIJEM_NEPRIJATY, PrijemVydejChoice.PRIJEM_KOMPLET_PRIJATY]
        hidden_filters = [
            PrijemVydejChoice.PRIJEM_BEZ_ZAKAZEK,
            PrijemVydejChoice.PRIJEM_VYEXPEDOVANY,
            PrijemVydejChoice.VYDEJ,
        ]

        for filter_value in visible_filters:
            data = {} if filter_value is None else {'prijem_vydej': filter_value}
            with self.subTest(filter_value=filter_value):
                actions = self.admin.get_actions(self.get_request('get', '/', data))
                self.assertIn('tisk_karet_beden_kamionu_action', actions)
                self.assertIn('tisk_karet_bedny_a_kontroly_kamionu_action', actions)

        for filter_value in hidden_filters:
            with self.subTest(filter_value=filter_value):
                actions = self.admin.get_actions(self.get_request('get', '/', {'prijem_vydej': filter_value}))
                self.assertNotIn('tisk_karet_beden_kamionu_action', actions)
                self.assertNotIn('tisk_karet_bedny_a_kontroly_kamionu_action', actions)

    def test_get_actions_karta_kontroly_prohybu_visibility_by_kamion_filter(self):
        action_name = 'tisk_karty_kontroly_prohybu_kamionu_action'

        visible_filters = [
            None,
            PrijemVydejChoice.PRIJEM_NEPRIJATY,
            PrijemVydejChoice.PRIJEM_KOMPLET_PRIJATY,
            PrijemVydejChoice.PRIJEM_VYEXPEDOVANY,
        ]
        hidden_filters = [
            PrijemVydejChoice.PRIJEM_BEZ_ZAKAZEK,
            PrijemVydejChoice.VYDEJ,
        ]

        for filter_value in visible_filters:
            data = {} if filter_value is None else {'prijem_vydej': filter_value}
            with self.subTest(filter_value=filter_value):
                request = self.get_request('get', '/', data)
                self.assertIn(action_name, self.admin.get_actions(request))

        for filter_value in hidden_filters:
            with self.subTest(filter_value=filter_value):
                request = self.get_request('get', '/', {'prijem_vydej': filter_value})
                self.assertNotIn(action_name, self.admin.get_actions(request))

    def test_zadani_mereni_view_requires_permission(self):
        kamion_vydej, _ = self._create_vydej_kamion_with_order()
        User = get_user_model()
        user = User.objects.create_user('view_no_perm', 'viewnoperm@example.com', 'pass', is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename='change_kamion'))
        self.client.force_login(user)

        url = reverse('admin:orders_kamion_zadani_mereni', args=[kamion_vydej.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], kamion_vydej.get_admin_url())

    def test_zadani_mereni_view_updates_measurements(self):
        kamion_vydej, zakazka = self._create_vydej_kamion_with_order()
        User = get_user_model()
        user = User.objects.create_user('view_with_perm', 'viewperm@example.com', 'pass', is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename='view_kamion'))
        user.user_permissions.add(Permission.objects.get(codename='change_kamion'))
        user.user_permissions.add(Permission.objects.get(codename='change_mereni_zakazky'))
        self.client.force_login(User.objects.get(pk=user.pk))

        url = reverse('admin:orders_kamion_zadani_mereni', args=[kamion_vydej.pk])
        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, 'form-0-tvrdost_povrchu')

        post_data = {
            'form-TOTAL_FORMS': '1',
            'form-INITIAL_FORMS': '1',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-id': str(zakazka.id),
            'form-0-tvrdost_povrchu': '720 HV',
            'form-0-tvrdost_jadra': '340 HV',
            'form-0-ohyb': 'OK',
            'form-0-krut': 'OK',
            'form-0-hazeni': '0,1 mm',
        }
        response = self.client.post(url, post_data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], kamion_vydej.get_admin_url())

        zakazka.refresh_from_db()
        self.assertEqual(zakazka.tvrdost_povrchu, '720 HV')
        self.assertEqual(zakazka.tvrdost_jadra, '340 HV')
        self.assertEqual(zakazka.ohyb, 'OK')
        self.assertEqual(zakazka.krut, 'OK')
        self.assertEqual(zakazka.hazeni, '0,1 mm')

    def test_get_typ_kamionu_variants(self):
        # Bez zakázek
        self.kamion.prijem_vydej = KamionChoice.PRIJEM
        self.kamion.save()
        self.assertEqual(self.admin.get_typ_kamionu(self.kamion), 'Bez zakázek')

        # Nepřijatý: aspoň jedna bedna NEPRIJATO
        z1 = Zakazka.objects.create(
            kamion_prijem=self.kamion,
            artikl='A2', prumer=1, delka=1,
            predpis=self.predpis, typ_hlavy=self.typ_hlavy, popis='p'
        )
        Bedna.objects.create(zakazka=z1, hmotnost=1, tara=1, mnozstvi=1, stav_bedny=StavBednyChoice.NEPRIJATO)
        self.assertEqual(self.admin.get_typ_kamionu(self.kamion), 'Nepřijatý')

        # Komplet přijatý: žádná NEPRIJATO, aspoň jedna "skladem" (např. PRIJATO)
        z1.bedny.update(stav_bedny=StavBednyChoice.PRIJATO)
        self.assertEqual(self.admin.get_typ_kamionu(self.kamion), 'Komplet přijatý')

        # Vyexpedovaný: všechny zakázky expedovány a všechny bedny ve stavu EXPEDOVANO
        z1.bedny.update(stav_bedny=StavBednyChoice.EXPEDOVANO)
        z1.expedovano = True
        z1.save()
        self.assertEqual(self.admin.get_typ_kamionu(self.kamion), 'Vyexpedovaný')

        # Výdej
        self.kamion.prijem_vydej = KamionChoice.VYDEJ
        self.kamion.save()
        self.assertEqual(self.admin.get_typ_kamionu(self.kamion), 'Výdej')

    def test_kamionadmin_get_list_display_by_filter(self):
        # default: bez filtru – ponechá odberatel a ponechá get_pocet_beden_skladem
        ld_default = self.admin.get_list_display(self.get_request())
        self.assertIn('odberatel', ld_default)
        self.assertIn('get_pocet_beden_skladem', ld_default)

        # Vydej filtr => odstraní get_pocet_beden_skladem a zachová odberatel
        ld_v = self.admin.get_list_display(self.get_request('get', '/', {'prijem_vydej': PrijemVydejChoice.VYDEJ}))
        self.assertIn('odberatel', ld_v)
        self.assertNotIn('get_pocet_beden_skladem', ld_v)

        # Příjem – Nepřijatý: ponechá get_pocet_beden_skladem, odstraní odberatel
        ld_pn = self.admin.get_list_display(self.get_request('get', '/', {'prijem_vydej': PrijemVydejChoice.PRIJEM_NEPRIJATY}))
        self.assertIn('get_pocet_beden_skladem', ld_pn)
        self.assertNotIn('odberatel', ld_pn)

        # Příjem – Komplet přijatý: ponechá get_pocet_beden_skladem, odstraní odberatel
        ld_pk = self.admin.get_list_display(self.get_request('get', '/', {'prijem_vydej': PrijemVydejChoice.PRIJEM_KOMPLET_PRIJATY}))
        self.assertIn('get_pocet_beden_skladem', ld_pk)
        self.assertNotIn('odberatel', ld_pk)

    def test_kamionadmin_delete_permissions_and_bulk(self):
        # Kamion P: blokován, pokud má bedny mimo NEPRIJATO
        kam_p = Kamion.objects.create(zakaznik=self.zakaznik, datum=date.today())
        z = Zakazka.objects.create(kamion_prijem=kam_p, artikl='X', prumer=1, delka=1, predpis=self.predpis, typ_hlavy=self.typ_hlavy, popis='x')
        Bedna.objects.create(zakazka=z, hmotnost=1, tara=1, mnozstvi=1, stav_bedny=StavBednyChoice.PRIJATO)
        req = self.get_request()
        # zapnout messages
        req.session = DummySession()
        req._messages = FallbackStorage(req)
        self.assertFalse(self.admin.has_delete_permission(req, kam_p))

        # Kamion P: povolen, pokud všechny bedny NEPRIJATO
        kam_ok = Kamion.objects.create(zakaznik=self.zakaznik, datum=date.today())
        z_ok = Zakazka.objects.create(kamion_prijem=kam_ok, artikl='Y', prumer=1, delka=1, predpis=self.predpis, typ_hlavy=self.typ_hlavy, popis='y')
        Bedna.objects.create(zakazka=z_ok, hmotnost=1, tara=0, mnozstvi=1, stav_bedny=StavBednyChoice.NEPRIJATO)
        self.assertTrue(self.admin.has_delete_permission(req, kam_ok))

        # Bulk delete: smaže jen povolené, pro blokované vypíše hlášky
        qs = Kamion.objects.filter(id__in=[kam_p.id, kam_ok.id])
        before = Kamion.objects.count()
        self.admin.delete_queryset(req, qs)
        after = Kamion.objects.count()
        self.assertEqual(after, before - 1)


class ZakazkaAdminTests(AdminBase):
    """
    Testy pro ZakazkaAdmin třídu.
    Testuje metody pro získání fieldsets, list_display a form s vlastními volbami.
    """
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.zakazka = Zakazka.objects.create(
            kamion_prijem=cls.kamion,
            artikl='A1', prumer=1, delka=1,
            predpis=cls.predpis, typ_hlavy=cls.typ_hlavy,
            popis='p'
        )
        cls.bedna = Bedna.objects.create(
            zakazka=cls.zakazka,
            hmotnost=Decimal(2),
            tara=Decimal(1),
            mnozstvi=1,
            )

    def setUp(self):
        self.admin = ZakazkaAdmin(Zakazka, self.site)

    def get_request(self, params=None):
        req = self.factory.get('/', params or {})
        req.user = self.user
        return req

    def test_get_fieldsets(self):
        fs_add = self.admin.get_fieldsets(self.get_request(), None)
        self.assertEqual(fs_add[0][0], 'Příjem zakázky na sklad:')

        fs_change = self.admin.get_fieldsets(self.get_request(), self.zakazka)
        self.assertEqual(fs_change[0][0], 'Zakázka skladem:')

    def test_get_list_display(self):
        ld = self.admin.get_list_display(self.get_request())
        self.assertNotIn('kamion_vydej_link', ld)
        ld2 = self.admin.get_list_display(self.get_request({'skladem': SklademZakazkyChoice.EXPEDOVANO}))
        self.assertIn('kamion_vydej_link', ld2)

    def test_has_change_permission_regular_user(self):
        """Uživatel bez práv nesmí měnit expedovanou zakázku."""
        User = get_user_model()
        user = User.objects.create_user('user_z', 'u@example.com', 'pass', is_staff=True)
        change_perm = Permission.objects.get(codename='change_zakazka')
        user.user_permissions.add(change_perm)

        self.zakazka.expedovano = True
        self.zakazka.save()

        req = self.factory.get('/')
        req.user = user

        self.assertFalse(self.admin.has_change_permission(req, self.zakazka))

        user.user_permissions.add(Permission.objects.get(codename='change_expedovana_zakazka'))
        req.user = User.objects.get(pk=req.user.pk)
        self.assertTrue(self.admin.has_change_permission(req, self.zakazka))

    # Zatím byla metoda get_list_editable deaktivována,
    # může se v budoucnu vrátit, proto test ponechávám zakomentovaný.
    # def test_get_list_editable_by_filter(self):
    #     # Bez filtru skladem => priorita je editovatelná
    #     le_default = self.admin.get_list_editable(self.get_request())
    #     self.assertEqual(le_default, ['priorita'])
    #     # Expedováno => nic editovatelného
    #     le_ex = self.admin.get_list_editable(self.get_request({'skladem': SklademZakazkyChoice.EXPEDOVANO}))
    #     self.assertEqual(le_ex, [])

    def test_zakazka_delete_permissions(self):
        # Zakázka s bednou ve stavu PRIJATO – blokováno
        z_block = Zakazka.objects.create(
            kamion_prijem=self.kamion,
            artikl='B1', prumer=1, delka=1,
            predpis=self.predpis, typ_hlavy=self.typ_hlavy, popis='b'
        )
        Bedna.objects.create(zakazka=z_block, hmotnost=1, tara=1, mnozstvi=1, stav_bedny=StavBednyChoice.PRIJATO)
        req = self.get_request()
        req.session = DummySession()
        req._messages = FallbackStorage(req)
        self.assertFalse(self.admin.has_delete_permission(req, z_block))

        # Zakázka s bednou pouze NEPRIJATO – povoleno
        z_ok = Zakazka.objects.create(
            kamion_prijem=self.kamion,
            artikl='B2', prumer=1, delka=1,
            predpis=self.predpis, typ_hlavy=self.typ_hlavy, popis='b2'
        )
        Bedna.objects.create(zakazka=z_ok, hmotnost=1, tara=0, mnozstvi=1, stav_bedny=StavBednyChoice.NEPRIJATO)
        self.assertTrue(self.admin.has_delete_permission(req, z_ok))

        # Hromadné mazání – smaže jen povolené a zapíše hlášky
        before = Zakazka.objects.count()
        self.admin.delete_queryset(req, Zakazka.objects.filter(id__in=[z_block.id, z_ok.id]))
        after = Zakazka.objects.count()
        self.assertEqual(after, before - 1)

    def test_priority_notifications_created_for_recipients(self):
        User = get_user_model()
        user_a = User.objects.create_user('u1', 'u1@example.com', 'pass', is_staff=True)
        user_b = User.objects.create_user('u2', 'u2@example.com', 'pass', is_staff=True)
        group = Group.objects.create(name='Notif')
        group.user_set.add(user_b)

        config = PriorityNotificationRecipient.objects.create(name='Test')
        config.users.add(user_a, self.user)
        config.groups.add(group)

        self.bedna.stav_bedny = StavBednyChoice.K_NAVEZENI
        self.bedna.save(update_fields=['stav_bedny'])

        self.zakazka.priorita = PrioritaChoice.STREDNI
        req = self.get_request()
        req.user = self.user

        self.admin.save_model(req, self.zakazka, form=None, change=True)

        notifications = Notification.objects.filter(zakazka=self.zakazka, bedna=self.bedna)
        self.assertEqual(notifications.count(), 2)
        recipients = set(notifications.values_list('recipient__username', flat=True))
        self.assertEqual(recipients, {'u1', 'u2'})

    def test_priority_notifications_not_created_when_no_bedny_in_state(self):
        User = get_user_model()
        recipient = User.objects.create_user('u3', 'u3@example.com', 'pass', is_staff=True)
        config = PriorityNotificationRecipient.objects.create(name='Test2')
        config.users.add(recipient)

        self.zakazka.priorita = PrioritaChoice.STREDNI
        req = self.get_request()
        req.user = self.user

        self.admin.save_model(req, self.zakazka, form=None, change=True)

        self.assertFalse(Notification.objects.filter(zakazka=self.zakazka).exists())


class BednaAdminTests(AdminBase):
    """
    Testy pro BednaAdmin třídu.
    Testuje metody pro kontrolu oprávnění, zobrazení seznamu a úpravy polí.
    """
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.zakazka = Zakazka.objects.create(
            kamion_prijem=cls.kamion,
            artikl='A1', prumer=1, delka=1,
            predpis=cls.predpis, typ_hlavy=cls.typ_hlavy,
            popis='p'
        )
        cls.bedna = Bedna.objects.create(
            zakazka=cls.zakazka,
            hmotnost=Decimal(2),
            tara=Decimal(1),
            mnozstvi=1,
        )

    def setUp(self):
        self.admin = BednaAdmin(Bedna, self.site)

    def test_media_includes_weight_summary_scripts(self):
        media_js = list(self.admin.media._js)

        self.assertIn('orders/js/bedny_hmotnost_sum.js', media_js)
        self.assertIn('orders/js/bedny_netto_hmotnost_sum.js', media_js)

    def get_request(self, params=None):
        req = self.factory.get('/', params or {})
        req.user = self.user
        return req

    def test_has_change_permission(self):
        perm = self.admin.has_change_permission(self.get_request(), self.bedna)
        self.assertTrue(perm)
        self.bedna.stav_bedny = StavBednyChoice.EXPEDOVANO
        perm = self.admin.has_change_permission(self.get_request(), self.bedna)
        self.assertTrue(perm)

    def test_change_form_shows_bedna_sarze_movement_summary(self):
        zarizeni = Zarizeni.objects.create(
            kod_zarizeni='Z1',
            nazev_zarizeni='Zařízení 1',
            zkraceny_nazev_zarizeni='Z1',
        )
        sarze = Sarze.objects.create(datum_zalozeni=timezone.localdate(), cislo_pripravku=1)
        krok_1 = SarzeKrok.objects.create(
            sarze=sarze,
            zarizeni=zarizeni,
            zacatek=time(6, 0),
            konec=time(7, 0),
            operator='Novak',
        )
        krok_2 = SarzeKrok.objects.create(
            sarze=sarze,
            zarizeni=zarizeni,
            zacatek=time(8, 0),
            konec=time(9, 0),
            operator='Svoboda',
        )
        other_bedna = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal(3),
            tara=Decimal(1),
            mnozstvi=1,
        )
        SarzeKrokBedna.objects.create(krok=krok_1, bedna=self.bedna, patro=1, procent_z_patra=40)
        SarzeKrokBedna.objects.create(krok=krok_1, bedna=other_bedna, patro=1, procent_z_patra=60)
        SarzeKrokBedna.objects.create(krok=krok_2, bedna=self.bedna, patro=2, procent_z_patra=100)

        fieldsets = self.admin.get_fieldsets(self.get_request(), self.bedna)
        html = str(self.admin.get_pohyb_v_sarzich(self.bedna))

        self.assertEqual(fieldsets[-1][0], 'Pohyb v šaržích')
        self.assertIn('get_pohyb_v_sarzich', fieldsets[-1][1]['fields'])
        self.assertIn(str(sarze), html)
        self.assertIn('2 kroků', html)
        self.assertIn('Krok 1', html)
        self.assertIn('Krok 2', html)
        self.assertIn('Patro 1', html)
        self.assertIn('Patro 2', html)
        self.assertIn(str(self.bedna.cislo_bedny), html)
        self.assertIn(str(other_bedna.cislo_bedny), html)
        self.assertIn('40 %', html)
        self.assertIn('60 %', html)
        self.assertIn('100 %', html)

    def test_has_change_permission_regular_user(self):
        """Oprávnění pro expedovanou a pozastavenou bednu."""
        User = get_user_model()
        user = User.objects.create_user('user_b', 'b@example.com', 'pass', is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename='change_bedna'))

        bed_ex = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal(2),
            tara=Decimal(1),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.EXPEDOVANO,
        )

        req = self.factory.get('/')
        req.user = user
        self.assertFalse(self.admin.has_change_permission(req, bed_ex))
        user.user_permissions.add(Permission.objects.get(codename='change_expedovana_bedna'))
        req.user = User.objects.get(pk=req.user.pk)
        self.assertTrue(self.admin.has_change_permission(req, bed_ex))

        bed_poz = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal(2),
            tara=Decimal(1),
            mnozstvi=1,
            pozastaveno=True,
        )
        self.assertFalse(self.admin.has_change_permission(req, bed_poz))
        req.user.user_permissions.add(Permission.objects.get(codename='change_pozastavena_bedna'))
        req.user = User.objects.get(pk=req.user.pk)
        self.assertTrue(self.admin.has_change_permission(req, bed_poz))

    def test_bedna_notif_alert_respects_user(self):
        User = get_user_model()
        current_user = User.objects.create_user('u_current', 'current@example.com', 'pass', is_staff=True)
        other_user = User.objects.create_user('u_other', 'other@example.com', 'pass', is_staff=True)
        self.bedna.stav_bedny = StavBednyChoice.K_NAVEZENI
        self.bedna.save(update_fields=['stav_bedny'])

        Notification.objects.create(
            recipient=other_user,
            zakazka=self.zakazka,
            bedna=self.bedna,
            notif_type=Notification.NotificationType.PRIORITA,
            message='Test jiné uživatele',
        )

        req = self.factory.get('/')
        req.user = current_user
        qs = self.admin.get_queryset(req)
        obj = qs.get(pk=self.bedna.pk)

        html = self.admin.get_notif_alert(obj)
        self.assertEqual('', str(html))

        # pro jiného uživatele se notifikace zobrazí
        req_other = self.factory.get('/')
        req_other.user = other_user
        qs_other = self.admin.get_queryset(req_other)
        obj_other = qs_other.get(pk=self.bedna.pk)
        html_other = self.admin.get_notif_alert(obj_other)
        self.assertIn('Změna priority', str(html_other))

    def test_changelist_view_and_list_display(self):
        req = self.get_request()
        self.admin.changelist_view(req)
        self.assertEqual(
            self.admin.list_editable,
            ['stav_bedny', 'tryskat', 'rovnat', 'hmotnost', 'poznamka']
        )

        req = self.get_request({'stav_bedny': 'EX'})
        self.admin.changelist_view(req)
        self.assertEqual(self.admin.list_editable, [])

        ld = self.admin.get_list_display(self.get_request())
        self.assertNotIn('kamion_vydej_link', ld)
        ld2 = self.admin.get_list_display(self.get_request({'stav_bedny': 'EX'}))
        self.assertIn('kamion_vydej_link', ld2)

    def test_changelist_view_pozastaveno_filter_keeps_editable(self):
        req = self.get_request({'pozastaveno': 'True'})
        self.admin.changelist_view(req)
        self.assertEqual(self.admin.list_editable, [])
        ld = self.admin.get_list_display(req)
        self.assertNotIn('kamion_vydej_link', ld)        

    def test_changelist_view_post_saves_only_changed_forms(self):
        bedna_changed = self.bedna
        bedna_unchanged = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal(3),
            tara=Decimal(1),
            mnozstvi=1,
            poznamka='beze zmeny',
        )

        req = self.factory.post('/', {'form-TOTAL_FORMS': '2', '_save': 'Uložit'})
        req.user = self.user
        req.session = DummySession()
        req._messages = FallbackStorage(req)

        class DummyForm:
            def __init__(self, instance, has_changed, changed_data, cleaned_data, initial):
                self.instance = instance
                self._has_changed = has_changed
                self.changed_data = changed_data
                self.cleaned_data = cleaned_data
                self.initial = initial

            def has_changed(self):
                return self._has_changed

        class DummyFormSet:
            def __init__(self, *args, **kwargs):
                self.forms = [
                    DummyForm(
                        instance=bedna_changed,
                        has_changed=True,
                        changed_data=['poznamka'],
                        cleaned_data={'poznamka': 'nova poznamka'},
                        initial={'poznamka': bedna_changed.poznamka},
                    ),
                    DummyForm(
                        instance=bedna_unchanged,
                        has_changed=False,
                        changed_data=[],
                        cleaned_data={'poznamka': bedna_unchanged.poznamka},
                        initial={'poznamka': bedna_unchanged.poznamka},
                    ),
                ]

            def is_valid(self):
                return True

        with patch.object(self.admin, 'get_changelist_formset', return_value=DummyFormSet):
            response = self.admin.changelist_view(req)

        self.assertEqual(response.status_code, 302)
        bedna_changed.refresh_from_db()
        bedna_unchanged.refresh_from_db()
        self.assertEqual(bedna_changed.poznamka, 'nova poznamka')
        self.assertEqual(bedna_unchanged.poznamka, 'beze zmeny')

    def test_changelist_view_post_conflict_adds_warning_and_saves(self):
        bedna_changed = self.bedna
        bedna_changed.poznamka = 'DB_hodnota'
        bedna_changed.save(update_fields=['poznamka'])

        req = self.factory.post('/', {'form-TOTAL_FORMS': '1', '_save': 'Uložit'})
        req.user = self.user
        req.session = DummySession()
        req._messages = FallbackStorage(req)

        class DummyForm:
            def __init__(self, instance):
                self.instance = instance
                self.changed_data = ['poznamka']
                self.cleaned_data = {'poznamka': 'NOVA'}
                self.initial = {'poznamka': 'INITIAL'}

            def has_changed(self):
                return True

        class DummyFormSet:
            def __init__(self, *args, **kwargs):
                self.forms = [DummyForm(bedna_changed)]

            def is_valid(self):
                return True

        with patch.object(self.admin, 'get_changelist_formset', return_value=DummyFormSet):
            response = self.admin.changelist_view(req)

        self.assertEqual(response.status_code, 302)
        bedna_changed.refresh_from_db()
        self.assertEqual(bedna_changed.poznamka, 'NOVA')

    def test_changelist_view_post_touched_markers_save_only_touched_fields(self):
        bedna_changed = self.bedna
        original_stav = bedna_changed.stav_bedny

        req = self.factory.post(
            '/',
            {
                'form-TOTAL_FORMS': '1',
                '_save': 'Uložit',
                '_touched_enabled': '1',
                '_touched_field': ['form-0-poznamka'],
            },
        )
        req.user = self.user
        req.session = DummySession()
        req._messages = FallbackStorage(req)

        class DummyForm:
            def __init__(self, instance):
                self.instance = instance
                self.prefix = 'form-0'
                self.changed_data = ['poznamka', 'stav_bedny']
                self.cleaned_data = {'poznamka': 'NOVA', 'stav_bedny': StavBednyChoice.EXPEDOVANO}
                self.initial = {'poznamka': instance.poznamka, 'stav_bedny': original_stav}

            def has_changed(self):
                return True

        class DummyFormSet:
            def __init__(self, *args, **kwargs):
                self.forms = [DummyForm(bedna_changed)]

            @staticmethod
            def get_default_prefix():
                return 'form'

            def is_valid(self):
                return True

        with patch.object(self.admin, 'get_changelist_formset', return_value=DummyFormSet):
            response = self.admin.changelist_view(req)

        self.assertEqual(response.status_code, 302)
        bedna_changed.refresh_from_db()
        self.assertEqual(bedna_changed.poznamka, 'NOVA')
        self.assertEqual(bedna_changed.stav_bedny, original_stav)

    def test_changelist_view_post_action_is_not_intercepted_by_custom_save(self):
        req = self.factory.post(
            '/',
            {
                'form-TOTAL_FORMS': '1',
                'index': '0',
                'action': 'export_bedny_to_csv_action',
            },
        )
        req.user = self.user
        req.session = DummySession()
        req._messages = FallbackStorage(req)

        with patch('orders.admin.SimpleHistoryAdmin.changelist_view', return_value=HttpResponse('ok')) as super_changelist:
            response = self.admin.changelist_view(req)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'ok')
        super_changelist.assert_called_once()

    def test_changelist_client_post_stale_untouched_row_does_not_fail_validation(self):
        bedna_touched = self.bedna
        bedna_touched.poznamka = 'puvodni-1'
        bedna_touched.save(update_fields=['poznamka'])

        bedna_untouched = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal(3),
            tara=Decimal(1),
            mnozstvi=1,
            poznamka='puvodni-2',
        )

        self.client.force_login(self.user)
        url = reverse('admin:orders_bedna_changelist')

        ordered = list(Bedna.objects.filter(pk__in=[bedna_touched.pk, bedna_untouched.pk]).order_by('id'))
        self.assertEqual(len(ordered), 2)
        self.assertEqual(ordered[0].pk, bedna_touched.pk)
        self.assertEqual(ordered[1].pk, bedna_untouched.pk)

        post_data = {
            'form-TOTAL_FORMS': '2',
            'form-INITIAL_FORMS': '2',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            '_save': 'Uložit',
            '_touched_enabled': '1',
            '_touched_field': ['form-0-poznamka'],

            'form-0-id': str(bedna_touched.pk),
            'form-0-stav_bedny': bedna_touched.stav_bedny,
            'form-0-tryskat': bedna_touched.tryskat,
            'form-0-rovnat': bedna_touched.rovnat,
            'form-0-hmotnost': str(bedna_touched.hmotnost),
            'form-0-poznamka': 'zmena-zalozka-2',

            'form-1-id': str(bedna_untouched.pk),
            'form-1-stav_bedny': '__INVALID_STALE_CHOICE__',
            'form-1-tryskat': bedna_untouched.tryskat,
            'form-1-rovnat': bedna_untouched.rovnat,
            'form-1-hmotnost': str(bedna_untouched.hmotnost),
            'form-1-poznamka': bedna_untouched.poznamka,
        }

        response = self.client.post(url, post_data)

        self.assertEqual(response.status_code, 302)
        bedna_touched.refresh_from_db()
        bedna_untouched.refresh_from_db()
        self.assertEqual(bedna_touched.poznamka, 'zmena-zalozka-2')
        self.assertEqual(bedna_untouched.poznamka, 'puvodni-2')

    def test_has_change_permission_neprijato_regular_user(self):
        """NEPRIJATO vyžaduje speciální oprávnění."""
        User = get_user_model()
        user = User.objects.create_user('user_bn', 'bn@example.com', 'pass', is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename='change_bedna'))

        bed_np = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal(2),
            tara=Decimal(0),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.NEPRIJATO,
        )

        req = self.factory.get('/')
        req.user = user
        self.assertFalse(self.admin.has_change_permission(req, bed_np))
        user.user_permissions.add(Permission.objects.get(codename='change_neprijata_bedna'))
        req.user = User.objects.get(pk=req.user.pk)
        self.assertTrue(self.admin.has_change_permission(req, bed_np))

    def test_has_change_permission_neprijato_poznamka_only(self):
        """Uživatel s oprávněním pro poznámku může měnit NEPRIJATO omezeně."""
        User = get_user_model()
        user = User.objects.create_user('user_bn2', 'bn2@example.com', 'pass', is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename='change_bedna'))

        bed_np = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal(2),
            tara=Decimal(0),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.NEPRIJATO,
        )

        req = self.factory.get('/')
        req.user = user
        self.assertFalse(self.admin.has_change_permission(req, bed_np))
        user.user_permissions.add(Permission.objects.get(codename='change_poznamka_neprijata_bedna'))
        req.user = User.objects.get(pk=req.user.pk)
        self.assertTrue(self.admin.has_change_permission(req, bed_np))

    def test_get_list_editable_neprijato_requires_perm(self):
        # Bez oprávnění – prázdné
        req = self.get_request({'stav_bedny': StavBednyChoice.NEPRIJATO})
        req.user = get_user_model().objects.create_user('user_le', 'le@example.com', 'pass', is_staff=True)
        self.assertEqual(self.admin.get_list_editable(req), [])
        # Jen oprávnění pro poznámku – pouze poznamka
        req_note = self.get_request({'stav_bedny': StavBednyChoice.NEPRIJATO})
        req_note.user = get_user_model().objects.create_user('user_len', 'len@example.com', 'pass', is_staff=True)
        req_note.user.user_permissions.add(Permission.objects.get(codename='change_poznamka_neprijata_bedna'))
        req_note.user = get_user_model().objects.get(pk=req_note.user.pk)
        self.assertEqual(self.admin.get_list_editable(req_note), ['poznamka'])
        # S oprávněním – defaultní sada, přidán i mnozstvi, pokud je stav bedny NEPRIJATO
        req.user.user_permissions.add(Permission.objects.get(codename='change_neprijata_bedna'))
        req.user = get_user_model().objects.get(pk=req.user.pk)
        editable = self.admin.get_list_editable(req)
        self.assertEqual(editable, ['stav_bedny', 'tryskat', 'rovnat', 'zinkovat', 'hmotnost', 'tara', 'poznamka', 'mnozstvi'])

    def test_get_actions_filters_zinkovani_by_filter(self):
        def _actions_for(value):
            req = self.get_request({'zinkovani': value})
            req.user = self.user
            return self.admin.get_actions(req)

        actions_nezadano = _actions_for(ZinkovaniChoice.NEZADANO)
        self.assertIn('oznacit_k_zinkovani_action', actions_nezadano)
        self.assertNotIn('odeslat_na_zinkovani_action', actions_nezadano)
        self.assertNotIn('export_na_zinkovani_action', actions_nezadano)
        self.assertNotIn('oznacit_po_zinkovani_action', actions_nezadano)
        self.assertNotIn('oznacit_uvolneno_action', actions_nezadano)

        actions_kz = _actions_for(ZinkovaniChoice.ZINKOVAT)
        self.assertIn('odeslat_na_zinkovani_action', actions_kz)
        self.assertNotIn('oznacit_k_zinkovani_action', actions_kz)
        self.assertNotIn('export_na_zinkovani_action', actions_kz)

        actions_nz = _actions_for(ZinkovaniChoice.V_ZINKOVNE)
        self.assertIn('export_na_zinkovani_action', actions_nz)
        self.assertIn('oznacit_po_zinkovani_action', actions_nz)
        self.assertIn('oznacit_uvolneno_action', actions_nz)

        actions_pz = _actions_for(ZinkovaniChoice.POZINKOVANO)
        self.assertIn('oznacit_uvolneno_action', actions_pz)
        self.assertNotIn('export_na_zinkovani_action', actions_pz)

    def test_get_actions_filters_prijato_do_zakaleno_by_stav(self):
        req_prijato = self.get_request({'stav_bedny': StavBednyChoice.PRIJATO})
        req_prijato.user = self.user
        actions_prijato = self.admin.get_actions(req_prijato)
        self.assertIn('oznacit_prijato_do_zakaleno_action', actions_prijato)

        req_jiny = self.get_request({'stav_bedny': StavBednyChoice.K_NAVEZENI})
        req_jiny.user = self.user
        actions_jiny = self.admin.get_actions(req_jiny)
        self.assertNotIn('oznacit_prijato_do_zakaleno_action', actions_jiny)

    def test_get_actions_prijato_do_zakaleno_requires_custom_permission(self):
        User = get_user_model()
        user = User.objects.create_user('user_mark_zak', 'markz@example.com', 'pass', is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename='change_bedna'))

        req = self.factory.get('/', {'stav_bedny': StavBednyChoice.PRIJATO})
        req.user = user
        actions_without = self.admin.get_actions(req)
        self.assertNotIn('oznacit_prijato_do_zakaleno_action', actions_without)

        user.user_permissions.add(Permission.objects.get(codename='mark_bedna_zakaleno'))
        req.user = User.objects.get(pk=user.pk)
        actions_with = self.admin.get_actions(req)
        self.assertIn('oznacit_prijato_do_zakaleno_action', actions_with)

    def test_has_mark_bedna_zakaleno_permission(self):
        User = get_user_model()
        user = User.objects.create_user('user_perm_zak', 'permzak@example.com', 'pass', is_staff=True)
        req = self.factory.get('/')
        req.user = user

        self.assertFalse(self.admin.has_mark_bedna_zakaleno_permission(req))

        user.user_permissions.add(Permission.objects.get(codename='mark_bedna_zakaleno'))
        req.user = User.objects.get(pk=user.pk)
        self.assertTrue(self.admin.has_mark_bedna_zakaleno_permission(req))

    def test_has_change_pozastavena_bedna_permission(self):
        User = get_user_model()
        user = User.objects.create_user('user_perm_pause', 'pauseperm@example.com', 'pass', is_staff=True)
        req = self.factory.get('/')
        req.user = user

        self.assertFalse(self.admin.has_change_pozastavena_bedna_permission(req))

        user.user_permissions.add(Permission.objects.get(codename='change_pozastavena_bedna'))
        req.user = User.objects.get(pk=user.pk)
        self.assertTrue(self.admin.has_change_pozastavena_bedna_permission(req))

    def test_get_actions_uvolnit_pozastavene_visibility_with_permission(self):
        User = get_user_model()
        user = User.objects.create_user('user_uvolnit', 'uvolnit@example.com', 'pass', is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename='change_bedna'))
        user.user_permissions.add(Permission.objects.get(codename='change_pozastavena_bedna'))
        user = User.objects.get(pk=user.pk)

        req_no_filter = self.factory.get('/')
        req_no_filter.user = user
        actions_no_filter = self.admin.get_actions(req_no_filter)
        self.assertIn('uvolnit_pozastavene_bedny_action', actions_no_filter)

        req_ex = self.factory.get('/', {'stav_bedny': StavBednyChoice.EXPEDOVANO})
        req_ex.user = user
        actions_ex = self.admin.get_actions(req_ex)
        self.assertNotIn('uvolnit_pozastavene_bedny_action', actions_ex)

        req_pr = self.factory.get('/', {'stav_bedny': StavBednyChoice.PRIJATO})
        req_pr.user = user
        actions_pr = self.admin.get_actions(req_pr)
        self.assertIn('uvolnit_pozastavene_bedny_action', actions_pr)

    def test_get_actions_uvolnit_pozastavene_hidden_without_permission(self):
        User = get_user_model()
        user = User.objects.create_user('user_no_uvolnit', 'nouvolnit@example.com', 'pass', is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename='change_bedna'))

        req = self.factory.get('/', {'stav_bedny': StavBednyChoice.PRIJATO})
        req.user = user
        actions = self.admin.get_actions(req)
        self.assertNotIn('uvolnit_pozastavene_bedny_action', actions)

    def test_get_readonly_fields_neprijato_poznamka_only(self):
        """Při oprávnění jen na poznámku jsou ostatní pole readonly."""
        user = get_user_model().objects.create_user('user_ro', 'ro@example.com', 'pass', is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename='change_bedna'))
        user.user_permissions.add(Permission.objects.get(codename='change_poznamka_neprijata_bedna'))
        req = self.factory.get('/')
        req.user = user

        bed_np = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal(2),
            tara=Decimal(0),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.NEPRIJATO,
        )

        readonly = set(self.admin.get_readonly_fields(req, bed_np))
        all_fields = {f.name for f in Bedna._meta.fields}
        self.assertIn('hmotnost', readonly)
        self.assertIn('tara', readonly)
        self.assertNotIn('poznamka', readonly)
        self.assertTrue(all_fields.issubset(readonly | {'poznamka'}))

    def test_bedna_list_display_pozice_toggle(self):
        # Pro PR, KN, NV je sloupec pozice vidět
        for code in (StavBednyChoice.PRIJATO, StavBednyChoice.K_NAVEZENI, StavBednyChoice.NAVEZENO):
            with self.subTest(stav=code):
                ld = self.admin.get_list_display(self.get_request({'stav_bedny': code}))
                self.assertIn('pozice', ld)
        # Pro jiné stavy není (např. EX)
        ld_ex = self.admin.get_list_display(self.get_request({'stav_bedny': StavBednyChoice.EXPEDOVANO}))
        self.assertNotIn('pozice', ld_ex)
        # A pro EX zůstává kamion_vydej_link
        self.assertIn('kamion_vydej_link', ld_ex)

    def test_bedna_get_list_filter_delka_removed_outside_states(self):
        # delka filter pouze v případě, že je filter stav bedny == PRIJATO
        # v K_NAVEZENI
        lf = self.admin.get_list_filter(self.get_request({'stav_bedny': StavBednyChoice.K_NAVEZENI}))
        self.assertNotIn(DelkaFilter, lf)
        # v NEPRIJATO
        lf2 = self.admin.get_list_filter(self.get_request({'stav_bedny': StavBednyChoice.NEPRIJATO}))
        self.assertNotIn(DelkaFilter, lf2)
        # v PRIJATO
        lf3 = self.admin.get_list_filter(self.get_request({'stav_bedny': StavBednyChoice.PRIJATO}))
        self.assertIn(DelkaFilter, lf3)

    def test_bedna_delete_queryset_only_neprijato(self):
        # Připrav 2 bedny – jedna PRIJATO (blok), jedna NEPRIJATO (povoleno)
        b_block = Bedna.objects.create(
            zakazka=self.zakazka, hmotnost=1, tara=1, mnozstvi=1, stav_bedny=StavBednyChoice.PRIJATO
        )
        b_ok = Bedna.objects.create(
            zakazka=self.zakazka, hmotnost=1, tara=0, mnozstvi=1, stav_bedny=StavBednyChoice.NEPRIJATO
        )
        req = self.get_request()
        req.session = DummySession()
        req._messages = FallbackStorage(req)
        before = Bedna.objects.count()
        self.admin.delete_queryset(req, Bedna.objects.filter(id__in=[b_block.id, b_ok.id]))
        after = Bedna.objects.count()
        self.assertEqual(after, before - 1)

    def test_history_methods_handle_missing_zakazka_reference(self):
        zakazka = Zakazka.objects.create(
            kamion_prijem=self.kamion,
            artikl='H-ORPHAN',
            prumer=Decimal('7.0'),
            delka=Decimal('123.0'),
            predpis=self.predpis,
            typ_hlavy=self.typ_hlavy,
            popis='historie orphan',
        )
        bedna = Bedna.objects.create(
            zakazka=zakazka,
            hmotnost=Decimal('2.0'),
            tara=Decimal('1.0'),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.NEPRIJATO,
        )
        bedna_id = bedna.id

        # Smazání zakázky přes ORM zajistí smazání živé bedny, ale historický záznam bedny zůstane.
        zakazka.delete()

        historical = Bedna.history.model.objects.filter(id=bedna_id).order_by('-history_date', '-history_id').first()
        self.assertIsNotNone(historical)

        self.assertEqual(self.admin.get_prumer(historical), '-')
        self.assertEqual(self.admin.get_delka_int(historical), '-')
        self.assertEqual(self.admin.get_skupina_TZ(historical), '-')
        self.assertEqual(self.admin.get_zakaznik_zkratka(historical), '-')
        self.assertEqual(self.admin.get_odberatel(historical), '-')
        self.assertEqual(self.admin.get_datum_prijem(historical), '-')
        self.assertEqual(self.admin.get_datum_vydej(historical), '-')
        self.assertEqual(self.admin.get_poradi_bedny_v_zakazce(historical), '-')
        self.assertEqual(self.admin.get_zkraceny_popis(historical), '-')
        self.assertEqual(self.admin.kamion_prijem_link(historical), None)
        self.assertEqual(self.admin.kamion_vydej_link(historical), None)
        self.assertEqual(self.admin.get_typ_hlavy(historical), '-')
        self.assertEqual(str(self.admin.get_priorita(historical)), '<span style="color: black;">-</span>')
        self.assertFalse(self.admin.get_celozavit(historical))
        self.assertIsNone(self.admin.zakazka_link(historical))

class BednaInlineGetFieldsTests(AdminBase):
    """
    Testy pro BednaInline.get_fields.
    Testuje, jak se mění pole podle typu zákazníka a stavu bedny.
    """
    def setUp(self):
        self.inline = BednaInline(Zakazka, self.site)

    def get_request(self):
        req = self.factory.get('/')
        req.user = self.user
        return req

    def create_bedna(self, code):
        idx = Zakaznik.objects.count() + 1
        zak = Zakaznik.objects.create(
            nazev=code,
            zkraceny_nazev=code,
            zkratka=code,
            ciselna_rada=100000 + idx,
        )
        kam = Kamion.objects.create(zakaznik=zak, datum=date.today())
        zakazka = Zakazka.objects.create(
            kamion_prijem=kam,
            artikl='A',
            prumer=1,
            delka=1,
            predpis=self.predpis,
            typ_hlavy=self.typ_hlavy,
            popis='p',
        )
        bedna = Bedna.objects.create(zakazka=zakazka, hmotnost=1, tara=1, mnozstvi=1, pozastaveno=True)
        setattr(bedna, 'kamion_prijem', zakazka.kamion_prijem)
        return bedna

    def test_add_view_excludes_cislo_bedny(self):
        fields = self.inline.get_fields(self.get_request(), None)
        self.assertNotIn('cislo_bedny', fields)

    def test_existing_rot_excludes_extra_fields(self):
        bedna = self.create_bedna('ROT')
        fields = self.inline.get_fields(self.get_request(), bedna.zakazka)
        self.assertNotIn('dodatecne_info', fields)
        self.assertNotIn('dodavatel_materialu', fields)
        self.assertNotIn('vyrobni_zakazka', fields)
        self.assertIn('behalter_nr', fields)

    def test_special_customers_exclude_behalter_nr(self):
        for code in ('SSH', 'SWG', 'HPM', 'FIS'):
            bedna = self.create_bedna(code)
            fields = self.inline.get_fields(self.get_request(), bedna.zakazka)
            with self.subTest(code=code):
                self.assertNotIn('behalter_nr', fields)
                self.assertNotIn('dodatecne_info', fields)
                self.assertNotIn('dodavatel_materialu', fields)
                self.assertNotIn('vyrobni_zakazka', fields)

    def test_get_changelist_formset_pozastavena_permissions(self):
        """
        Testuje, zda jsou pole v BednaInline formuláři zakázána pro pozastavené bedny,
        pokud uživatel nemá oprávnění pro změnu pozastavené bedny.
        """
        User = get_user_model()
        user = User.objects.create_user('user_fs', 'fs@example.com', 'pass', is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename='change_bedna'))

        bedna = self.create_bedna('SSH')
        zakazka = bedna.zakazka

        req = self.factory.get('/')
        req.user = user
        Formset = self.inline.get_formset(req, zakazka)
        fs = Formset(queryset=Bedna.objects.filter(id=bedna.id), instance=zakazka)
        form = fs.forms[0]
        # Všechny ne-skrývané widgety mají být disabled, hidden pole (např. id) musí zůstat aktivní kvůli uložení
        for name, field in form.fields.items():
            if getattr(field.widget, 'is_hidden', False):
                continue
            self.assertTrue(field.disabled, msg=f"Field '{name}' should be disabled for paused bedna without permission")

        req = self.factory.get('/')
        req.user = user
        req.user.user_permissions.add(Permission.objects.get(codename='change_pozastavena_bedna'))
        req.user = User.objects.get(pk=req.user.pk)
        Formset = self.inline.get_formset(req, zakazka)
        fs = Formset(queryset=Bedna.objects.filter(id=bedna.id), instance=zakazka)
        form = fs.forms[0]
        for name, field in form.fields.items():
            if getattr(field.widget, 'is_hidden', False):
                continue
            self.assertFalse(field.disabled, msg=f"Field '{name}' should be enabled for paused bedna with permission")

    def test_brutto_excluded_when_all_tara_positive(self):
        bedna = self.create_bedna('ROT')
        # Vytvoř ještě jednu bednu se stejnou zakázkou a kladnou tarou
        Bedna.objects.create(zakazka=bedna.zakazka, hmotnost=1, tara=1, mnozstvi=1)
        fields = self.inline.get_fields(self.get_request(), bedna.zakazka)
        self.assertNotIn('brutto', fields)

        # Uprav jednu bednu tak, aby tara nebyla > 0, 'brutto' se má objevit
        b_any = bedna.zakazka.bedny.first()
        b_any.tara = None
        b_any.save()
        fields2 = self.inline.get_fields(self.get_request(), bedna.zakazka)
        self.assertIn('brutto', fields2)


class NotificationAdminTests(AdminBase):
    def setUp(self):
        self.admin = NotificationAdmin(Notification, self.site)
        self.zakazka = Zakazka.objects.create(
            kamion_prijem=self.kamion,
            artikl='ART1',
            prumer=Decimal('10.0'),
            delka=Decimal('50.0'),
            predpis=self.predpis,
            typ_hlavy=self.typ_hlavy,
            popis='Test zakázka',
        )
        self.bedna = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal('2.0'),
            tara=Decimal('1.0'),
            mnozstvi=1,
        )

    def test_notification_queryset_filtered_for_user(self):
        User = get_user_model()
        current_user = User.objects.create_user('u_current2', 'current2@example.com', 'pass', is_staff=True)
        other_user = User.objects.create_user('u_other2', 'other2@example.com', 'pass', is_staff=True)

        Notification.objects.create(
            recipient=current_user,
            zakazka=self.zakazka,
            bedna=self.bedna,
            notif_type=Notification.NotificationType.PRIORITA,
            message='Test moje 2',
        )

        Notification.objects.create(
            recipient=other_user,
            zakazka=self.zakazka,
            bedna=self.bedna,
            notif_type=Notification.NotificationType.PRIORITA,
            message='Test jiné 2',
        )

        req = self.factory.get('/')
        req.user = current_user
        qs = self.admin.get_queryset(req)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().recipient, current_user)


class SarzeKrokBednaInlineAdminTests(AdminBase):
    def setUp(self):
        self.sarze_inline = SarzeKrokBednaInline(SarzeKrok, self.site)
        self.zarizeni = Zarizeni.objects.create(
            kod_zarizeni='SZ1',
            nazev_zarizeni='Sarze Zarizeni',
            zkraceny_nazev_zarizeni='SZ1',
        )
        self.sarze = Sarze.objects.create(
            cislo_sarze=10,
            datum_zalozeni=date.today(),
            aktivni=True,
        )
        self.krok = SarzeKrok.objects.create(
            sarze=self.sarze,
            poradi=1,
            datum=date.today(),
            zarizeni=self.zarizeni,
            zacatek=time(8, 0),
            operator='OP',
            program='P1',
        )

    def test_sarze_inline_bedna_autocomplete_supports_zakaznik_zkratka_and_filters_only_skladem(self):
        self.client.force_login(self.user)

        zakaznik = Zakaznik.objects.create(
            nazev='AutoSearch',
            zkraceny_nazev='AS',
            zkratka='ZKRTEST',
            ciselna_rada=200000,
        )
        kamion = Kamion.objects.create(zakaznik=zakaznik, datum=date.today())
        zakazka = Zakazka.objects.create(
            kamion_prijem=kamion,
            artikl='AUT-1',
            prumer=Decimal('10.0'),
            delka=Decimal('20.0'),
            predpis=self.predpis,
            typ_hlavy=self.typ_hlavy,
            popis='autocomplete',
        )

        skladem_bedna = Bedna.objects.create(
            zakazka=zakazka,
            hmotnost=Decimal('1.0'),
            tara=Decimal('1.0'),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.PRIJATO,
        )
        ne_skladem_bedna = Bedna.objects.create(
            zakazka=zakazka,
            hmotnost=Decimal('1.0'),
            tara=Decimal('1.0'),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.EXPEDOVANO,
        )

        response = self.client.get(
            reverse('admin:autocomplete'),
            {
                'app_label': 'orders',
                'model_name': 'sarzekrokbedna',
                'field_name': 'bedna',
                'term': 'ZKRTEST',
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        returned_ids = {item['id'] for item in payload.get('results', [])}

        self.assertIn(str(skladem_bedna.pk), returned_ids)
        self.assertNotIn(str(ne_skladem_bedna.pk), returned_ids)

    def test_sarze_inline_bedna_autocomplete_returns_no_results_for_short_term(self):
        self.client.force_login(self.user)

        zakaznik = Zakaznik.objects.create(
            nazev='ShortAutoSearch',
            zkraceny_nazev='SAS',
            zkratka='XYZ',
            ciselna_rada=210000,
        )
        kamion = Kamion.objects.create(zakaznik=zakaznik, datum=date.today())
        zakazka = Zakazka.objects.create(
            kamion_prijem=kamion,
            artikl='EMPTY-AUTO',
            prumer=Decimal('10.0'),
            delka=Decimal('20.0'),
            predpis=self.predpis,
            typ_hlavy=self.typ_hlavy,
            popis='short autocomplete',
        )
        Bedna.objects.create(
            zakazka=zakazka,
            hmotnost=Decimal('1.0'),
            tara=Decimal('1.0'),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.PRIJATO,
        )

        response = self.client.get(
            reverse('admin:autocomplete'),
            {
                'app_label': 'orders',
                'model_name': 'sarzekrokbedna',
                'field_name': 'bedna',
                'term': 'XYZ',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('results'), [])

    def test_sarze_inline_formset_rejects_bedna_outside_skladem_states(self):
        request = self.factory.get('/admin/orders/sarzekrok/')
        request.user = self.user

        formset_class = self.sarze_inline.get_formset(request, obj=self.krok)
        prefix = formset_class.get_default_prefix()

        bedna_mimo_skladem = Bedna.objects.create(
            zakazka=Zakazka.objects.create(
                kamion_prijem=self.kamion,
                artikl='BAD-1',
                prumer=Decimal('9.0'),
                delka=Decimal('30.0'),
                predpis=self.predpis,
                typ_hlavy=self.typ_hlavy,
                popis='bad inline',
            ),
            hmotnost=Decimal('1.0'),
            tara=Decimal('1.0'),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.EXPEDOVANO,
        )

        data = {
            f'{prefix}-TOTAL_FORMS': '1',
            f'{prefix}-INITIAL_FORMS': '0',
            f'{prefix}-MIN_NUM_FORMS': '0',
            f'{prefix}-MAX_NUM_FORMS': '1000',
            f'{prefix}-0-bedna': str(bedna_mimo_skladem.pk),
            f'{prefix}-0-patro': '1',
            f'{prefix}-0-procent_z_patra': '100',
            f'{prefix}-0-popis_mimo_db': '',
            f'{prefix}-0-zakaznik_mimo_db': '',
            f'{prefix}-0-zakazka_mimo_db': '',
            f'{prefix}-0-cislo_bedny_mimo_db': '',
        }

        formset = formset_class(data=data, instance=self.krok, prefix=prefix)

        self.assertFalse(formset.is_valid())
        self.assertTrue(any('nejsou ve stavu skladem' in str(err) for err in formset.non_form_errors()))

    def test_sarze_inline_formset_requires_any_row_on_add(self):
        request = self.factory.get('/admin/orders/sarzekrok/add/')
        request.user = self.user

        formset_class = self.sarze_inline.get_formset(request, obj=None)
        prefix = formset_class.get_default_prefix()

        data = {
            f'{prefix}-TOTAL_FORMS': '1',
            f'{prefix}-INITIAL_FORMS': '0',
            f'{prefix}-MIN_NUM_FORMS': '0',
            f'{prefix}-MAX_NUM_FORMS': '1000',
            f'{prefix}-0-bedna': '',
            f'{prefix}-0-patro': '',
            f'{prefix}-0-procent_z_patra': '',
            f'{prefix}-0-popis_mimo_db': '',
            f'{prefix}-0-zakaznik_mimo_db': '',
            f'{prefix}-0-zakazka_mimo_db': '',
            f'{prefix}-0-cislo_bedny_mimo_db': '',
        }

        krok = SarzeKrok(
            sarze=self.sarze,
            datum=date.today(),
            zarizeni=self.zarizeni,
            zacatek=time(8, 0),
            operator='OP-ADD',
        )
        formset = formset_class(data=data, instance=krok, prefix=prefix)

        self.assertFalse(formset.is_valid())
        self.assertTrue(
            any(
                'Krok šarže nebyl uložen. Vyplňte v inline alespoň jeden řádek s bednou nebo popisem mimo DB.' in str(err)
                for err in formset.non_form_errors()
            )
        )

    def test_sarze_inline_formset_requires_any_row_on_existing_step(self):
        request = self.factory.get('/admin/orders/sarzekrok/')
        request.user = self.user

        formset_class = self.sarze_inline.get_formset(request, obj=self.krok)
        prefix = formset_class.get_default_prefix()

        data = {
            f'{prefix}-TOTAL_FORMS': '0',
            f'{prefix}-INITIAL_FORMS': '0',
            f'{prefix}-MIN_NUM_FORMS': '0',
            f'{prefix}-MAX_NUM_FORMS': '1000',
        }

        formset = formset_class(data=data, instance=self.krok, prefix=prefix)

        self.assertFalse(formset.is_valid())
        self.assertTrue(
            any(
                'Krok šarže nebyl uložen. Vyplňte v inline alespoň jeden řádek s bednou nebo popisem mimo DB.' in str(err)
                for err in formset.non_form_errors()
            )
        )

    def test_sarze_inline_formset_rejects_sum_procent_over_100_in_same_patro(self):
        request = self.factory.get('/admin/orders/sarzekrok/')
        request.user = self.user

        formset_class = self.sarze_inline.get_formset(request, obj=self.krok)
        prefix = formset_class.get_default_prefix()

        data = {
            f'{prefix}-TOTAL_FORMS': '2',
            f'{prefix}-INITIAL_FORMS': '0',
            f'{prefix}-MIN_NUM_FORMS': '0',
            f'{prefix}-MAX_NUM_FORMS': '1000',

            f'{prefix}-0-bedna': '',
            f'{prefix}-0-patro': '1',
            f'{prefix}-0-procent_z_patra': '60',
            f'{prefix}-0-popis_mimo_db': 'ZELEZO-A',
            f'{prefix}-0-zakaznik_mimo_db': 'Zak',
            f'{prefix}-0-zakazka_mimo_db': 'Z-1',
            f'{prefix}-0-cislo_bedny_mimo_db': 'M-1',

            f'{prefix}-1-bedna': '',
            f'{prefix}-1-patro': '1',
            f'{prefix}-1-procent_z_patra': '50',
            f'{prefix}-1-popis_mimo_db': 'ZELEZO-B',
            f'{prefix}-1-zakaznik_mimo_db': 'Zak',
            f'{prefix}-1-zakazka_mimo_db': 'Z-2',
            f'{prefix}-1-cislo_bedny_mimo_db': 'M-2',
        }

        formset = formset_class(data=data, instance=self.krok, prefix=prefix)

        self.assertFalse(formset.is_valid())
        self.assertTrue(any('Součet procent v rámci jednoho patra nesmí překročit 100 %.' in str(err) for err in formset.non_form_errors()))


class SarzeKrokBednaAdminActionTests(AdminBase):
    def setUp(self):
        self.admin = SarzeKrokBednaAdmin(SarzeKrokBedna, self.site)
        self.zarizeni_1 = Zarizeni.objects.create(
            kod_zarizeni='A1',
            nazev_zarizeni='Zarizeni A1',
            zkraceny_nazev_zarizeni='A1',
        )
        self.zarizeni_2 = Zarizeni.objects.create(
            kod_zarizeni='A2',
            nazev_zarizeni='Zarizeni A2',
            zkraceny_nazev_zarizeni='A2',
        )
        self.sarze = Sarze.objects.create(
            cislo_sarze=100,
            datum_zalozeni=date.today(),
            cislo_pripravku=21,
            aktivni=True,
        )
        self.krok_1 = SarzeKrok.objects.create(
            sarze=self.sarze,
            poradi=1,
            datum=date.today(),
            zarizeni=self.zarizeni_1,
            zacatek=time(8, 0),
            operator='OP1',
            program='P1',
        )
        self.krok_2 = SarzeKrok.objects.create(
            sarze=self.sarze,
            poradi=2,
            datum=date.today(),
            zarizeni=self.zarizeni_2,
            zacatek=time(9, 0),
            operator='OP2',
            program='P2',
        )
        self.zakazka = Zakazka.objects.create(
            kamion_prijem=self.kamion,
            artikl='AKCE-1',
            prumer=Decimal('10.0'),
            delka=Decimal('50.0'),
            predpis=self.predpis,
            typ_hlavy=self.typ_hlavy,
            popis='test akce',
        )
        self.bedna = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal('2.0'),
            tara=Decimal('1.0'),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.PRIJATO,
        )

    def test_action_creates_new_step_and_copies_selected_rows(self):
        source = SarzeKrokBedna.objects.create(
            krok=self.krok_1,
            bedna=self.bedna,
            patro=1,
            procent_z_patra=100,
        )
        request = self.factory.post(
            '/admin/orders/sarzekrokbedna/',
            {
                'apply': '1',
                'action': 'vytvorit_dalsi_krok_sarze_action',
                '_selected_action': [source.pk],
                'datum': date.today().strftime('%Y-%m-%d'),
                'zarizeni': self.zarizeni_2.pk,
                'operator': 'OP-NOVY',
                'zacatek': '10:15',
            },
        )
        request.user = self.user
        request.session = DummySession()
        request._messages = FallbackStorage(request)

        response = vytvorit_dalsi_krok_sarze_action(self.admin, request, SarzeKrokBedna.objects.filter(pk=source.pk))

        self.assertEqual(response.status_code, 302)
        novy_krok = SarzeKrok.objects.exclude(pk__in=[self.krok_1.pk, self.krok_2.pk]).get()
        self.assertEqual(novy_krok.sarze_id, self.krok_1.sarze_id)
        self.assertEqual(novy_krok.zarizeni_id, self.zarizeni_2.pk)
        self.assertEqual(novy_krok.zacatek, time(10, 15))
        self.assertEqual(novy_krok.operator, 'OP-NOVY')
        self.assertTrue(SarzeKrokBedna.objects.filter(pk=source.pk).exists())
        self.assertTrue(
            SarzeKrokBedna.objects.filter(
                krok=novy_krok,
                bedna=self.bedna,
                patro=1,
            ).exists()
        )

    def test_action_ignores_repeated_submit_with_same_token(self):
        source = SarzeKrokBedna.objects.create(
            krok=self.krok_1,
            bedna=self.bedna,
            patro=4,
            procent_z_patra=100,
        )
        post_data = {
            'apply': '1',
            'action': 'vytvorit_dalsi_krok_sarze_action',
            '_selected_action': [source.pk],
            '_sarzekrok_action_token': 'repeat-token-denik',
            'datum': date.today().strftime('%Y-%m-%d'),
            'zarizeni': self.zarizeni_2.pk,
            'operator': 'OP-REPEAT',
            'zacatek': '10:45',
        }

        first_request = self.factory.post('/admin/orders/sarzekrokbedna/', post_data)
        first_request.user = self.user
        first_request.session = DummySession()
        first_request._messages = FallbackStorage(first_request)

        second_request = self.factory.post('/admin/orders/sarzekrokbedna/', post_data)
        second_request.user = self.user
        second_request.session = DummySession()
        second_request._messages = FallbackStorage(second_request)

        first_response = vytvorit_dalsi_krok_sarze_action(
            self.admin,
            first_request,
            SarzeKrokBedna.objects.filter(pk=source.pk),
        )
        second_response = vytvorit_dalsi_krok_sarze_action(
            self.admin,
            second_request,
            SarzeKrokBedna.objects.filter(pk=source.pk),
        )

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 302)
        self.assertEqual(SarzeKrok.objects.count(), 3)
        novy_krok = SarzeKrok.objects.get(action_token='repeat-token-denik')
        self.assertEqual(novy_krok.poradi, 3)
        self.assertEqual(SarzeKrokBedna.objects.filter(krok=novy_krok).count(), 1)

        messages_text = [message.message for message in second_request._messages]
        self.assertTrue(any('Opakované odeslání stejné akce bylo ignorováno.' in text for text in messages_text))

    def test_action_first_step_renders_init_form(self):
        source = SarzeKrokBedna.objects.create(
            krok=self.krok_1,
            bedna=self.bedna,
            patro=8,
            procent_z_patra=100,
        )

        request = self.factory.post('/admin/orders/sarzekrokbedna/')
        request.user = self.user
        request.session = DummySession()
        request._messages = FallbackStorage(request)

        response = vytvorit_dalsi_krok_sarze_action(self.admin, request, SarzeKrokBedna.objects.filter(pk=source.pk))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(SarzeKrok.objects.count(), 2)

    def test_action_requires_rows_from_one_source_step(self):
        source_a = SarzeKrokBedna.objects.create(
            krok=self.krok_1,
            bedna=self.bedna,
            patro=2,
            procent_z_patra=50,
        )
        source_b = SarzeKrokBedna.objects.create(
            krok=self.krok_2,
            bedna=self.bedna,
            patro=3,
            procent_z_patra=50,
        )
        request = self.factory.post('/admin/orders/sarzekrokbedna/')
        request.user = self.user
        request.session = DummySession()
        request._messages = FallbackStorage(request)

        response = vytvorit_dalsi_krok_sarze_action(
            self.admin,
            request,
            SarzeKrokBedna.objects.filter(pk__in=[source_a.pk, source_b.pk]),
        )

        self.assertIsNone(response)
        self.assertEqual(SarzeKrok.objects.count(), 2)

    def test_action_copies_mimo_db_row(self):
        source = SarzeKrokBedna.objects.create(
            krok=self.krok_1,
            bedna=None,
            patro=7,
            procent_z_patra=80,
            popis_mimo_db='ZELEZO',
            zakaznik_mimo_db='TEST',
            zakazka_mimo_db='Z-1',
            cislo_bedny_mimo_db='M-001',
        )
        request = self.factory.post(
            '/admin/orders/sarzekrokbedna/',
            {
                'apply': '1',
                'action': 'vytvorit_dalsi_krok_sarze_action',
                '_selected_action': [source.pk],
                'datum': date.today().strftime('%Y-%m-%d'),
                'zarizeni': self.zarizeni_2.pk,
                'operator': 'OP-MIMO',
                'zacatek': '11:00',
            },
        )
        request.user = self.user
        request.session = DummySession()
        request._messages = FallbackStorage(request)

        response = vytvorit_dalsi_krok_sarze_action(self.admin, request, SarzeKrokBedna.objects.filter(pk=source.pk))

        self.assertEqual(response.status_code, 302)
        novy_krok = SarzeKrok.objects.exclude(pk__in=[self.krok_1.pk, self.krok_2.pk]).get()
        self.assertEqual(novy_krok.zarizeni_id, self.zarizeni_2.pk)
        self.assertTrue(SarzeKrokBedna.objects.filter(pk=source.pk).exists())
        self.assertTrue(
            SarzeKrokBedna.objects.filter(
                krok=novy_krok,
                bedna__isnull=True,
                patro=7,
                popis_mimo_db='ZELEZO',
                zakaznik_mimo_db='TEST',
                zakazka_mimo_db='Z-1',
                cislo_bedny_mimo_db='M-001',
            ).exists()
        )

    def test_action_warns_when_source_step_has_no_konec(self):
        source = SarzeKrokBedna.objects.create(
            krok=self.krok_1,
            bedna=self.bedna,
            patro=9,
            procent_z_patra=100,
        )
        request = self.factory.post(
            '/admin/orders/sarzekrokbedna/',
            {
                'apply': '1',
                'action': 'vytvorit_dalsi_krok_sarze_action',
                '_selected_action': [source.pk],
                'datum': date.today().strftime('%Y-%m-%d'),
                'zarizeni': self.zarizeni_2.pk,
                'operator': 'OP-WARN',
                'zacatek': '12:00',
            },
        )
        request.user = self.user
        request.session = DummySession()
        request._messages = FallbackStorage(request)

        response = vytvorit_dalsi_krok_sarze_action(
            self.admin,
            request,
            SarzeKrokBedna.objects.filter(pk=source.pk),
        )

        self.assertEqual(response.status_code, 302)
        messages_text = [message.message for message in request._messages]
        self.assertTrue(
            any('Původní krok šarže nemá vyplněný konec, nezapomeňte jej vyplnit.' in text for text in messages_text)
        )

    def test_action_copies_multiple_mimo_db_rows_in_same_patro(self):
        row_a = SarzeKrokBedna.objects.create(
            krok=self.krok_1,
            bedna=None,
            patro=7,
            procent_z_patra=40,
            popis_mimo_db='ZELEZO-A',
            zakaznik_mimo_db='TEST',
            zakazka_mimo_db='Z-1',
            cislo_bedny_mimo_db='M-001',
        )
        row_b = SarzeKrokBedna.objects.create(
            krok=self.krok_1,
            bedna=None,
            patro=7,
            procent_z_patra=30,
            popis_mimo_db='ZELEZO-B',
            zakaznik_mimo_db='TEST',
            zakazka_mimo_db='Z-2',
            cislo_bedny_mimo_db='M-002',
        )

        request = self.factory.post(
            '/admin/orders/sarzekrokbedna/',
            {
                'apply': '1',
                'action': 'vytvorit_dalsi_krok_sarze_action',
                '_selected_action': [row_a.pk, row_b.pk],
                'datum': date.today().strftime('%Y-%m-%d'),
                'zarizeni': self.zarizeni_2.pk,
                'operator': 'OP-MIMO-2',
                'zacatek': '11:30',
            },
        )
        request.user = self.user
        request.session = DummySession()
        request._messages = FallbackStorage(request)

        response = vytvorit_dalsi_krok_sarze_action(
            self.admin,
            request,
            SarzeKrokBedna.objects.filter(pk__in=[row_a.pk, row_b.pk]),
        )

        self.assertEqual(response.status_code, 302)
        novy_krok = SarzeKrok.objects.exclude(pk__in=[self.krok_1.pk, self.krok_2.pk]).get()
        copied_rows = SarzeKrokBedna.objects.filter(krok=novy_krok, bedna__isnull=True, patro=7)
        self.assertEqual(copied_rows.count(), 2)
        self.assertTrue(copied_rows.filter(popis_mimo_db='ZELEZO-A', cislo_bedny_mimo_db='M-001').exists())
        self.assertTrue(copied_rows.filter(popis_mimo_db='ZELEZO-B', cislo_bedny_mimo_db='M-002').exists())


class SarzeKrokAdminActionTests(AdminBase):
    def setUp(self):
        self.admin = SarzeKrokAdmin(SarzeKrok, self.site)
        self.zarizeni = Zarizeni.objects.create(
            kod_zarizeni='B1',
            nazev_zarizeni='Zarizeni B1',
            zkraceny_nazev_zarizeni='B1',
        )
        self.sarze = Sarze.objects.create(
            cislo_sarze=101,
            datum_zalozeni=date.today(),
            cislo_pripravku=11,
            aktivni=True,
        )
        self.krok = SarzeKrok.objects.create(
            sarze=self.sarze,
            poradi=1,
            datum=date.today(),
            zarizeni=self.zarizeni,
            zacatek=time(7, 30),
            operator='OPX',
            program='PGX',
        )
        self.zakazka = Zakazka.objects.create(
            kamion_prijem=self.kamion,
            artikl='AKCE-2',
            prumer=Decimal('10.0'),
            delka=Decimal('50.0'),
            predpis=self.predpis,
            typ_hlavy=self.typ_hlavy,
            popis='test akce 2',
        )
        self.bedna = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal('2.0'),
            tara=Decimal('1.0'),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.PRIJATO,
        )

    def test_action_creates_new_step_with_all_rows(self):
        SarzeKrokBedna.objects.create(krok=self.krok, bedna=self.bedna, patro=1, procent_z_patra=40)
        SarzeKrokBedna.objects.create(krok=self.krok, bedna=self.bedna, patro=1, procent_z_patra=20)
        SarzeKrokBedna.objects.create(
            krok=self.krok,
            bedna=None,
            patro=2,
            procent_z_patra=60,
            popis_mimo_db='ZELEZO',
            zakaznik_mimo_db='TEST',
            zakazka_mimo_db='Z-2',
            cislo_bedny_mimo_db='M-002',
        )

        request = self.factory.post(
            '/admin/orders/sarzekrok/',
            {
                'apply': '1',
                'action': 'vytvorit_novy_krok_z_kroku_sarze_action',
                '_selected_action': [self.krok.pk],
                'datum': date.today().strftime('%Y-%m-%d'),
                'zarizeni': self.zarizeni.pk,
                'operator': 'OPX-2',
                'zacatek': '13:30',
            },
        )
        request.user = self.user
        request.session = DummySession()
        request._messages = FallbackStorage(request)

        response = vytvorit_novy_krok_z_kroku_sarze_action(self.admin, request, SarzeKrok.objects.filter(pk=self.krok.pk))

        self.assertEqual(response.status_code, 302)
        novy_krok = SarzeKrok.objects.exclude(pk=self.krok.pk).get()
        self.assertEqual(novy_krok.sarze_id, self.krok.sarze_id)
        self.assertEqual(novy_krok.zarizeni_id, self.zarizeni.pk)
        self.assertEqual(novy_krok.zacatek, time(13, 30))
        self.assertEqual(novy_krok.operator, 'OPX-2')
        self.assertEqual(SarzeKrokBedna.objects.filter(krok=self.krok).count(), 3)
        self.assertEqual(SarzeKrokBedna.objects.filter(krok=novy_krok).count(), 3)
        self.assertEqual(
            list(
                SarzeKrokBedna.objects
                .filter(krok=novy_krok, bedna=self.bedna, patro=1)
                .values_list('procent_z_patra', flat=True)
            ),
            [40, 20],
        )

    def test_action_ignores_repeated_submit_with_same_token(self):
        SarzeKrokBedna.objects.create(krok=self.krok, bedna=self.bedna, patro=1, procent_z_patra=100)
        post_data = {
            'apply': '1',
            'action': 'vytvorit_novy_krok_z_kroku_sarze_action',
            '_selected_action': [self.krok.pk],
            '_sarzekrok_action_token': 'repeat-token-krok',
            'datum': date.today().strftime('%Y-%m-%d'),
            'zarizeni': self.zarizeni.pk,
            'operator': 'OPX-REPEAT',
            'zacatek': '13:45',
        }

        first_request = self.factory.post('/admin/orders/sarzekrok/', post_data)
        first_request.user = self.user
        first_request.session = DummySession()
        first_request._messages = FallbackStorage(first_request)

        second_request = self.factory.post('/admin/orders/sarzekrok/', post_data)
        second_request.user = self.user
        second_request.session = DummySession()
        second_request._messages = FallbackStorage(second_request)

        first_response = vytvorit_novy_krok_z_kroku_sarze_action(
            self.admin,
            first_request,
            SarzeKrok.objects.filter(pk=self.krok.pk),
        )
        second_response = vytvorit_novy_krok_z_kroku_sarze_action(
            self.admin,
            second_request,
            SarzeKrok.objects.filter(pk=self.krok.pk),
        )

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 302)
        self.assertEqual(SarzeKrok.objects.count(), 2)
        novy_krok = SarzeKrok.objects.get(action_token='repeat-token-krok')
        self.assertEqual(novy_krok.poradi, 2)
        self.assertEqual(SarzeKrokBedna.objects.filter(krok=novy_krok).count(), 1)

        messages_text = [message.message for message in second_request._messages]
        self.assertTrue(any('Opakované odeslání stejné akce bylo ignorováno.' in text for text in messages_text))

    def test_action_first_step_renders_init_form(self):
        request = self.factory.post('/admin/orders/sarzekrok/')
        request.user = self.user
        request.session = DummySession()
        request._messages = FallbackStorage(request)

        response = vytvorit_novy_krok_z_kroku_sarze_action(self.admin, request, SarzeKrok.objects.filter(pk=self.krok.pk))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(SarzeKrok.objects.count(), 1)

    def test_action_requires_exactly_one_step(self):
        druhy_krok = SarzeKrok.objects.create(
            sarze=self.sarze,
            poradi=2,
            datum=date.today(),
            zarizeni=self.zarizeni,
            zacatek=time(8, 30),
            operator='OPY',
            program='PGY',
        )

        request = self.factory.post(
            '/admin/orders/sarzekrok/',
            {
                'apply': '1',
                'action': 'vytvorit_novy_krok_z_kroku_sarze_action',
                '_selected_action': [self.krok.pk],
                'datum': date.today().strftime('%Y-%m-%d'),
                'zarizeni': self.zarizeni.pk,
                'operator': 'OPX-3',
                'zacatek': '14:45',
            },
        )
        request.user = self.user
        request.session = DummySession()
        request._messages = FallbackStorage(request)

        response = vytvorit_novy_krok_z_kroku_sarze_action(
            self.admin,
            request,
            SarzeKrok.objects.filter(pk__in=[self.krok.pk, druhy_krok.pk]),
        )

        self.assertIsNone(response)

    def test_action_warns_when_source_step_has_no_konec(self):
        request = self.factory.post(
            '/admin/orders/sarzekrok/',
            {
                'apply': '1',
                'action': 'vytvorit_novy_krok_z_kroku_sarze_action',
                '_selected_action': [self.krok.pk],
                'datum': date.today().strftime('%Y-%m-%d'),
                'zarizeni': self.zarizeni.pk,
                'operator': 'OPX-4',
                'zacatek': '15:00',
            },
        )
        request.user = self.user
        request.session = DummySession()
        request._messages = FallbackStorage(request)

        response = vytvorit_novy_krok_z_kroku_sarze_action(
            self.admin,
            request,
            SarzeKrok.objects.filter(pk=self.krok.pk),
        )

        self.assertEqual(response.status_code, 302)
        messages_text = [message.message for message in request._messages]
        self.assertTrue(
            any('Původní krok šarže nemá vyplněný konec, nezapomeňte jej vyplnit.' in text for text in messages_text)
        )

    def test_action_copies_multiple_mimo_db_rows_in_same_patro(self):
        SarzeKrokBedna.objects.create(
            krok=self.krok,
            bedna=None,
            patro=3,
            procent_z_patra=45,
            popis_mimo_db='ZELEZO-A',
            zakaznik_mimo_db='TEST',
            zakazka_mimo_db='Z-3',
            cislo_bedny_mimo_db='M-010',
        )
        SarzeKrokBedna.objects.create(
            krok=self.krok,
            bedna=None,
            patro=3,
            procent_z_patra=35,
            popis_mimo_db='ZELEZO-B',
            zakaznik_mimo_db='TEST',
            zakazka_mimo_db='Z-4',
            cislo_bedny_mimo_db='M-011',
        )

        request = self.factory.post(
            '/admin/orders/sarzekrok/',
            {
                'apply': '1',
                'action': 'vytvorit_novy_krok_z_kroku_sarze_action',
                '_selected_action': [self.krok.pk],
                'datum': date.today().strftime('%Y-%m-%d'),
                'zarizeni': self.zarizeni.pk,
                'operator': 'OPX-MIMO',
                'zacatek': '16:10',
            },
        )
        request.user = self.user
        request.session = DummySession()
        request._messages = FallbackStorage(request)

        response = vytvorit_novy_krok_z_kroku_sarze_action(
            self.admin,
            request,
            SarzeKrok.objects.filter(pk=self.krok.pk),
        )

        self.assertEqual(response.status_code, 302)
        novy_krok = SarzeKrok.objects.exclude(pk=self.krok.pk).get()
        copied_rows = SarzeKrokBedna.objects.filter(krok=novy_krok, bedna__isnull=True, patro=3)
        self.assertEqual(copied_rows.count(), 2)
        self.assertTrue(copied_rows.filter(popis_mimo_db='ZELEZO-A', cislo_bedny_mimo_db='M-010').exists())
        self.assertTrue(copied_rows.filter(popis_mimo_db='ZELEZO-B', cislo_bedny_mimo_db='M-011').exists())

    def test_change_form_requires_zarizeni_operator_a_zacatek(self):
        novy_krok = SarzeKrok.objects.create(
            sarze=self.sarze,
            datum=date.today(),
            zarizeni=self.zarizeni,
            zacatek=time(6, 0),
            operator='OP-REQ',
            program='PG0',
        )

        request = self.factory.get(f'/admin/orders/sarzekrok/{novy_krok.pk}/change/')
        request.user = self.user

        form_class = self.admin.get_form(request, obj=novy_krok, change=True)

        self.assertTrue(form_class.base_fields['zarizeni'].required)
        self.assertTrue(form_class.base_fields['operator'].required)
        self.assertTrue(form_class.base_fields['zacatek'].required)

    def test_add_form_vyzaduje_zarizeni_operator_a_zacatek(self):
        request = self.factory.get('/admin/orders/sarzekrok/add/')
        request.user = self.user

        form_class = self.admin.get_form(request, obj=None, change=False)

        self.assertTrue(form_class.base_fields['zarizeni'].required)
        self.assertTrue(form_class.base_fields['operator'].required)
        self.assertTrue(form_class.base_fields['zacatek'].required)


class SarzeAdminCreateBehaviorTests(AdminBase):
    def setUp(self):
        self.admin = SarzeAdmin(Sarze, self.site)

    def test_get_fields_hides_datum_zalozeni_on_add(self):
        request = self.factory.get('/admin/orders/sarze/add/')
        request.user = self.user

        fields = self.admin.get_fields(request, obj=None)

        self.assertNotIn('datum_zalozeni', fields)

    def test_get_fields_shows_datum_zalozeni_on_change(self):
        sarze = Sarze.objects.create(
            datum_zalozeni=date.today(),
            cislo_pripravku=5,
            aktivni=True,
        )
        request = self.factory.get(f'/admin/orders/sarze/{sarze.pk}/change/')
        request.user = self.user

        fields = self.admin.get_fields(request, obj=sarze)

        self.assertIn('datum_zalozeni', fields)

    def test_media_loads_admin_actions_target_blank_script(self):
        media_js = list(self.admin.media._js)

        self.assertIn('orders/js/admin_actions_target_blank.js', media_js)

    def test_save_model_autofills_datum_zalozeni_on_create(self):
        request = self.factory.post('/admin/orders/sarze/add/')
        request.user = self.user

        sarze = Sarze(cislo_pripravku=9, aktivni=True)
        self.admin.save_model(request, sarze, form=None, change=False)

        self.assertIsNotNone(sarze.pk)
        self.assertEqual(sarze.datum_zalozeni, date.today())

    def test_inline_krok_vyzaduje_povinna_pole_pri_vytvoreni_sarze(self):
        request = self.factory.post('/admin/orders/sarze/add/')
        request.user = self.user

        inline = SarzeKrokInline(Sarze, self.site)
        formset_class = inline.get_formset(request, obj=None)
        prefix = formset_class.get_default_prefix()

        data = {
            f'{prefix}-TOTAL_FORMS': '1',
            f'{prefix}-INITIAL_FORMS': '0',
            f'{prefix}-MIN_NUM_FORMS': '1',
            f'{prefix}-MAX_NUM_FORMS': '1',
            f'{prefix}-0-datum': '',
            f'{prefix}-0-zarizeni': '',
            f'{prefix}-0-zacatek': '',
            f'{prefix}-0-operator': '',
            f'{prefix}-0-konec': '',
            f'{prefix}-0-program': '',
            f'{prefix}-0-alarm': '',
            f'{prefix}-0-poznamka': '',
        }

        sarze = Sarze(cislo_pripravku=7, aktivni=True, datum_zalozeni=date.today())
        formset = formset_class(data=data, instance=sarze, prefix=prefix)

        self.assertFalse(formset.is_valid())
        self.assertTrue(
            any(
                'Šarže nebyla uložena. Vyplňte v inline prvního kroku povinná pole: Datum, Pracoviště, Začátek a Operátor.' in str(err)
                for err in formset.non_form_errors()
            )
        )

    def test_inline_krok_s_castecne_vyplnenim_spadne_na_django_required(self):
        request = self.factory.post('/admin/orders/sarze/add/')
        request.user = self.user

        zarizeni = Zarizeni.objects.create(
            kod_zarizeni='I1',
            nazev_zarizeni='Inline Zarizeni 1',
            zkraceny_nazev_zarizeni='I1',
        )

        inline = SarzeKrokInline(Sarze, self.site)
        formset_class = inline.get_formset(request, obj=None)
        prefix = formset_class.get_default_prefix()

        data = {
            f'{prefix}-TOTAL_FORMS': '1',
            f'{prefix}-INITIAL_FORMS': '0',
            f'{prefix}-MIN_NUM_FORMS': '1',
            f'{prefix}-MAX_NUM_FORMS': '1',
            f'{prefix}-0-datum': date.today().strftime('%Y-%m-%d'),
            f'{prefix}-0-zarizeni': '',
            f'{prefix}-0-zacatek': '',
            f'{prefix}-0-operator': '',
            f'{prefix}-0-konec': '',
            f'{prefix}-0-program': '',
            f'{prefix}-0-alarm': '',
            f'{prefix}-0-poznamka': '',
        }

        sarze = Sarze(cislo_pripravku=8, aktivni=True, datum_zalozeni=date.today())
        formset = formset_class(data=data, instance=sarze, prefix=prefix)

        self.assertFalse(formset.is_valid())


class SarzeAdminSearchByDisplayedNumberTests(AdminBase):
    def setUp(self):
        self.sarze_admin = SarzeAdmin(Sarze, self.site)
        self.sarzekrok_admin = SarzeKrokAdmin(SarzeKrok, self.site)
        self.sarzekrokbedna_admin = SarzeKrokBednaAdmin(SarzeKrokBedna, self.site)

        self.sarze_25 = Sarze.objects.create(
            cislo_sarze=25,
            datum_zalozeni=date.today(),
            cislo_pripravku=1,
            aktivni=True,
        )
        self.sarze_125 = Sarze.objects.create(
            cislo_sarze=125,
            datum_zalozeni=date.today(),
            cislo_pripravku=2,
            aktivni=True,
        )

        self.zarizeni = Zarizeni.objects.create(
            kod_zarizeni='S1',
            nazev_zarizeni='Zarizeni S1',
            zkraceny_nazev_zarizeni='S1',
        )

        self.krok_25 = SarzeKrok.objects.create(
            sarze=self.sarze_25,
            poradi=1,
            datum=date.today(),
            zarizeni=self.zarizeni,
            zacatek=time(8, 0),
            operator='OP25',
            program='PG25',
        )
        self.krok_125 = SarzeKrok.objects.create(
            sarze=self.sarze_125,
            poradi=1,
            datum=date.today(),
            zarizeni=self.zarizeni,
            zacatek=time(9, 0),
            operator='OP125',
            program='PG125',
        )

        self.zakazka = Zakazka.objects.create(
            kamion_prijem=self.kamion,
            artikl='SARZE-SEARCH',
            prumer=Decimal('10.0'),
            delka=Decimal('20.0'),
            predpis=self.predpis,
            typ_hlavy=self.typ_hlavy,
            popis='Sarze search',
        )
        self.bedna = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal('1.0'),
            tara=Decimal('1.0'),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.PRIJATO,
        )

        self.radek_25 = SarzeKrokBedna.objects.create(
            krok=self.krok_25,
            bedna=self.bedna,
            patro=1,
            procent_z_patra=100,
        )
        self.radek_125 = SarzeKrokBedna.objects.create(
            krok=self.krok_125,
            bedna=self.bedna,
            patro=2,
            procent_z_patra=100,
        )

    def test_sarze_admin_find_by_displayed_sarze_number(self):
        request = self.factory.get('/admin/orders/sarze/')
        request.user = self.user

        queryset, _ = self.sarze_admin.get_search_results(
            request,
            Sarze.objects.all(),
            'S00025',
        )

        self.assertSetEqual(set(queryset.values_list('id', flat=True)), {self.sarze_25.id})

    def test_sarzekrok_admin_find_by_displayed_sarze_number(self):
        request = self.factory.get('/admin/orders/sarzekrok/')
        request.user = self.user

        queryset, _ = self.sarzekrok_admin.get_search_results(
            request,
            SarzeKrok.objects.all(),
            'S00025',
        )

        self.assertSetEqual(set(queryset.values_list('id', flat=True)), {self.krok_25.id})

    def test_sarzekrokbedna_admin_find_by_displayed_sarze_number(self):
        request = self.factory.get('/admin/orders/sarzekrokbedna/')
        request.user = self.user

        queryset, _ = self.sarzekrokbedna_admin.get_search_results(
            request,
            SarzeKrokBedna.objects.all(),
            'S00025',
        )

        self.assertSetEqual(set(queryset.values_list('id', flat=True)), {self.radek_25.id})


class PredpisAdminSaveAsTests(AdminBase):
    def setUp(self):
        self.admin = PredpisAdmin(Predpis, self.site)

    def test_saveasnew_copies_cena_relations_from_source_predpis(self):
        source_predpis = Predpis.objects.create(
            nazev='P-SRC',
            skupina=1,
            zakaznik=self.zakaznik,
            aktivni=False,
        )
        new_predpis = Predpis.objects.create(
            nazev='P-NEW',
            skupina=1,
            zakaznik=self.zakaznik,
            aktivni=True,
        )

        cena_1 = Cena.objects.create(
            popis='C1',
            zakaznik=self.zakaznik,
            delka_min=Decimal('10.0'),
            delka_max=Decimal('20.0'),
            cena_za_kg=Decimal('1.00'),
        )
        cena_2 = Cena.objects.create(
            popis='C2',
            zakaznik=self.zakaznik,
            delka_min=Decimal('20.0'),
            delka_max=Decimal('30.0'),
            cena_za_kg=Decimal('1.10'),
        )
        cena_1.predpis.add(source_predpis)
        cena_2.predpis.add(source_predpis)

        request = self.factory.post(
            f'/admin/orders/predpis/{source_predpis.pk}/change/',
            data={'_saveasnew_copy_ceny_deactivate': '1'},
        )
        request.user = self.user
        request.resolver_match = SimpleNamespace(kwargs={'object_id': str(source_predpis.pk)})

        self.admin._copy_cena_relations_on_saveasnew_copy_ceny_deactivate(request, new_predpis)
        self.admin._copy_cena_relations_on_saveasnew_copy_ceny_deactivate(request, new_predpis)

        self.assertTrue(cena_1.predpis.filter(pk=new_predpis.pk).exists())
        self.assertTrue(cena_2.predpis.filter(pk=new_predpis.pk).exists())

        through_model = Cena.predpis.through
        self.assertEqual(
            through_model.objects.filter(cena_id=cena_1.pk, predpis_id=new_predpis.pk).count(),
            1,
        )
        self.assertEqual(
            through_model.objects.filter(cena_id=cena_2.pk, predpis_id=new_predpis.pk).count(),
            1,
        )

    def test_saveasnew_can_deactivate_source_predpis(self):
        source_predpis = Predpis.objects.create(
            nazev='P-SRC-ACTIVE',
            skupina=1,
            zakaznik=self.zakaznik,
            aktivni=True,
        )
        new_predpis = Predpis.objects.create(
            nazev='P-NEW-ACTIVE',
            skupina=1,
            zakaznik=self.zakaznik,
            aktivni=True,
        )

        request = self.factory.post(
            f'/admin/orders/predpis/{source_predpis.pk}/change/',
            data={'_saveasnew_copy_ceny_deactivate': '1'},
        )
        request.user = self.user
        request.resolver_match = SimpleNamespace(kwargs={'object_id': str(source_predpis.pk)})

        self.admin._deactivate_source_predpis_on_saveasnew_copy_ceny_deactivate(request, new_predpis)
        source_predpis.refresh_from_db()

        self.assertFalse(source_predpis.aktivni)


class CenaAdminTests(AdminBase):
    def setUp(self):
        self.admin = CenaAdmin(Cena, self.site)
        self.cena = Cena.objects.create(
            popis='CENA-TEST',
            zakaznik=self.zakaznik,
            delka_min=Decimal('10.0'),
            delka_max=Decimal('20.0'),
            cena_za_kg=Decimal('1.00'),
            cena_rovnani_za_kg=Decimal('2.00'),
            cena_tryskani_za_kg=Decimal('3.00'),
        )

    def test_changelist_view_post_touched_markers_save_only_touched_fields(self):
        cena_instance = self.cena
        original_rovnani = self.cena.cena_rovnani_za_kg

        req = self.factory.post(
            '/',
            {
                'form-TOTAL_FORMS': '1',
                '_save': 'Uložit',
                '_touched_enabled': '1',
                '_touched_field': ['form-0-cena_za_kg'],
            },
        )
        req.user = self.user
        req.session = DummySession()
        req._messages = FallbackStorage(req)

        class DummyForm:
            def __init__(self, instance):
                self.instance = instance
                self.prefix = 'form-0'
                self.changed_data = ['cena_za_kg', 'cena_rovnani_za_kg']
                self.cleaned_data = {
                    'cena_za_kg': Decimal('1.25'),
                    'cena_rovnani_za_kg': Decimal('2.50'),
                }
                self.initial = {
                    'cena_za_kg': instance.cena_za_kg,
                    'cena_rovnani_za_kg': original_rovnani,
                }

            def has_changed(self):
                return True

        class DummyFormSet:
            def __init__(self, *args, **kwargs):
                self.forms = [DummyForm(cena_instance)]

            @staticmethod
            def get_default_prefix():
                return 'form'

            def is_valid(self):
                return True

        with patch.object(self.admin, 'get_changelist_formset', return_value=DummyFormSet):
            response = self.admin.changelist_view(req)

        self.assertEqual(response.status_code, 302)
        self.cena.refresh_from_db()
        self.assertEqual(self.cena.cena_za_kg, Decimal('1.25'))
        self.assertEqual(self.cena.cena_rovnani_za_kg, original_rovnani)

    def test_changelist_includes_dirty_guard_script(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('admin:orders_cena_changelist'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'orders/js/changelist_dirty_guard.js')

