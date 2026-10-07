from datetime import date, datetime, timedelta, timezone as datetime_timezone

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
        response = self.client.get(self.url)
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
        KontrolaBedny.objects.create(bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.NESHODA)

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

        response = self.client.get(self.url)
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

        response = self.client.get(self.url)
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
        response = self.client.get(self.url)
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

    def test_filters_by_local_day_and_lists_unique_days_newest_first(self):
        response = self.client.get(self.url, {'den_filter': '2026-10-02'})
        self.assert_bedny(response, [self.other_bedna, self.bedna])
        self.assertEqual(response.context['den_choices'], [
            ('', 'VŠE'), ('2026-10-03', '03.10.2026'), ('2026-10-02', '02.10.2026'),
            ('2026-10-01', '01.10.2026'), ('nezjisteno', 'Datum nezjištěno'),
        ])
        self.assertContains(response, '<option value="2026-10-02" selected>02.10.2026</option>', html=True)

    def test_filters_by_missing_day(self):
        response = self.client.get(self.url, {'den_filter': 'nezjisteno'})
        self.assert_bedny(response, [self.without_date_bedna])

    def test_combines_filters_and_htmx_returns_only_updated_content(self):
        response = self.client.get(self.url, {
            'zakaznik_filter': 'TST', 'duvod_filter': 'neshoda_vrstva', 'den_filter': '2026-10-02',
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
        response = self.client.get(self.url, {'zakaznik_filter': '', 'duvod_filter': '', 'den_filter': ''})
        self.assert_bedny(response, [
            self.next_day_bedna, self.other_bedna, self.bedna,
            self.previous_day_bedna, self.without_date_bedna,
        ])

    def test_invalid_reason_and_day_are_ignored(self):
        for invalid_day in ('invalid', '2026-02-30'):
            with self.subTest(day=invalid_day):
                response = self.client.get(self.url, {
                    'duvod_filter': 'bedna__zakazka__id', 'den_filter': invalid_day,
                })
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.context['items']), 5)
                self.assertEqual(response.context['duvod_filter'], '')
                self.assertEqual(response.context['den_filter'], '')

    def test_htmx_history_restore_returns_full_page_with_filters(self):
        response = self.client.get(
            self.url, {'zakaznik_filter': 'DRH'},
            HTTP_HX_REQUEST='true', HTTP_HX_HISTORY_RESTORE_REQUEST='true',
        )
        self.assert_bedny(response, [self.other_bedna])
        self.assertTemplateUsed(response, 'orders/neshody_prehled.html')
        self.assertTemplateUsed(response, 'orders/base.html')
