from django.test import TestCase
from datetime import date, timedelta
from decimal import Decimal

from orders.forms import (
    ZakazkaAdminForm,
    ZakazkaInlineForm,
    BednaAdminForm,
    VyberKamionVydejForm,
)
from orders.models import Zakaznik, Kamion, Zakazka, Predpis, TypHlavy, Bedna
from orders.choices import (
    StavBednyChoice,
    TryskaniChoice,
    RovnaniChoice,
    KamionChoice,
)


class FormsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.z1 = Zakaznik.objects.create(
            nazev="Z1", zkraceny_nazev="Z1", zkratka="Z1", ciselna_rada=100000
        )
        cls.z2 = Zakaznik.objects.create(
            nazev="Z2", zkraceny_nazev="Z2", zkratka="Z2", ciselna_rada=200000
        )
        cls.pred1 = Predpis.objects.create(nazev="P1", skupina=1, zakaznik=cls.z1)
        cls.pred2 = Predpis.objects.create(nazev="P2", skupina=1, zakaznik=cls.z2)
        cls.typ = TypHlavy.objects.create(nazev="T")

        # kamiony prijem
        cls.kamion_active = Kamion.objects.create(zakaznik=cls.z1, datum=date.today())
        cls.kamion_exped = Kamion.objects.create(zakaznik=cls.z1, datum=date.today())
        cls.kamion_empty = Kamion.objects.create(zakaznik=cls.z1, datum=date.today())
        cls.kamion_other = Kamion.objects.create(zakaznik=cls.z2, datum=date.today())

        # zakazky pro filtr kamionu
        Zakazka.objects.create(
            kamion_prijem=cls.kamion_active,
            artikl="A",
            prumer=1,
            delka=1,
            predpis=cls.pred1,
            typ_hlavy=cls.typ,
            popis="p",
        )
        Zakazka.objects.create(
            kamion_prijem=cls.kamion_exped,
            artikl="A",
            prumer=1,
            delka=1,
            predpis=cls.pred1,
            typ_hlavy=cls.typ,
            popis="p",
            expedovano=True,
        )
        Zakazka.objects.create(
            kamion_prijem=cls.kamion_other,
            artikl="A",
            prumer=1,
            delka=1,
            predpis=cls.pred2,
            typ_hlavy=cls.typ,
            popis="p",
        )

        # vydej kamiony
        cls.kamion_vydej_ok = Kamion.objects.create(
            zakaznik=cls.z1,
            datum=date.today(),
            prijem_vydej=KamionChoice.VYDEJ,
        )
        cls.kamion_vydej_old = Kamion.objects.create(
            zakaznik=cls.z1,
            datum=date.today() - timedelta(days=20),
            prijem_vydej=KamionChoice.VYDEJ,
        )
        cls.kamion_vydej_other = Kamion.objects.create(
            zakaznik=cls.z2,
            datum=date.today(),
            prijem_vydej=KamionChoice.VYDEJ,
        )

        cls.zakazka_edit = Zakazka.objects.create(
            kamion_prijem=cls.kamion_active,
            artikl="B",
            prumer=1,
            delka=1,
            predpis=cls.pred1,
            typ_hlavy=cls.typ,
            popis="p",
        )
        cls.bedna = Bedna.objects.create(
            zakazka=cls.zakazka_edit,
            hmotnost=Decimal(1),
            tara=Decimal(1),
            mnozstvi=1,
            stav_bedny=StavBednyChoice.K_NAVEZENI,
            tryskat=TryskaniChoice.CISTA,
            rovnat=RovnaniChoice.ROVNA,
        )


class ZakazkaPredpisValidatorTests(FormsBase):
    def test_validator_raises_when_zakaznik_differs(self):
        data = {
            "kamion_prijem": self.kamion_other.pk,
            "predpis": self.pred1.pk,
            "artikl": "X",
            "prumer": "1",
            "delka": "1",
            "typ_hlavy": self.typ.pk,
            "popis": "p",
        }
        form = ZakazkaAdminForm(data)
        self.assertFalse(form.is_valid())
        err = form.non_field_errors()[0]
        self.assertIn("nepatří zákazníkovi", err)


class ZakazkaAdminFormTests(FormsBase):
    def test_querysets_for_add(self):
        form = ZakazkaAdminForm()
        self.assertEqual(set(form.fields["predpis"].queryset), {self.pred1, self.pred2})
        self.assertEqual(
            set(form.fields["kamion_prijem"].queryset),
            {self.kamion_active, self.kamion_other},
        )

    def test_querysets_for_change(self):
        form = ZakazkaAdminForm(instance=self.zakazka_edit)
        self.assertEqual(set(form.fields["predpis"].queryset), {self.pred1})
        self.assertEqual(
            set(form.fields["kamion_prijem"].queryset),
            {self.kamion_active, self.kamion_other},
        )


class ZakazkaInlineFormTests(FormsBase):
    def test_querysets_default_and_with_zakaznik(self):
        form_default = ZakazkaInlineForm()
        self.assertEqual(set(form_default.fields["predpis"].queryset), {self.pred1, self.pred2})

        form_zak = ZakazkaInlineForm(zakaznik=self.z1)
        self.assertEqual(set(form_zak.fields["predpis"].queryset), {self.pred1})

    def test_queryset_for_existing_instance(self):
        form = ZakazkaInlineForm(instance=self.zakazka_edit)
        self.assertEqual(set(form.fields["predpis"].queryset), {self.pred1})


class BednaAdminFormTests(FormsBase):
    def test_initial_values(self):
        form_new = BednaAdminForm()
        # Nový default je NEPRIJATO (původně PRIJATO)
        self.assertEqual(form_new.fields["stav_bedny"].initial, StavBednyChoice.NEPRIJATO)
        self.assertEqual(form_new.fields["tryskat"].initial, TryskaniChoice.NEZADANO)
        self.assertEqual(form_new.fields["rovnat"].initial, RovnaniChoice.NEZADANO)

        form_existing = BednaAdminForm(instance=self.bedna)
        self.assertEqual(form_existing.fields["stav_bedny"].initial, self.bedna.stav_bedny)
        self.assertEqual(form_existing.fields["tryskat"].initial, self.bedna.tryskat)
        self.assertEqual(form_existing.fields["rovnat"].initial, self.bedna.rovnat)


class VyberKamionVydejFormTests(FormsBase):
    def test_queryset_filtered_by_customer_and_date(self):
        form = VyberKamionVydejForm(zakaznik=self.z1)
        self.assertEqual(list(form.fields["kamion"].queryset), [self.kamion_vydej_ok])
