from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db.models import Prefetch
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.utils import timezone
from weasyprint import HTML

from orders import actions
from orders.choices import KamionChoice, PrijemVydejChoice, RovnaniChoice, StavBednyChoice, TryskaniChoice, TypZkouskyChoice, UvolneniKontrolyChoice, VysledekKontrolyChoice, ZinkovaniChoice
from orders.models import Bedna, Kamion, KontrolaBedny, MereniBedny, Zakazka, Zakaznik
from orders.services.exceptions import ServiceValidationError
from orders.services.expedice_service import expedice_beden_do_existujiciho_kamionu
from orders.services.pdf_cards_service import build_cards_pdf
from orders.services.filled_quality_cards_service import (
    MEASUREMENT_COLUMNS, build_filled_context, build_filled_quality_cards_pdf,
    resolve_filled_customer_template,
)
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class FilledQualityCardsTests(KontrolaBednyTestBase):
    def setUp(self):
        self.customer = self.bedna.zakazka.kamion_prijem.zakaznik
        self.customer.zkratka = 'EUR'
        self.customer.save()
        self.bedna.hmotnost = Decimal('100')
        self.bedna.save()
        self.request = RequestFactory().get('/')
        self.request.user = self.user
        self.request.session = {}
        self.request._messages = FallbackStorage(self.request)
        self.qs = Bedna.objects.filter(pk=self.bedna.pk)

    def create_control(self, **values):
        kontrola = KontrolaBedny(bedna=self.bedna, **values)
        kontrola._history_user = self.user
        kontrola.save()
        return kontrola

    def measurement(self, kontrola, kind, value, order=1, user=None, measured_at=None):
        item = MereniBedny(
            kontrola=kontrola, typ_zkousky=kind, hodnota=Decimal(value),
            poradi=order, zmeril=user or self.user, zmereno_at=measured_at or timezone.now(),
        )
        item._history_user = user or self.user
        item.save()
        return item

    def context(self):
        bedna = self.qs.select_related('kontrola__uvolneni_zmenil', 'zakazka__kamion_prijem__zakaznik', 'zakazka__predpis').prefetch_related(
            Prefetch('kontrola__mereni', queryset=MereniBedny.objects.select_related('zmeril').order_by('poradi', 'pk'), to_attr='print_measurements'),
        ).get()
        return build_filled_context(bedna, timezone.now(), 'Tisknoucí uživatel')

    def test_first_ten_per_type_follow_order_with_gaps_and_preserve_all_stored_values(self):
        kontrola = self.create_control()
        for kind in MEASUREMENT_COLUMNS:
            for index in reversed(range(12)):
                self.measurement(kontrola, kind, str(index), order=index * 2 + 1)
        context = self.context()
        self.assertEqual(context['quality_card']['rows'], [[Decimal(index)] * 7 for index in range(10)])
        self.assertEqual(MereniBedny.objects.count(), 84)
        self.assertEqual(MereniBedny.history.count(), 84)
        template, _ = resolve_filled_customer_template('EUR')
        html = render_to_string(template, context)
        self.assertEqual(html.count('class="measurement-value'), 70)
        self.assertIn('class="measurement-value">0</td>', html)
        self.assertNotIn('class="measurement-value">10</td>', html)
        self.assertNotIn('class="measurement-value">11</td>', html)

    def test_short_test_has_blank_cells_and_decimal_precision_is_preserved(self):
        kontrola = self.create_control()
        self.measurement(kontrola, TypZkouskyChoice.TVRDOST_POVRCHU, '592.1234')
        self.measurement(kontrola, TypZkouskyChoice.OHYB, '12.5000')
        template, _ = resolve_filled_customer_template('eur')
        html = render_to_string(template, self.context())
        self.assertIn('class="measurement-value">592,1234</td>', html)
        self.assertIn('class="measurement-value">12,5</td>', html)
        self.assertIn('class="status-value status-cross">-</span>', html)
        self.assertEqual(html.count('class="measurement-value"></td>'), 68)
        self.assertIn(f'Interní č. {self.bedna.cislo_bedny} · 1/1', html)

    def test_template_shows_bending_limits_and_only_defined_qs_limit(self):
        self.create_control()
        template, _ = resolve_filled_customer_template('eur')
        for code, length, normal, release in (
            ('EUR', '100', '0,6', None), ('ROT', '123.4', '0,4936', '0,7404'),
            ('SWG', '300', '1,8', None), ('SWG', '400', '1,8', None),
            ('TST', '100', None, None),
        ):
            with self.subTest(customer=code, length=length):
                self.customer.zkratka = code
                self.customer.save(update_fields=['zkratka'])
                self.bedna.zakazka.delka = Decimal(length)
                self.bedna.zakazka.save(update_fields=['delka'])
                html = render_to_string(template, self.context())
                if normal is None:
                    self.assertNotIn('max.', html)
                else:
                    self.assertEqual(html.count(f'max. {normal} mm'), 3)
                if release is None:
                    self.assertNotIn('QS max.', html)
                else:
                    self.assertEqual(html.count(f'QS max. {release} mm'), 3)
                headers = html.split('<thead>', 1)[1].split('</thead>', 1)[0]
                self.assertNotIn('None', headers)

    def test_print_colors_only_bending_columns_using_customer_limits(self):
        kontrola = self.create_control()
        for kind in (
            TypZkouskyChoice.PROHYB_PO_TZ, TypZkouskyChoice.PROHYB_PO_KOULENI,
            TypZkouskyChoice.PROHYB_PO_ROVNANI,
        ):
            for order, value in enumerate(('0.4', '0.4001', '0.6', '0.6001'), start=1):
                self.measurement(kontrola, kind, value, order=order)
        for kind in (
            TypZkouskyChoice.OHYB, TypZkouskyChoice.KRUT,
            TypZkouskyChoice.TVRDOST_POVRCHU, TypZkouskyChoice.TVRDOST_JADRA,
        ):
            self.measurement(kontrola, kind, '0.6001')
        template, _ = resolve_filled_customer_template('eur')
        for code, states in (
            ('ROT', ('', 'odchylka', 'odchylka', 'nevyhovuje')),
            ('EUR', ('', '', '', 'nevyhovuje')),
            ('TST', ('', '', '', '')),
        ):
            with self.subTest(customer=code):
                self.customer.zkratka = code
                self.customer.save(update_fields=['zkratka'])
                html = render_to_string(template, self.context())
                for value, state in zip(('0,4', '0,4001', '0,6', '0,6001'), states):
                    suffix = f' prohyb-{state}' if state else ''
                    expected_count = 7 if value == '0,6001' and not state else 3
                    self.assertEqual(html.count(f'<td class="measurement-value{suffix}">{value}</td>'), expected_count)
                self.assertEqual(html.count('<td class="measurement-value">0,6001</td>'), 7 if code == 'TST' else 4)
                self.assertEqual(html.count(' prohyb-odchylka">'), states.count('odchylka') * 3)
                self.assertEqual(html.count(' prohyb-nevyhovuje">'), states.count('nevyhovuje') * 3)
                self.assertEqual(html.count('class="measurement-value'), 70)
        self.assertEqual(MereniBedny.history.count(), 16)

    def test_print_displays_release_with_deviation_and_nonconformity(self):
        kontrola = self.create_control()
        template, _ = resolve_filled_customer_template('eur')
        for status, css, released in (
            (UvolneniKontrolyChoice.UVOLNENO, 'status-good', True),
            (UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU, 'status-warning', True),
            (UvolneniKontrolyChoice.NESHODA, 'status-bad', True),
            (UvolneniKontrolyChoice.NEROZHODNUTO, 'status-pending', False),
        ):
            with self.subTest(status=status):
                kontrola.uvolneni = status
                kontrola.uvolneni_zmenil = self.user if released else None
                kontrola.uvolneni_zmeneno_at = timezone.now() if released else None
                kontrola.save()
                html = render_to_string(template, self.context())
                self.assertIn(f'<td class="{css}"><span class="field-label">Uvolnění ', html)
                details = html.split('/ Freigabe</span></span>', 1)[1].split('</td>', 1)[0]
                self.assertIn(status.label, details)
                self.assertEqual('class="release-detail"' in details, released)
                if released:
                    self.assertIn(self.user.username, details)
                    self.assertIn(timezone.localtime(kontrola.uvolneni_zmeneno_at).strftime('%d.%m.%Y %H:%M'), details)

    def test_print_keeps_original_order_and_total_after_partial_shipments(self):
        self.bedna.tara = 1
        self.bedna.mnozstvi = 100
        self.bedna.stav_bedny = StavBednyChoice.K_EXPEDICI
        self.bedna.rovnat = RovnaniChoice.ROVNA
        self.bedna.tryskat = TryskaniChoice.CISTA
        self.bedna.zinkovat = ZinkovaniChoice.NEZINKOVAT
        self.bedna.save()
        root = self.bedna.zakazka
        bedny = [self.bedna] + [Bedna.objects.create(
            zakazka=root, hmotnost=100, tara=1, mnozstvi=100,
            stav_bedny=StavBednyChoice.K_EXPEDICI, rovnat=RovnaniChoice.ROVNA,
            tryskat=TryskaniChoice.CISTA, zinkovat=ZinkovaniChoice.NEZINKOVAT,
        ) for _ in range(9)]

        for positions in ((1, 2, 3), (5, 6, 9)):
            truck = Kamion.objects.create(
                zakaznik=self.customer, datum=root.kamion_prijem.datum,
                prijem_vydej=KamionChoice.VYDEJ,
            )
            expedice_beden_do_existujiciho_kamionu(
                bedny_qs=Bedna.objects.filter(pk__in=[bedny[position - 1].pk for position in positions]),
                kamion_vydej=truck,
            )

        # Print one container from each separated order and one still being measured.
        printed_positions = (1, 4, 5)
        printed_ids = [bedny[position - 1].pk for position in printed_positions]
        for bedna in Bedna.objects.filter(pk__in=printed_ids):
            KontrolaBedny.objects.create(bedna=bedna)
            self.assertEqual(bedna.poradi_bedny, 1)
            self.assertLess(bedna.zakazka.pocet_beden, 10)

        with patch('orders.services.pdf_cards_service.HTML') as renderer:
            renderer.return_value.write_pdf.return_value = b'%PDF-original-order'
            response = build_filled_quality_cards_pdf(Bedna.objects.filter(pk__in=printed_ids), self.request)

        html = renderer.call_args.kwargs['string']
        for position in printed_positions:
            self.assertIn(f'Interní č. {bedny[position - 1].cislo_bedny} · {position}/10', html)
        self.assertEqual(response.content, b'%PDF-original-order')

    def test_measurement_date_range_uses_earliest_and_latest_day(self):
        kontrola = self.create_control()
        older = timezone.now() - timedelta(days=2)
        newer = timezone.now()
        self.measurement(kontrola, TypZkouskyChoice.OHYB, '12', measured_at=older)
        self.measurement(kontrola, TypZkouskyChoice.KRUT, '25', measured_at=older)
        self.measurement(kontrola, TypZkouskyChoice.PROHYB_PO_TZ, '1.5', measured_at=newer)

        card = self.context()['quality_card']
        self.assertEqual(card['datum_mereni_od'], timezone.localdate(older))
        self.assertEqual(card['datum_mereni_do'], timezone.localdate(newer))

    def test_eur_template_keeps_original_requirements_and_fits_one_a4_page(self):
        self.user.first_name, self.user.last_name = 'Jan', 'Kontrolor'
        self.user.save()
        kontrola = self.create_control(
            cistota=VysledekKontrolyChoice.NOK, ulozeni=VysledekKontrolyChoice.OK,
            uvolneni=UvolneniKontrolyChoice.UVOLNENO, uvolneni_zmenil=self.user,
            uvolneni_zmeneno_at=timezone.now(), poznamka='Poznámka <kontroly>',
        )
        self.bedna.vyrobni_zakazka = 'OBJ-123'
        self.bedna.sarze = 'CH-123'
        self.bedna.behalter_nr = 'DEMO-001'
        self.bedna.tryskat = TryskaniChoice.OTRYSKANA
        self.bedna.save()
        predpis = self.bedna.zakazka.predpis
        predpis.ohyb, predpis.krut = 'min. 30°', 'min. 25 Nm'
        predpis.povrch, predpis.jadro = '550-650 HV', '300-400 HV'
        predpis.save()
        for kind in MEASUREMENT_COLUMNS:
            for order in range(1, 11):
                self.measurement(kontrola, kind, '580.2500', order=order)
        template, _ = resolve_filled_customer_template('eur')
        html = render_to_string(template, self.context())
        for text in ('Mind. 5 Prüfmuster', 'Eurotec - F.3', 'HPM - F 73c'):
            self.assertIn(text, html)
        self.assertNotIn('{% extends', html)
        self.assertEqual(html.count('class="measurement-row"'), 10)
        for requirement in ('min. 30°', 'min. 25 Nm', '550-650 HV', '300-400 HV'):
            self.assertIn(requirement, html)
        self.assertIn('Jan Kontrolor', html)
        self.assertIn('Uvolněno', html)
        self.assertIn('class="status-value status-check">✓</span>', html)
        self.assertNotIn('Poznámka &lt;kontroly&gt;', html)
        self.assertEqual(html.count('class="controller-value"'), 7)
        self.assertIn('A1-CH-123', html)
        for code, status in (
            ('EUR', UvolneniKontrolyChoice.UVOLNENO), ('ROT', UvolneniKontrolyChoice.UVOLNENO),
            ('EUR', UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU),
            ('EUR', UvolneniKontrolyChoice.NESHODA),
        ):
            with self.subTest(customer=code, status=status):
                self.customer.zkratka = code
                self.customer.save(update_fields=['zkratka'])
                kontrola.uvolneni = status
                kontrola.save()
                html = render_to_string(template, self.context())
                document = HTML(string=html).render()
                self.assertEqual(len(document.pages), 1)
                text_boxes = [box for box in document.pages[0]._page_box.descendants() if getattr(box, 'text', '').strip()]
                self.assertLess(max(box.position_y + box.height for box in text_boxes), document.pages[0].height - 37)

    def test_per_column_measuring_people_are_separate_from_printing_user(self):
        kontrola = self.create_control()
        self.measurement(kontrola, TypZkouskyChoice.OHYB, '12')
        editor = get_user_model().objects.create_user(username='editor')
        self.measurement(kontrola, TypZkouskyChoice.PROHYB_PO_TZ, '1.5', user=editor)
        card = self.context()['quality_card']
        self.assertEqual(card['kontrolovali'], ['kontrolor', '', 'editor', '', '', '', ''])

    def test_new_service_generates_pdf_without_creating_more_history(self):
        kontrola = self.create_control()
        self.measurement(kontrola, TypZkouskyChoice.KRUT, '25')
        before = (KontrolaBedny.history.count(), MereniBedny.history.count())
        response = build_filled_quality_cards_pdf(self.qs, self.request)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('vyplnene_karty_kontroly_kvality_eur.pdf', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertEqual(before, (KontrolaBedny.history.count(), MereniBedny.history.count()))

    def test_original_print_still_renders_blank_card_when_measurements_exist(self):
        kontrola = self.create_control(poznamka='POZNAMKA_ELEKTRONICKE_KONTROLY')
        self.measurement(kontrola, TypZkouskyChoice.OHYB, '1234.5678')
        with patch('orders.services.pdf_cards_service.HTML') as renderer:
            renderer.return_value.write_pdf.return_value = b'%PDF-original'
            response = build_cards_pdf(
                bedny_qs=self.qs, template_paths=['orders/karta_kontroly_kvality/karta_kontroly_kvality_eur.html'],
                filename='karty_kontroly_kvality_eur.pdf', request=self.request,
            )
        html = renderer.call_args.kwargs['string']
        self.assertNotIn('1234,5678', html)
        self.assertNotIn('POZNAMKA_ELEKTRONICKE_KONTROLY', html)
        self.assertIn('Eurotec - F.3', html)
        self.assertEqual(response.content, b'%PDF-original')

    def test_missing_control_and_unsupported_customers_report_validation_errors(self):
        with self.assertRaisesMessage(ServiceValidationError, 'Chybí uložená kontrola'):
            build_filled_quality_cards_pdf(self.qs, self.request)
        self.assertFalse(KontrolaBedny.objects.exists())
        self.create_control()
        for code in ('FIS', 'HPM', 'ROT', 'SPX', 'SSH', 'SWG', 'XXX'):
            with self.subTest(customer=code):
                self.customer.zkratka = code
                self.customer.save()
                with self.assertRaisesMessage(ServiceValidationError, 'pouze pro zákazníka EUR'):
                    build_filled_quality_cards_pdf(self.qs, self.request)

    def test_mixed_customers_are_rejected(self):
        customer = Zakaznik.objects.create(nazev='Druhý', zkraceny_nazev='DR', zkratka='SPX', ciselna_rada=200000)
        kamion = Kamion.objects.create(zakaznik=customer, datum=timezone.localdate())
        zakazka = Zakazka.objects.create(kamion_prijem=kamion, predpis=self.bedna.zakazka.predpis, typ_hlavy=self.bedna.zakazka.typ_hlavy, artikl='B', prumer=10, delka=100)
        Bedna.objects.create(zakazka=zakazka)
        with self.assertRaisesMessage(ServiceValidationError, 'od jednoho zákazníka'):
            build_filled_quality_cards_pdf(Bedna.objects.all(), self.request)

    def test_actions_select_bedny_from_each_overview(self):
        self.create_control()
        with patch('orders.actions.build_filled_quality_cards_pdf', return_value=HttpResponse(b'%PDF-demo')) as builder:
            for action, model, pk in (
                (actions.tisk_vyplnenych_karet_kontroly_kvality_action, Bedna, self.bedna.pk),
                (actions.tisk_vyplnenych_karet_kontroly_kvality_zakazek_action, Zakazka, self.bedna.zakazka.pk),
                (actions.tisk_vyplnenych_karet_kontroly_kvality_kamionu_action, Kamion, self.bedna.zakazka.kamion_prijem_id),
            ):
                self.assertEqual(action(admin.site._registry[model], self.request, model.objects.filter(pk=pk)).status_code, 200)
                self.assertEqual(list(builder.call_args.args[0].values_list('pk', flat=True)), [self.bedna.pk])

    def test_actions_show_validation_message_instead_of_pdf_if_control_is_missing(self):
        response = actions.tisk_vyplnenych_karet_kontroly_kvality_action(admin.site._registry[Bedna], self.request, self.qs)
        self.assertIsNone(response)
        self.assertTrue(any('Chybí uložená kontrola' in str(message) for message in self.request._messages))

    def test_truck_action_rejects_multiple_trucks_and_outgoing_truck(self):
        kamion = self.bedna.zakazka.kamion_prijem
        kamion_admin = admin.site._registry[Kamion]
        with patch('orders.actions.build_filled_quality_cards_pdf') as builder:
            self.assertIsNone(actions.tisk_vyplnenych_karet_kontroly_kvality_kamionu_action(kamion_admin, self.request, Kamion.objects.none()))
            kamion.prijem_vydej = KamionChoice.VYDEJ
            kamion.save()
            self.assertIsNone(actions.tisk_vyplnenych_karet_kontroly_kvality_kamionu_action(kamion_admin, self.request, Kamion.objects.filter(pk=kamion.pk)))
        builder.assert_not_called()

    def test_actions_available_to_staff_with_view_permission_and_truck_filters_match_original(self):
        self.user.is_staff = True
        self.user.save()
        self.user.user_permissions.add(Permission.objects.get(codename='view_bedna'))
        available = admin.site._registry[Bedna].get_actions(self.request)
        self.assertIn('tisk_karet_kontroly_kvality_action', available)
        self.assertIn('tisk_vyplnenych_karet_kontroly_kvality_action', available)
        self.user.is_superuser = True
        self.user.save()
        # Permission caches belong to the user instance; reload after changing roles.
        self.request.user = get_user_model().objects.get(pk=self.user.pk)
        for filter_value in PrijemVydejChoice:
            request = RequestFactory().get('/', {'prijem_vydej': filter_value})
            request.user = self.request.user
            available = admin.site._registry[Kamion].get_actions(request)
            self.assertEqual('tisk_karet_kontroly_kvality_kamionu_action' in available, 'tisk_vyplnenych_karet_kontroly_kvality_kamionu_action' in available)
