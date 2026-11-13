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
from orders.choices import KamionChoice, PrijemVydejChoice, StavBednyChoice
from orders.models import Bedna, Cena, Kamion, Predpis, TypHlavy, Zakazka, Zakaznik
from orders.services.exceptions import ServiceValidationError
from orders.services.omega_export_service import build_spx_delivery_note


class OmegaExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = Zakaznik.objects.create(
            nazev='SPAX International GmbH & Co. KG', zkraceny_nazev='SPAX',
            zkratka='SPX', ciselna_rada=200000, proforma_po_bednach=True,
        )
        cls.incoming = Kamion.objects.create(zakaznik=cls.customer, datum=date(2026, 10, 1))
        cls.outgoing = Kamion.objects.create(
            zakaznik=cls.customer, datum=date(2026, 10, 29), prijem_vydej=KamionChoice.VYDEJ,
        )
        head = TypHlavy.objects.create(nazev='SK')
        specification = Predpis.objects.create(nazev='OMEGA test', zakaznik=cls.customer)
        cls.order = Zakazka.objects.create(
            kamion_prijem=cls.incoming, kamion_vydej=cls.outgoing, predpis=specification,
            typ_hlavy=head, artikl='0641000801600', popis='SPAX-3 SMK TSP40 TGW',
            prumer=8, delka=160,
        )
        cls.price = Cena.objects.create(
            zakaznik=cls.customer, popis='Kalení SPX', delka_min=0, delka_max=200,
            cena_za_kg=Decimal('1.06'),
        )
        cls.price.predpis.add(specification)
        cls.crate = Bedna.objects.create(
            zakazka=cls.order, hmotnost=Decimal('234.0'), tara=25, mnozstvi=1,
            vyrobni_zakazka='4501539341', stav_bedny=StavBednyChoice.EXPEDOVANO,
        )
        cls.second = Bedna.objects.create(
            zakazka=cls.order, hmotnost=Decimal('218.0'), tara=25, mnozstvi=1,
            vyrobni_zakazka='0000123456', stav_bedny=StavBednyChoice.EXPEDOVANO,
        )
        cls.staff = get_user_model().objects.create_user('omega-staff', is_staff=True)
        cls.staff.user_permissions.add(Permission.objects.get(
            content_type__app_label='orders', codename='view_kamion',
        ))
        cls.url = reverse('admin:orders_kamion_changelist')

    def setUp(self):
        self.client.force_login(self.staff)

    def action_data(self, **extra):
        return {
            'action': 'export_omega_spx_action', '_selected_action': str(self.outgoing.pk),
            'select_across': '0', **extra,
        }

    def test_document_layout_prices_and_strings_match_proforma(self):
        note = build_spx_delivery_note(self.outgoing)
        self.assertEqual(note.total, Decimal('479.12'))
        self.assertEqual(note.weight, Decimal('452.0'))
        self.assertEqual(note.lines[0].total, self.crate.cena_za_bednu)
        self.assertEqual(note.lines[1].total, self.second.cena_za_bednu)
        html = render_to_string('orders/proforma_faktura_po_bednach.html', {'kamion': self.outgoing})
        self.assertIn('0641000801600', html)
        self.assertIn('0000123456', html)
        self.assertIn('479,12', html)
        payload = note.to_bytes()
        self.assertFalse(payload.startswith(b'\xef\xbb\xbf'))
        self.assertTrue(payload.endswith(b'\r\n'))
        self.assertNotIn(b'\n', payload.replace(b'\r\n', b''))
        rows = [row.split('\t') for row in payload.decode('cp1250').splitlines()]
        self.assertEqual(rows[0], ['R00', 'T01'])
        self.assertEqual(len(rows), 4)
        header = rows[1]
        self.assertEqual(len(header), 43)
        self.assertEqual(header[:7], [
            'R01', self.outgoing.cislo_dl, self.customer.nazev, '',
            '29.10.2026', '29.10.2026', '29.10.2026',
        ])
        self.assertEqual(header[9], '479.12')
        self.assertEqual(header[16:20], ['479.12', '2', '', ''])
        self.assertEqual(header[39:43], ['EUR', '1', '1', '479.12'])
        item = rows[2]
        self.assertEqual(len(item), 19)
        self.assertEqual(item[0], 'R02')
        self.assertEqual(item[2:6], ['234.0', 'kg', '1.06', '0'])
        self.assertEqual(item[9], 'V')
        self.assertEqual(item[18], '0641000801600')
        for value in ('Kalení', '4501539341', '0641000801600', 'SPAX-3 SMK TSP40 TGW', '8x160'):
            self.assertIn(value, item[1])
        self.assertIn('0000123456', rows[3][1])

    def test_excludes_nonbillable_crates_and_heat_exclusions(self):
        Bedna.objects.filter(pk=self.crate.pk).update(fakturovat=False)
        note = build_spx_delivery_note(self.outgoing)
        self.assertEqual([line.crate_number for line in note.lines], [self.second.cislo_bedny])
        Bedna.objects.filter(pk=self.second.pk).update(nefakturovat_kaleni=True)
        with self.assertRaisesMessage(ServiceValidationError, 'žádnou bednu'):
            build_spx_delivery_note(self.outgoing)

    def test_price_rounds_each_crate_before_summing(self):
        self.price.cena_za_kg = Decimal('1.05')
        self.price.save()
        Bedna.objects.filter(pk__in=[self.crate.pk, self.second.pk]).update(hmotnost=Decimal('0.1'))
        note = build_spx_delivery_note(self.outgoing)
        self.assertEqual([line.total for line in note.lines], [Decimal('0.11'), Decimal('0.11')])
        self.assertEqual(note.total, Decimal('0.22'))

    def test_each_order_uses_its_own_length_interval_price(self):
        price = Cena.objects.create(
            zakaznik=self.customer, popis='Delší SPX', delka_min=200, delka_max=300,
            cena_za_kg=Decimal('1.21'),
        )
        price.predpis.add(self.order.predpis)
        order = Zakazka.objects.create(
            kamion_prijem=self.incoming, kamion_vydej=self.outgoing, predpis=self.order.predpis,
            typ_hlavy=self.order.typ_hlavy, artikl='0671000802200',
            popis='SPAX-3 TK TSP40 4CUT', prumer=8, delka=220,
        )
        Bedna.objects.create(
            zakazka=order, hmotnost=Decimal('150.0'), tara=25, mnozstvi=1,
            vyrobni_zakazka='4501538929', stav_bedny=StavBednyChoice.EXPEDOVANO,
        )
        note = build_spx_delivery_note(self.outgoing)
        self.assertEqual(note.lines[-1].unit_price, Decimal('1.21'))
        self.assertEqual(note.lines[-1].total, Decimal('181.50'))
        self.assertEqual(note.total, Decimal('660.62'))

    def test_rejects_missing_zero_and_ambiguous_prices(self):
        for value in (Decimal('0.00'), Decimal('-1.00')):
            with self.subTest(price=value):
                Cena.objects.filter(pk=self.price.pk).update(cena_za_kg=value)
                with self.assertRaisesMessage(ServiceValidationError, 'cena kalení'):
                    build_spx_delivery_note(self.outgoing)
        Cena.objects.filter(pk=self.price.pk).update(cena_za_kg=Decimal('1.06'))
        duplicate = Cena.objects.create(
            zakaznik=self.customer, popis='Překryv', delka_min=0, delka_max=200,
            cena_za_kg=Decimal('1.50'),
        )
        duplicate.predpis.set(self.price.predpis.all())
        with self.assertRaisesMessage(ServiceValidationError, 'cena kalení'):
            build_spx_delivery_note(self.outgoing)
        duplicate.delete()
        self.price.predpis.clear()
        with self.assertRaisesMessage(ServiceValidationError, 'cena kalení'):
            build_spx_delivery_note(self.outgoing)

    def test_rejects_unsafe_text_missing_order_and_long_document_number(self):
        for field, value in (
            ('vyrobni_zakazka', ''), ('vyrobni_zakazka', '4501\tR01'),
        ):
            with self.subTest(field=field, value=value):
                Bedna.objects.filter(pk=self.crate.pk).update(**{field: value})
                with self.assertRaises(ServiceValidationError):
                    build_spx_delivery_note(self.outgoing)
        Bedna.objects.filter(pk=self.crate.pk).update(vyrobni_zakazka='4501539341')
        for value in ('unsafe\nR01', 'unsafe\x1ftext', 'symbol \U0001f600'):
            with self.subTest(description=value):
                Zakazka.objects.filter(pk=self.order.pk).update(popis=value)
                with self.assertRaises(ServiceValidationError):
                    build_spx_delivery_note(self.outgoing)
        Zakazka.objects.filter(pk=self.order.pk).update(popis='SPAX screws')
        self.outgoing.cislo_dl = 'X' * 21
        with self.assertRaisesMessage(ServiceValidationError, '20 znaků'):
            build_spx_delivery_note(self.outgoing)

    def test_rejects_unshipped_crates_and_cross_customer(self):
        Bedna.objects.filter(pk=self.crate.pk).update(hmotnost=Decimal('234.0'), stav_bedny=StavBednyChoice.PRIJATO)
        with self.assertRaisesMessage(ServiceValidationError, 'Expedováno'):
            build_spx_delivery_note(self.outgoing)
        Bedna.objects.filter(pk=self.crate.pk).update(stav_bedny=StavBednyChoice.EXPEDOVANO)
        other = Zakaznik.objects.create(nazev='Other', zkraceny_nazev='OTH', zkratka='OTH', ciselna_rada=300000)
        Kamion.objects.filter(pk=self.incoming.pk).update(zakaznik=other)
        with self.assertRaisesMessage(ServiceValidationError, 'zákazník příjmu'):
            build_spx_delivery_note(self.outgoing)

    def test_scope_rejects_incoming_other_customers_and_other_billing_modes(self):
        with self.assertRaisesMessage(ServiceValidationError, 'pouze pro kamion výdej'):
            build_spx_delivery_note(self.incoming)
        for flags in (
            {'zkratka': 'EUR'}, {'fakturovat_rovnani': True},
            {'fakturovat_tryskani': True}, {'proforma_po_bednach': False},
        ):
            with self.subTest(flags=flags):
                customer = Zakaznik.objects.get(pk=self.customer.pk)
                for field, value in flags.items():
                    setattr(customer, field, value)
                self.outgoing.zakaznik = customer
                with self.assertRaises(ServiceValidationError):
                    build_spx_delivery_note(self.outgoing)

    def test_action_preview_and_download_work_with_view_permission_without_writes(self):
        history_count = Bedna.history.count()
        response = self.client.post(self.url, self.action_data())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'admin/orders/kamion/omega_export.html')
        self.assertContains(response, '4501539341')
        self.assertContains(response, '0000123456')
        self.assertContains(response, '479,12')
        self.assertContains(response, 'csrfmiddlewaretoken')
        # Formulář může být odeslán i z filtrovaného seznamu kamionů.
        response = self.client.post(self.url + '?prijem_vydej=' + PrijemVydejChoice.VYDEJ,
                                    self.action_data(omega_download='1'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, build_spx_delivery_note(self.outgoing).to_bytes())
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn('windows-1250', response['Content-Type'])
        self.assertIn('private', response['Cache-Control'])
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(Bedna.history.count(), history_count)
        self.assertEqual(Kamion.objects.count(), 2)

    def test_action_rejects_multiple_trucks_and_invalid_data_without_download(self):
        for extra in (
            {'_selected_action': [str(self.outgoing.pk), str(self.incoming.pk)]},
            {'_selected_action': str(self.incoming.pk)},
        ):
            with self.subTest(extra=extra):
                response = self.client.post(self.url, self.action_data(omega_download='1', **extra))
                self.assertEqual(response.status_code, 302)
                self.assertNotIn('Content-Disposition', response)
                self.assertTrue(list(get_messages(response.wsgi_request)))

    def test_action_unavailable_without_permission_and_for_incoming_filter(self):
        truck_admin = KamionAdmin(Kamion, admin.site)
        request = RequestFactory().get('/', {'prijem_vydej': PrijemVydejChoice.PRIJEM_NEPRIJATY})
        request.user = self.staff
        self.assertNotIn('export_omega_spx_action', truck_admin.get_actions(request))
        self.staff.user_permissions.clear()
        self.client.force_login(get_user_model().objects.get(pk=self.staff.pk))
        response = self.client.post(self.url, self.action_data(omega_download='1'))
        self.assertEqual(response.status_code, 403)
        self.client.logout()
        response = self.client.post(self.url, self.action_data(omega_download='1'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)
