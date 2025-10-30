from decimal import Decimal
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.messages import get_messages
from django.http import HttpResponse
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile

from orders.utils import (
    get_verbose_name_for_column,
    utilita_tisk_dokumentace,
    utilita_tisk_dokumentace_sablony,
    utilita_tisk_dl_a_proforma_faktury,
    utilita_expedice_zakazek,
    utilita_kontrola_zakazek,
    utilita_validate_excel_upload,
)
from orders.models import Bedna, Zakazka, Kamion
from orders.choices import StavBednyChoice, KamionChoice
from .tests_models import ModelsBase
from django.conf import settings


class UtilsBase(ModelsBase):
    """
    Základní třída pro testy utilit v aplikaci orders.
    Obsahuje nastavení a pomocné metody pro testování.
    """
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.factory = RequestFactory()
        User = get_user_model()
        cls.user = User.objects.create_superuser('admin', 'a@example.com', 'pass')
        settings.SECRET_KEY = 'test'

    def get_request(self, method='get', data=None):
        req = getattr(self.factory, method)('/', data or {})
        req.user = self.user
        req.session = {}
        req._messages = FallbackStorage(req)
        return req


class GetVerboseNameTests(UtilsBase):
    def test_nested_verbose_name(self):
        name = get_verbose_name_for_column(
            Bedna,
            'zakazka__kamion_prijem__zakaznik__nazev'
        )
        self.assertEqual(name, 'Název zákazníka')
        self.assertEqual(
            get_verbose_name_for_column(Bedna, 'zakazka__kamion_prijem__datum'),
            'Datum'
        )


class UtilitaTiskDokumentaceTests(UtilsBase):
    @patch('orders.utils.render_to_string')
    @patch('orders.utils.HTML.write_pdf')
    def test_tisk_dokumentace(self, mock_pdf, mock_render):
        mock_render.side_effect = ['H1', 'H2']
        mock_pdf.return_value = b'PDF'
        qs = Bedna.objects.all()
        resp = utilita_tisk_dokumentace(
            None,
            self.get_request(),
            qs,
            'path.html',
            'file.pdf'
        )
        self.assertIsInstance(resp, HttpResponse)
        self.assertEqual(resp.content, b'PDF')
        self.assertEqual(mock_render.call_count, qs.count())
        mock_pdf.assert_called_once()

    def test_tisk_dokumentace_empty_queryset(self):
        req = self.get_request()
        resp = utilita_tisk_dokumentace(
            None,
            req,
            Bedna.objects.none(),
            'path.html',
            'file.pdf'
        )
        # Vrací None a zapíše chybovou hlášku
        self.assertIsNone(resp)
        msgs = list(get_messages(req))
        self.assertEqual(len(msgs), 1)
        self.assertIn('Není vybrána žádná bedna k tisku', msgs[0].message)

    @patch('orders.utils.render_to_string')
    @patch('orders.utils.HTML.write_pdf')
    def test_tisk_dokumentace_sablony(self, mock_pdf, mock_render):
        qs = Bedna.objects.all()
        mock_render.side_effect = ['A', 'B'] * qs.count()
        mock_pdf.return_value = b'PDF'
        resp = utilita_tisk_dokumentace_sablony(
            None,
            self.get_request(),
            qs,
            ['path-one.html', 'path-two.html'],
            'combined.pdf',
        )
        self.assertIsInstance(resp, HttpResponse)
        self.assertEqual(resp.content, b'PDF')
        # Dvakrát volání renderu na jednu bednu a dvě šablony
        self.assertEqual(mock_render.call_count, qs.count() * 2)
        mock_pdf.assert_called_once()

    def test_tisk_dokumentace_sablony_missing_templates(self):
        req = self.get_request()
        resp = utilita_tisk_dokumentace_sablony(
            None,
            req,
            Bedna.objects.all(),
            [],
            'combined.pdf',
        )
        self.assertIsNone(resp)
        msgs = list(get_messages(req))
        self.assertEqual(len(msgs), 1)
        self.assertIn('Není k dispozici žádná šablona pro tisk dokumentace.', msgs[0].message)


class UtilitaTiskDLProformaTests(UtilsBase):
    @patch('orders.utils.render_to_string')
    @patch('orders.utils.HTML.write_pdf')
    def test_tisk_dl_a_proforma(self, mock_pdf, mock_render):
        mock_render.return_value = 'HTML'
        mock_pdf.return_value = b'PDF2'
        req = self.get_request()
        resp = utilita_tisk_dl_a_proforma_faktury(
            None,
            req,
            self.kamion_prijem,
            'tpl.html',
            'doklad.pdf'
        )
        self.assertIsInstance(resp, HttpResponse)
        self.assertEqual(resp.content, b'PDF2')
        self.assertIn('inline; filename="doklad.pdf"', resp['Content-Disposition'])
        mock_render.assert_called_once()
        mock_pdf.assert_called_once()


