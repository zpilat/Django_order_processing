from decimal import Decimal
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.messages import get_messages
from django.http import HttpResponse
from unittest.mock import patch

from orders.utils import (
    get_verbose_name_for_column,
    utilita_tisk_dokumentace,
    utilita_expedice_zakazek,
    utilita_kontrola_zakazek,
    utilita_zkraceni_popisu_beden,
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


class UtilitaExpediceZakazekTests(UtilsBase):
    def test_expedice_beden(self):
        self.bedna1.stav_bedny = StavBednyChoice.K_EXPEDICI
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
        self.bedna1.stav_bedny = StavBednyChoice.K_EXPEDICI
        self.bedna1.save()
        req = self.get_request('post')
        utilita_kontrola_zakazek(None, req, Zakazka.objects.filter(id=self.zakazka.id))
        msgs = list(get_messages(req))
        self.assertEqual(len(msgs), 1)
        self.assertIn('Pouze kompletní zakázky', msgs[0].message)


class UtilitaZkraceniPopisuTests(UtilsBase):
    def test_zkraceni_popisu(self):
        self.zakazka.popis = 'abc def 1234 xxx'
        utilita_zkraceni_popisu_beden(self.bedna1)
        self.assertEqual(self.zakazka.popis, 'abc def')