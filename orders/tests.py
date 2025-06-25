from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile

from datetime import date
from unittest.mock import patch

from orders.admin import KamionAdmin, ZakazkaAdmin, BednaAdmin
from orders.models import Zakaznik, Kamion, Zakazka, Bedna, Predpis
from orders.choices import StavBednyChoice, TypHlavyChoice


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
            nazev='Test', zkraceny_nazev='T', zkratka='TST', ciselna_rada=100000
        )
        cls.kamion = Kamion.objects.create(zakaznik=cls.zakaznik, datum=date.today())
        cls.predpis = Predpis.objects.create(nazev='Test Predpis', skupina=1, zakaznik=cls.zakaznik,)


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
        return req

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
            typ_hlavy=TypHlavyChoice.TK,
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
        self.assertNotIn('misto_expedice', fields_add)

        self.kamion.prijem_vydej = 'P'
        fields_edit = self.admin.get_fields(self.get_request(), self.kamion)
        self.assertNotIn('misto_expedice', fields_edit)
        self.assertIn('prijem_vydej', fields_edit)

        self.kamion.prijem_vydej = 'V'
        fields_edit = self.admin.get_fields(self.get_request(), self.kamion)
        self.assertIn('misto_expedice', fields_edit)

        rof_add = self.admin.get_readonly_fields(self.get_request(), None)
        self.assertEqual(rof_add, ['prijem_vydej'])
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


        df_data = {
            'Abhol- datum': ['2024-01-01'],
            'Abmessung': ['10 x 50'],
            'Bezeichnung': ['desc 1'],
            'Sonder / Zusatzinfo': [''],
            'Artikel- nummer': ['A1'],
            'n. Zg. / as drg': ['123'],
            'Material- charge': ['M1'],
            'Material': ['steel'],
            'Ober- fläche': ['ZP'],
            'Gewicht in kg': [1],
            'Tara kg': [1],
            'Behälter-Nr.:': [1],
            'Lief.': ['L1'],
            'Fertigungs- aftrags Nr.': ['F1'],
            'Typ hlavy': ['TK'],  # přidáno
        }
        import pandas as pandas_mod
        df = pandas_mod.DataFrame(df_data)
        file_mock = SimpleUploadedFile('f.xlsx', b'fakecontent', content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        valid_req = self.get_request('post', data={'file': file_mock}, path=url)
        valid_req.FILES['file'] = file_mock

        # Mockni _messages storage
        valid_req.session = {}
        valid_req._messages = FallbackStorage(valid_req)

        with patch('orders.admin.pd.read_excel', return_value=df):
            resp = self.admin.import_view(valid_req)

        self.assertEqual(resp.status_code, 302)

    def test_save_formset_creates_bedny(self):
        admin_form = type('F', (), {'instance': self.kamion})()

        zak = Zakazka(
            artikl='A1', prumer=1, delka=1,
            predpis=self.predpis, typ_hlavy=TypHlavyChoice.TK,
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
            predpis=cls.predpis, typ_hlavy=TypHlavyChoice.TK,
            popis='p'
        )
        cls.bedna = Bedna.objects.create(
            zakazka=cls.zakazka,
            hmotnost=1,
            tara=1,
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
        ld2 = self.admin.get_list_display(self.get_request({'skladem': '1'}))
        self.assertIn('kamion_vydej_link', ld2)

    def test_get_form_custom_choices(self):
        Form = self.admin.get_form(self.get_request(), self.zakazka)
        form = Form()
        prvni_bedna = self.zakazka.bedny.first()
        self.assertEqual(form.fields['stav_bedny'].initial, prvni_bedna.stav_bedny)


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
            predpis=cls.predpis, typ_hlavy=TypHlavyChoice.TK,
            popis='p'
        )
        cls.bedna = Bedna.objects.create(
            zakazka=cls.zakazka,
            hmotnost=1,
            tara=1,
        )

    def setUp(self):
        self.admin = BednaAdmin(Bedna, self.site)

    def get_request(self, params=None):
        req = self.factory.get('/', params or {})
        req.user = self.user
        return req

    def test_has_change_permission(self):
        perm = self.admin.has_change_permission(self.get_request(), self.bedna)
        self.assertTrue(perm)
        self.bedna.stav_bedny = StavBednyChoice.EXPEDOVANO
        perm = self.admin.has_change_permission(self.get_request(), self.bedna)
        self.assertFalse(perm)

    def test_changelist_view_and_list_display(self):
        req = self.get_request()
        self.admin.changelist_view(req)
        self.assertEqual(self.admin.list_editable, ('stav_bedny', 'rovnat', 'tryskat', 'poznamka'))

        req = self.get_request({'stav_bedny_vlastni': 'EX'})
        self.admin.changelist_view(req)
        self.assertEqual(self.admin.list_editable, ())

        ld = self.admin.get_list_display(self.get_request())
        self.assertNotIn('kamion_vydej_link', ld)
        ld2 = self.admin.get_list_display(self.get_request({'stav_bedny_vlastni': 'EX'}))
        self.assertIn('kamion_vydej_link', ld2)