class UtilitaExpediceZakazekTests(UtilsBase):
    def test_expedice_beden(self):
        self.bedna1 = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal(2),
            tara=Decimal(1),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.K_EXPEDICI,
        )
        self.bedna1.save()

        original_create = Zakazka.objects.create
        def create_wrapper(**kwargs):
            if 'predpis' in kwargs:
                kwargs['predpis_id'] = kwargs.pop('predpis')
            if 'typ_hlavy' in kwargs:
                kwargs['typ_hlavy_id'] = kwargs.pop('typ_hlavy')
            return original_create(**kwargs)

        with patch('orders.utils.Zakazka.objects.create', side_effect=create_wrapper):
            kamion = Kamion.objects.create(
                zakaznik=self.zakaznik,
                datum=self.kamion_prijem.datum,
                prijem_vydej=KamionChoice.VYDEJ
            )
            qs = Zakazka.objects.filter(id=self.zakazka.id)
            utilita_expedice_zakazek(None, self.get_request('post'), qs, kamion)

            self.bedna1.refresh_from_db()
            self.bedna2.refresh_from_db()
            self.zakazka.refresh_from_db()

            self.assertEqual(self.bedna1.stav_bedny, StavBednyChoice.EXPEDOVANO)
            self.assertNotEqual(self.bedna2.zakazka, self.zakazka)
            self.assertTrue(self.zakazka.expedovano)
            self.assertEqual(self.zakazka.kamion_vydej, kamion)


class UtilitaKontrolaZakazekTests(UtilsBase):
    def test_no_bedny(self):
        zak = Zakazka.objects.create(
            kamion_prijem=self.kamion_prijem,
            artikl='A2', prumer=Decimal('1'), delka=Decimal('1'),
            predpis=self.predpis, typ_hlavy=self.typ_hlavy,
            popis='p'
        )
        req = self.get_request('post')
        utilita_kontrola_zakazek(None, req, Zakazka.objects.filter(id=zak.id))
        msgs = list(get_messages(req))
        self.assertEqual(len(msgs), 1)
        self.assertIn('nemá žádné bedny', msgs[0].message)

    def test_no_k_expedici(self):
        req = self.get_request('post')
        utilita_kontrola_zakazek(None, req, Zakazka.objects.filter(id=self.zakazka.id))
        msgs = list(get_messages(req))
        self.assertEqual(len(msgs), 1)
        self.assertIn('nemá žádné bedny ve stavu K_EXPEDICI', msgs[0].message)

    def test_pouze_komplet(self):
        self.zakaznik.pouze_komplet = True
        self.zakaznik.save()
        self.bedna1 = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal(2),
            tara=Decimal(1),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.K_EXPEDICI,
        )
        self.bedna1.save()
        req = self.get_request('post')
        utilita_kontrola_zakazek(None, req, Zakazka.objects.filter(id=self.zakazka.id))
        msgs = list(get_messages(req))
        self.assertEqual(len(msgs), 1)
        self.assertIn('Pouze kompletní zakázky', msgs[0].message)

    def test_ok_when_has_at_least_one_k_expedici(self):
        # Bez příznaku pouze_komplet a s 1 bednou v K_EXPEDICI → bez chybové hlášky
        b = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal(1),
            tara=Decimal(1),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.K_EXPEDICI,
        )
        req = self.get_request('post')
        utilita_kontrola_zakazek(None, req, Zakazka.objects.filter(id=self.zakazka.id))
        msgs = list(get_messages(req))
        self.assertEqual(len(msgs), 0)

    def test_ok_when_pouze_komplet_and_all_k_expedici(self):
        # S příznakem pouze_komplet a všechny bedny v K_EXPEDICI → bez chybové hlášky
        self.zakaznik.pouze_komplet = True
        self.zakaznik.save()
        Bedna.objects.filter(zakazka=self.zakazka).update(stav_bedny=StavBednyChoice.K_EXPEDICI)
        req = self.get_request('post')
        utilita_kontrola_zakazek(None, req, Zakazka.objects.filter(id=self.zakazka.id))
        msgs = list(get_messages(req))
        self.assertEqual(len(msgs), 0)


class UtilsTests(UtilsBase):
    def test_zkraceny_popis_property(self):
        # Zakázka s číslem v popisu → vrátí text do prvního výskytu čísla
        z = self.zakazka
        z.popis = "Očekávaný zkrácený text 123 další část"
        self.assertEqual(z.zkraceny_popis, "Očekávaný zkrácený text")

    def test_zkraceny_popis_property_bez_cisla(self):
        # Zakázka bez čísla v popisu → vrátí celý text
        z = self.zakazka
        z.popis = "Celý popis bez čísel"
        self.assertEqual(z.zkraceny_popis, "Celý popis bez čísel")