from datetime import date, datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from orders.choices import UvolneniKontrolyChoice
from orders.models import Bedna, Kamion, KontrolaBedny, Zakazka, Zakaznik
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class NeshodyPrehledTests(KontrolaBednyTestBase):
    def setUp(self):
        self.url = reverse('neshody_prehled')
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(
            response, f'{reverse("login")}?next={self.url}',
            fetch_redirect_response=False,
        )

    def test_empty_overview(self):
        response = self.client.get(self.url, {'den_filter_od': '', 'den_filter_do': ''})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'orders/neshody_prehled.html')
        self.assertEqual(response.context['items'], [])
        self.assertContains(response, 'Momentálně není evidována žádná bedna ve stavu Neshoda.')

    def test_shows_both_bent_screw_ratios_including_zero(self):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        customer.pocet_vrutu_pro_kontrolu_prohybu = 25
        customer.save(update_fields=['pocet_vrutu_pro_kontrolu_prohybu'])
        KontrolaBedny.objects.create(
            bedna=self.bedna,
            uvolneni=UvolneniKontrolyChoice.NESHODA,
            pocet_krivych_vrutu_prvni_mereni=0,
            pocet_krivych_vrutu_druhe_mereni=3,
            uvolneni_zmeneno_at=timezone.now(),
        )

        response = self.client.get(self.url)
        item = response.context['items'][0]
        self.assertEqual(item['pomer_krivych_vrutu_prvni_mereni'], '0 / 25')
        self.assertEqual(item['pomer_krivych_vrutu_druhe_mereni'], '3 / 25')
        self.assertContains(response, '<div class="col-md-1">Křivých</div>')
        self.assertContains(response, '<div>0 / 25</div>')
        self.assertContains(response, '<div>3 / 25</div>')

        customer.pocet_vrutu_pro_kontrolu_prohybu = None
        customer.save(update_fields=['pocet_vrutu_pro_kontrolu_prohybu'])
        response = self.client.get(self.url)
        item = response.context['items'][0]
        self.assertEqual(item['pomer_krivych_vrutu_prvni_mereni'], '0 / —')
        self.assertEqual(item['pomer_krivych_vrutu_druhe_mereni'], '3 / —')

    def test_shows_placeholder_when_bent_screw_counts_are_empty(self):
        KontrolaBedny.objects.create(
            bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
            uvolneni_zmeneno_at=timezone.now(),
        )

        response = self.client.get(self.url)
        item = response.context['items'][0]
        self.assertIsNone(item['pomer_krivych_vrutu_prvni_mereni'])
        self.assertIsNone(item['pomer_krivych_vrutu_druhe_mereni'])
        self.assertContains(response, '<div class="text-muted">—</div>')

    def test_separates_nonconformities_by_day_and_groups_missing_dates(self):
        dates = (
            timezone.make_aware(datetime(2026, 10, 2, 15)),
            timezone.make_aware(datetime(2026, 10, 2, 9)),
            timezone.make_aware(datetime(2026, 10, 1, 16)),
            None,
            None,
        )
        for index, marked_at in enumerate(dates):
            bedna = self.bedna if index == 0 else Bedna.objects.create(zakazka=self.bedna.zakazka)
            KontrolaBedny.objects.create(
                bedna=bedna,
                uvolneni=UvolneniKontrolyChoice.NESHODA,
                uvolneni_zmeneno_at=marked_at,
            )

        response = self.client.get(self.url, {'den_filter_od': '', 'den_filter_do': ''})
        html = response.content.decode('utf-8')
        self.assertEqual(len(response.context['items']), 5)
        headings = [
            section.split('>', 1)[1].split('</h2>', 1)[0].strip()
            for section in html.split('<h2 class="nonconformity-day')[1:]
        ]
        self.assertEqual(headings, ['02.10.2026', '01.10.2026', 'Datum označení nezjištěno'])

    def test_shows_only_current_nonconformities_newest_first_with_missing_times_last(self):
        self.user.first_name = 'Jan'
        self.user.last_name = 'Novák'
        self.user.save(update_fields=['first_name', 'last_name'])
        older = timezone.now() - timedelta(days=2)
        newer = timezone.now() - timedelta(hours=1)
        first = KontrolaBedny.objects.create(
            bedna=self.bedna,
            uvolneni=UvolneniKontrolyChoice.NESHODA,
            uvolneni_zmeneno_at=older,
            uvolneni_zmenil=self.user,
            neshoda_krivost=True,
            neshoda_vrstva=True,
            neshoda_jine=True,
            poznamka='Poškozený závit',
        )
        newest_bedna = Bedna.objects.create(zakazka=self.bedna.zakazka)
        KontrolaBedny.objects.create(
            bedna=newest_bedna,
            uvolneni=UvolneniKontrolyChoice.NESHODA,
            uvolneni_zmeneno_at=newer,
            neshoda_cistota=True,
        )
        without_time_bedna = Bedna.objects.create(zakazka=self.bedna.zakazka)
        KontrolaBedny.objects.create(
            bedna=without_time_bedna,
            uvolneni=UvolneniKontrolyChoice.NESHODA,
        )
        released_bedna = Bedna.objects.create(zakazka=self.bedna.zakazka)
        KontrolaBedny.objects.create(
            bedna=released_bedna,
            uvolneni=UvolneniKontrolyChoice.UVOLNENO,
            uvolneni_zmeneno_at=timezone.now(),
        )

        # Pozdější úprava důvodů nemá změnit čas rozhodnutí ani pořadí.
        first.poznamka = 'Poškozený závit · doplněno'
        first.save(update_fields=['poznamka'])

        response = self.client.get(self.url, {'den_filter_od': '', 'den_filter_do': ''})
        items = response.context['items']
        self.assertEqual(
            [item['cislo_bedny'] for item in items],
            [newest_bedna.cislo_bedny, self.bedna.cislo_bedny, without_time_bedna.cislo_bedny],
        )
        self.assertEqual(items[1]['duvody'], ['Vrstva', 'Křivost', 'Jiné'])
        self.assertEqual(items[1]['poznamka'], 'Poškozený závit · doplněno')
        self.assertEqual(items[1]['oznaceno_at'], older)
        self.assertEqual(items[1]['oznacil'], 'Jan Novák')
        self.assertContains(response, 'Jan Novák')
        self.assertContains(response, 'Čas nezjištěn')
        self.assertNotContains(response, reverse('bedna_kontrola', args=[self.bedna.cislo_bedny]))

        self.user.user_permissions.add(Permission.objects.get(codename='view_bedna'))
        response = self.client.get(self.url, {'den_filter_od': '', 'den_filter_do': ''})
        self.assertContains(response, reverse('bedna_kontrola', args=[self.bedna.cislo_bedny]))
        self.assertContains(response, reverse('bedna_kontrola', args=[newest_bedna.cislo_bedny]))

    def test_admin_index_groups_control_overviews_below_workplace_overviews(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=['is_staff', 'is_superuser'])

        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertLess(html.index('Přehledy pracovišť'), html.index('Přehledy kontroly'))
        self.assertLess(html.index('Přehledy kontroly'), html.index('Přehledy výroby'))
        section = html.split('Přehledy kontroly', 1)[1].split('</table>', 1)[0]
        self.assertIn(reverse('kontrola_prehled'), section)
        self.assertIn(self.url, section)
        self.assertLess(section.index('Přehled kontroly'), section.index('Přehled neshod'))


