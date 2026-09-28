from decimal import Decimal

from django.test import SimpleTestCase

from orders.templatetags.custom_filters import stav_prohybu


class StavProhybuTests(SimpleTestCase):
    def test_normal_and_qs_limits_are_inclusive(self):
        limits = {'bezny': Decimal('0.4'), 'pro_uvolneni_s_odchylkou': Decimal('0.6')}
        for value, expected in (
            ('0', ''), ('0.3999', ''), ('0.4', ''), ('0.4001', 'odchylka'),
            ('0.5', 'odchylka'), ('0.6', 'odchylka'), ('0.6001', 'nevyhovuje'),
        ):
            with self.subTest(value=value):
                self.assertEqual(stav_prohybu(Decimal(value), limits), expected)

    def test_exceeding_normal_limit_without_qs_is_red(self):
        limits = {'bezny': Decimal('0.6'), 'pro_uvolneni_s_odchylkou': None}
        self.assertEqual(stav_prohybu(Decimal('0.6'), limits), '')
        self.assertEqual(stav_prohybu(Decimal('0.6001'), limits), 'nevyhovuje')

    def test_missing_value_or_limit_is_not_evaluated(self):
        self.assertEqual(stav_prohybu(None, {'bezny': Decimal('0.4')}), '')
        self.assertEqual(stav_prohybu(Decimal('100'), None), '')
        self.assertEqual(stav_prohybu(Decimal('100'), {'bezny': None, 'pro_uvolneni_s_odchylkou': None}), '')

    def test_fractional_limits_are_not_rounded(self):
        limits = {'bezny': Decimal('0.4936'), 'pro_uvolneni_s_odchylkou': Decimal('0.7404')}
        for value, expected in (
            ('0.4936', ''), ('0.4937', 'odchylka'), ('0.7404', 'odchylka'), ('0.7405', 'nevyhovuje'),
        ):
            with self.subTest(value=value):
                self.assertEqual(stav_prohybu(Decimal(value), limits), expected)

    def test_zero_limit_is_defined(self):
        limits = {'bezny': Decimal('0'), 'pro_uvolneni_s_odchylkou': None}
        self.assertEqual(stav_prohybu(Decimal('0'), limits), '')
        self.assertEqual(stav_prohybu(Decimal('0.0001'), limits), 'nevyhovuje')
