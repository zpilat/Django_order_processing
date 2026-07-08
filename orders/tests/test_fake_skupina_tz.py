from django.test import TestCase
from django.utils import timezone
from decimal import Decimal

from orders.models import Zakaznik, Kamion, Predpis, TypHlavy, Zakazka, Bedna
from orders.utils import build_fake_skupina_TZ_annotation


class FakeSkupinaTZTests(TestCase):
    def setUp(self):
        self.zakaznik = Zakaznik.objects.create(nazev='Test', zkraceny_nazev='T', zkratka='TST', ciselna_rada=99999)
        self.typ_hlavy = TypHlavy.objects.create(nazev='H1')
        # kamion pro prijem
        self.kamion = Kamion.objects.create(zakaznik=self.zakaznik, datum=timezone.now().date(), prijem_vydej='P')

    def test_mapping_material_10B21_with_skupina_1(self):
        predpis = Predpis.objects.create(nazev='P1', skupina=1, zakaznik=self.zakaznik)
        zak = Zakazka.objects.create(kamion_prijem=self.kamion, artikl='A1', prumer=Decimal('10.0'), delka=Decimal('100.0'), predpis=predpis, typ_hlavy=self.typ_hlavy, popis='x')
        bedna = Bedna.objects.create(zakazka=zak, material='10B21')
        self.assertEqual(bedna.fake_skupina_TZ, 10)

    def test_no_mapping_for_other_material_or_skupina(self):
        predpis = Predpis.objects.create(nazev='P2', skupina=1, zakaznik=self.zakaznik)
        zak = Zakazka.objects.create(kamion_prijem=self.kamion, artikl='A2', prumer=Decimal('12.0'), delka=Decimal('120.0'), predpis=predpis, typ_hlavy=self.typ_hlavy, popis='y')
        bedna = Bedna.objects.create(zakazka=zak, material='S235')
        # material není 10B21 → vrací se původní skupina
        self.assertEqual(bedna.fake_skupina_TZ, 1)

        # jiná skupina nechá hodnotu průchozí
        predpis2 = Predpis.objects.create(nazev='P3', skupina=5, zakaznik=self.zakaznik)
        zak2 = Zakazka.objects.create(kamion_prijem=self.kamion, artikl='A3', prumer=Decimal('8.0'), delka=Decimal('80.0'), predpis=predpis2, typ_hlavy=self.typ_hlavy, popis='z')
        bedna2 = Bedna.objects.create(zakazka=zak2, material='10B21')
        self.assertEqual(bedna2.fake_skupina_TZ, 5)

    def test_property_matches_sql_annotation(self):
        predpis_1 = Predpis.objects.create(nazev='P4', skupina=1, zakaznik=self.zakaznik)
        predpis_5 = Predpis.objects.create(nazev='P5', skupina=5, zakaznik=self.zakaznik)
        zak_1 = Zakazka.objects.create(kamion_prijem=self.kamion, artikl='A4', prumer=Decimal('10.0'), delka=Decimal('100.0'), predpis=predpis_1, typ_hlavy=self.typ_hlavy, popis='a')
        zak_5 = Zakazka.objects.create(kamion_prijem=self.kamion, artikl='A5', prumer=Decimal('12.0'), delka=Decimal('120.0'), predpis=predpis_5, typ_hlavy=self.typ_hlavy, popis='b')
        bedny = [
            Bedna.objects.create(zakazka=zak_1, material='10B21'),
            Bedna.objects.create(zakazka=zak_1, material='S235'),
            Bedna.objects.create(zakazka=zak_5, material='17B2'),
        ]

        annotated = {
            bedna.pk: bedna.fake_skupina_TZ_ann
            for bedna in Bedna.objects.filter(pk__in=[b.pk for b in bedny]).annotate(
                fake_skupina_TZ_ann=build_fake_skupina_TZ_annotation()
            )
        }

        for bedna in bedny:
            with self.subTest(bedna=bedna.pk):
                self.assertEqual(bedna.fake_skupina_TZ, annotated[bedna.pk])