class NeshodyPrehledFilterTests(KontrolaBednyTestBase):
    def setUp(self):
        # V UTC je 2. října, v Praze je již 3. října.
        now_patch = patch(
            'orders.views.timezone.now',
            return_value=datetime(2026, 10, 2, 22, 30, tzinfo=datetime_timezone.utc),
        )
        now_patch.start()
        self.addCleanup(now_patch.stop)
        self.url = reverse('neshody_prehled')
        self.client.force_login(self.user)
        customer = Zakaznik.objects.create(
            nazev='Druhý zákazník', zkraceny_nazev='DRUHY', zkratka='DRH', ciselna_rada=200000,
        )
        kamion = Kamion.objects.create(zakaznik=customer, datum=date(2026, 10, 2))
        original = self.bedna.zakazka
        other_order = Zakazka.objects.create(
            kamion_prijem=kamion, predpis=original.predpis, typ_hlavy=original.typ_hlavy,
            artikl='A2', prumer=original.prumer, delka=original.delka, popis='Druhá zakázka',
        )
        self.other_bedna = Bedna.objects.create(zakazka=other_order)
        self.next_day_bedna = Bedna.objects.create(zakazka=original)
        self.without_date_bedna = Bedna.objects.create(zakazka=original)
        self.previous_day_bedna = Bedna.objects.create(zakazka=original)
        # V UTC je ještě předchozí den; v Praze již 2. října 00:30.
        KontrolaBedny.objects.create(
            bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
            uvolneni_zmeneno_at=datetime(2026, 10, 1, 22, 30, tzinfo=datetime_timezone.utc),
            neshoda_krivost=True, neshoda_vrstva=True,
        )
        KontrolaBedny.objects.create(
            bedna=self.other_bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
            uvolneni_zmeneno_at=timezone.make_aware(datetime(2026, 10, 2, 23, 59)),
            neshoda_cistota=True,
        )
        KontrolaBedny.objects.create(
            bedna=self.next_day_bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
            uvolneni_zmeneno_at=timezone.make_aware(datetime(2026, 10, 3)),
            neshoda_krivost=True,
        )
        KontrolaBedny.objects.create(
            bedna=self.without_date_bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
            neshoda_jine=True,
        )
        KontrolaBedny.objects.create(
            bedna=self.previous_day_bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
            uvolneni_zmeneno_at=timezone.make_aware(datetime(2026, 10, 1, 23, 59)),
            neshoda_cistota=True,
        )
        released_bedna = Bedna.objects.create(zakazka=original)
        KontrolaBedny.objects.create(
            bedna=released_bedna, uvolneni=UvolneniKontrolyChoice.UVOLNENO,
            uvolneni_zmeneno_at=timezone.make_aware(datetime(2026, 10, 4)),
            neshoda_krivost=True,
        )

    def assert_bedny(self, response, bedny):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item['cislo_bedny'] for item in response.context['items']],
            [bedna.cislo_bedny for bedna in bedny],
        )

    def test_filters_by_customer(self):
        response = self.client.get(self.url, {'zakaznik_filter': 'DRH'})
        self.assert_bedny(response, [self.other_bedna])
        self.assertContains(response, '<option value="DRH" selected>DRUHY</option>', html=True)

    def test_filters_by_each_reason_including_multiple_reasons_on_one_control(self):
        for reason in ('neshoda_krivost', 'neshoda_vrstva'):
            with self.subTest(reason=reason):
                response = self.client.get(self.url, {'duvod_filter': reason})
                expected = [self.next_day_bedna, self.bedna] if reason == 'neshoda_krivost' else [self.bedna]
                self.assert_bedny(response, expected)
                self.assertEqual(response.context['duvod_filter'], reason)

    def test_filters_by_local_day_including_both_boundaries(self):
        response = self.client.get(self.url, {
            'den_filter_od': '2026-10-02', 'den_filter_do': '2026-10-02',
        })
        self.assert_bedny(response, [self.other_bedna, self.bedna])
        self.assertEqual(response.context['den_filter_od'], '2026-10-02')
        self.assertEqual(response.context['den_filter_do'], '2026-10-02')

        for name in ('den_filter_od', 'den_filter_do'):
            self.assertContains(response, (
                f'<input type="date" name="{name}" id="{name}" value="2026-10-02" '
                'class="form-control form-control-sm">'
            ), html=True)

    def test_defaults_to_oldest_current_nonconformity_and_local_today(self):
        KontrolaBedny.objects.filter(uvolneni=UvolneniKontrolyChoice.UVOLNENO).update(
            uvolneni_zmeneno_at=timezone.make_aware(datetime(2026, 9, 1)),
        )
        future_bedna = Bedna.objects.create(zakazka=self.bedna.zakazka)
        KontrolaBedny.objects.create(
            bedna=future_bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
            uvolneni_zmeneno_at=timezone.make_aware(datetime(2026, 10, 4)),
        )
        response = self.client.get(self.url)
        self.assertEqual(response.context['den_filter_od'], '2026-10-01')
        self.assertEqual(response.context['den_filter_do'], '2026-10-03')
        self.assert_bedny(response, [
            self.next_day_bedna, self.other_bedna, self.bedna, self.previous_day_bedna,
        ])

    def test_default_start_is_not_affected_by_customer_or_reason(self):
        response = self.client.get(self.url, {
            'zakaznik_filter': 'DRH', 'duvod_filter': 'neshoda_cistota',
        })
        self.assert_bedny(response, [self.other_bedna])
        self.assertEqual(response.context['den_filter_od'], '2026-10-01')

    def test_default_start_is_empty_when_no_dated_nonconformity_exists(self):
        for keep_undated in (True, False):
            with self.subTest(keep_undated=keep_undated):
                kontroly = KontrolaBedny.objects.filter(uvolneni=UvolneniKontrolyChoice.NESHODA)
                if keep_undated:
                    kontroly = kontroly.filter(uvolneni_zmeneno_at__isnull=False)
                kontroly.delete()
                response = self.client.get(self.url)
                self.assert_bedny(response, [])
                self.assertEqual(response.context['den_filter_od'], '')
                self.assertEqual(response.context['den_filter_do'], '2026-10-03')

    def test_filters_by_range(self):
        response = self.client.get(self.url, {
            'den_filter_od': '2026-10-01', 'den_filter_do': '2026-10-02',
        })
        self.assert_bedny(response, [self.other_bedna, self.bedna, self.previous_day_bedna])

    def test_filters_by_start_only(self):
        response = self.client.get(self.url, {'den_filter_od': '2026-10-02', 'den_filter_do': ''})
        self.assert_bedny(response, [self.next_day_bedna, self.other_bedna, self.bedna])
        self.assertEqual(response.context['den_filter_do'], '')

    def test_filters_by_end_only(self):
        response = self.client.get(self.url, {'den_filter_od': '', 'den_filter_do': '2026-10-02'})
        self.assert_bedny(response, [self.other_bedna, self.bedna, self.previous_day_bedna])
        self.assertEqual(response.context['den_filter_od'], '')

    def test_combines_filters_and_htmx_returns_only_updated_content(self):
        response = self.client.get(self.url, {
            'zakaznik_filter': 'TST', 'duvod_filter': 'neshoda_vrstva',
            'den_filter_od': '2026-10-02', 'den_filter_do': '2026-10-02',
        }, HTTP_HX_REQUEST='true')
        self.assert_bedny(response, [self.bedna])
        self.assertTemplateUsed(response, 'orders/partials/neshody_prehled_content.html')
        self.assertTemplateNotUsed(response, 'orders/base.html')
        self.assertContains(response, 'id="neshody-prehled-content"')
        self.assertContains(response, 'hx-target="#neshody-prehled-content"')
        self.assertContains(response, 'hx-push-url="true"')
        self.assertContains(response, 'Celkem: 1')
        self.assertContains(response, '<option value="neshoda_vrstva" selected>Vrstva</option>', html=True)

    def test_empty_filtered_results_and_clearing_filters(self):
        response = self.client.get(self.url, {'zakaznik_filter': 'DRH', 'duvod_filter': 'neshoda_vrstva'})
        self.assert_bedny(response, [])
        self.assertContains(response, 'Zvoleným filtrům neodpovídá žádná neshoda.')
        self.assertNotContains(response, 'Momentálně není evidována žádná bedna ve stavu Neshoda.')
        response = self.client.get(self.url, {
            'zakaznik_filter': '', 'duvod_filter': '', 'den_filter_od': '', 'den_filter_do': '',
        })
        self.assertFalse(response.context['has_filters'])
        self.assertEqual(response.context['den_filter_od'], '')
        self.assertEqual(response.context['den_filter_do'], '')
        self.assert_bedny(response, [
            self.next_day_bedna, self.other_bedna, self.bedna,
            self.previous_day_bedna, self.without_date_bedna,
        ])

    def test_invalid_reason_is_ignored(self):
        response = self.client.get(self.url, {'duvod_filter': 'bedna__zakazka__id'})
        self.assertEqual(response.context['duvod_filter'], '')
        self.assert_bedny(response, [
            self.next_day_bedna, self.other_bedna, self.bedna, self.previous_day_bedna,
        ])

    def test_invalid_dates_show_error_without_unfiltered_results(self):
        for invalid_day in ('invalid', '2026-02-30'):
            for name in ('den_filter_od', 'den_filter_do'):
                with self.subTest(day=invalid_day, name=name):
                    response = self.client.get(self.url, {name: invalid_day})
                    self.assert_bedny(response, [])
                    self.assertTrue(response.context['date_filter_errors'])
                    self.assertContains(response, 'zadejte platné datum.')

    def test_reversed_range_shows_error(self):
        response = self.client.get(self.url, {
            'den_filter_od': '2026-10-03', 'den_filter_do': '2026-10-01',
        })
        self.assert_bedny(response, [])
        self.assertContains(response, 'Datum od nesmí být pozdější než datum do.')

    def test_htmx_history_restore_returns_full_page_with_filters(self):
        response = self.client.get(
            self.url, {
                'zakaznik_filter': 'DRH', 'den_filter_od': '2026-10-02', 'den_filter_do': '2026-10-02',
            },
            HTTP_HX_REQUEST='true', HTTP_HX_HISTORY_RESTORE_REQUEST='true',
        )
        self.assert_bedny(response, [self.other_bedna])
        self.assertTemplateUsed(response, 'orders/neshody_prehled.html')
        self.assertTemplateUsed(response, 'orders/base.html')
        self.assertEqual(response.context['den_filter_od'], '2026-10-02')
        self.assertEqual(response.context['den_filter_do'], '2026-10-02')


