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

    def payload(self, count):
        return {
            'nazev': self.customer.nazev,
            'zkraceny_nazev': self.customer.zkraceny_nazev,
            'ciselna_rada': self.customer.ciselna_rada,
            'pocet_vrutu_pro_kontrolu_prohybu': count,
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
