"""Regresní scénáře částek, sazeb a dokladů v obou způsobech fakturace."""

from datetime import date
from decimal import Decimal
from html.parser import HTMLParser
from itertools import product
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.admin.utils import label_for_field
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from orders import actions
from orders.billing import billed_amount, validate_proforma_pricing
from orders.choices import KamionChoice, RovnaniChoice, StavBednyChoice, TryskaniChoice
from orders.models import (
    Bedna, Cena, Kamion, Predpis, Rozpracovanost, RozpracovanostBednaSnapshot,
    TypHlavy, Zakazka, Zakaznik,
)


class ProformaRows(HTMLParser):
    """Čte skutečně vytištěné buňky, nikoli jen přítomnost částky někde v HTML."""

    def __init__(self, html):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        elif tag == 'td':
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == 'td' and self.cell is not None:
            value = ''.join(''.join(self.cell).split())
            self.row.append(value)
            self.cell = None
        elif tag == 'tr' and self.row:
            self.rows.append(self.row)
            self.row = None


class BillingAmountTests(SimpleTestCase):
    def test_decimal_half_up_on_both_sides_of_cent_and_exact_half_cent(self):
        for weight, rate, expected in (
            ('0.1', '1.04', '0.10'),
            ('0.1', '1.05', '0.11'),
            ('0.1', '1.06', '0.11'),
            ('100.1', '1.05', '105.11'),
            ('9999.9', '99999999.99', '999989999900.00'),
        ):
            with self.subTest(weight=weight, rate=rate):
                self.assertEqual(billed_amount(Decimal(weight), Decimal(rate)), Decimal(expected))

    def test_empty_and_zero_values_are_zero_for_intermediate_display(self):
        for weight, rate in ((None, '1.05'), (0, '1.05'), ('100.1', None), ('100.1', 0)):
            with self.subTest(weight=weight, rate=rate):
                self.assertEqual(billed_amount(weight, rate), Decimal('0.00'))

    def test_zero_amount_is_formatted_without_negative_zero(self):
        self.assertEqual(format(billed_amount(0, Decimal('-1.05')), '.2f'), '0.00')


class BillingTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = Zakaznik.objects.create(
            nazev='Fakturační test', zkraceny_nazev='BILL', zkratka='SPX',
            ciselna_rada=200000, proforma_po_bednach=False,
            fakturovat_rovnani=False, fakturovat_tryskani=False,
        )
        cls.incoming = Kamion.objects.create(zakaznik=cls.customer, datum=date(2026, 11, 16))
        cls.truck = Kamion.objects.create(
            zakaznik=cls.customer, datum=date(2026, 11, 17), prijem_vydej=KamionChoice.VYDEJ,
        )
        cls.spec = Predpis.objects.create(nazev='BILL', zakaznik=cls.customer)
        cls.head = TypHlavy.objects.create(nazev='BILL')
        cls.order = Zakazka.objects.create(
            kamion_prijem=cls.incoming, kamion_vydej=cls.truck,
            predpis=cls.spec, typ_hlavy=cls.head, artikl='BILL-A',
            prumer=8, delka=100, popis='Fakturační test',
        )
        cls.price = Cena.objects.create(
            zakaznik=cls.customer, popis='BILL', delka_min=0, delka_max=200,
            cena_za_kg=Decimal('1.05'), cena_rovnani_za_kg=Decimal('0.95'),
            cena_tryskani_za_kg=Decimal('0.15'),
        )
        cls.price.predpis.add(cls.spec)
        cls.first = cls.make_crate(cls.order, vyrobni_zakazka='BILL-1')
        cls.second = cls.make_crate(cls.order, vyrobni_zakazka='BILL-2')
        cls.user = get_user_model().objects.create_superuser('billing', 'bill@example.com', None)

    @staticmethod
    def make_crate(order, **values):
        defaults = dict(
            zakazka=order, hmotnost=Decimal('100.1'), tara=20, mnozstvi=1,
            fakturovat=True, fakturovat_kaleni=True,
            fakturovat_rovnani=True, fakturovat_tryskani=True,
            rovnat=RovnaniChoice.VYROVNANA, tryskat=TryskaniChoice.OTRYSKANA,
        )
        defaults.update(values)
        return Bedna.objects.create(**defaults)

    def set_mode(self, per_crate):
        self.customer.proforma_po_bednach = per_crate
        self.customer.save(update_fields=['proforma_po_bednach'])
        self.order = Zakazka.objects.select_related('kamion_prijem__zakaznik').get(pk=self.order.pk)
        self.truck.refresh_from_db()

    def snapshot(self, *crates):
        snapshot = Rozpracovanost.objects.create()
        for crate in crates:
            RozpracovanostBednaSnapshot.objects.create(
                rozpracovanost=snapshot, bedna=crate, stav_bedny=crate.stav_bedny,
                rovnat=crate.rovnat, tryskat=crate.tryskat, zinkovat=crate.zinkovat,
            )
        return snapshot

    def report(self, snapshot):
        request = RequestFactory().get('/')
        request.user = self.user
        with (
            patch('orders.actions.render_to_string', wraps=render_to_string) as render_mock,
            patch('orders.actions.finders.find', return_value=None),
            patch('orders.actions.HTML') as pdf_mock,
        ):
            pdf_mock.return_value.write_pdf.return_value = b'%PDF'
            response = actions.tisk_rozpracovanost_action(
                SimpleNamespace(message_user=Mock()), request,
                Rozpracovanost.objects.filter(pk=snapshot.pk),
            )
        self.assertEqual(response.status_code, 200)
        return render_mock.call_args.args[1]

    def order_amounts(self):
        return (self.order.cena_za_zakazku, self.order.cena_rovnani_za_zakazku,
                self.order.cena_tryskani_za_zakazku)

    def truck_amounts(self):
        return (self.truck.cena_za_kamion_vydej, self.truck.cena_rovnani_za_kamion_vydej,
                self.truck.cena_tryskani_za_kamion_vydej)


