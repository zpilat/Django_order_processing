from decimal import Decimal
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.messages import get_messages
from django.http import HttpResponse
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
import csv
import io

from orders.utils import (
    get_verbose_name_for_column,
    utilita_tisk_dokumentace,
    utilita_tisk_dokumentace_sablony,
    utilita_tisk_dl_a_proforma_faktury,
    utilita_expedice_zakazek,
    utilita_expedice_beden,
    utilita_kontrola_zakazek,
    utilita_validate_excel_upload,
    utilita_export_beden_zinkovani_csv,
    validate_bedny_pripraveny_k_expedici,
)
from orders.models import Bedna, Zakazka, Kamion
from orders.choices import StavBednyChoice, KamionChoice, ZinkovaniChoice
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
        qs = Bedna.objects.all()
        mock_render.side_effect = ['H'] * qs.count()
        mock_pdf.return_value = b'PDF'
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
            puvodni_kamion_vydej = self.zakazka.kamion_vydej
            qs = Zakazka.objects.filter(id=self.zakazka.id)
            utilita_expedice_zakazek(None, self.get_request('post'), qs, kamion)

            self.bedna1.refresh_from_db()
            self.bedna2.refresh_from_db()
            self.zakazka.refresh_from_db()

            self.assertEqual(self.bedna1.stav_bedny, StavBednyChoice.EXPEDOVANO)
            # Neexpedované bedny zůstávají v původní zakázce (nemění se zakazka ani stav)
            self.assertEqual(self.bedna2.zakazka, self.zakazka)
            # Původní zakázka zůstává neexpedovaná, kamion_vydej zůstává původní
            self.assertFalse(self.zakazka.expedovano)
            self.assertEqual(self.zakazka.kamion_vydej, puvodni_kamion_vydej)

            nove_zakazky = Zakazka.objects.exclude(id=self.zakazka.id)
            self.assertTrue(nove_zakazky.exists())
            nova = nove_zakazky.latest('id')
            self.assertEqual(nova.kamion_vydej, kamion)
            self.assertTrue(nova.expedovano)
            self.assertEqual(self.bedna1.zakazka, nova)


