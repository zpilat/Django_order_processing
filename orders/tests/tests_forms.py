from django.test import TestCase
from datetime import date, time, timedelta
from decimal import Decimal

from orders.forms import (
    ZakazkaAdminForm,
    ZakazkaInlineForm,
    BednaAdminForm,
    VyberKamionVydejForm,
    BednaChangeListForm,
    SarzeKrokActionInitForm,
)
from orders.models import Zakaznik, Kamion, Zakazka, Predpis, TypHlavy, Bedna, Zarizeni
from orders.choices import (
    StavBednyChoice,
    TryskaniChoice,
    RovnaniChoice,
    ZinkovaniChoice,
    KamionChoice,
    PrioritaChoice,
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

    def test_validator_positive_when_zakaznik_matches(self):
        data = {
            "kamion_prijem": self.kamion_active.pk,
            "predpis": self.pred1.pk,
            "artikl": "X",
            "prumer": "1",
            "delka": "1",
            "typ_hlavy": self.typ.pk,
            "popis": "p",
            "celozavit": False,
            "priorita": PrioritaChoice.NIZKA,
        }
        form = ZakazkaAdminForm(data)
        self.assertTrue(form.is_valid())

    def test_queryset_for_change_includes_current_inactive_predpis(self):
        inactive_predpis = Predpis.objects.create(
            nazev="P1-inactive",
            skupina=1,
            zakaznik=self.z1,
            aktivni=False,
        )
        self.zakazka_edit.predpis = inactive_predpis
        self.zakazka_edit.save(update_fields=["predpis"])

        form = ZakazkaAdminForm(instance=self.zakazka_edit)
        self.assertIn(inactive_predpis, form.fields["predpis"].queryset)
        self.assertIn(self.pred1, form.fields["predpis"].queryset)


class ZakazkaInlineFormTests(FormsBase):
    def test_querysets_default_and_with_zakaznik(self):
        form_default = ZakazkaInlineForm()
        self.assertEqual(set(form_default.fields["predpis"].queryset), {self.pred1, self.pred2})

        form_zak = ZakazkaInlineForm(zakaznik=self.z1)
        self.assertEqual(set(form_zak.fields["predpis"].queryset), {self.pred1})

    def test_queryset_for_existing_instance(self):
        form = ZakazkaInlineForm(instance=self.zakazka_edit)
        self.assertEqual(set(form.fields["predpis"].queryset), {self.pred1})

    def test_queryset_for_existing_instance_includes_current_inactive_predpis(self):
        inactive_predpis = Predpis.objects.create(
            nazev="P1-inline-inactive",
            skupina=1,
            zakaznik=self.z1,
            aktivni=False,
        )
        self.zakazka_edit.predpis = inactive_predpis
        self.zakazka_edit.save(update_fields=["predpis"])

        form = ZakazkaInlineForm(instance=self.zakazka_edit)
        self.assertIn(inactive_predpis, form.fields["predpis"].queryset)
        self.assertIn(self.pred1, form.fields["predpis"].queryset)

    def test_decimal_helper_fields_accept_comma(self):
        form = ZakazkaInlineForm(data={
            "celkova_hmotnost": "12,5",
            "tara": "1,5",
        })

        self.assertEqual(form.fields["celkova_hmotnost"].clean("12,5"), Decimal("12.5"))
        self.assertEqual(form.fields["tara"].clean("1,5"), Decimal("1.5"))


class BednaAdminFormTests(FormsBase):
    def test_initial_values(self):
        form_new = BednaAdminForm()
        # Nový default je NEPRIJATO (původně PRIJATO)
        self.assertEqual(form_new.fields["stav_bedny"].initial, StavBednyChoice.NEPRIJATO)
        self.assertEqual(form_new.fields["tryskat"].initial, TryskaniChoice.NEZADANO)
        self.assertEqual(form_new.fields["rovnat"].initial, RovnaniChoice.NEZADANO)
        self.assertEqual(form_new.fields["zinkovat"].initial, ZinkovaniChoice.NEZINKOVAT)

        form_existing = BednaAdminForm(instance=self.bedna)
        self.assertEqual(form_existing.fields["stav_bedny"].initial, self.bedna.stav_bedny)
        self.assertEqual(form_existing.fields["tryskat"].initial, self.bedna.tryskat)
        self.assertEqual(form_existing.fields["rovnat"].initial, self.bedna.rovnat)
        self.assertEqual(form_existing.fields["zinkovat"].initial, self.bedna.zinkovat)

    def test_clean_computes_tara_from_brutto(self):
        form = BednaAdminForm(data={
            "zakazka": self.zakazka_edit.pk,
            "hmotnost": "2.0",
            "tara": "",
            "mnozstvi": 1,
            "stav_bedny": StavBednyChoice.NEPRIJATO,
            "brutto": "3.1",
            "tryskat": TryskaniChoice.NEZADANO,
            "rovnat": RovnaniChoice.NEZADANO,
            "zinkovat": ZinkovaniChoice.NEZINKOVAT,
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["tara"], Decimal("1.1"))

    def test_brutto_accepts_decimal_comma(self):
        form = BednaAdminForm(data={
            "zakazka": self.zakazka_edit.pk,
            "hmotnost": "2.0",
            "tara": "",
            "mnozstvi": 1,
            "stav_bedny": StavBednyChoice.NEPRIJATO,
            "brutto": "3,1",
            "tryskat": TryskaniChoice.NEZADANO,
            "rovnat": RovnaniChoice.NEZADANO,
            "zinkovat": ZinkovaniChoice.NEZINKOVAT,
        })

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["brutto"], Decimal("3.1"))
        self.assertEqual(form.cleaned_data["tara"], Decimal("1.1"))

    def test_clean_errors_when_tara_already_set(self):
        form = BednaAdminForm(data={
            "zakazka": self.zakazka_edit.pk,
            "hmotnost": "2.0",
            "tara": "1.0",
            "mnozstvi": 1,
            "stav_bedny": StavBednyChoice.NEPRIJATO,
            "brutto": "3.0",
            "tryskat": TryskaniChoice.NEZADANO,
            "rovnat": RovnaniChoice.NEZADANO,
            "zinkovat": ZinkovaniChoice.NEZINKOVAT,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("brutto", form.errors)

    def test_clean_errors_when_missing_hmotnost(self):
        form = BednaAdminForm(data={
            "zakazka": self.zakazka_edit.pk,
            "hmotnost": "",
            "tara": "",
            "mnozstvi": 1,
            "stav_bedny": StavBednyChoice.NEPRIJATO,
            "brutto": "1.0",
            "tryskat": TryskaniChoice.NEZADANO,
            "rovnat": RovnaniChoice.NEZADANO,
            "zinkovat": ZinkovaniChoice.NEZINKOVAT,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("hmotnost", form.errors)

    def test_clean_errors_when_brutto_le_than_hmotnost(self):
        form = BednaAdminForm(data={
            "zakazka": self.zakazka_edit.pk,
            "hmotnost": "2.0",
            "tara": "",
            "mnozstvi": 1,
            "stav_bedny": StavBednyChoice.NEPRIJATO,
            "brutto": "2.0",
            "tryskat": TryskaniChoice.NEZADANO,
            "rovnat": RovnaniChoice.NEZADANO,
            "zinkovat": ZinkovaniChoice.NEZINKOVAT,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("brutto", form.errors)

    def test_zakazka_queryset_excludes_expedovano(self):
        # Přidej další zakázku expedovanou pro ověření filtru
        Zakazka.objects.create(
            kamion_prijem=self.kamion_active,
            artikl="C",
            prumer=1,
            delka=1,
            predpis=self.pred1,
            typ_hlavy=self.typ,
            popis="p",
            expedovano=True,
        )
        form = BednaAdminForm()
        qs = form.fields["zakazka"].queryset
        # Očekáváme pouze neexpedované zakázky
        self.assertTrue(all(not z.expedovano for z in qs))


class BednaChangeListFormTests(FormsBase):
    def test_choices_follow_model_rules(self):
        form = BednaChangeListForm(instance=self.bedna)
        self.assertEqual(form.fields["stav_bedny"].choices, self.bedna.get_allowed_stav_bedny_choices())
        self.assertEqual(form.fields["stav_bedny"].initial, self.bedna.stav_bedny)
        self.assertEqual(form.fields["tryskat"].choices, self.bedna.get_allowed_tryskat_choices())
        self.assertEqual(form.fields["tryskat"].initial, self.bedna.tryskat)
        self.assertEqual(form.fields["rovnat"].choices, self.bedna.get_allowed_rovnat_choices())
        self.assertEqual(form.fields["rovnat"].initial, self.bedna.rovnat)
        self.assertEqual(form.fields["zinkovat"].choices, self.bedna.get_allowed_zinkovat_choices())
        self.assertEqual(form.fields["zinkovat"].initial, self.bedna.zinkovat)


class VyberKamionVydejFormTests(FormsBase):
    def test_queryset_filtered_by_customer_and_date(self):
        form = VyberKamionVydejForm(zakaznik=self.z1)
        self.assertEqual(list(form.fields["kamion"].queryset), [self.kamion_vydej_ok])

    def test_no_customer_yields_empty_queryset(self):
        form = VyberKamionVydejForm()
        self.assertEqual(list(form.fields["kamion"].queryset), [])


class SarzeKrokActionInitFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.zarizeni = Zarizeni.objects.create(
            kod_zarizeni="FORM-KROK",
            nazev_zarizeni="Test formuláře kroku",
        )

    def _data(self, **overrides):
        data = {
            'datum': '2026-08-20',
            'zarizeni': str(self.zarizeni.pk),
            'zacatek': '22:00',
            'datum_konce': '2026-08-21',
            'konec': '01:00',
            'operator': 'Novak',
        }
        data.update(overrides)
        return data

    def test_accepts_end_on_following_day(self):
        form = SarzeKrokActionInitForm(self._data())

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['datum_konce'], date(2026, 8, 21))
        self.assertEqual(form.cleaned_data['konec'], time(1, 0))

    def test_requires_end_date_with_end_time(self):
        form = SarzeKrokActionInitForm(self._data(datum_konce=''))

        self.assertFalse(form.is_valid())
        self.assertIn('datum_konce', form.errors)

    def test_rejects_end_before_start(self):
        form = SarzeKrokActionInitForm(
            self._data(datum_konce='2026-08-20', konec='21:00')
        )

        self.assertFalse(form.is_valid())
        self.assertIn('datum_konce', form.errors)