class BillingEligibilityTests(BillingTestBase):
    def test_list_rates_remain_visible_for_all_switches_and_states(self):
        for master, heat, straightening, blasting in product((False, True), repeat=4):
            for straight_state, blast_state in (('--', '--'), ('RO', 'CI'), ('KR', 'SP'), ('VY', 'OT')):
                with self.subTest(flags=(master, heat, straightening, blasting), states=(straight_state, blast_state)):
                    crate = Bedna(
                        zakazka=self.order, fakturovat=master, fakturovat_kaleni=heat,
                        fakturovat_rovnani=straightening, fakturovat_tryskani=blasting,
                        rovnat=straight_state, tryskat=blast_state,
                    )
                    self.assertEqual(
                        (crate.cena_za_kg, crate.cena_rovnani_za_kg, crate.cena_tryskani_za_kg),
                        (Decimal('1.05'), Decimal('0.95'), Decimal('0.15')),
                    )

    def test_amounts_cover_all_flags_and_every_technological_state(self):
        for flags in product((False, True), repeat=4):
            master, heat, straightening, blasting = flags
            for straight_state, blast_state in product(RovnaniChoice.values, TryskaniChoice.values):
                with self.subTest(flags=flags, straight=straight_state, blast=blast_state):
                    crate = Bedna(
                        zakazka=self.order, hmotnost=Decimal('100.1'),
                        fakturovat=master, fakturovat_kaleni=heat,
                        fakturovat_rovnani=straightening, fakturovat_tryskani=blasting,
                        rovnat=straight_state, tryskat=blast_state,
                    )
                    self.assertEqual(
                        (crate.cena_za_bednu, crate.cena_rovnani_za_bednu, crate.cena_tryskani_za_bednu),
                        (
                            Decimal('105.11') if master and heat else Decimal('0.00'),
                            Decimal('95.10') if master and straightening and straight_state == 'VY' else Decimal('0.00'),
                            Decimal('15.02') if master and blasting and blast_state == 'OT' else Decimal('0.00'),
                        ),
                    )

    def test_straightening_only_has_no_heat_count_weight_or_charge(self):
        Bedna.objects.filter(zakazka=self.order).update(fakturovat=False)
        Bedna.objects.filter(pk=self.first.pk).update(
            fakturovat=True, fakturovat_kaleni=False, fakturovat_tryskani=False,
        )
        for per_crate in (False, True):
            with self.subTest(per_crate=per_crate):
                self.set_mode(per_crate)
                self.assertEqual(self.order_amounts(), (Decimal('0.00'), Decimal('95.10'), Decimal('0.00')))
                self.assertEqual(self.truck_amounts(), self.order_amounts())
                for obj in (self.order, self.truck):
                    self.assertEqual(obj.pocet_beden_fakturovaneho_kaleni, 0)
                    self.assertEqual(obj.hmotnost_fakturovaneho_kaleni, Decimal('0'))
                    self.assertEqual(obj.pocet_vyrovnanych_beden, 1)
                    self.assertEqual(obj.hmotnost_vyrovnanych_beden, Decimal('100.1'))
                    self.assertEqual(obj.pocet_otryskanych_beden, 0)
                    self.assertEqual(obj.hmotnost_otryskanych_beden, Decimal('0'))

    def test_zero_rate_does_not_remove_crates_from_counts_and_weights(self):
        Cena.objects.filter(pk=self.price.pk).update(
            cena_za_kg=0, cena_rovnani_za_kg=0, cena_tryskani_za_kg=0,
        )
        self.assertEqual(self.order_amounts(), (Decimal('0.00'),) * 3)
        for obj in (self.order, self.truck):
            self.assertEqual(obj.pocet_beden_fakturovaneho_kaleni, 2)
            self.assertEqual(obj.pocet_vyrovnanych_beden, 2)
            self.assertEqual(obj.pocet_otryskanych_beden, 2)
            self.assertEqual(obj.hmotnost_fakturovaneho_kaleni, Decimal('200.2'))
        self.assertEqual(len(validate_proforma_pricing(self.truck)), 3)

    def test_atypical_crates_follow_the_same_billing_rules(self):
        Bedna.objects.filter(zakazka=self.order).update(
            atypicky_prubeh=True, fakturovat_kaleni=False,
            fakturovat_tryskani=False, fakturovat_zinkovani=True,
        )
        self.assertEqual(self.order_amounts(), (Decimal('0.00'), Decimal('190.19'), Decimal('0.00')))

    def test_zinc_switch_alone_has_no_billed_amount(self):
        Bedna.objects.filter(zakazka=self.order).update(
            fakturovat_kaleni=False, fakturovat_rovnani=False,
            fakturovat_tryskani=False, fakturovat_zinkovani=True,
        )
        self.assertEqual(self.order_amounts(), (Decimal('0.00'),) * 3)
        self.assertEqual(validate_proforma_pricing(self.truck), [])

    def test_admin_labels_distinguish_list_rates_from_billed_amounts(self):
        for model in (Bedna, Zakazka):
            for field in ('cena_za_kg', 'cena_rovnani_za_kg', 'cena_tryskani_za_kg'):
                self.assertIn('Ceníková cena', label_for_field(field, model))
        self.assertIn('Účtovaná cena', label_for_field('cena_za_bednu', Bedna))

    def test_mixed_crates_reconcile_counts_weights_and_amounts_across_outputs(self):
        Bedna.objects.filter(pk=self.second.pk).update(fakturovat=False)
        crates = [
            self.first, self.second,
            self.make_crate(self.order, hmotnost=Decimal('50.1'), rovnat='RO'),
            self.make_crate(self.order, hmotnost=Decimal('70.1'), fakturovat_kaleni=False, tryskat='CI'),
            self.make_crate(self.order, hmotnost=Decimal('80.1'), fakturovat_rovnani=False, fakturovat_tryskani=False),
            self.make_crate(self.order, hmotnost=Decimal('90.1'), fakturovat_kaleni=False,
                            fakturovat_rovnani=False, tryskat='SP'),
        ]
        snapshot = self.snapshot(*crates)
        for per_crate, totals in (
            (False, ('241.82', '161.69', '22.53')),
            (True, ('241.83', '161.70', '22.54')),
        ):
            with self.subTest(per_crate=per_crate):
                self.set_mode(per_crate)
                expected = tuple(map(Decimal, totals))
                self.assertEqual(self.order_amounts(), expected)
                self.assertEqual(self.truck_amounts(), expected)
                for obj in (self.order, self.truck):
                    self.assertEqual(
                        (obj.pocet_beden_fakturovaneho_kaleni, obj.pocet_vyrovnanych_beden, obj.pocet_otryskanych_beden),
                        (3, 2, 2),
                    )
                    self.assertEqual(
                        (obj.hmotnost_fakturovaneho_kaleni, obj.hmotnost_vyrovnanych_beden, obj.hmotnost_otryskanych_beden),
                        tuple(map(Decimal, ('230.3', '170.2', '150.2'))),
                    )
                section = self.report(snapshot)['sections'][0]
                self.assertEqual(
                    (section['sum_cena_netto'], section['sum_rovnani_cena_netto'], section['sum_tryskani_cena_netto']),
                    expected,
                )
                row = section['zakazky'][0]
                self.assertEqual((row['pocet_beden'], row['rovnani_pocet_beden'], row['tryskani_pocet_beden']), (3, 2, 2))


