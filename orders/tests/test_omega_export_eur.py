from datetime import date
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import reverse

from orders.admin import KamionAdmin
from orders.choices import KamionChoice, PrijemVydejChoice, RovnaniChoice, StavBednyChoice, TryskaniChoice
from orders.models import Bedna, Cena, Kamion, Predpis, TypHlavy, Zakazka, Zakaznik
from orders.services.exceptions import ServiceValidationError
from orders.services.omega_export_service import build_eur_delivery_note, build_omega_delivery_note


class EurOmegaExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = Zakaznik.objects.create(
            nazev='EUR test', zkraceny_nazev='EUR', zkratka='EUR', ciselna_rada=100000,
            proforma_po_bednach=False, fakturovat_tryskani=True,
        )
        cls.incoming = Kamion.objects.create(zakaznik=cls.customer, datum=date(2026, 10, 1))
        cls.outgoing = Kamion.objects.create(
            zakaznik=cls.customer, datum=date(2026, 11, 3), prijem_vydej=KamionChoice.VYDEJ,
        )
        head = TypHlavy.objects.create(nazev='SK')
        specification = Predpis.objects.create(nazev='EUR export', zakaznik=cls.customer)
        cls.first = Zakazka.objects.create(
            kamion_prijem=cls.incoming, kamion_vydej=cls.outgoing,
            artikl='000123456789', popis='HSPT SK vruty 8x160',
            prumer=Decimal('8.0'), delka=Decimal('160.0'), predpis=specification, typ_hlavy=head,
        )
        cls.second = Zakazka.objects.create(
            kamion_prijem=cls.incoming, kamion_vydej=cls.outgoing,
            artikl='ART-002', popis='Druhý vrut 8x220',
            prumer=Decimal('8.5'), delka=Decimal('220.0'), predpis=specification, typ_hlavy=head,
        )
        cls.first_price = Cena.objects.create(
            zakaznik=cls.customer, popis='Krátké EUR', delka_min=0, delka_max=200,
            cena_za_kg=Decimal('1.05'), cena_tryskani_za_kg=Decimal('0.15'),
            cena_rovnani_za_kg=Decimal('0.20'),
        )
        cls.second_price = Cena.objects.create(
            zakaznik=cls.customer, popis='Dlouhé EUR', delka_min=200, delka_max=1000,
            cena_za_kg=Decimal('2.00'), cena_tryskani_za_kg=Decimal('0.15'),
            cena_rovnani_za_kg=Decimal('0.20'),
        )
        cls.first_price.predpis.add(specification)
        cls.second_price.predpis.add(specification)
        cls.crates = [Bedna.objects.create(
            zakazka=order, hmotnost=Decimal('100.1'), tara=25, mnozstvi=1,
            stav_bedny=StavBednyChoice.EXPEDOVANO, tryskat=TryskaniChoice.OTRYSKANA,
            rovnat=RovnaniChoice.ROVNA, fakturovat_kaleni=True, fakturovat_tryskani=True,
        ) for order in (cls.first, cls.first, cls.second)]
        cls.staff = get_user_model().objects.create_user('eur-export', is_staff=True)
        cls.staff.user_permissions.add(Permission.objects.get(
            content_type__app_label='orders', codename='view_kamion',
        ))
        cls.url = reverse('admin:orders_kamion_changelist')

    def setUp(self):
        self.client.force_login(self.staff)

    def action_data(self, **extra):
        return {
            'action': 'export_omega_action', '_selected_action': str(self.outgoing.pk),
            'select_across': '0', **extra,
        }

    def test_heat_is_grouped_by_order_and_blasting_is_one_piece(self):
        note = build_omega_delivery_note(self.outgoing)
        self.assertEqual(len(note.lines), 3)
        first, second, blasting = note.lines
        self.assertEqual(first.name, 'HSPT SK vruty, 8x160')
        self.assertEqual(first.order_number, '000123456789')
        self.assertEqual(first.quantity, Decimal('200.2'))
        self.assertEqual(first.total, Decimal('210.21'))  # Po bednách by vyšlo 210,22.
        self.assertEqual(second.name, 'Druhý vrut, 8,5x220')
        self.assertEqual(second.total, Decimal('200.20'))
        self.assertEqual(blasting.name, 'Sandblasting of screws (300,3kg x 0,15EUR)')
        self.assertEqual((blasting.quantity, blasting.unit), (Decimal('1'), 'ks'))
        self.assertEqual(blasting.unit_price, Decimal('45.05'))
        self.assertEqual(blasting.total, self.outgoing.cena_tryskani_za_kamion_vydej)
        self.assertEqual(first.total + second.total, self.outgoing.cena_za_kamion_vydej)
        self.assertEqual(note.total, Decimal('455.46'))
        self.assertEqual(note.weight, Decimal('300.3'))  # Souhrnný ks se nepřičítá ke kg.
        self.assertEqual(note.weight, self.outgoing.hmotnost_fakturovaneho_kaleni)
        html = render_to_string('orders/proforma_faktura_po_zakazkach.html', {'kamion': self.outgoing})
        self.assertIn('410,41', html)
        self.assertIn('45,05', html)

    def test_txt_field_positions_and_header_sum(self):
        rows = [row.split('\t') for row in build_eur_delivery_note(self.outgoing).to_bytes().decode('cp1250').splitlines()]
        self.assertEqual(rows[0], ['R00', 'T01'])
        self.assertEqual(rows[1][16:18], ['455.46', '2'])
        self.assertEqual(rows[1][39:43], ['EUR', '1', '1', '455.46'])
        self.assertEqual(len(rows[1]), 64)
        self.assertEqual(rows[1][43:60], [''] * 17)
        self.assertEqual(rows[1][60:64], ['-2', '3', '', '-2'])
        for row in rows[2:]:  # Kalení i souhrn tryskání mají vlastní nastavení.
            self.assertEqual(len(row), 46)
            self.assertEqual(row[19:29], [''] * 10)
            self.assertEqual(row[29], 'Osv')
            self.assertEqual(row[30:44], [''] * 14)
            self.assertEqual(row[44:46], ['-2', '3'])
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[2][1:5], ['HSPT SK vruty, 8x160', '200.2', 'kg', '1.05'])
        self.assertEqual(rows[2][10], '')
        self.assertEqual(rows[2][16:19], ['', '000123456789', ''])
        self.assertEqual(rows[3][16:19], ['', 'ART-002', ''])
        self.assertEqual(rows[4][2:5], ['1', 'ks', '45.05'])
        self.assertEqual(rows[4][10], '')
        self.assertEqual(rows[4][16:19], ['', '', ''])

    def test_blasting_uses_sum_of_rounded_order_totals_not_total_weight_times_rate(self):
        Bedna.objects.filter(pk=self.crates[1].pk).update(fakturovat=False)
        Bedna.objects.filter(pk__in=[self.crates[0].pk, self.crates[2].pk]).update(hmotnost=Decimal('0.1'))
        note = build_eur_delivery_note(self.outgoing)
        self.assertEqual(note.lines[-1].name, 'Sandblasting of screws (0,2kg x 0,15EUR)')
        self.assertEqual(note.lines[-1].unit_price, Decimal('0.04'))
        self.assertEqual(note.lines[-1].total, self.outgoing.cena_tryskani_za_kamion_vydej)

    def test_nonbillable_crates_and_disabled_operations_do_not_add_weight_or_amount(self):
        Bedna.objects.filter(pk=self.crates[0].pk).update(fakturovat=False)
        Bedna.objects.filter(pk=self.crates[1].pk).update(fakturovat_kaleni=False)
        Bedna.objects.filter(pk=self.crates[2].pk).update(fakturovat_tryskani=False)
        note = build_eur_delivery_note(self.outgoing)
        self.assertEqual(len(note.lines), 2)
        self.assertEqual(note.lines[0].order_number, 'ART-002')
        self.assertEqual(note.lines[0].quantity, Decimal('100.1'))
        self.assertEqual(note.lines[-1].name, 'Sandblasting of screws (100,1kg x 0,15EUR)')
        self.assertEqual(note.total, Decimal('215.22'))

    def test_zero_blasting_omits_summary_row_and_heat_exclusions_allow_blasting_only(self):
        Bedna.objects.update(fakturovat_tryskani=False)
        self.assertEqual(len(build_eur_delivery_note(self.outgoing).lines), 2)
        Bedna.objects.update(fakturovat_tryskani=True, fakturovat_kaleni=False)
        note = build_eur_delivery_note(self.outgoing)
        self.assertEqual(len(note.lines), 1)
        self.assertEqual(note.lines[0].unit, 'ks')
        self.assertEqual(note.weight, 0)
        self.assertEqual(note.total, Decimal('45.05'))

    def test_blasting_rate_must_be_positive_for_every_blasted_crate(self):
        for rate in (Decimal('-0.01'), Decimal('0'), None):
            with self.subTest(rate=rate):
                Cena.objects.filter(pk=self.second_price.pk).update(cena_tryskani_za_kg=rate)
                with self.assertRaisesMessage(ServiceValidationError, 'kladná cena tryskání'):
                    build_eur_delivery_note(self.outgoing)

    def test_rate_check_also_applies_to_nonbillable_blasted_crates(self):
        Bedna.objects.filter(pk=self.crates[2].pk).update(fakturovat=False)
        Cena.objects.filter(pk=self.second_price.pk).update(cena_tryskani_za_kg=Decimal('0'))
        with self.assertRaisesMessage(ServiceValidationError, 'kladná cena tryskání'):
            build_eur_delivery_note(self.outgoing)

    def test_blasting_groups_multiple_orders_by_rate_and_keeps_proforma_totals(self):
        Cena.objects.filter(pk=self.second_price.pk).update(
            delka_max=300, cena_tryskani_za_kg=Decimal('0.25'),
        )
        third_price = Cena.objects.create(
            zakaznik=self.customer, popis='Nejdelší EUR', delka_min=300, delka_max=1000,
            cena_za_kg=Decimal('2.00'), cena_tryskani_za_kg=Decimal('0.50'),
        )
        third_price.predpis.add(self.first.predpis)
        for length in (Decimal('400'), Decimal('160')):
            order = Zakazka.objects.create(
                kamion_prijem=self.incoming, kamion_vydej=self.outgoing,
                artikl=f'ART-{length}', popis=f'Vrut {length}', prumer=8, delka=length,
                predpis=self.first.predpis, typ_hlavy=self.first.typ_hlavy,
            )
            Bedna.objects.create(
                zakazka=order, hmotnost=Decimal('0.1'), tara=25, mnozstvi=1,
                stav_bedny=StavBednyChoice.EXPEDOVANO, tryskat=TryskaniChoice.OTRYSKANA,
                fakturovat_kaleni=True, fakturovat_tryskani=True,
            )
        note = build_omega_delivery_note(self.outgoing)
        blasting = [line for line in note.lines if line.operation == 'Tryskání']
        self.assertEqual([(line.name, line.total) for line in blasting], [
            ('Sandblasting of screws (200,3kg x 0,15EUR)', Decimal('30.05')),
            ('Sandblasting of screws (100,1kg x 0,25EUR)', Decimal('25.03')),
            ('Sandblasting of screws (0,1kg x 0,50EUR)', Decimal('0.05')),
        ])
        self.assertTrue(all(line.quantity == 1 and line.unit == 'ks' and line.unit_price == line.total
                            for line in blasting))
        self.assertEqual(sum(line.total for line in blasting), self.outgoing.cena_tryskani_za_kamion_vydej)
        self.assertEqual(note.total, self.outgoing.cena_za_kamion_vydej + self.outgoing.cena_tryskani_za_kamion_vydej)
        rows = [row.split('\t') for row in note.to_bytes().decode('cp1250').splitlines()]
        self.assertEqual(rows[1][16], str(note.total))
        self.assertTrue(all(row[29] == 'Osv' for row in rows[2:]))
        self.assertTrue(all(row[10] == row[17] == row[18] == '' and row[2:4] == ['1', 'ks']
                            for row in rows[-3:]))
        response = self.client.post(self.url, self.action_data())
        for line in blasting:
            self.assertContains(response, line.name)
        response = self.client.post(self.url, self.action_data(omega_download='1'))
        self.assertEqual(response.content, note.to_bytes())

    def test_nonbillable_and_disabled_blasting_do_not_create_rate_groups(self):
        Cena.objects.filter(pk=self.second_price.pk).update(cena_tryskani_za_kg=Decimal('0.50'))
        for excluded in ({'fakturovat': False}, {'fakturovat_tryskani': False}, {'tryskat': TryskaniChoice.CISTA}):
            with self.subTest(excluded=excluded):
                Bedna.objects.filter(pk=self.crates[2].pk).update(
                    fakturovat=True, fakturovat_tryskani=True, tryskat=TryskaniChoice.OTRYSKANA,
                )
                Bedna.objects.filter(pk=self.crates[2].pk).update(**excluded)
                blasting = [line for line in build_eur_delivery_note(self.outgoing).lines if line.operation == 'Tryskání']
                self.assertEqual([(line.name, line.total) for line in blasting], [
                    ('Sandblasting of screws (200,2kg x 0,15EUR)', Decimal('30.03')),
                ])

    def test_clean_crate_does_not_require_blasting_rate(self):
        Bedna.objects.filter(pk=self.crates[2].pk).update(tryskat=TryskaniChoice.CISTA)
        Cena.objects.filter(pk=self.second_price.pk).update(cena_tryskani_za_kg=None)
        self.assertEqual(build_eur_delivery_note(self.outgoing).lines[-1].total, Decimal('30.03'))

    def test_nonzero_straightening_blocks_export_but_unperformed_straightening_does_not(self):
        Bedna.objects.filter(pk=self.crates[0].pk).update(fakturovat_rovnani=True)
        self.assertTrue(build_eur_delivery_note(self.outgoing).lines)
        Bedna.objects.filter(pk=self.crates[0].pk).update(rovnat=RovnaniChoice.VYROVNANA)
        for builder in (build_eur_delivery_note, build_omega_delivery_note):
            with self.assertRaisesMessage(ServiceValidationError, 'rovnání'):
                builder(self.outgoing)

    def test_enabled_zinc_blocks_export_for_eur_and_nonbillable_zinc_is_excluded(self):
        Bedna.objects.filter(pk=self.crates[0].pk).update(fakturovat_zinkovani=True)
        for builder in (build_eur_delivery_note, build_omega_delivery_note):
            with self.assertRaisesMessage(ServiceValidationError, 'zinkování'):
                builder(self.outgoing)
        Bedna.objects.filter(pk=self.crates[0].pk).update(fakturovat=False)
        self.assertTrue(build_eur_delivery_note(self.outgoing).lines)

    def test_rejects_wrong_grouping_unshipped_crates_invalid_prices_and_empty_truck(self):
        self.outgoing.zakaznik.proforma_po_bednach = True
        with self.assertRaisesMessage(ServiceValidationError, 'po zakázkách'):
            build_eur_delivery_note(self.outgoing)
        self.outgoing.zakaznik.proforma_po_bednach = False
        Bedna.objects.filter(pk=self.crates[0].pk).update(stav_bedny=StavBednyChoice.PRIJATO)
        with self.assertRaisesMessage(ServiceValidationError, 'Expedováno'):
            build_eur_delivery_note(self.outgoing)
        Bedna.objects.filter(pk=self.crates[0].pk).update(stav_bedny=StavBednyChoice.EXPEDOVANO)
        Cena.objects.filter(pk=self.first_price.pk).update(cena_za_kg=0)
        with self.assertRaisesMessage(ServiceValidationError, 'cena kalení'):
            build_eur_delivery_note(self.outgoing)
        Bedna.objects.update(fakturovat=False)
        with self.assertRaisesMessage(ServiceValidationError, 'žádné fakturované'):
            build_eur_delivery_note(self.outgoing)

    def test_rejects_oversize_article_unsafe_description_and_cross_customer(self):
        Zakazka.objects.filter(pk=self.first.pk).update(artikl='X' * 21)
        with self.assertRaisesMessage(ServiceValidationError, '20 znaků'):
            build_eur_delivery_note(self.outgoing)
        Zakazka.objects.filter(pk=self.first.pk).update(artikl='000123456789', popis='Bad\tname')
        with self.assertRaisesMessage(ServiceValidationError, 'řídicí znak'):
            build_eur_delivery_note(self.outgoing)
        Zakazka.objects.filter(pk=self.first.pk).update(popis='Vrut 8x160')
        other = Zakaznik.objects.create(nazev='Other', zkraceny_nazev='OTH', zkratka='OTH', ciselna_rada=300000)
        Kamion.objects.filter(pk=self.incoming.pk).update(zakaznik=other)
        with self.assertRaisesMessage(ServiceValidationError, 'zákazník příjmu'):
            build_eur_delivery_note(self.outgoing)

    def test_incoming_and_unsupported_customers_are_rejected(self):
        with self.assertRaisesMessage(ServiceValidationError, 'kamion výdej'):
            build_omega_delivery_note(self.incoming)
        self.outgoing.zakaznik.zkratka = 'OTH'
        with self.assertRaisesMessage(ServiceValidationError, 'pouze zákazníky SPX a EUR'):
            build_omega_delivery_note(self.outgoing)

    def test_common_action_preview_and_download_revalidate_without_writes(self):
        history_count = Bedna.history.count()
        response = self.client.post(self.url, self.action_data())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sandblasting of screws')
        self.assertContains(response, 'EUR/MJ')
        self.assertContains(response, 'export_omega_action')
        self.assertContains(response, '455,46')
        response = self.client.post(self.url, self.action_data(omega_download='1'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, build_eur_delivery_note(self.outgoing).to_bytes())
        self.assertIn('omega_eur_', response['Content-Disposition'])
        self.assertEqual(Bedna.history.count(), history_count)
        Bedna.objects.filter(pk=self.crates[0].pk).update(fakturovat_zinkovani=True)
        response = self.client.post(self.url, self.action_data(omega_download='1'))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('Content-Disposition', response)
        self.assertTrue(any('zinkování' in str(message) for message in get_messages(response.wsgi_request)))

    def test_common_action_scope_and_permission(self):
        truck_admin = KamionAdmin(Kamion, admin.site)
        for mode in (PrijemVydejChoice.VYDEJ, PrijemVydejChoice.PRIJEM_NEPRIJATY):
            request = RequestFactory().get('/', {'prijem_vydej': mode})
            request.user = self.staff
            actions = truck_admin.get_actions(request)
            self.assertEqual('export_omega_action' in actions, mode == PrijemVydejChoice.VYDEJ)
            self.assertNotIn('export_omega_spx_action', actions)
        self.staff.user_permissions.clear()
        self.client.force_login(get_user_model().objects.get(pk=self.staff.pk))
        self.assertEqual(self.client.post(self.url, self.action_data()).status_code, 403)
