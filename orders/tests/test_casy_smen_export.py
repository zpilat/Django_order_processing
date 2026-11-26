import csv
from datetime import date, datetime
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from orders.choices import TypZarizeniChoice as DeviceType
from orders.models import Sarze, SarzeKrok, SarzeKrokBedna, Zarizeni
from orders.services.casy_smen_export_service import (
    build_mesicni_export_pater, last_complete_shift_month,
)


@override_settings(TIME_ZONE='Europe/Prague', SECURE_SSL_REDIRECT=False)
class LastCompleteShiftMonthTests(SimpleTestCase):
    def test_month_is_complete_only_after_its_final_night_shift(self):
        for timestamp, start, end in (
            ('2026-11-26T12:00', date(2026, 10, 1), date(2026, 11, 1)),
            ('2026-12-01T05:59:59', date(2026, 10, 1), date(2026, 11, 1)),
            ('2026-12-01T06:00:00', date(2026, 11, 1), date(2026, 12, 1)),
            ('2027-01-01T06:00:00', date(2026, 12, 1), date(2027, 1, 1)),
            ('2024-03-01T06:00:00', date(2024, 2, 1), date(2024, 3, 1)),
            ('2026-03-01T06:00:00', date(2026, 2, 1), date(2026, 3, 1)),
        ):
            with self.subTest(timestamp=timestamp):
                now = datetime.fromisoformat(timestamp).replace(tzinfo=ZoneInfo('Europe/Prague'))
                self.assertEqual(last_complete_shift_month(now=now), (start, end))

    @override_settings(TIME_ZONE='UTC')
    def test_cutoff_uses_prague_time_even_when_default_timezone_is_different(self):
        self.assertEqual(
            last_complete_shift_month(now=datetime.fromisoformat('2026-12-01T05:00:00+00:00')),
            (date(2026, 11, 1), date(2026, 12, 1)),
        )


