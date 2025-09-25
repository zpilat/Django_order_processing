from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.urls import reverse

from orders.models import (
    Zakaznik,
    Odberatel,
    Kamion,
    Predpis,
    TypHlavy,
    Zakazka,
    Cena,
    Bedna,
)
from orders.choices import StavBednyChoice, KamionChoice


class ModelsBase(TestCase):
    """
    Základní třída pro testy modelů.
    Obsahuje metodu setUpTestData, která vytvoří potřebné instance modelů.
    Tato metoda se spustí jednou před všemi testy v této třídě.
    """
    @classmethod
    def setUpTestData(cls):
        cls.zakaznik = Zakaznik.objects.create(
            nazev="Eurotec",
            zkraceny_nazev="EUR",
            zkratka="EUR",
            ciselna_rada=100000,
        )
        cls.kamion_prijem = Kamion.objects.create(
            zakaznik=cls.zakaznik,
            datum=date.today(),
            prijem_vydej=KamionChoice.PRIJEM,
        )
        cls.kamion_vydej = Kamion.objects.create(
            zakaznik=cls.zakaznik,
            datum=date.today(),
            prijem_vydej=KamionChoice.VYDEJ,
        )
        cls.predpis = Predpis.objects.create(
            nazev="P1",
            skupina=1,
            zakaznik=cls.zakaznik,
        )
        cls.typ_hlavy = TypHlavy.objects.create(nazev="TH")
        cls.cena = Cena.objects.create(
            popis="C",
            zakaznik=cls.zakaznik,
            delka_min=Decimal("50"),
            delka_max=Decimal("150"),
            cena_za_kg=Decimal("2.00"),
        )
        cls.cena.predpis.add(cls.predpis)
        cls.zakazka = Zakazka.objects.create(
            kamion_prijem=cls.kamion_prijem,
            kamion_vydej=cls.kamion_vydej,
            artikl="A1",
            prumer=Decimal("10"),
            delka=Decimal("100"),
            predpis=cls.predpis,
            typ_hlavy=cls.typ_hlavy,
            popis="Test",
        )
        cls.bedna1 = Bedna.objects.create(
            zakazka=cls.zakazka,
            hmotnost=Decimal("2"),
            tara=Decimal("1"),
        )
        cls.bedna2 = Bedna.objects.create(
            zakazka=cls.zakazka,
            hmotnost=Decimal("2"),
            tara=Decimal("1"),
        )


class TestModels(ModelsBase):
    """
    Testy pro modely v aplikaci orders.
    Tato třída dědí z ModelsBase, která obsahuje metodu setUpTestData,
    která vytvoří potřebné instance modelů.
    Testy ověřují základní funkčnost modelů, jako jsou metody a vlastnosti.
    """
    def test_zakaznik_str(self):
        self.assertEqual(str(self.zakaznik), self.zakaznik.zkraceny_nazev)

    def test_kamion_celkova_hmotnost_netto(self):
        self.assertEqual(
            self.kamion_prijem.celkova_hmotnost_netto,
            Decimal("4.0"),
        )

    def test_kamion_celkova_hmotnost_brutto(self):
        self.assertEqual(
            self.kamion_prijem.celkova_hmotnost_brutto,
            Decimal("6.0"),
        )

    def test_zakazka_cena_za_zakazku_a_kg(self):
        self.assertEqual(self.zakazka.cena_za_zakazku, Decimal("8.00"))
        self.assertEqual(self.zakazka.cena_za_kg, Decimal("2.00"))

    def test_kamion_cena_za_kamion_vydej(self):
        self.assertEqual(self.kamion_vydej.cena_za_kamion_vydej, Decimal("8.00"))

    def test_bedna_poradi_bedny(self):
        self.assertEqual(self.bedna2.poradi_bedny, 2)

    def test_allowed_stav_bedny_choices(self):
        choices = self.bedna1.get_allowed_stav_bedny_choices()
        # Nově je výchozí stav NEPRIJATO, takže počáteční dvojice odpovídá NEPRIJATO -> PRIJATO
        self.assertEqual(
            choices[:2],
            [
                (StavBednyChoice.NEPRIJATO, "Nepřijato"),
                (StavBednyChoice.PRIJATO, "Přijato"),
            ],
        )

    def test_bedna_cena_za_bednu(self):
        self.assertEqual(self.bedna1.cena_za_bednu, Decimal("4.00"))

    def test_get_admin_url(self):
        url = reverse("admin:orders_kamion_change", args=[self.kamion_prijem.pk])
        self.assertEqual(self.kamion_prijem.get_admin_url(), url)