class NeshodyPrehledPdfTests(KontrolaBednyTestBase):
    def setUp(self):
        self.url = reverse('neshody_prehled')
        self.pdf_url = reverse('neshody_prehled_pdf')
        self.client.force_login(self.user)
        now_patch = patch(
            'orders.views.timezone.now',
            return_value=datetime(2026, 10, 28, 12, tzinfo=datetime_timezone.utc),
        )
        now_patch.start()
        self.addCleanup(now_patch.stop)
        self.user.first_name = 'Jan'
        self.user.last_name = 'Novák'
        self.user.save(update_fields=['first_name', 'last_name'])
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        customer.pocet_vrutu_pro_kontrolu_prohybu = 25
        customer.save(update_fields=['pocet_vrutu_pro_kontrolu_prohybu'])
        self.bedna.hmotnost = Decimal('432.1')
        self.bedna.save(update_fields=['hmotnost'])
        KontrolaBedny.objects.create(
            bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
            uvolneni_zmeneno_at=timezone.make_aware(datetime(2026, 10, 2, 0, 30)),
            uvolneni_zmenil=self.user, neshoda_krivost=True, neshoda_vrstva=True,
            pocet_krivych_vrutu_prvni_mereni=0, pocet_krivych_vrutu_druhe_mereni=3,
            poznamka='Poškozený závit\nDoplněná poznámka',
        )
        self.other_bedna = Bedna.objects.create(zakazka=self.bedna.zakazka)
        KontrolaBedny.objects.create(
            bedna=self.other_bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
            uvolneni_zmeneno_at=timezone.make_aware(datetime(2026, 10, 3, 15)),
            neshoda_cistota=True,
        )
        self.undated_bedna = Bedna.objects.create(zakazka=self.bedna.zakazka)
        KontrolaBedny.objects.create(bedna=self.undated_bedna, uvolneni=UvolneniKontrolyChoice.NESHODA)
        released_bedna = Bedna.objects.create(zakazka=self.bedna.zakazka)
        KontrolaBedny.objects.create(
            bedna=released_bedna, uvolneni=UvolneniKontrolyChoice.UVOLNENO,
            uvolneni_zmeneno_at=timezone.now(),
        )

    def test_pdf_requires_login(self):
        self.client.logout()
        response = self.client.get(self.pdf_url)
        self.assertRedirects(
            response, f'{reverse("login")}?next={self.pdf_url}', fetch_redirect_response=False,
        )

    def test_pdf_link_preserves_effective_filters_after_htmx_update(self):
        for params in ({}, {'den_filter_od': '', 'den_filter_do': ''}, {
            'zakaznik_filter': 'TST', 'duvod_filter': 'neshoda_vrstva',
            'den_filter_od': '2026-10-02', 'den_filter_do': '2026-10-02',
        }):
            with self.subTest(params=params):
                response = self.client.get(self.url, params, HTTP_HX_REQUEST='true')
                soup = BeautifulSoup(response.content, 'html.parser')
                link = soup.find('a', string='Tisk do PDF')
                self.assertIsNotNone(link)
                self.assertEqual(link['target'], '_blank')
                pdf_url = urlsplit(link['href'])
                self.assertEqual(pdf_url.path, self.pdf_url)
                self.assertEqual(parse_qs(pdf_url.query, keep_blank_values=True), {
                    name: [response.context[name]]
                    for name in ('zakaznik_filter', 'duvod_filter', 'den_filter_od', 'den_filter_do')
                })

    @patch('orders.views.HTML')
    def test_pdf_items_match_overview_with_combined_and_open_filters(self, renderer):
        renderer.return_value.write_pdf.return_value = b'%PDF-test'
        for params in ({}, {'den_filter_od': '', 'den_filter_do': ''}, {
            'zakaznik_filter': 'TST', 'duvod_filter': 'neshoda_vrstva',
            'den_filter_od': '2026-10-02', 'den_filter_do': '2026-10-02',
        }, {'den_filter_od': '', 'den_filter_do': '2026-10-02'}, {
            'den_filter_od': '2026-10-03', 'den_filter_do': '',
        }, {'zakaznik_filter': 'NEEXISTUJE'}):
            with self.subTest(params=params):
                overview = self.client.get(self.url, params)
                response = self.client.get(self.pdf_url, params)
                self.assertEqual(response.status_code, 200)
                soup = BeautifulSoup(renderer.call_args.kwargs['string'], 'html.parser')
                printed_numbers = [
                    int(row.find_all('td')[1].strong.get_text())
                    for row in soup.select('tbody tr:not(.day-header)')
                ]
                self.assertEqual(printed_numbers, [item['cislo_bedny'] for item in overview.context['items']])

    @patch('orders.views.HTML')
    def test_pdf_contains_filters_all_columns_barcode_and_net_weight(self, renderer):
        renderer.return_value.write_pdf.return_value = b'%PDF-test'
        response = self.client.get(self.pdf_url, {
            'zakaznik_filter': 'TST', 'duvod_filter': 'neshoda_vrstva',
            'den_filter_od': '2026-10-02', 'den_filter_do': '2026-10-02',
        })
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('inline;', response['Content-Disposition'])
        soup = BeautifulSoup(renderer.call_args.kwargs['string'], 'html.parser')
        self.assertEqual(soup.h1.get_text(), 'Přehled neshod')
        self.assertIn('28.10.2026 13:00', soup.get_text())
        self.assertIn('Celkem beden: 1', soup.get_text())
        self.assertEqual(len(soup.select('thead th')), 8)
        filters = soup.select_one('.filters').get_text()
        for text in ('TEST', 'Vrstva', '2.10.2026 - 2.10.2026'):
            self.assertIn(text, filters)
        cells = soup.select_one('tbody tr:not(.day-header)').find_all('td')
        self.assertIsNotNone(cells[0].find('svg'))
        self.assertIn(self.bedna.get_stav_bedny_display(), cells[1].get_text())
        for text in ('TEST', self.bedna.zakazka.artikl, 'Ø10', '100'):
            self.assertIn(text, cells[2].get_text())
        for text in ('Vrstva', 'Křivost', 'Poškozený závit', 'Doplněná poznámka'):
            self.assertIn(text, cells[3].get_text())
        for text in ('0 / 25', '3 / 25'):
            self.assertIn(text, cells[4].get_text())
        self.assertIn('Jan Novák', cells[5].get_text())
        self.assertIn('02.10.26 00:30', cells[5].get_text())
        self.assertEqual(cells[6].get_text(), '432,1')
        self.assertEqual(cells[7].get_text(), '')

    @patch('orders.views.HTML')
    def test_pdf_handles_missing_dates_and_missing_or_zero_weight(self, renderer):
        renderer.return_value.write_pdf.return_value = b'%PDF-test'
        self.bedna.hmotnost = Decimal('0.0')
        self.bedna.save(update_fields=['hmotnost'])
        response = self.client.get(self.pdf_url, {'den_filter_od': '', 'den_filter_do': ''})
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(renderer.call_args.kwargs['string'], 'html.parser')
        self.assertIn('Datum označení nezjištěno', soup.get_text())
        self.assertEqual(soup.select_one('.filters').get_text().count('Bez omezení'), 2)
        rows = soup.select('tbody tr:not(.day-header)')
        self.assertEqual(rows[0].find_all('td')[6].get_text(), '—')
        self.assertEqual(rows[1].find_all('td')[6].get_text(), '0,0')
        self.assertEqual(rows[-1].find_all('td')[5].get_text().strip(), 'Čas nezjištěn')

    @patch('orders.views.HTML')
    def test_invalid_dates_block_pdf_generation(self, renderer):
        for params in ({'den_filter_od': 'invalid'}, {'den_filter_do': '2026-02-30'}, {
            'den_filter_od': '2026-10-03', 'den_filter_do': '2026-10-02',
        }):
            with self.subTest(params=params):
                response = self.client.get(self.pdf_url, params)
                self.assertEqual(response.status_code, 400)
                renderer.assert_not_called()
                overview = self.client.get(self.url, params)
                soup = BeautifulSoup(overview.content, 'html.parser')
                self.assertIsNone(soup.find('a', string='Tisk do PDF'))

    def test_generates_real_pdf(self):
        response = self.client.get(self.pdf_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertTrue(response.content.rstrip().endswith(b'%%EOF'))
        self.assertEqual(int(response['Content-Length']), len(response.content))
        self.assertIn('no-store', response['Cache-Control'])
