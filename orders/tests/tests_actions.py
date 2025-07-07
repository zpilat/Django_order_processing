from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.admin.sites import AdminSite
from django.http import HttpResponse
from unittest.mock import patch
from datetime import date

from orders.models import (
    Zakaznik, Kamion, Zakazka, Bedna, Predpis, TypHlavy,
    Odberatel
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
        cls.bedna = Bedna.objects.create(zakazka=cls.zakazka, hmotnost=1, tara=1)

    def get_request(self, method='get', data=None):
        req = getattr(self.factory, method)('/', data or {})
        req.user = self.user
        req.session = {}
        req._messages = FallbackStorage(req)
        return req


class ActionsTests(ActionsBase):
    @patch('orders.actions.utilita_tisk_dokumentace')
    def test_tisk_karet_beden_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        req = self.get_request()
        qs = Bedna.objects.all()
        resp = actions.tisk_karet_beden_action(None, req, qs)
        mock_util.assert_called_once_with(None, req, qs,
                                          'orders/karta_bedny_eur.html', 'karty_beden.pdf')
        self.assertIsInstance(resp, HttpResponse)

    def test_tisk_karet_beden_action_empty(self):
        resp = actions.tisk_karet_beden_action(None, self.get_request(), Bedna.objects.none())
        self.assertIsNone(resp)

    @patch('orders.actions.utilita_tisk_dokumentace')
    def test_tisk_karet_kontroly_kvality_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        resp = actions.tisk_karet_kontroly_kvality_action(None, self.get_request(), Bedna.objects.all())
        mock_util.assert_called_once()
        self.assertIsInstance(resp, HttpResponse)

    @patch('orders.actions.utilita_expedice_zakazek')
    @patch('orders.actions.utilita_kontrola_zakazek')
    def test_expedice_zakazek_action(self, mock_kontrola, mock_expedice):
        data = {'apply': '1', 'odberatel': self.odberatel.id}
        req = self.get_request('post', data)
        with patch('orders.actions.Kamion.objects.create', return_value=self.kamion_vydej) as mock_create:
            resp = actions.expedice_zakazek_action(None, req, Zakazka.objects.all())
        self.assertIsNone(resp)
        mock_create.assert_called()
        mock_expedice.assert_called()

    def test_expedice_zakazek_action_empty(self):
        resp = actions.expedice_zakazek_action(None, self.get_request('post'), Zakazka.objects.none())
        self.assertIsNone(resp)

    @patch('orders.actions.utilita_expedice_zakazek')
    @patch('orders.actions.utilita_kontrola_zakazek')
    def test_expedice_zakazek_kamion_action(self, mock_kontrola, mock_expedice):
        data = {'apply': '1', 'kamion': self.kamion_vydej.id}
        req = self.get_request('post', data)
        qs = Zakazka.objects.all()
        resp = actions.expedice_zakazek_kamion_action(None, req, qs)
        self.assertIsNone(resp)
        mock_expedice.assert_called_with(None, req, qs, self.kamion_vydej)

    @patch('orders.actions.utilita_tisk_dokumentace')
    def test_tisk_karet_beden_zakazek_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        resp = actions.tisk_karet_beden_zakazek_action(None, self.get_request(), Zakazka.objects.all())
        self.assertIsInstance(resp, HttpResponse)

    @patch('orders.actions.utilita_tisk_dokumentace')
    def test_tisk_karet_kontroly_kvality_zakazek_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        resp = actions.tisk_karet_kontroly_kvality_zakazek_action(None, self.get_request(), Zakazka.objects.all())
        self.assertIsInstance(resp, HttpResponse)

    def test_vratit_zakazky_z_expedice_action(self):
        self.zakazka.expedovano = True
        self.zakazka.kamion_vydej = self.kamion_vydej
        self.zakazka.save()
        actions.vratit_zakazky_z_expedice_action(None, self.get_request('post'), Zakazka.objects.all())
        self.zakazka.refresh_from_db()
        self.assertFalse(self.zakazka.expedovano)
        self.assertIsNone(self.zakazka.kamion_vydej)
        self.assertEqual(self.zakazka.bedny.first().stav_bedny, StavBednyChoice.K_EXPEDICI)

    def test_import_kamionu_action(self):
        kamion = Kamion.objects.create(zakaznik=self.zakaznik, datum=date.today())
        resp = actions.import_kamionu_action(self.site, self.get_request('post'), Kamion.objects.filter(id=kamion.id))
        self.assertIsNotNone(resp)

    @patch('orders.actions.utilita_tisk_dl_a_proforma_faktury')
    def test_tisk_dodaciho_listu_kamionu_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        resp = actions.tisk_dodaciho_listu_kamionu_action(self.site, self.get_request(), Kamion.objects.filter(id=self.kamion_vydej.id))
        self.assertIsInstance(resp, HttpResponse)

    @patch('orders.actions.utilita_tisk_dl_a_proforma_faktury')
    def test_tisk_proforma_faktury_kamionu_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        resp = actions.tisk_proforma_faktury_kamionu_action(self.site, self.get_request(), Kamion.objects.filter(id=self.kamion_vydej.id))
        self.assertIsInstance(resp, HttpResponse)

    @patch('orders.actions.utilita_tisk_dokumentace')
    def test_tisk_karet_beden_kamionu_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        resp = actions.tisk_karet_beden_kamionu_action(None, self.get_request(), Kamion.objects.filter(id=self.kamion_prijem.id))
        self.assertIsInstance(resp, HttpResponse)

    @patch('orders.actions.utilita_tisk_dokumentace')
    def test_tisk_karet_kontroly_kvality_kamionu_action(self, mock_util):
        mock_util.return_value = HttpResponse('ok')
        resp = actions.tisk_karet_kontroly_kvality_kamionu_action(None, self.get_request(), Kamion.objects.filter(id=self.kamion_prijem.id))
        self.assertIsInstance(resp, HttpResponse)