class BillingRoundingTests(BillingTestBase):
    def test_order_mode_rounds_total_weight_for_each_operation(self):
        self.set_mode(False)
        expected = tuple(map(Decimal, ('210.21', '190.19', '30.03')))
        self.assertEqual(self.order_amounts(), expected)
        self.assertEqual(self.truck_amounts(), expected)
        self.assertEqual(self.first.cena_za_bednu, Decimal('105.11'))
        self.assertNotEqual(self.order.cena_za_zakazku, self.first.cena_za_bednu + self.second.cena_za_bednu)

    def test_crate_mode_sums_rounded_crates_for_each_operation(self):
        self.set_mode(True)
        expected = tuple(map(Decimal, ('210.22', '190.20', '30.04')))
        self.assertEqual(self.order_amounts(), expected)
        self.assertEqual(self.truck_amounts(), expected)

    def test_changing_customer_mode_changes_only_aggregate_rounding(self):
        for mode, expected in ((False, '210.21'), (True, '210.22'), (False, '210.21')):
            self.set_mode(mode)
            self.assertEqual(self.order.cena_za_zakazku, Decimal(expected))
            self.assertEqual(self.truck.cena_za_kamion_vydej, Decimal(expected))
            self.assertEqual(self.first.cena_za_bednu, Decimal('105.11'))
            self.assertEqual(self.first.cena_za_kg, Decimal('1.05'))

    def test_truck_sums_rounded_orders_instead_of_repricing_combined_weight(self):
        Bedna.objects.filter(zakazka=self.order).update(hmotnost=Decimal('0.1'))
        second_order = Zakazka.objects.create(
            kamion_prijem=self.incoming, kamion_vydej=self.truck,
            predpis=self.spec, typ_hlavy=self.head, artikl='BILL-B',
            prumer=8, delka=100, popis='Druhá zakázka',
        )
        Bedna.objects.filter(pk=self.second.pk).update(zakazka=second_order)
        self.assertEqual(self.order.cena_za_zakazku, Decimal('0.11'))
        self.assertEqual(second_order.cena_za_zakazku, Decimal('0.11'))
        self.assertEqual(self.truck.cena_za_kamion_vydej, Decimal('0.22'))

    def test_empty_order_and_incoming_truck_have_zero_amounts(self):
        Bedna.objects.filter(zakazka=self.order).update(zakazka=Zakazka.objects.create(
            kamion_prijem=self.incoming, predpis=self.spec, typ_hlavy=self.head,
            prumer=8, delka=100, popis='Mimo výdej',
        ))
        self.assertEqual(self.order_amounts(), (Decimal('0.00'),) * 3)
        self.assertEqual(self.truck_amounts(), (Decimal('0.00'),) * 3)
        self.assertEqual(self.incoming.cena_za_kamion_vydej, Decimal('0.00'))

    def test_length_boundaries_are_inclusive_at_start_and_exclusive_at_end(self):
        self.price.delka_max = Decimal('100')
        self.price.save()
        next_price = Cena.objects.create(
            zakaznik=self.customer, popis='Od 100', delka_min=100, delka_max=200,
            cena_za_kg=Decimal('2.05'), cena_rovnani_za_kg=Decimal('1.95'),
            cena_tryskani_za_kg=Decimal('0.25'),
        )
        next_price.predpis.add(self.spec)
        for length, expected in (
            ('99.9', ('1.05', '0.95', '0.15')),
            ('100.0', ('2.05', '1.95', '0.25')),
            ('199.9', ('2.05', '1.95', '0.25')),
            ('200.0', ('0.00', '0.00', '0.00')),
        ):
            with self.subTest(length=length):
                self.order.delka = Decimal(length)
                self.assertEqual(
                    (self.order.cena_za_kg, self.order.cena_rovnani_za_kg, self.order.cena_tryskani_za_kg),
                    tuple(map(Decimal, expected)),
                )