class UtilitaExpediceBedenTests(UtilsBase):
    def _create_bedna(self, state, zakazka=None):
        return Bedna.objects.create(
            zakazka=zakazka or self.zakazka,
            hmotnost=Decimal("1"),
            tara=Decimal("0.5"),
            mnozstvi=1,
            stav_bedny=state,
        )

    def test_utilita_expedice_beden_partial_split(self):
        # Připrav dvě bedny k expedici a jednu ponech neexpedovanou
        self.bedna1.stav_bedny = StavBednyChoice.K_EXPEDICI
        self.bedna1.save()
        self.bedna2.stav_bedny = StavBednyChoice.K_EXPEDICI
        self.bedna2.save()
        treti = self._create_bedna(StavBednyChoice.PRIJATO)

        self.zakazka.kamion_vydej = None
        self.zakazka.expedovano = False
        self.zakazka.save()

        kamion = Kamion.objects.create(
            zakaznik=self.zakaznik,
            datum=self.kamion_prijem.datum,
            prijem_vydej=KamionChoice.VYDEJ,
        )
        puvodni_kamion_vydej = self.zakazka.kamion_vydej
        qs = Bedna.objects.filter(id__in=[self.bedna1.id, self.bedna2.id])

        utilita_expedice_beden(None, self.get_request('post'), qs, kamion)

        self.bedna1.refresh_from_db()
        self.bedna2.refresh_from_db()
        treti.refresh_from_db()
        self.zakazka.refresh_from_db()

        self.assertEqual(self.bedna1.stav_bedny, StavBednyChoice.EXPEDOVANO)
        self.assertEqual(self.bedna2.stav_bedny, StavBednyChoice.EXPEDOVANO)
        self.assertEqual(treti.stav_bedny, StavBednyChoice.PRIJATO)
        # Původní zakázka zůstává s neexpedovanou bednou, kamion_vydej zůstává původní
        self.assertEqual(self.zakazka.kamion_vydej, puvodni_kamion_vydej)
        self.assertFalse(self.zakazka.expedovano)

        nove_zakazky = Zakazka.objects.exclude(id=self.zakazka.id)
        self.assertTrue(nove_zakazky.exists())
        nova = nove_zakazky.latest('id')
        # Expedované bedny jsou v nové zakázce s kamionem a expedičním příznakem
        self.assertEqual(nova.kamion_vydej, kamion)
        self.assertTrue(nova.expedovano)
        self.assertEqual(self.bedna1.zakazka, nova)
        self.assertEqual(self.bedna2.zakazka, nova)
        # Neexpedovaná bedna zůstává v původní zakázce
        self.assertEqual(treti.zakazka, self.zakazka)

    def test_utilita_expedice_beden_partial_selection_mixes(self):
        # Tři bedny K_EXPEDICI, vybereme jen jednu => expeduji se 1, dvě se přesunou do nové zakázky
        b1 = self._create_bedna(StavBednyChoice.K_EXPEDICI)
        b2 = self._create_bedna(StavBednyChoice.K_EXPEDICI)
        b3 = self._create_bedna(StavBednyChoice.K_EXPEDICI)

        kamion = Kamion.objects.create(
            zakaznik=self.zakaznik,
            datum=self.kamion_prijem.datum,
            prijem_vydej=KamionChoice.VYDEJ,
        )
        puvodni_kamion_vydej = self.zakazka.kamion_vydej

        qs = Bedna.objects.filter(id__in=[b1.id])
        utilita_expedice_beden(None, self.get_request('post'), qs, kamion)

        for bedna in (b1, b2, b3):
            bedna.refresh_from_db()
        self.zakazka.refresh_from_db()

        self.assertEqual(b1.stav_bedny, StavBednyChoice.EXPEDOVANO)
        self.assertEqual(b2.stav_bedny, StavBednyChoice.K_EXPEDICI)
        self.assertEqual(b3.stav_bedny, StavBednyChoice.K_EXPEDICI)
        # Původní zakázka zůstává s neexpedovanými bednami
        self.assertEqual(self.zakazka.kamion_vydej, puvodni_kamion_vydej)
        self.assertFalse(self.zakazka.expedovano)

        nove_zakazky = Zakazka.objects.exclude(id=self.zakazka.id)
        self.assertTrue(nove_zakazky.exists())
        nova = nove_zakazky.latest('id')
        # Expedovaná bedna je v nové zakázce s kamionem
        self.assertEqual(nova.kamion_vydej, kamion)
        self.assertTrue(nova.expedovano)
        self.assertEqual(b1.zakazka, nova)
        # Neexpedované bedny zůstávají v původní zakázce
        self.assertEqual(b2.zakazka, self.zakazka)
        self.assertEqual(b3.zakazka, self.zakazka)


class UtilitaZinkovaniTests(UtilsBase):
    def test_utilita_export_beden_zinkovani_csv_format(self):
        self.zakazka.popis = 'Popis Z'
        self.zakazka.vrstva = 'V1'
        self.zakazka.povrch = 'Zn'
        self.zakazka.save(update_fields=['popis', 'vrstva', 'povrch'])

        bedna = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal('2.50'),
            tara=Decimal('1'),
            mnozstvi=3,
            cislo_bedny=5,
        )

        resp = utilita_export_beden_zinkovani_csv(Bedna.objects.filter(id=bedna.id))
        self.assertIsInstance(resp, HttpResponse)

        rows = list(csv.reader(io.StringIO(resp.content.decode('utf-8-sig')), delimiter=';'))
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(rows[1][0], str(bedna.cislo_bedny))
        self.assertEqual(rows[1][1], '')
        self.assertEqual(rows[1][2], '')
        self.assertEqual(rows[1][3], 'Popis Z')
        self.assertEqual(rows[1][4], self.zakazka.artikl)
        self.assertEqual(rows[1][5], '10.0 x 100.0')
        self.assertEqual(rows[1][6], '2,5')
        self.assertEqual(rows[1][7], '3')
        self.assertEqual(rows[1][8], 'V1')
        self.assertEqual(rows[1][9], 'Zn')

    def test_validate_bedny_pripraveny_k_expedici_rejects_invalid_zinkovani(self):
        class _Admin:
            def __init__(self):
                self.messages = []

            def message_user(self, request, message, level=None):
                self.messages.append(message)

        admin_obj = _Admin()
        req = self.get_request('post')

        Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal('1'),
            tara=Decimal('1'),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.K_EXPEDICI,
            zinkovat=ZinkovaniChoice.ZINKOVAT,
        )

        ok = validate_bedny_pripraveny_k_expedici(admin_obj, req, Bedna.objects.all())
        self.assertFalse(ok)
        self.assertTrue(any('zinkování' in msg for msg in admin_obj.messages))

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