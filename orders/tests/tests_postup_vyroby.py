from decimal import Decimal
from django.test import TestCase
from django.db.models import Case, Value, IntegerField

from orders.models import Zakaznik, Kamion, Predpis, TypHlavy, Zakazka, Bedna
from datetime import date
from orders.choices import StavBednyChoice, RovnaniChoice, TryskaniChoice, KamionChoice
from orders.utils import build_postup_vyroby_cases

class TestPostupVyrobyAnnotation(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.zakaznik = Zakaznik.objects.create(
            nazev="Z",
            zkraceny_nazev="Z",
            zkratka="Z",
            ciselna_rada=100000,
        )
        cls.kamion = Kamion.objects.create(zakaznik=cls.zakaznik, prijem_vydej=KamionChoice.PRIJEM, datum=date.today())
        cls.predpis = Predpis.objects.create(nazev="P", skupina=1, zakaznik=cls.zakaznik)
        cls.typ = TypHlavy.objects.create(nazev="TH")
        cls.zakazka = Zakazka.objects.create(
            kamion_prijem=cls.kamion,
            artikl="A",
            prumer=Decimal("10"),
            delka=Decimal("100"),
            predpis=cls.predpis,
            typ_hlavy=cls.typ,
            popis="TEST",
        )

    def _make_bedna(self, stav, rovnat=RovnaniChoice.NEZADANO, tryskat=TryskaniChoice.NEZADANO):
        return Bedna.objects.create(
            zakazka=self.zakazka,
            hmotnost=Decimal("1"),
            tara=Decimal("1"),
            mnozstvi=1,
            stav_bedny=stav,
            rovnat=rovnat,
            tryskat=tryskat,
        )

    def test_annotation_matches_property_all_key_states(self):
        combos = [
            (StavBednyChoice.NEPRIJATO, RovnaniChoice.NEZADANO, TryskaniChoice.NEZADANO),  # 0
            (StavBednyChoice.PRIJATO, RovnaniChoice.NEZADANO, TryskaniChoice.NEZADANO),    # 0
            (StavBednyChoice.K_NAVEZENI, RovnaniChoice.NEZADANO, TryskaniChoice.NEZADANO), # 10
            (StavBednyChoice.NAVEZENO, RovnaniChoice.NEZADANO, TryskaniChoice.NEZADANO),   # 20
            (StavBednyChoice.DO_ZPRACOVANI, RovnaniChoice.NEZADANO, TryskaniChoice.NEZADANO), # 30
            (StavBednyChoice.ZAKALENO, RovnaniChoice.NEZADANO, TryskaniChoice.NEZADANO),   # 50
            # ZKONTROLOVANO varianty
            (StavBednyChoice.ZKONTROLOVANO, RovnaniChoice.NEZADANO, TryskaniChoice.NEZADANO), # 60
            (StavBednyChoice.ZKONTROLOVANO, RovnaniChoice.ROVNA, TryskaniChoice.NEZADANO),     # 75
            (StavBednyChoice.ZKONTROLOVANO, RovnaniChoice.NEZADANO, TryskaniChoice.CISTA),     # 75
            (StavBednyChoice.ZKONTROLOVANO, RovnaniChoice.ROVNA, TryskaniChoice.CISTA),        # 90
            (StavBednyChoice.K_EXPEDICI, RovnaniChoice.ROVNA, TryskaniChoice.CISTA),           # 100
            (StavBednyChoice.EXPEDOVANO, RovnaniChoice.VYROVNANA, TryskaniChoice.OTRYSKANA),   # 100
        ]
        created_ids = []
        for stav, rov, tr in combos:
            b = self._make_bedna(stav, rov, tr)
            created_ids.append(b.id)

        # Anotace
        annotated = (
            Bedna.objects.filter(id__in=created_ids)
            .annotate(postup_vyroby_value=Case(*build_postup_vyroby_cases(), default=Value(0), output_field=IntegerField()))
        )
        mismatch = []
        for bedna in annotated:
            if bedna.postup_vyroby != bedna.postup_vyroby_value:
                mismatch.append((bedna.id, bedna.stav_bedny, bedna.rovnat, bedna.tryskat, bedna.postup_vyroby, bedna.postup_vyroby_value))
        self.assertFalse(mismatch, f"Neshoda mezi property a anotací: {mismatch}")

    def test_performance_one_query_for_annotation(self):
        # Vytvoříme několik beden
        for _ in range(5):
            self._make_bedna(StavBednyChoice.NEPRIJATO)
        with self.assertNumQueries(1):
            list(
                Bedna.objects.all().annotate(
                    postup_vyroby_value=Case(*build_postup_vyroby_cases(), default=Value(0), output_field=IntegerField())
                ).values_list('id', 'postup_vyroby_value')
            )
