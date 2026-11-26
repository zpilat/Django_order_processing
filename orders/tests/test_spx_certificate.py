from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import Permission
from django.contrib.messages.storage.fallback import FallbackStorage
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from django.urls import reverse

from orders.actions import tisk_protokolu_kamionu_vydej_action
from orders.admin import KamionAdmin
from orders.choices import KamionChoice, TypZkouskyChoice, UvolneniKontrolyChoice
from orders.models import Bedna, Kamion, KontrolaBedny, MereniBedny, Zakazka
from orders.services.exceptions import ServiceValidationError
from orders.services.spx_certificate_service import build_spx_certificate_rows
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


@override_settings(SECURE_SSL_REDIRECT=False)
class SpxCertificateTests(KontrolaBednyTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.order = cls.bedna.zakazka
        customer = cls.order.kamion_prijem.zakaznik
        customer.zkratka = 'SPX'
        customer.save(update_fields=['zkratka'])
        cls.truck = Kamion.objects.create(
            zakaznik=customer, datum=cls.order.kamion_prijem.datum,
            prijem_vydej=KamionChoice.VYDEJ,
        )
        cls.order.kamion_vydej = cls.truck
        cls.order.save(update_fields=['kamion_vydej'])
        cls.control = KontrolaBedny.objects.create(
            bedna=cls.bedna, uvolneni=UvolneniKontrolyChoice.UVOLNENO,
        )
        for kind, value in (
            (TypZkouskyChoice.TVRDOST_POVRCHU, '350.1234'),
            (TypZkouskyChoice.TVRDOST_JADRA, '340'),
            (TypZkouskyChoice.PROHYB_PO_TZ, '0.25'),
        ):
            MereniBedny.objects.create(kontrola=cls.control, typ_zkousky=kind, poradi=1, hodnota=value)
        cls.user.is_staff = True
        cls.user.save(update_fields=['is_staff'])
        cls.user.user_permissions.add(Permission.objects.get(
            content_type__app_label='orders', codename='view_kamion',
        ))
        cls.url = reverse('protokol_kamion_vydej_pdf', args=[cls.truck.pk])

    def add_crate(self, *, order=None, number=None, measured=True):
        crate = Bedna.objects.create(zakazka=order or self.order)
        if number is not None:
            crate.cislo_bedny = number
            crate.save(update_fields=['cislo_bedny'])
        control = KontrolaBedny.objects.create(bedna=crate, uvolneni=UvolneniKontrolyChoice.UVOLNENO)
        if measured:
            for kind, value in (
                (TypZkouskyChoice.TVRDOST_POVRCHU, 360),
                (TypZkouskyChoice.TVRDOST_JADRA, 345),
                (TypZkouskyChoice.PROHYB_PO_TZ, '0.3'),
            ):
                MereniBedny.objects.create(kontrola=control, typ_zkousky=kind, poradi=1, hodnota=value)
        return crate, control

    def action(self, queryset=None):
        request = RequestFactory().post('/admin/orders/kamion/')
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)
        response = tisk_protokolu_kamionu_vydej_action(
            KamionAdmin(Kamion, admin.site), request,
            queryset if queryset is not None else Kamion.objects.filter(pk=self.truck.pk),
        )
        return response, [str(message) for message in request._messages]

    def test_one_two_and_three_crates_use_first_values_only(self):
        """Skutečný počet beden určuje počet hodnot; další měření se netisknou."""
        MereniBedny.objects.create(
            kontrola=self.control, typ_zkousky=TypZkouskyChoice.TVRDOST_POVRCHU,
            poradi=2, hodnota=999,
        )
        for count in range(1, 4):
            with self.subTest(crates=count):
                row = build_spx_certificate_rows(self.truck)[0]
                self.assertEqual(len(row['tvrdost_povrchu']), count)
                self.assertEqual(len(row['tvrdost_jadra']), count)
                self.assertEqual(len(row['hazeni']), count)
                self.assertEqual(row['tvrdost_povrchu'][0], Decimal('350.1234'))
                self.assertNotIn(Decimal('999'), row['tvrdost_povrchu'])
                self.assertEqual((row['ohyb'], row['krut']), ('OK', 'OK'))
            self.add_crate(measured=count < 3)
        self.assertEqual(len(build_spx_certificate_rows(self.truck)[0]['hazeni']), 3)

    def test_crates_are_selected_by_number_instead_of_creation_order(self):
        """První tři bedny se určují číslem bedny, nezávisle na ID."""
        last, _ = self.add_crate(number=self.bedna.cislo_bedny + 10, measured=False)
        third, _ = self.add_crate(number=self.bedna.cislo_bedny + 5)
        second, _ = self.add_crate(number=self.bedna.cislo_bedny + 1)
        row = build_spx_certificate_rows(self.truck)[0]
        self.assertEqual([crate.pk for crate in row['bedny']], [self.bedna.pk, second.pk, third.pk, last.pk])
        self.assertEqual(row['tvrdost_jadra'], [Decimal(340), Decimal(345), Decimal(345)])

    def test_deflection_prefers_straightening_including_zero_and_preserves_precision(self):
        """Fáze prohybu se volí samostatně pro každou bednu, včetně nuly."""
        second, control = self.add_crate()
        third, third_control = self.add_crate()
        MereniBedny.objects.create(
            kontrola=control, typ_zkousky=TypZkouskyChoice.PROHYB_PO_ROVNANI, poradi=3, hodnota=0,
        )
        MereniBedny.objects.create(
            kontrola=control, typ_zkousky=TypZkouskyChoice.PROHYB_PO_ROVNANI, poradi=4, hodnota=99,
        )
        MereniBedny.objects.create(
            kontrola=third_control, typ_zkousky=TypZkouskyChoice.PROHYB_PO_ROVNANI,
            poradi=1, hodnota='0.1234',
        )
        MereniBedny.objects.create(
            kontrola=self.control, typ_zkousky=TypZkouskyChoice.PROHYB_PO_KOULENI,
            poradi=1, hodnota=99,
        )
        self.assertEqual(build_spx_certificate_rows(self.truck)[0]['hazeni'], [Decimal('.25'), 0, Decimal('.1234')])

    def test_missing_measurements_are_reported_without_substitution_from_later_crates(self):
        """Chybějící zkoušky prvních beden se nenahradí čtvrtou bednou ani ručními poli."""
        self.add_crate()
        third, control = self.add_crate(measured=False)
        self.add_crate()
        self.order.tvrdost_povrchu = 'legacy'
        self.order.tvrdost_jadra = 'legacy'
        self.order.hazeni = 'legacy'
        self.order.save()
        with self.assertRaises(ServiceValidationError) as caught:
            build_spx_certificate_rows(self.truck)
        message = str(caught.exception)
        self.assertIn(str(third.cislo_bedny), message)
        self.assertIn('Tvrdost povrchu', message)
        self.assertIn('Tvrdost jádra', message)
        self.assertIn('Prohyb po rovnání i Prohyb po TZ', message)

    def test_missing_control_blocks_selected_crate(self):
        """Chybějící kontrola vede k přehlednému hlášení chybějících měření."""
        self.control.delete()
        with self.assertRaisesMessage(ServiceValidationError, f'bedna {self.bedna.cislo_bedny}'):
            build_spx_certificate_rows(self.truck)

    def test_each_mechanical_reason_on_fourth_crate_blocks_entire_certificate(self):
        """Neshoda ohybu i obou krutů blokuje tisk také mimo tři vzorkované bedny."""
        self.add_crate()
        self.add_crate()
        fourth, control = self.add_crate(measured=False)
        control.uvolneni = UvolneniKontrolyChoice.NESHODA
        for field, label in (
            ('neshoda_ohyb_nizky', 'Ohyb nízký'),
            ('neshoda_krut_nizky', 'Krut nízký'),
            ('neshoda_krut_vysoky', 'Krut vysoký'),
        ):
            with self.subTest(reason=field):
                setattr(control, field, True)
                control.save()
                with self.assertRaises(ServiceValidationError) as caught:
                    build_spx_certificate_rows(self.truck)
                self.assertIn(str(fourth.cislo_bedny), str(caught.exception))
                self.assertIn(label, str(caught.exception))
                setattr(control, field, False)

    def test_qs_release_and_resolved_historical_nonconformity_give_ok(self):
        """QS s odchylkou ani starší vyřešená neshoda neblokují mechanické OK."""
        self.control.neshoda_krut_nizky = True
        self.control.neshoda_ohyb_nizky = True
        for status in (
            UvolneniKontrolyChoice.NESHODA, UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU,
            UvolneniKontrolyChoice.UVOLNENO,
        ):
            self.control.uvolneni = status
            self.control.save()
            if status != UvolneniKontrolyChoice.NESHODA:
                row = build_spx_certificate_rows(self.truck)[0]
                self.assertEqual((row['ohyb'], row['krut']), ('OK', 'OK'))
        self.assertTrue(self.control.history.filter(uvolneni=UvolneniKontrolyChoice.NESHODA).exists())

    def test_unrelated_nonconformity_does_not_change_mechanical_result(self):
        """Ohyb a krut se odvozují pouze z odpovídajících důvodů neshody."""
        self.control.uvolneni = UvolneniKontrolyChoice.NESHODA
        self.control.neshoda_vrstva = True
        self.control.save()
        row = build_spx_certificate_rows(self.truck)[0]
        self.assertEqual((row['ohyb'], row['krut']), ('OK', 'OK'))

    def test_partial_outbound_order_is_independent_from_original_and_other_shipments(self):
        """Původní část a jiný výdej stejného artiklu nemění výběr ani neshody."""
        original = self.order
        original.kamion_vydej = None
        original.save(update_fields=['kamion_vydej'])
        self.control.uvolneni = UvolneniKontrolyChoice.NESHODA
        self.control.neshoda_krut_vysoky = True
        self.control.save()
        shipped = Zakazka.objects.create(
            kamion_prijem=original.kamion_prijem, kamion_vydej=self.truck,
            puvodni_zakazka=original, artikl=original.artikl, predpis=original.predpis,
            typ_hlavy=original.typ_hlavy, prumer=original.prumer, delka=original.delka, popis='Výdej části',
        )
        crate, _ = self.add_crate(order=shipped)
        other_truck = Kamion.objects.create(
            zakaznik=self.truck.zakaznik, datum=self.truck.datum, prijem_vydej=KamionChoice.VYDEJ,
        )
        other_order = Zakazka.objects.create(
            kamion_prijem=original.kamion_prijem, kamion_vydej=other_truck,
            puvodni_zakazka=original, artikl=original.artikl, predpis=original.predpis,
            typ_hlavy=original.typ_hlavy, prumer=original.prumer, delka=original.delka, popis='Jiný výdej',
        )
        _, other_control = self.add_crate(order=other_order)
        other_control.uvolneni = UvolneniKontrolyChoice.NESHODA
        other_control.neshoda_ohyb_nizky = True
        other_control.save()
        rows = build_spx_certificate_rows(self.truck)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['zakazka'].pk, shipped.pk)
        self.assertEqual([bedna.pk for bedna in rows[0]['bedny']], [crate.pk])
        self.assertEqual(rows[0]['tvrdost_povrchu'], [Decimal(360)])

    def test_rendering_stacks_values_and_does_not_write_manual_fields_or_history(self):
        """Každá hodnota má vlastní řádek; tisk nepřepisuje ruční pole ani audit."""
        self.add_crate()
        self.add_crate()
        self.order.tvrdost_povrchu = 'LEGACY_VALUE'
        self.order.save(update_fields=['tvrdost_povrchu'])
        history_count = self.order.history.count()
        rows = build_spx_certificate_rows(self.truck)
        html = render_to_string('orders/protokol_kamion_vydej_spx.html', {
            'kamion': self.truck, 'certificate_rows': rows,
        })
        self.assertIn('<td><div>350,1234</div><div>360</div><div>360</div></td>', html)
        self.assertIn('<td><div>340</div><div>345</div><div>345</div></td>', html)
        self.assertIn('<td><div>0,25</div><div>0,3</div><div>0,3</div></td>', html)
        self.assertNotIn('LEGACY_VALUE', html)
        self.order.refresh_from_db()
        self.assertEqual(self.order.tvrdost_povrchu, 'LEGACY_VALUE')
        self.assertEqual(self.order.history.count(), history_count)

    def test_action_redirects_only_with_valid_measurements(self):
        """Akce otevře PDF a při chybě zůstane v adminu s vysvětlením."""
        response, messages = self.action()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.url)
        self.control.mereni.all().delete()
        response, messages = self.action()
        self.assertIsNone(response)
        self.assertIn(f'bedna {self.bedna.cislo_bedny}', ' '.join(messages))

    def test_other_customers_are_rejected_by_action_and_direct_link(self):
        """Omezení na SPX platí pro akci i přímý odkaz bez chybějící šablony."""
        customer = self.truck.zakaznik
        customer.zkratka = 'EUR'
        customer.save(update_fields=['zkratka'])
        response, messages = self.action()
        self.assertIsNone(response)
        self.assertIn('pouze pro kamiony výdej zákazníka SPX', ' '.join(messages))
        self.client.force_login(self.user)
        with patch('orders.views.HTML') as renderer:
            self.assertContains(self.client.get(self.url), 'SPX', status_code=400)
            renderer.assert_not_called()

    def test_empty_truck_and_empty_order_are_rejected(self):
        """Certifikát nepotvrdí prázdný kamion ani zakázku bez beden."""
        Bedna.objects.filter(pk=self.bedna.pk).update(zakazka=self.make_unshipped_order())
        with self.assertRaisesMessage(ServiceValidationError, 'nemá žádné bedny'):
            build_spx_certificate_rows(self.truck)
        self.order.kamion_vydej = None
        self.order.save(update_fields=['kamion_vydej'])
        with self.assertRaisesMessage(ServiceValidationError, 'nemá žádné výdejové zakázky'):
            build_spx_certificate_rows(self.truck)

    def make_unshipped_order(self):
        return Zakazka.objects.create(
            kamion_prijem=self.order.kamion_prijem, artikl='Nevydaná', predpis=self.order.predpis,
            typ_hlavy=self.order.typ_hlavy, prumer=8, delka=100, popis='Nevydaná',
        )

    def test_direct_link_revalidates_after_action(self):
        """Změna měření nebo neshody po akci zablokuje následné otevření PDF."""
        self.assertEqual(self.action()[0].status_code, 302)
        self.control.uvolneni = UvolneniKontrolyChoice.NESHODA
        self.control.neshoda_krut_vysoky = True
        self.control.save()
        self.client.force_login(self.user)
        with patch('orders.views.HTML') as renderer:
            response = self.client.get(self.url)
            self.assertContains(response, 'Krut vysoký', status_code=400)
            renderer.assert_not_called()
        self.control.uvolneni = UvolneniKontrolyChoice.UVOLNENO
        self.control.save()
        self.control.mereni.filter(typ_zkousky=TypZkouskyChoice.TVRDOST_JADRA).delete()
        self.assertContains(self.client.get(self.url), 'Tvrdost jádra', status_code=400)

    def test_direct_link_requires_permission_and_produces_pdf(self):
        """PDF je dostupné po přihlášení s oprávněním prohlížet kamiony."""
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.user)
        with patch('orders.views.HTML.write_pdf', return_value=b'%PDF-test') as renderer:
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/pdf')
            self.assertEqual(response.content, b'%PDF-test')
            renderer.assert_called_once()
        self.user.user_permissions.clear()
        self.assertEqual(self.client.get(self.url).status_code, 403)
