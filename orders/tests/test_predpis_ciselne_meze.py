from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from orders.models import Predpis
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class PredpisCiselneMezeTests(KontrolaBednyTestBase):
    kinds = ('ohyb', 'krut', 'povrch', 'jadro', 'vrstva')

    def prescription(self, **values):
        return Predpis(nazev='Číselné meze', zakaznik=self.bedna.zakazka.kamion_prijem.zakaznik, **values)

    def test_existing_text_requirements_do_not_populate_numeric_limits(self):
        item = self.prescription(ohyb='min. 45°', krut='12,1 – 14,0 Nm', vrstva='CHD 550 HV0,3', vrstva_2='0,1 – 0,3 mm')
        item.full_clean()
        item.save()
        item.refresh_from_db()
        for kind in self.kinds:
            for suffix in ('min', 'max', 'qsmax'):
                name = f'{kind}_{suffix}'
                self.assertIsNone(getattr(item, name))
                self.assertIsNone(getattr(item.history.latest(), name))
        self.assertEqual(item.vrstva, 'CHD 550 HV0,3')
        self.assertEqual(item.vrstva_2, '0,1 – 0,3 mm')

    def test_decimal_limits_preserve_precision_and_history_without_changing_text(self):
        item = self.prescription(krut='Původní text', krut_min=Decimal('12.1001'), krut_max=Decimal('14.0001'), vrstva_min=Decimal('0.1234'))
        item.full_clean()
        item.save()
        item.krut_qsmax = Decimal('15.6789')
        item.save()
        saved = Predpis.objects.get(pk=item.pk)
        self.assertEqual(saved.krut_min, Decimal('12.1001'))
        self.assertEqual(saved.vrstva_min, Decimal('0.1234'))
        self.assertEqual(saved.krut, 'Původní text')
        self.assertEqual(list(item.history.order_by('history_id').values_list('krut_qsmax', flat=True)), [None, Decimal('15.6789')])

    def test_limits_can_be_one_sided_or_equal_and_zero_is_not_missing(self):
        for kind in self.kinds:
            for limits in ({'min': Decimal('0')}, {'max': Decimal('10')}, {'min': Decimal('10'), 'max': Decimal('10'), 'qsmax': Decimal('10')}):
                with self.subTest(kind=kind, limits=limits):
                    self.prescription(**{f'{kind}_{key}': value for key, value in limits.items()}).full_clean()

    def test_negative_or_reversed_limits_are_rejected(self):
        for kind in self.kinds:
            for suffix in ('min', 'max', 'qsmax'):
                with self.subTest(kind=kind, negative=suffix):
                    with self.assertRaises(ValidationError) as error:
                        self.prescription(**{f'{kind}_{suffix}': Decimal('-0.0001')}).full_clean()
                    self.assertIn(f'{kind}_{suffix}', error.exception.message_dict)
            for values, error_field in (
                ({'min': Decimal('20'), 'max': Decimal('10')}, 'max'),
                ({'max': Decimal('20'), 'qsmax': Decimal('10')}, 'qsmax'),
            ):
                with self.subTest(kind=kind, values=values):
                    with self.assertRaises(ValidationError) as error:
                        self.prescription(**{f'{kind}_{key}': value for key, value in values.items()}).full_clean()
                    self.assertIn(f'{kind}_{error_field}', error.exception.message_dict)

    def test_invalid_number_reports_validation_error_without_crashing_range_comparison(self):
        for field, value in (('ohyb_min', 'překlep'), ('ohyb_qsmax', Decimal('NaN'))):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError) as error:
                    self.prescription(ohyb_max=Decimal('45'), **{field: value}).full_clean()
                self.assertIn(field, error.exception.message_dict)

    def test_admin_groups_and_saves_limits_and_rejects_inconsistent_range(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        item = self.bedna.zakazka.predpis
        url = reverse('admin:orders_predpis_change', args=[item.pk])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'příprava pro budoucí automatické vyhodnocení')
        self.assertContains(page, 'Jedna společná sada číselných mezí')
        for kind in self.kinds:
            for suffix in ('min', 'max', 'qsmax'):
                self.assertContains(page, f'name="{kind}_{suffix}"')
        data = dict(nazev=item.nazev, zakaznik=item.zakaznik_id, aktivni='on', ohyb='min. 45°', ohyb_min='45', ohyb_max='30', _save='Uložit')
        invalid = self.client.post(url, data)
        self.assertEqual(invalid.status_code, 200)
        self.assertIn('ohyb_max', invalid.context['adminform'].form.errors)
        item.refresh_from_db()
        self.assertIsNone(item.ohyb_min)
        data.update(ohyb_max='180', vrstva_min='0,15', vrstva_max='0,2345', krut_min='0')
        saved = self.client.post(url, data)
        self.assertEqual(saved.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.ohyb_min, Decimal('45'))
        self.assertEqual(item.ohyb_max, Decimal('180'))
        self.assertEqual(item.vrstva_min, Decimal('0.15'))
        self.assertEqual(item.ohyb, 'min. 45°')
        self.assertEqual(item.history.latest().history_user_id, self.user.pk)
        page = self.client.get(url)
        form = page.context['adminform'].form
        for name, value in (
            ('ohyb_min', '45'), ('ohyb_max', '180'), ('krut_min', '0'),
            ('vrstva_min', '0,15'), ('vrstva_max', '0,2345'), ('ohyb_qsmax', None),
        ):
            with self.subTest(field=name):
                self.assertEqual(form.fields[name].widget.format_value(form[name].value()), value)
        unchanged = type(form)(data=data, instance=item)
        self.assertTrue(unchanged.is_valid(), unchanged.errors)
        for name in ('ohyb_min', 'ohyb_max', 'krut_min', 'vrstva_min', 'vrstva_max'):
            self.assertNotIn(name, unchanged.changed_data)
