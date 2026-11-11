import csv
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase

from orders.models import Predpis
from orders.services.predpis_meze_service import navrh_mezi
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class ParsePredpisMezeTests(SimpleTestCase):
    def prescription(self, **changes):
        values = dict(nazev='Test', zakaznik=SimpleNamespace(zkratka='EUR'), vrstva=None, vrstva_2=None)
        values.update(changes)
        return SimpleNamespace(**values)

    def test_units_and_method_numbers_are_not_measurement_limits(self):
        for kind, text, minimum, maximum in (
            ('ohyb', 'min. 45˚', '45', None), ('ohyb', 'min. 30', '30', None),
            ('ohyb', '45° - 180°', '45', '180'), ('krut', 'min. 28Nm', '28', None),
            ('krut', '25,3 – 31,0 Nm', '25.3', '31'), ('krut', 'max. 20,5 Nm', None, '20.5'),
            ('jadro', '350 – 550 HV0,3', '350', '550'),
            ('jadro', '350 - 500 HV5 (HV10)', '350', '500'),
            ('povrch', 'min. 600 HV0,3', '600', None),
        ):
            with self.subTest(kind=kind, text=text):
                parsed = navrh_mezi(self.prescription(**{kind: text}), kind)
                self.assertEqual(parsed.stav, 'prevod')
                self.assertEqual(parsed.minimum, Decimal(minimum) if minimum is not None else None)
                self.assertEqual(parsed.maximum, Decimal(maximum) if maximum is not None else None)

    def test_ambiguous_unknown_and_reversed_formats_are_not_guessed(self):
        for kind, text in (('jadro', '300–400 (350–500) HV0,3'), ('povrch', '600 / 700 HV1'), ('krut', '30 – 20 Nm'), ('ohyb', 'min. -45°')):
            with self.subTest(kind=kind, text=text):
                self.assertEqual(navrh_mezi(self.prescription(**{kind: text}), kind).stav, 'rucne')
        for text in ('', None, '-', 'neměří se'):
            self.assertEqual(navrh_mezi(self.prescription(krut=text), 'krut').stav, 'bez_meze')

    def test_confirmed_core_exception_requires_customer_name_and_text(self):
        text = '300 – 400 (350 - 500) HV0,3'
        item = self.prescription(nazev='00829_Ø7,4', jadro=text)
        parsed = navrh_mezi(item, 'jadro')
        self.assertEqual((parsed.minimum, parsed.maximum), (Decimal('350'), Decimal('500')))
        item.zakaznik.zkratka = 'TST'
        self.assertEqual(navrh_mezi(item, 'jadro').stav, 'rucne')

    def test_layer_uses_both_fields_and_rejects_conflicts_and_garbled_text(self):
        for first, second, minimum, maximum in (
            ('CHD 550 HV0,3', '0,1 – 0,3 mm', '0.1', '0.3'),
            ('min. 0,15 mm', 'CHD 550 HV1', '0.15', None),
            ('0,15 mm', None, '0.15', None), ('CHD 400 HV0,3', '0,3 mm', '0.3', None),
            ('CHD 450 HV0,3min. 0,1 mm', None, '0.1', None),
        ):
            with self.subTest(first=first, second=second):
                parsed = navrh_mezi(self.prescription(vrstva=first, vrstva_2=second), 'vrstva')
                self.assertEqual(parsed.stav, 'prevod')
                self.assertEqual(parsed.minimum, Decimal(minimum))
                self.assertEqual(parsed.maximum, Decimal(maximum) if maximum is not None else None)
        for first, second in (('CHD 400 HV0,30,3 mm', None), ('min. 0,1 mm', 'min. 0,2 mm'), ('CHD 550 HV0,3', 'unexpected 0,1 mm')):
            self.assertEqual(navrh_mezi(self.prescription(vrstva=first, vrstva_2=second), 'vrstva').stav, 'rucne')
        for first in ('CHD 550 HV0,3', 'průběh tvrdosti'):
            self.assertEqual(navrh_mezi(self.prescription(vrstva=first), 'vrstva').stav, 'metodika')
        confirmed = self.prescription(nazev='00432_Ø7,5', vrstva='CHD 550 HV1', vrstva_2='min. 0,2 - 0,4 mm')
        parsed = navrh_mezi(confirmed, 'vrstva')
        self.assertEqual((parsed.minimum, parsed.maximum), (Decimal('0.2'), Decimal('0.4')))
        confirmed.nazev = 'Jiný předpis'
        self.assertEqual(navrh_mezi(confirmed, 'vrstva').stav, 'rucne')


