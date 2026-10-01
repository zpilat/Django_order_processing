from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from orders.models import Zakaznik


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
        self.assertContains(response, 'Počet vrutů pro kontrolu prohybu')
        self.assertContains(response, 'Počet vrutů kontrolovaných z každé bedny.')
        self.assertContains(response, 'name="pocet_vrutu_pro_kontrolu_prohybu"')
        self.assertContains(response, 'Maximální počet křivých vrutů při kontrole prohybu')
        self.assertContains(response, 'name="max_krivych_vrutu"')

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