class BillingDocumentTests(BillingTestBase):
    def test_order_proforma_cells_reconcile_weight_rate_count_and_total(self):
        self.set_mode(False)
        rows = ProformaRows(render_to_string(
            'orders/proforma_faktura_po_zakazkach.html', {'kamion': self.truck},
        )).rows
        item = next(row for row in rows if row[0] == 'BILL-A')
        self.assertEqual(item[4:], [
            '2', '200,2', '1,05', '210,21',
            '2', '200,2', '0,95', '190,19',
            '2', '200,2', '0,15', '30,03',
        ])
        self.assertEqual(rows[-1][1:], [
            '2ks', '200,2kg', '', '210,21€',
            '2ks', '200,2kg', '', '190,19€',
            '2ks', '200,2kg', '', '30,03€',
        ])

    def test_crate_proforma_footer_is_sum_of_actual_printed_amounts(self):
        self.set_mode(True)
        rows = ProformaRows(render_to_string(
            'orders/proforma_faktura_po_bednach.html', {'kamion': self.truck},
        )).rows
        items = [row for row in rows if len(row) > 2 and row[2] == 'BILL-A']
        self.assertEqual(len(items), 2)
        for item in items:
            self.assertEqual(item[5:], [
                '100,1kg', '1,05€', '105,11€',
                '100,1kg', '0,95€', '95,10€',
                '100,1kg', '0,15€', '15,02€',
            ])
        self.assertEqual(rows[-1][1:], [
            '200,2kg', '', '210,22€',
            '200,2kg', '', '190,20€',
            '200,2kg', '', '30,04€',
        ])

    def test_proformas_keep_list_rate_when_operation_is_not_billed(self):
        Bedna.objects.filter(zakazka=self.order).update(fakturovat_kaleni=False)
        for per_crate, template in (
            (False, 'proforma_faktura_po_zakazkach'),
            (True, 'proforma_faktura_po_bednach'),
        ):
            with self.subTest(per_crate=per_crate):
                self.set_mode(per_crate)
                rows = ProformaRows(render_to_string(f'orders/{template}.html', {'kamion': self.truck})).rows
                if per_crate:
                    item = next(row for row in rows if len(row) > 2 and row[2] == 'BILL-A')
                    self.assertEqual(item[5:8], ['0,0kg', '1,05€', '0,00€'])
                else:
                    item = next(row for row in rows if row[0] == 'BILL-A')
                    self.assertEqual(item[4:8], ['0', '0,0', '1,05', '0,00'])

    def test_proformas_exclude_whole_nonbillable_orders_and_crates(self):
        Bedna.objects.filter(zakazka=self.order).update(fakturovat=False)
        for per_crate, template in (
            (False, 'proforma_faktura_po_zakazkach'),
            (True, 'proforma_faktura_po_bednach'),
        ):
            self.set_mode(per_crate)
            rows = ProformaRows(render_to_string(f'orders/{template}.html', {'kamion': self.truck})).rows
            self.assertFalse(any('BILL-A' in row for row in rows))
            self.assertEqual(self.truck_amounts(), (Decimal('0.00'),) * 3)

    def test_report_uses_customer_mode_for_every_operation(self):
        snapshot = self.snapshot(self.first, self.second)
        for per_crate, expected in (
            (False, ('210.21', '190.19', '30.03')),
            (True, ('210.22', '190.20', '30.04')),
        ):
            with self.subTest(per_crate=per_crate):
                self.set_mode(per_crate)
                section = self.report(snapshot)['sections'][0]
                row = section['zakazky'][0]
                self.assertEqual(
                    (row['cena_netto'], row['rovnani_cena_netto'], row['tryskani_cena_netto']),
                    tuple(map(Decimal, expected)),
                )
                self.assertEqual(
                    (section['sum_cena_netto'], section['sum_rovnani_cena_netto'], section['sum_tryskani_cena_netto']),
                    self.truck_amounts(),
                )
                self.assertEqual((row['pocet_beden'], row['rovnani_pocet_beden'], row['tryskani_pocet_beden']), (2, 2, 2))
                self.assertEqual((row['hmotnost'], row['rovnani_hmotnost'], row['tryskani_hmotnost']), (Decimal('200.2'),) * 3)

    def test_report_never_adds_other_crates_from_same_order(self):
        snapshot = self.snapshot(self.first)
        for per_crate in (False, True):
            self.set_mode(per_crate)
            row = self.report(snapshot)['sections'][0]['zakazky'][0]
            self.assertEqual(
                (row['cena_netto'], row['rovnani_cena_netto'], row['tryskani_cena_netto']),
                tuple(map(Decimal, ('105.11', '95.10', '15.02'))),
            )
            self.assertEqual(row['pocet_beden'], 1)
            self.assertEqual(row['hmotnost'], Decimal('100.1'))

    def test_report_counts_only_actual_billed_operations_and_selected_crates(self):
        Bedna.objects.filter(pk=self.first.pk).update(fakturovat_kaleni=False, tryskat='CI')
        Bedna.objects.filter(pk=self.second.pk).update(fakturovat=False)
        snapshot = self.snapshot(self.first, self.second)
        section = self.report(snapshot)['sections'][0]
        row = section['zakazky'][0]
        self.assertEqual((row['pocet_beden'], row['rovnani_pocet_beden'], row['tryskani_pocet_beden']), (0, 1, 0))
        self.assertEqual((row['hmotnost'], row['rovnani_hmotnost'], row['tryskani_hmotnost']),
                         (Decimal('0'), Decimal('100.1'), Decimal('0')))
        self.assertEqual(row['rovnani_cena_netto'], Decimal('95.10'))
        self.assertEqual(row['cena_kg'], Decimal('1.05'))

    def test_report_warns_only_about_prices_for_billed_operations(self):
        Bedna.objects.filter(zakazka=self.order).update(rovnat='RO', tryskat='CI')
        Cena.objects.filter(pk=self.price.pk).update(cena_rovnani_za_kg=None, cena_tryskani_za_kg=None)
        snapshot = self.snapshot(self.first, self.second)
        self.assertEqual(self.report(snapshot)['pricing_warnings'], [])
        Bedna.objects.filter(pk=self.first.pk).update(rovnat='VY')
        warnings = self.report(snapshot)['pricing_warnings']
        self.assertEqual(len(warnings), 1)
        self.assertIn('cena rovnání', warnings[0])

    def test_report_keeps_different_customer_modes_and_prices_separate(self):
        other_customer = Zakaznik.objects.create(
            nazev='Druhý zákazník', zkraceny_nazev='OTHER', zkratka='EUR',
            ciselna_rada=300000, proforma_po_bednach=True,
        )
        incoming = Kamion.objects.create(zakaznik=other_customer, datum=date(2026, 11, 16))
        spec = Predpis.objects.create(nazev='OTHER', zakaznik=other_customer)
        order = Zakazka.objects.create(
            kamion_prijem=incoming, predpis=spec, typ_hlavy=self.head,
            artikl='OTHER-A', prumer=8, delka=100, popis='Jiná cena a režim',
        )
        price = Cena.objects.create(
            zakaznik=other_customer, popis='OTHER', delka_min=0, delka_max=200,
            cena_za_kg=Decimal('2.05'),
        )
        price.predpis.add(spec)
        other_crates = [
            self.make_crate(order, fakturovat_rovnani=False, fakturovat_tryskani=False)
            for _ in range(2)
        ]
        context = self.report(self.snapshot(self.first, self.second, *other_crates))
        totals = {section['zakaznik'].pk: section['sum_cena_netto'] for section in context['sections']}
        self.assertEqual(totals, {self.customer.pk: Decimal('210.21'), other_customer.pk: Decimal('410.42')})
        self.assertEqual(context['pricing_warnings'], [])

    def test_pdf_view_selects_matching_template_for_both_modes(self):
        self.client.force_login(self.user)
        url = reverse('proforma_kamion_vydej_pdf', args=[self.truck.pk])
        for per_crate, template in (
            (False, 'proforma_faktura_po_zakazkach'),
            (True, 'proforma_faktura_po_bednach'),
        ):
            self.set_mode(per_crate)
            with patch('orders.views.utilita_tisk_dl_a_proforma_faktury') as pdf:
                pdf.return_value = HttpResponse(b'%PDF', content_type='application/pdf')
                self.assertEqual(self.client.get(url).status_code, 200)
                self.assertEqual(pdf.call_args.args[3], f'orders/{template}.html')

    def test_direct_pdf_view_revalidates_prices_and_does_not_generate_invalid_pdf(self):
        self.client.force_login(self.user)
        url = reverse('proforma_kamion_vydej_pdf', args=[self.truck.pk])
        Cena.objects.filter(pk=self.price.pk).update(cena_rovnani_za_kg=None)
        with patch('orders.views.utilita_tisk_dl_a_proforma_faktury') as pdf:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 400)
            self.assertContains(response, 'cena rovnání', status_code=400)
            pdf.assert_not_called()