class PrevodMeziCommandTests(KontrolaBednyTestBase):
    def setUp(self):
        self.item = self.bedna.zakazka.predpis
        self.item.ohyb = 'min. 45°'
        self.item.krut = '12,1 – 14,0 Nm'
        self.item.jadro = '350 – 550 HV0,3'
        self.item.vrstva = 'CHD 550 HV0,3'
        self.item.vrstva_2 = '0,1 – 0,3 mm'
        self.item.save()

    def run_command(self, **options):
        call_command('doplnit_meze_predpisu', stdout=StringIO(), **options)

    def test_preview_never_changes_values_or_history(self):
        history = self.item.history.count()
        with TemporaryDirectory() as directory:
            report = Path(directory) / 'preview.csv'
            self.run_command(csv=report)
            with report.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream, delimiter=';'))
            torsion = next(row for row in rows if row['id'] == str(self.item.pk) and row['zkouska'] == 'krut')
            self.assertEqual(torsion['navrh_min'], '12,1')
            self.assertEqual(torsion['text'], self.item.krut)
            self.assertEqual(torsion['puvodni_min'], '')
        self.item.refresh_from_db()
        self.assertIsNone(self.item.ohyb_min)
        self.assertEqual(self.item.history.count(), history)

    def test_apply_records_one_history_per_prescription_and_is_idempotent(self):
        history = self.item.history.count()
        self.run_command(apply=True)
        self.item.refresh_from_db()
        self.assertEqual(self.item.ohyb_min, Decimal('45'))
        self.assertIsNone(self.item.ohyb_max)
        self.assertEqual((self.item.krut_min, self.item.krut_max), (Decimal('12.1'), Decimal('14')))
        self.assertEqual((self.item.vrstva_min, self.item.vrstva_max), (Decimal('0.1'), Decimal('0.3')))
        self.assertEqual(self.item.jadro, '350 – 550 HV0,3')
        self.assertIsNone(self.item.jadro_qsmax)
        self.assertEqual(self.item.history.count(), history + 1)
        self.assertIn('Doplnění číselných mezí', self.item.history.latest().history_change_reason)
        self.run_command(apply=True)
        self.assertEqual(self.item.history.count(), history + 1)

    def test_partial_manual_limits_and_qs_are_preserved(self):
        self.item.krut_min = Decimal('13')
        self.item.jadro_qsmax = Decimal('600')
        self.item.save()
        self.run_command(apply=True)
        self.item.refresh_from_db()
        self.assertEqual(self.item.krut_min, Decimal('13'))
        self.assertIsNone(self.item.krut_max)
        self.assertEqual(self.item.jadro_max, Decimal('550'))
        self.assertEqual(self.item.jadro_qsmax, Decimal('600'))

    def test_failure_rolls_back_all_values_and_history(self):
        other = Predpis.objects.create(nazev='Second', zakaznik=self.item.zakaznik, ohyb='min. 30°')
        history = Predpis.history.count()
        original_save = Predpis.save

        def save_or_fail(instance, *args, **kwargs):
            if instance.pk == other.pk:
                raise RuntimeError('Simulated write failure')
            return original_save(instance, *args, **kwargs)

        with patch.object(Predpis, 'save', save_or_fail):
            with self.assertRaises(RuntimeError):
                self.run_command(apply=True)
        self.item.refresh_from_db()
        self.assertIsNone(self.item.ohyb_min)
        self.assertEqual(Predpis.history.count(), history)
