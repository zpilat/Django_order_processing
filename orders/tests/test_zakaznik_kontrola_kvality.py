from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from orders.forms import MinutySekundyField
from orders.models import DOBA_ZKOUSKY_FIELDS, Zakaznik


class MinutySekundyFieldTests(SimpleTestCase):
    def test_minutes_are_not_interpreted_as_hours_and_round_trip_above_one_hour(self):
        field = MinutySekundyField(required=False)
        for submitted, expected, displayed in (
            ('00:01', timedelta(seconds=1), '00:01'),
            ('2:30', timedelta(seconds=150), '02:30'),
            (' 02:30 ', timedelta(seconds=150), '02:30'),
            ('90:05', timedelta(minutes=90, seconds=5), '90:05'),
            ('1500:00', timedelta(minutes=1500), '1500:00'),
            ('', None, None),
        ):
            with self.subTest(value=submitted):
                parsed = field.clean(submitted)
                self.assertEqual(parsed, expected)
                self.assertEqual(field.prepare_value(parsed), displayed)

    def test_rejects_ambiguous_formats_invalid_seconds_and_overflow(self):
        field = MinutySekundyField()
        for submitted in ('30', '02:60', '02:99', '02:3', '1:02:30', '2.5', '-01:30', 'abc', '9' * 30 + ':00'):
            with self.subTest(value=submitted), self.assertRaises(ValidationError):
                field.clean(submitted)


class ZakaznikKontrolaKvalityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = Zakaznik.objects.create(
            nazev='Test kontroly', zkraceny_nazev='TEST', zkratka='TST',
            ciselna_rada=100000,
        )
        cls.user = get_user_model().objects.create_superuser(username='admin', password='test')

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse('admin:orders_zakaznik_change', args=[self.customer.pk])

    def payload(self, count, max_krivych=''):
        return {
            'nazev': self.customer.nazev,
            'zkraceny_nazev': self.customer.zkraceny_nazev,
            'ciselna_rada': self.customer.ciselna_rada,
            'pocet_vrutu_pro_kontrolu_prohybu': count,
            'max_krivych_vrutu': max_krivych,
            '_save': 'Uložit',
        }

    def test_count_is_optional_and_positive_when_defined(self):
        self.assertIsNone(self.customer.pocet_vrutu_pro_kontrolu_prohybu)
        for value in (None, 1, 5):
            with self.subTest(value=value):
                self.customer.pocet_vrutu_pro_kontrolu_prohybu = value
                self.customer.full_clean()
        for value in (0, -1):
            with self.subTest(value=value):
                self.customer.pocet_vrutu_pro_kontrolu_prohybu = value
                with self.assertRaises(ValidationError) as caught:
                    self.customer.full_clean()
                self.assertIn('pocet_vrutu_pro_kontrolu_prohybu', caught.exception.message_dict)

    def test_admin_displays_quality_fieldset_and_help(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Kontrola kvality')
        self.assertContains(response, 'Celkový počet vrutů odebraných pro kontrolu prohybu')
        self.assertContains(response, 'Celkový počet vrutů odebraných z každé bedny.')
        self.assertContains(response, 'name="pocet_vrutu_pro_kontrolu_prohybu"')
        self.assertContains(response, 'Maximální počet křivých vrutů při kontrole prohybu')
        self.assertContains(response, 'name="max_krivych_vrutu"')
        fieldsets = dict(response.context['adminform'].fieldsets)
        for field in ('min_hodnot_mechanicke', 'min_hodnot_prohyb', 'min_hodnot_tvrdost', 'nazev_protokolu', 'vyplnene_kkk_po_zakazkach'):
            self.assertIn(field, fieldsets['Kontrola kvality']['fields'])
            self.assertContains(response, f'name="{field}"')

    def test_admin_saves_order_zip_setting_and_history(self):
        self.assertFalse(self.customer.vyplnene_kkk_po_zakazkach)
        for submitted, expected in (({'vyplnene_kkk_po_zakazkach': 'on'}, True), ({}, False)):
            with self.subTest(expected=expected):
                response = self.client.post(self.url, {**self.payload(''), **submitted})
                self.assertEqual(response.status_code, 302)
                self.customer.refresh_from_db()
                self.assertEqual(self.customer.vyplnene_kkk_po_zakazkach, expected)
                self.assertEqual(self.customer.history.first().vyplnene_kkk_po_zakazkach, expected)

    def test_admin_saves_displays_and_clears_test_durations_with_history(self):
        times = ('02:30', '03:15', '90:05', '00:30', '00:45', '01:20')
        expected_times = (150, 195, 5405, 30, 45, 80)
        self.assertTrue(all(getattr(self.customer, field) is None for field in DOBA_ZKOUSKY_FIELDS))
        original_history = self.customer.history.first()
        response = self.client.post(self.url, {
            **self.payload(''), **dict(zip(DOBA_ZKOUSKY_FIELDS, times)),
        })
        self.assertEqual(response.status_code, 302)
        self.customer.refresh_from_db()
        history = self.customer.history.first()
        for field, seconds in zip(DOBA_ZKOUSKY_FIELDS, expected_times):
            with self.subTest(field=field):
                self.assertEqual(getattr(self.customer, field), timedelta(seconds=seconds))
                self.assertEqual(getattr(history, field), timedelta(seconds=seconds))
                self.assertIsNone(getattr(original_history, field))
        self.assertEqual(history.history_user, self.user)

        response = self.client.get(self.url)
        self.assertContains(response, 'Doby trvání zkoušek')
        self.assertContains(response, 'Čas pro všechny vzorky z jedné bedny.')
        self.assertContains(response, 'Čas jednoho měření na jednom vrutu.')
        fieldsets = dict(response.context['adminform'].fieldsets)
        for field, displayed in zip(DOBA_ZKOUSKY_FIELDS, times):
            self.assertIn(field, fieldsets['Doby trvání zkoušek']['fields'])
            self.assertEqual(response.context['adminform'].form[field].value(), displayed)
            self.assertContains(response, f'value="{displayed}"')

        response = self.client.post(self.url, {
            **self.payload(''), **dict.fromkeys(DOBA_ZKOUSKY_FIELDS, ''),
        })
        self.assertEqual(response.status_code, 302)
        self.customer.refresh_from_db()
        for field in DOBA_ZKOUSKY_FIELDS:
            self.assertIsNone(getattr(self.customer, field))
            self.assertIsNone(getattr(self.customer.history.first(), field))

    def test_admin_rejects_invalid_durations_without_saving_or_creating_history(self):
        for value in ('00:00', '02:60', '1:02:30', '-01:00'):
            with self.subTest(value=value):
                response = self.client.post(self.url, {
                    **self.payload(''), **dict.fromkeys(DOBA_ZKOUSKY_FIELDS, value),
                })
                self.assertEqual(response.status_code, 200)
                self.assertTrue(set(DOBA_ZKOUSKY_FIELDS).issubset(response.context['adminform'].form.errors))
                self.customer.refresh_from_db()
                self.assertTrue(all(getattr(self.customer, field) is None for field in DOBA_ZKOUSKY_FIELDS))
                self.assertEqual(self.customer.history.count(), 1)

    def test_duration_constraints_reject_nonpositive_values_in_model_and_database(self):
        for field in DOBA_ZKOUSKY_FIELDS:
            for value in (timedelta(), timedelta(seconds=-1)):
                with self.subTest(field=field, value=value):
                    setattr(self.customer, field, value)
                    with self.assertRaises(ValidationError) as caught:
                        self.customer.full_clean()
                    self.assertIn(field, caught.exception.message_dict)
                    with self.assertRaises(IntegrityError), transaction.atomic():
                        Zakaznik.objects.filter(pk=self.customer.pk).update(**{field: value})
            setattr(self.customer, field, None)

    def test_kkk_minimums_are_optional_positive_and_enforced_in_database(self):
        for field in ('min_hodnot_mechanicke', 'min_hodnot_prohyb', 'min_hodnot_tvrdost'):
            for value in (None, 1, 25):
                with self.subTest(field=field, value=value):
                    setattr(self.customer, field, value)
                    self.customer.full_clean()
            for value in (0, -1):
                with self.subTest(field=field, value=value):
                    setattr(self.customer, field, value)
                    with self.assertRaises(ValidationError):
                        self.customer.full_clean()
                    with self.assertRaises(IntegrityError), transaction.atomic():
                        Zakaznik.objects.filter(pk=self.customer.pk).update(**{field: value})
            setattr(self.customer, field, None)

    def test_admin_saves_kkk_settings_and_history_independently_of_sample_size(self):
        settings = {
            'min_hodnot_mechanicke': '5', 'min_hodnot_prohyb': '3',
            'min_hodnot_tvrdost': '2', 'nazev_protokolu': 'HPM - F 73c\nEurotec - F.3',
        }
        response = self.client.post(self.url, {**self.payload('32', '2'), **settings})
        self.assertEqual(response.status_code, 302)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.pocet_vrutu_pro_kontrolu_prohybu, 32)
        for field, expected in settings.items():
            expected = expected if field == 'nazev_protokolu' else int(expected)
            self.assertEqual(getattr(self.customer, field), expected)
            self.assertEqual(getattr(self.customer.history.first(), field), expected)
        response = self.client.post(self.url, {**self.payload('32', '2'), 'nazev_protokolu': ''})
        self.assertEqual(response.status_code, 302)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.pocet_vrutu_pro_kontrolu_prohybu, 32)
        for field in settings:
            expected = '' if field == 'nazev_protokolu' else None
            self.assertEqual(getattr(self.customer, field), expected)
            self.assertEqual(getattr(self.customer.history.first(), field), expected)

    def test_admin_changelist_shows_quality_counts_instead_of_contact_details(self):
        self.customer.pocet_vrutu_pro_kontrolu_prohybu = 25
        self.customer.max_krivych_vrutu = 0
        self.customer.save(update_fields=['pocet_vrutu_pro_kontrolu_prohybu', 'max_krivych_vrutu'])

        response = self.client.get(reverse('admin:orders_zakaznik_changelist'))
        self.assertEqual(response.status_code, 200)
        columns = response.context['cl'].list_display
        self.assertIn('get_vzorek_prohybu', columns)
        self.assertIn('get_max_krivych_vrutu', columns)
        self.assertEqual(columns[-3:], ['get_vzorek_prohybu', 'get_max_krivych_vrutu', 'ciselna_rada'])
        for removed in ('kontaktni_osoba', 'telefon', 'email'):
            self.assertNotIn(removed, columns)
        self.assertContains(response, 'Vzorek (ks)')
        self.assertContains(response, 'Max. křivých')
        self.assertContains(response, '<td class="field-get_vzorek_prohybu">25</td>')
        self.assertContains(response, '<td class="field-get_max_krivych_vrutu">0</td>')

    def test_admin_rejects_nonpositive_or_fractional_counts_without_saving(self):
        for value in ('0', '-1', '1.5'):
            with self.subTest(value=value):
                response = self.client.post(self.url, self.payload(value))
                self.assertEqual(response.status_code, 200)
                self.assertIn('pocet_vrutu_pro_kontrolu_prohybu', response.context['adminform'].form.errors)
                self.customer.refresh_from_db()
                self.assertIsNone(self.customer.pocet_vrutu_pro_kontrolu_prohybu)
                self.assertEqual(self.customer.history.count(), 1)

    def test_admin_saves_count_and_clearing_it_in_customer_history(self):
        for submitted, expected in (('1', 1), ('5', 5), ('', None)):
            with self.subTest(value=submitted):
                response = self.client.post(self.url, self.payload(submitted))
                self.assertEqual(response.status_code, 302)
                self.customer.refresh_from_db()
                self.assertEqual(self.customer.pocet_vrutu_pro_kontrolu_prohybu, expected)
                self.assertEqual(self.customer.history.first().pocet_vrutu_pro_kontrolu_prohybu, expected)
        self.assertEqual(
            list(self.customer.history.order_by('history_id').values_list('pocet_vrutu_pro_kontrolu_prohybu', flat=True)),
            [None, 1, 5, None],
        )

    def test_admin_saves_zero_maximum_and_clearing_it_in_customer_history(self):
        field = 'max_krivych_vrutu'
        for submitted, expected in (('0', 0), ('2', 2), ('', None)):
            with self.subTest(value=submitted):
                response = self.client.post(self.url, self.payload('', max_krivych=submitted))
                self.assertEqual(response.status_code, 302)
                self.customer.refresh_from_db()
                self.assertEqual(getattr(self.customer, field), expected)
                self.assertEqual(getattr(self.customer.history.first(), field), expected)

    def test_admin_rejects_invalid_maximum_without_saving(self):
        field = 'max_krivych_vrutu'
        for submitted in ('-1', '1.5', 'abc'):
            with self.subTest(value=submitted):
                response = self.client.post(self.url, self.payload('', max_krivych=submitted))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context['adminform'].form.errors)
                self.customer.refresh_from_db()
                self.assertIsNone(getattr(self.customer, field))
