from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile

from decimal import Decimal
from datetime import date
from unittest.mock import patch

from orders.admin import KamionAdmin, ZakazkaAdmin, BednaAdmin, BednaInline
from orders.models import Zakaznik, Kamion, Zakazka, Bedna, Predpis, TypHlavy, Odberatel, Cena
from orders.choices import StavBednyChoice


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
        cls.typ_hlavy = TypHlavy.objects.create(nazev='SK', popis='Zápustná hlava')


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
        self.assertEqual(rof_add, ['prijem_vydej', 'poradove_cislo'])
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

        df_data = {
            'Abhol- datum': ['2024-01-01'],
            'Unnamed: 7': ['10 x 50'],
            'Bezeichnung': ['desc 1'],
            'Sonder / Zusatzinfo': [''],
            'Artikel- nummer': ['A1'],
            'n. Zg. / \nas drg': ['123'],
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

        valid_req = self.get_request('post', data={'file': file_mock}, path=url)
        valid_req.FILES['file'] = file_mock

        # Mockni _messages storage
        valid_req.session = {}
        valid_req._messages = FallbackStorage(valid_req)

        with patch('orders.admin.pd.read_excel', return_value=df):
            zak_before = Zakazka.objects.count()
            bedna_before = Bedna.objects.count()
            resp = self.admin.import_view(valid_req)

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Zakazka.objects.count(), zak_before + 1)
        self.assertEqual(Bedna.objects.count(), bedna_before + 1)

        # cleanup created objects
        Zakazka.objects.all().delete()
        Bedna.objects.all().delete()
        predpis_import.delete()
        typ_hlavy_import.delete()

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
        ld2 = self.admin.get_list_display(self.get_request({'skladem': '1'}))
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

    def test_changelist_view_and_list_display(self):
        req = self.get_request()
        self.admin.changelist_view(req)
        # Nově zahrnujeme i 'tara' v inline editaci a defaultní sada obsahuje tato pole
        self.assertEqual(
            self.admin.list_editable,
            ['stav_bedny', 'tryskat', 'rovnat', 'hmotnost', 'tara', 'poznamka']
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
        for field in form.fields:
            self.assertTrue(form.fields[field].disabled)

        req = self.factory.get('/')
        req.user = user
        req.user.user_permissions.add(Permission.objects.get(codename='change_pozastavena_bedna'))
        req.user = User.objects.get(pk=req.user.pk)
        Formset = self.inline.get_formset(req, zakazka)
        fs = Formset(queryset=Bedna.objects.filter(id=bedna.id), instance=zakazka)
        form = fs.forms[0]
        for field in form.fields:
            self.assertFalse(form.fields[field].disabled)