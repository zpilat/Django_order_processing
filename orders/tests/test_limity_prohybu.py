from decimal import Decimal

from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class LimityProhybuTests(KontrolaBednyTestBase):
    def limits(self, code, length):
        self.bedna.zakazka.kamion_prijem.zakaznik.zkratka = code
        self.bedna.zakazka.delka = Decimal(length)
        return self.bedna.limity_prohybu

    def test_limits_for_all_defined_customers(self):
        for code, normal, release in (
            ('EUR', '0.6', None), ('HPM', '0.6', None), ('FIS', '0.6', None),
            ('SPX', '0.4', None), ('SSH', '0.4', None),
            ('ROT', '0.4', '0.6'), ('SWG', '0.6', None),
        ):
            with self.subTest(customer=code):
                self.assertEqual(self.limits(code, '100'), {
                    'bezny': Decimal(normal),
                    'pro_uvolneni_s_odchylkou': Decimal(release) if release is not None else None,
                })

    def test_swg_switches_to_fixed_limit_above_300_mm(self):
        for length, expected in (
            ('299.9', '1.7994'), ('300', '1.8'), ('300.1', '1.8'), ('500', '1.8'),
        ):
            with self.subTest(length=length):
                self.assertEqual(self.limits('SWG', length), {
                    'bezny': Decimal(expected),
                    'pro_uvolneni_s_odchylkou': None,
                })

    def test_fractional_length_preserves_exact_decimal_limits(self):
        self.assertEqual(self.limits('ROT', '123.4'), {
            'bezny': Decimal('0.4936'),
            'pro_uvolneni_s_odchylkou': Decimal('0.7404'),
        })

    def test_undefined_customer_has_no_limits(self):
        self.assertEqual(self.limits('TST', '100'), {
            'bezny': None, 'pro_uvolneni_s_odchylkou': None,
        })