@override_settings(TIME_ZONE='Europe/Prague', SECURE_SSL_REDIRECT=False)
class CasySmenExportTests(TestCase):
    tz = ZoneInfo('Europe/Prague')
    now = datetime(2026, 11, 26, 12, tzinfo=tz)

    def setUp(self):
        self.devices = {}
        for kind in (DeviceType.NAKLADANI, DeviceType.VYKLADANI, DeviceType.TRYSKAC):
            self.devices[kind] = Zarizeni.objects.create(
                kod_zarizeni=kind, nazev_zarizeni=kind.label,
                zkraceny_nazev_zarizeni=kind, typ_zarizeni=kind,
            )
        self.user = get_user_model().objects.create_user('mesicni_export')
        self.url = reverse('dashboard_casy_smen_csv')

    def instant(self, text):
        return datetime.fromisoformat(text).replace(tzinfo=self.tz)

    def loading(self, starts, end=None):
        return self.step(starts[0], end, kind=DeviceType.NAKLADANI, starts=starts)

    def step(self, start, end, *, kind=DeviceType.TRYSKAC, floors=3, starts=None, batch=None, order=1,
             created_at=None):
        start = self.instant(start)
        end = self.instant(end) if end else None
        batch = batch or Sarze.objects.create(datum_zalozeni=start.date())
        step = SarzeKrok(
            sarze=batch, poradi=order, zarizeni=self.devices[kind], operator='Test',
            datum=start.date(), zacatek=start.time(),
            datum_konce=end.date() if end else None, konec=end.time() if end else None,
        )
        if created_at:
            step._history_date = self.instant(created_at)
        step.save()
        for index in range(len(starts) if starts else floors):
            item = SarzeKrokBedna(krok=step, patro=index + 1, popis_mimo_db='Test')
            item._history_date = self.instant(starts[index]) if starts else start
            item.save()
        return step

    def export(self, now=None):
        result = build_mesicni_export_pater(now=now or self.now)
        rows = list(csv.reader(StringIO(result['content'].lstrip('\ufeff')), delimiter=';'))
        return result, rows[0], rows[1:]

    def test_csv_has_one_wide_row_per_day_and_zero_values_for_empty_shifts(self):
        result, headers, rows = self.export()
        self.assertEqual(result['filename'], 'patra_smeny_2026-10.csv')
        self.assertTrue(result['content'].startswith('\ufeff'))
        self.assertEqual(len(headers), 12)
        self.assertEqual(headers[0], 'Datum směn')
        self.assertEqual(headers[1], 'Naložená patra 12h 06:00–18:00')
        self.assertEqual(headers[2], 'Vyložená patra 12h 06:00–18:00')
        self.assertEqual(headers[-2], 'Vyložená patra 8h 22:00–06:00')
        self.assertEqual(headers[-1], 'Stav evidence')
        self.assertEqual(len(rows), 31)
        self.assertEqual(rows[0], ['01.10.2026', *(['0,0'] * 10), 'OK'])
        self.assertEqual(rows[-1][0], '31.10.2026')
        self.assertTrue(all(len(row) == len(headers) for row in rows))

    def test_export_reuses_loading_and_uniform_unloading_shift_calculations(self):
        self.loading([
            '2026-10-20T13:20', '2026-10-20T13:40',
            '2026-10-20T14:20', '2026-10-20T17:40',
        ], '2026-10-20T18:20')
        self.step('2026-10-20T17:30', '2026-10-20T19:00', kind=DeviceType.VYKLADANI)
        _, _, rows = self.export()
        self.assertEqual(rows[19], [
            '20.10.2026', '3,5', '1,0', '0,5', '2,0',
            '1,5', '0,0', '2,5', '3,0', '0,0', '0,0', 'OK',
        ])

    def test_month_boundaries_include_only_work_between_first_day_six_and_next_month_six(self):
        self.loading(['2026-09-30T23:00', '2026-10-01T05:00'], '2026-10-01T07:00')
        self.step('2026-09-30T22:00', '2026-10-01T10:00')
        self.loading(['2026-10-31T23:00', '2026-11-01T05:00'], '2026-11-01T07:00')
        self.step('2026-10-31T22:00', '2026-11-01T07:00')
        self.step('2026-09-30T23:00', '2026-10-01T06:00', floors=6)
        self.step('2026-11-01T06:00', '2026-11-01T07:00', floors=6)
        _, _, rows = self.export()
        self.assertEqual(rows[0], [
            '01.10.2026', '0,5', '1,0', '0,0', '0,0',
            '0,5', '1,0', '0,0', '0,0', '0,0', '0,0', 'OK',
        ])
        self.assertEqual(rows[-1], [
            '31.10.2026', '0,0', '0,0', '1,5', '2,7',
            '0,0', '0,0', '0,0', '0,0', '1,5', '2,7', 'OK',
        ])

    def test_csv_marks_invalid_open_and_repeated_records_instead_of_silent_zeroes(self):
        self.step('2026-10-15T09:00', '2026-10-15T10:00', floors=0)
        self.loading(['2026-10-16T17:00', '2026-10-16T19:00'])
        first = self.step('2026-10-12T09:00', '2026-10-12T10:00')
        self.step('2026-10-12T11:00', '2026-10-12T12:00', batch=first.sarze, order=2)
        _, _, rows = self.export()
        self.assertIn('Vykládání: šarže s více průchody 1', rows[11][-1])
        self.assertIn('Vykládání: chybné kroky 1', rows[14][-1])
        self.assertIn('Nakládání: neuzavřené kroky 1', rows[15][-1])
        self.assertEqual(rows[15][1], '0,5')
        self.assertEqual(rows[15][3], '0,5')

    def test_csv_includes_the_closing_minute_but_keeps_month_boundaries_at_six(self):
        self.loading(
            ['2026-10-01T05:59:00', '2026-10-01T06:00:59.500000'], '2026-10-01T06:00',
        )
        self.step('2026-10-01T05:59', '2026-10-01T06:00')
        self.loading(
            ['2026-11-01T05:59:00', '2026-11-01T06:00:59.500000'], '2026-11-01T06:00',
        )
        self.step('2026-11-01T05:59', '2026-11-01T06:00')
        _, _, rows = self.export()
        self.assertEqual(rows[0], [
            '01.10.2026', '1,5', '1,5', '0,0', '0,0',
            '1,5', '1,5', '0,0', '0,0', '0,0', '0,0', 'OK',
        ])
        self.assertEqual(rows[-1], [
            '31.10.2026', '0,0', '0,0', '0,5', '1,5',
            '0,0', '0,0', '0,0', '0,0', '0,5', '1,5', 'OK',
        ])

    def test_leap_month_has_twenty_nine_daily_rows(self):
        result, _, rows = self.export(self.instant('2024-03-01T06:00'))
        self.assertEqual(result['filename'], 'patra_smeny_2024-02.csv')
        self.assertEqual(len(rows), 29)
        self.assertEqual(rows[-1][0], '29.02.2024')

    def test_csv_counts_history_fallback_and_records_it_in_the_last_column(self):
        step = self.step(
            '2026-10-20T17:00', None, kind=DeviceType.NAKLADANI,
            starts=['2026-10-20T17:00', '2026-10-20T17:59:30'],
            created_at='2026-10-20T16:59',
        )
        step.datum_konce = date(2026, 10, 20)
        step.konec = self.instant('2026-10-20T17:58').time()
        step._history_date = self.instant('2026-10-20T18:00:30')
        step.save()
        self.loading(['2026-10-20T19:00'], '2026-10-20T18:59')
        counts = (SarzeKrok.history.count(), SarzeKrokBedna.history.count())
        _, _, rows = self.export()
        self.assertEqual(rows[19], [
            '20.10.2026', '1,5', '0,0', '0,5', '0,0',
            '0,0', '0,0', '2,0', '0,0', '0,0', '0,0',
            'Nakládání: chybné kroky 1; Nakládání: konec podle historie uzavření u kroků 1',
        ])
        self.assertEqual(rows[18][-1], 'OK')
        self.assertEqual(rows[20][-1], 'OK')
        self.assertEqual(counts, (SarzeKrok.history.count(), SarzeKrokBedna.history.count()))

    def test_download_requires_login_and_is_an_excel_compatible_attachment(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.user)
        with patch('orders.views.timezone.now', return_value=self.now):
            response = self.client.get(self.url, {'datum': '2026-11-24'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="patra_smeny_2026-10.csv"')
        self.assertTrue(response.content.startswith(b'\xef\xbb\xbf'))
        rows = list(csv.reader(StringIO(response.content.decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(len(rows), 32)
        self.assertEqual(rows[1][0], '01.10.2026')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_button_shows_export_month_independently_of_selected_daily_date(self):
        self.client.force_login(self.user)
        with patch('orders.views.timezone.now', return_value=self.now):
            response = self.client.get(reverse('dashboard_casy_nakladani'), {'datum': '2026-11-20'})
        self.assertContains(response, f'href="{self.url}"')
        self.assertContains(response, 'CSV za 10/2026')
        self.assertContains(response, 'od 01.10.2026 06:00 do 01.11.2026 06:00')

    def test_export_does_not_change_data_or_history(self):
        self.step('2026-10-20T09:00', '2026-10-20T10:00')
        counts = (SarzeKrok.objects.count(), SarzeKrokBedna.objects.count(),
                  SarzeKrok.history.count(), SarzeKrokBedna.history.count())
        self.export()
        self.assertEqual(counts, (SarzeKrok.objects.count(), SarzeKrokBedna.objects.count(),
                                  SarzeKrok.history.count(), SarzeKrokBedna.history.count()))
