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
    Pozice,
)
from orders.choices import (
    StavBednyChoice,
    KamionChoice,
    TryskaniChoice,
    RovnaniChoice,
)
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError


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
            cena_tryskani_za_kg=Decimal("0.50"),
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
            mnozstvi=1,
        )
        cls.bedna2 = Bedna.objects.create(
            zakazka=cls.zakazka,
            hmotnost=Decimal("2"),
            tara=Decimal("1"),
            mnozstvi=1,
        )

        cls.zakaznik_rot = Zakaznik.objects.create(
            nazev="Rot",
            zkraceny_nazev="ROT",
            zkratka="ROT",
            ciselna_rada=400000,
        )
        cls.kamion_prijem_rot = Kamion.objects.create(
            zakaznik=cls.zakaznik_rot,
            datum=date.today(),
            prijem_vydej=KamionChoice.PRIJEM,
        )
        cls.predpis_rot = Predpis.objects.create(
            nazev="P-ROT",
            skupina=1,
            zakaznik=cls.zakaznik_rot,
        )
        cls.cena_rot = Cena.objects.create(
            popis="C-ROT",
            zakaznik=cls.zakaznik_rot,
            delka_min=Decimal("50"),
            delka_max=Decimal("150"),
            cena_za_kg=Decimal("1.00"),
            cena_rovnani_za_kg=Decimal("0.30"),
        )
        cls.cena_rot.predpis.add(cls.predpis_rot)
        cls.zakazka_rot = Zakazka.objects.create(
            kamion_prijem=cls.kamion_prijem_rot,
            artikl="R1",
            prumer=Decimal("8"),
            delka=Decimal("100"),
            predpis=cls.predpis_rot,
            typ_hlavy=cls.typ_hlavy,
            popis="Rotování",
        )
        cls.bedna_rot1 = Bedna.objects.create(
            zakazka=cls.zakazka_rot,
            hmotnost=Decimal("3"),
            tara=Decimal("1"),
            mnozstvi=1,
            rovnat=RovnaniChoice.VYROVNANA,
        )
        cls.bedna_rot2 = Bedna.objects.create(
            zakazka=cls.zakazka_rot,
            hmotnost=Decimal("2"),
            tara=Decimal("1"),
            mnozstvi=1,
            rovnat=RovnaniChoice.VYROVNANA,
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

    # --- Pricing boundaries and non-EUR behavior ---
    def test_zakazka_cena_range_boundaries(self):
        # délka == min je zahrnuta
        z = Zakazka.objects.create(
            kamion_prijem=self.kamion_prijem,
            kamion_vydej=self.kamion_vydej,
            artikl="A2",
            prumer=Decimal("10"),
            delka=Decimal("50"),
            predpis=self.predpis,
            typ_hlavy=self.typ_hlavy,
            popis="Test",
        )
        self.assertEqual(z.cena_za_kg, Decimal("2.00"))

        # délka == max je vyjmutá (delka_max__gt)
        z2 = Zakazka.objects.create(
            kamion_prijem=self.kamion_prijem,
            artikl="A3",
            prumer=Decimal("10"),
            delka=Decimal("150"),
            predpis=self.predpis,
            typ_hlavy=self.typ_hlavy,
            popis="Test",
        )
        self.assertEqual(z2.cena_za_kg, 0)

    def test_pricing_for_non_eur_customer_is_zero(self):
        z = Zakaznik.objects.create(
            nazev="Other",
            zkraceny_nazev="OTH",
            zkratka="OTH",
            ciselna_rada=500000,
        )
        k = Kamion.objects.create(zakaznik=z, datum=date.today())
        pr = Predpis.objects.create(nazev="P2", skupina=1, zakaznik=z)
        th = TypHlavy.objects.create(nazev="TH2")
        zak = Zakazka.objects.create(
            kamion_prijem=k,
            artikl="B1",
            prumer=Decimal("5"),
            delka=Decimal("80"),
            predpis=pr,
            typ_hlavy=th,
            popis="x",
        )
        self.assertEqual(zak.cena_za_kg, 0)
        self.assertEqual(zak.cena_za_zakazku, 0)
        b = Bedna.objects.create(zakazka=zak, hmotnost=Decimal("2"), tara=Decimal("1"), mnozstvi=1)
        self.assertEqual(b.cena_za_bednu, 0)

    # --- Kamion aggregate/count behavior ---
    def test_kamion_pocet_beden_skladem_and_expedovano(self):
        # příjem: skladem = bedny na skladě (ne NEPRIJATO, ne EXPEDOVANO)
        # výchozí stav jsou 2× NEPRIJATO → skladem 0
        self.assertEqual(self.kamion_prijem.pocet_beden_skladem, 0)
        self.assertEqual(self.kamion_prijem.pocet_beden_expedovano, 0)

        # posun jedné bedny na PRIJATO → skladem 1
        self.bedna1.stav_bedny = StavBednyChoice.PRIJATO
        self.bedna1.save()
        self.assertEqual(self.kamion_prijem.pocet_beden_skladem, 1)

        # označíme stejnou bednu EXPEDOVANO → skladem 0, expedovano 1
        self.bedna1.stav_bedny = StavBednyChoice.EXPEDOVANO
        self.bedna1.save()
        self.assertEqual(self.kamion_prijem.pocet_beden_skladem, 0)
        self.assertEqual(self.kamion_prijem.pocet_beden_expedovano, 1)

        # výdej: všechny bedny v kamionu výdej se počítají jako expedované
        self.assertEqual(self.kamion_vydej.pocet_beden_expedovano, 2)

    def test_cena_model_stores_optional_pricing_fields(self):
        self.assertEqual(self.cena.cena_tryskani_za_kg, Decimal("0.50"))
        self.assertEqual(self.cena_rot.cena_rovnani_za_kg, Decimal("0.30"))

    def test_bedna_tryskani_pricing_for_eur_customer(self):
        self.bedna1.tryskat = TryskaniChoice.OTRYSKANA
        self.bedna1.save(update_fields=["tryskat"])
        self.bedna2.tryskat = TryskaniChoice.OTRYSKANA
        self.bedna2.save(update_fields=["tryskat"])

        self.assertEqual(self.bedna1.cena_tryskani_za_kg, Decimal("0.50"))
        self.assertEqual(self.bedna1.cena_tryskani_za_bednu, Decimal("1.00"))
        self.assertEqual(self.zakazka.cena_tryskani_za_zakazku, Decimal("2.00"))

    def test_bedna_rovnani_pricing_for_rot_customer(self):
        self.assertEqual(self.bedna_rot1.cena_rovnani_za_kg, Decimal("0.30"))
        self.assertEqual(self.bedna_rot1.cena_rovnani_za_bednu, Decimal("0.90"))
        self.assertEqual(self.zakazka_rot.cena_rovnani_za_zakazku, Decimal("1.50"))

    def test_kamion_hmotnost_otryskanych_beden(self):
        # ve výdeji: suma hmotností OTRYSKANA
        self.bedna1.tryskat = TryskaniChoice.OTRYSKANA
        self.bedna1.save()
        self.bedna2.tryskat = TryskaniChoice.OTRYSKANA
        self.bedna2.save()
        self.assertEqual(self.kamion_vydej.hmotnost_otryskanych_beden, Decimal("4.0"))

        # v příjmu by měla vyhodit ValidationError
        with self.assertRaises(ValidationError):
            _ = self.kamion_prijem.hmotnost_otryskanych_beden

    def test_kamion_invalid_type_raises_in_aggregates(self):
        k = Kamion.objects.create(zakaznik=self.zakaznik, datum=date.today())
        # Nastavíme do neplatného stavu a ověříme, že property hlásí ValidationError
        k.prijem_vydej = "X"
        with self.assertRaises(ValidationError):
            _ = k.celkova_hmotnost_netto
        with self.assertRaises(ValidationError):
            _ = k.celkova_hmotnost_brutto

    def test_kamion_vydej_sets_dl_number_on_create(self):
        # nový zákazník, aby poradové číslo začínalo od 1
        z = Zakaznik.objects.create(
            nazev="DLZ",
            zkraceny_nazev="DLZ",
            zkratka="DLZ",
            ciselna_rada=600000,
        )
        k = Kamion.objects.create(zakaznik=z, datum=date.today(), prijem_vydej=KamionChoice.VYDEJ)
        expected = f"EXP-001-{k.datum.year}-{z.zkratka}"
        self.assertEqual(k.cislo_dl, expected)

    # --- Zakazka delete guard ---
    def test_zakazka_delete_guard(self):
        # jedna bedna v PRIJATO → mazání zakázky blokováno
        self.bedna1.stav_bedny = StavBednyChoice.PRIJATO
        self.bedna1.full_clean()
        self.bedna1.save()
        with self.assertRaises(ProtectedError):
            self.zakazka.delete()

        # nastavíme všechny do NEPRIJATO → mazání povoleno
        for b in Bedna.objects.filter(zakazka=self.zakazka):
            b.stav_bedny = StavBednyChoice.NEPRIJATO
            b.save()
        self.zakazka.delete()
        self.assertFalse(Zakazka.objects.filter(id=self.zakazka.id).exists())

    # --- Bedna validations & constraints ---
    def test_bedna_clean_requires_tryskani_and_rovnani_for_k_expedici(self):
        b = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal("1"),
            tara=Decimal("1"),
            mnozstvi=1,
        )
        b.stav_bedny = StavBednyChoice.K_EXPEDICI
        b.tryskat = TryskaniChoice.NEZADANO
        b.rovnat = RovnaniChoice.NEZADANO
        with self.assertRaises(ValidationError):
            b.full_clean()

        # Nastavíme povolené kombinace, čisté by mělo projít
        b.tryskat = TryskaniChoice.CISTA
        b.rovnat = RovnaniChoice.ROVNA
        b.full_clean()  # nevyhodí výjimku

    def test_bedna_clean_requires_pozice_for_k_navezeni_and_navezeno(self):
        b = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal("1"),
            tara=Decimal("1"),
            mnozstvi=1,
        )
        b.stav_bedny = StavBednyChoice.K_NAVEZENI
        with self.assertRaises(ValidationError):
            b.full_clean()

        # S pozicí projde
        p = Pozice.objects.create(kod="A")
        b.pozice = p
        b.full_clean()

        # Pro NAVEZENO také musí mít pozici
        b2 = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal("1"),
            tara=Decimal("1"),
            mnozstvi=1,
        )
        b2.stav_bedny = StavBednyChoice.NAVEZENO
        with self.assertRaises(ValidationError):
            b2.full_clean()

    def test_bedna_requires_positive_fields_when_not_neprijato(self):
        b = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal("1"),
            tara=Decimal("1"),
            mnozstvi=1,
        )
        b.stav_bedny = StavBednyChoice.PRIJATO
        b.hmotnost = Decimal("0")
        with self.assertRaises(ValidationError):
            b.full_clean()

    # --- Bedna delete guard ---
    def test_bedna_delete_guard_blocks_when_not_neprijato(self):
        b = self.bedna1
        b.stav_bedny = StavBednyChoice.PRIJATO
        # Ujisti se, že validace projde (hodnoty jsou už >0)
        b.full_clean()
        b.save()
        with self.assertRaises(ProtectedError):
            b.delete()

    def test_bedna_delete_allowed_when_neprijato(self):
        b = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal("1"),
            tara=Decimal("1"),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.NEPRIJATO,
        )
        # NEPRIJATO dovolí smazání
        b.delete()
        self.assertFalse(Bedna.objects.filter(id=b.id).exists())

    # --- Bedna save helpers ---
    def test_bedna_numbering_increments_and_starts_from_customer_series(self):
        z = Zakaznik.objects.create(
            nazev="Z2",
            zkraceny_nazev="Z2",
            zkratka="Z2",
            ciselna_rada=200000,
        )
        k = Kamion.objects.create(zakaznik=z, datum=date.today())
        pr = Predpis.objects.create(nazev="PX", skupina=1, zakaznik=z)
        th = TypHlavy.objects.create(nazev="H2")
        zak = Zakazka.objects.create(
            kamion_prijem=k,
            artikl="A",
            prumer=Decimal("1"),
            delka=Decimal("1"),
            predpis=pr,
            typ_hlavy=th,
            popis="p",
        )
        b1 = Bedna.objects.create(zakazka=zak, hmotnost=Decimal("1"), tara=Decimal("1"), mnozstvi=1)
        b2 = Bedna.objects.create(zakazka=zak, hmotnost=Decimal("1"), tara=Decimal("1"), mnozstvi=1)
        self.assertEqual(b1.cislo_bedny, z.ciselna_rada + 1)
        self.assertEqual(b2.cislo_bedny, z.ciselna_rada + 2)

    def test_bedna_vse_tryskat_sets_tryskat_spinava_on_create(self):
        z = Zakaznik.objects.create(
            nazev="Z3",
            zkraceny_nazev="Z3",
            zkratka="Z3",
            ciselna_rada=300000,
            vse_tryskat=True,
        )
        k = Kamion.objects.create(zakaznik=z, datum=date.today())
        pr = Predpis.objects.create(nazev="PY", skupina=1, zakaznik=z)
        th = TypHlavy.objects.create(nazev="H3")
        zak = Zakazka.objects.create(
            kamion_prijem=k,
            artikl="A",
            prumer=Decimal("1"),
            delka=Decimal("1"),
            predpis=pr,
            typ_hlavy=th,
            popis="p",
        )
        b = Bedna.objects.create(zakazka=zak, hmotnost=Decimal("1"), tara=Decimal("1"), mnozstvi=1)
        self.assertEqual(b.tryskat, TryskaniChoice.SPINAVA)

    def test_bedna_save_clears_pozice_outside_navezeni_states(self):
        p = Pozice.objects.create(kod="B")
        b = Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal("1"),
            tara=Decimal("1"),
            mnozstvi=1,
            pozice=p,
        )
        b.poznamka_k_navezeni = "X"
        b.stav_bedny = StavBednyChoice.PRIJATO
        b.save()
        b.refresh_from_db()
        self.assertIsNone(b.pozice)
        self.assertIsNone(b.poznamka_k_navezeni)

    # --- Kamion delete guard ---
    def test_kamion_prijem_delete_guard_blocks_when_any_bedna_not_neprijato(self):
        # nastav jednu bednu do PRIJATO
        self.bedna1.stav_bedny = StavBednyChoice.PRIJATO
        self.bedna1.full_clean()
        self.bedna1.save()
        with self.assertRaises(ProtectedError):
            self.kamion_prijem.delete()