class BillingValidationTests(BillingTestBase):
    def test_straightening_only_does_not_require_positive_heat_or_blasting_price(self):
        Bedna.objects.filter(zakazka=self.order).update(fakturovat_kaleni=False, fakturovat_tryskani=False)
        Cena.objects.filter(pk=self.price.pk).update(cena_za_kg=0, cena_tryskani_za_kg=None)
        self.assertEqual(validate_proforma_pricing(self.truck), [])
        self.assertEqual(self.order_amounts(), (Decimal('0.00'), Decimal('190.19'), Decimal('0.00')))

    def test_unused_and_unperformed_operations_do_not_require_prices(self):
        Cena.objects.filter(pk=self.price.pk).update(cena_rovnani_za_kg=None, cena_tryskani_za_kg=None)
        Bedna.objects.filter(zakazka=self.order).update(rovnat='RO', tryskat='CI')
        self.assertEqual(validate_proforma_pricing(self.truck), [])
        Bedna.objects.filter(zakazka=self.order).update(
            rovnat='VY', tryskat='OT', fakturovat_rovnani=False, fakturovat_tryskani=False,
        )
        self.assertEqual(validate_proforma_pricing(self.truck), [])

    def test_each_actually_billed_operation_requires_positive_price(self):
        for field, label, values in (
            ('cena_za_kg', 'kalení', ('0.00', '-1.00')),
            ('cena_rovnani_za_kg', 'rovnání', (None, '0.00', '-1.00')),
            ('cena_tryskani_za_kg', 'tryskání', (None, '0.00', '-1.00')),
        ):
            original = getattr(self.price, field)
            for value in values:
                with self.subTest(field=field, value=value):
                    Cena.objects.filter(pk=self.price.pk).update(**{field: value})
                    errors = validate_proforma_pricing(self.truck)
                    self.assertEqual(len(errors), 1)
                    self.assertIn(f'cena {label}', errors[0])
            Cena.objects.filter(pk=self.price.pk).update(**{field: original})

    def test_missing_and_overlapping_price_records_block_proforma(self):
        duplicate = Cena.objects.create(
            zakaznik=self.customer, popis='Překryv', delka_min=0, delka_max=200,
            cena_za_kg=2, cena_rovnani_za_kg=1, cena_tryskani_za_kg=1,
        )
        duplicate.predpis.add(self.spec)
        self.assertIn('nalezeno více cen', ' '.join(validate_proforma_pricing(self.truck)))
        duplicate.delete()
        self.price.predpis.clear()
        self.assertIn('nenalezena cena', ' '.join(validate_proforma_pricing(self.truck)))

    def test_nonbillable_and_empty_orders_do_not_require_price_records(self):
        self.price.predpis.clear()
        Bedna.objects.filter(zakazka=self.order).update(fakturovat=False)
        self.assertEqual(validate_proforma_pricing(self.truck), [])
        Zakazka.objects.create(
            kamion_prijem=self.incoming, kamion_vydej=self.truck, predpis=self.spec,
            typ_hlavy=self.head, prumer=8, delka=300, popis='Prázdná bez ceny',
        )
        self.assertEqual(validate_proforma_pricing(self.truck), [])

    def test_missing_zero_and_negative_weight_block_only_billable_crates(self):
        for weight in (None, Decimal('0'), Decimal('-0.1')):
            with self.subTest(weight=weight):
                Bedna.objects.filter(pk=self.first.pk).update(hmotnost=weight)
                errors = validate_proforma_pricing(self.truck)
                self.assertEqual(len(errors), 1)
                self.assertIn('kladná fakturovaná hmotnost', errors[0])
                Bedna.objects.filter(pk=self.first.pk).update(fakturovat=False)
                self.assertEqual(validate_proforma_pricing(self.truck), [])
                Bedna.objects.filter(pk=self.first.pk).update(fakturovat=True)

    def test_pdf_view_also_rejects_missing_weight(self):
        self.client.force_login(self.user)
        Bedna.objects.filter(pk=self.first.pk).update(hmotnost=None)
        response = self.client.get(reverse('proforma_kamion_vydej_pdf', args=[self.truck.pk]))
        self.assertContains(response, 'kladná fakturovaná hmotnost', status_code=400)

    def test_cross_customer_order_is_rejected_before_using_another_price_or_mode(self):
        other = Zakaznik.objects.create(
            nazev='Jiný', zkraceny_nazev='JINY', zkratka='OTH', ciselna_rada=300000,
            proforma_po_bednach=True,
        )
        Kamion.objects.filter(pk=self.incoming.pk).update(zakaznik=other)
        self.assertIn('zákazník příjmu neodpovídá', ' '.join(validate_proforma_pricing(self.truck)))

    def test_customer_billing_defaults_do_not_override_saved_crate_switches(self):
        self.assertFalse(self.customer.fakturovat_rovnani)
        self.assertFalse(self.customer.fakturovat_tryskani)
        self.assertEqual(self.order_amounts(), tuple(map(Decimal, ('210.21', '190.19', '30.03'))))
        self.assertEqual(validate_proforma_pricing(self.truck), [])
