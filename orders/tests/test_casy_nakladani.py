from datetime import date, datetime, time, timedelta
from decimal import Decimal
from fractions import Fraction
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from orders.choices import TypZarizeniChoice
from orders.models import Sarze, SarzeKrok, SarzeKrokBedna, Zarizeni
from orders.services.casy_nakladani_service import (
    build_casy_nakladani_prehled, FLOOR_DELETED_REASON,
)
from orders.views import _build_vyroba_dashboard_context


@override_settings(TIME_ZONE='Europe/Prague', SECURE_SSL_REDIRECT=False)
class CasyNakladaniTests(TestCase):
    day = date(2026, 11, 24)
    tz = ZoneInfo('Europe/Prague')
    now = datetime(2026, 11, 26, 12, tzinfo=tz)
    minute_tail = Decimal('59.999999')

    def setUp(self):
        self.device = Zarizeni.objects.create(
            kod_zarizeni='NAK', nazev_zarizeni='Nakládání',
            zkraceny_nazev_zarizeni='NAK', typ_zarizeni=TypZarizeniChoice.NAKLADANI,
        )
        self.user = get_user_model().objects.create_user('nakladani')
        self.url = reverse('dashboard_casy_nakladani')

    def instant(self, text):
        value = datetime.fromisoformat(text)
        return value if value.tzinfo is not None else value.replace(tzinfo=self.tz)

    def add_floor(self, step, floor, timestamp):
        item = SarzeKrokBedna(krok=step, patro=floor, popis_mimo_db='Test')
        item._history_date = self.instant(timestamp)
        item.save()
        return item

    def create_loading(self, starts, end=None, *, device=None, created_at=None):
        first = self.instant(starts[0])
        finish = self.instant(end) if end else None
        batch = Sarze.objects.create(datum_zalozeni=first.date(), cislo_pracoviste=1)
        step = SarzeKrok(
            sarze=batch, poradi=1, zarizeni=device or self.device,
            datum=first.date(), zacatek=first.time(), operator='Test',
            datum_konce=finish.date() if finish else None,
            konec=finish.time() if finish else None,
        )
        if created_at:
            step._history_date = self.instant(created_at)
        step.save()
        for floor, timestamp in enumerate(starts, 1):
            self.add_floor(step, floor, timestamp)
        return step

    def save_loading_end(self, step, end, saved_at):
        finish = self.instant(end) if end else None
        step.datum_konce = finish.date() if finish else None
        step.konec = finish.time() if finish else None
        step._history_date = self.instant(saved_at)
        step.save()

    def report(self, day=None):
        return build_casy_nakladani_prehled(date_value=day or self.day, now=self.now)

    def scheme(self, report, key):
        return next(scheme for scheme in report['schemes'] if scheme['key'] == key)

    def test_both_shift_schemes_split_the_same_floor_intervals(self):
        self.create_loading([
            '2026-11-24T13:20', '2026-11-24T13:40',
            '2026-11-24T14:20', '2026-11-24T17:40',
        ], '2026-11-24T18:20')
        report = self.report()
        twelve = self.scheme(report, 'twelve')
        eight = self.scheme(report, 'eight')
        # Poslední patro trvá 40 minut a téměř 60 sekund, z toho 20 minut v denní.
        day_share = Decimal(1200) / (2400 + self.minute_tail)
        self.assertAlmostEqual(twelve['rows'][0]['patra'], 3 + day_share, places=20)
        self.assertAlmostEqual(twelve['rows'][1]['patra'], 1 - day_share, places=20)
        self.assertAlmostEqual(twelve['rows'][0]['sarze'], (3 + day_share) / 4, places=20)
        self.assertAlmostEqual(twelve['rows'][1]['sarze'], (1 - day_share) / 4, places=20)
        self.assertEqual([r['patra'] for r in eight['rows']], [Decimal('1.5'), Decimal('2.5'), 0])
        self.assertEqual([r['sarze'] for r in eight['rows']], [Decimal('.375'), Decimal('.625'), 0])
        self.assertEqual(twelve['total'], eight['total'])
        self.assertEqual(twelve['total']['patra'], 4)
        self.assertEqual(twelve['total']['sarze'], 1)
        self.assertAlmostEqual(twelve['total']['hours'], 5 + self.minute_tail / 3600, places=20)
        self.assertEqual(len(report['details']), 4)

    def test_two_point_four_of_four_floors_is_point_six_batches(self):
        self.create_loading([
            '2026-11-24T07:00', '2026-11-24T08:00',
            '2026-11-24T17:00', '2026-11-24T19:30',
        ], '2026-11-24T20:00')
        rows = self.scheme(self.report(), 'twelve')['rows']
        self.assertEqual(rows[0]['patra'], Decimal('2.4'))
        self.assertEqual(rows[0]['sarze'], Decimal('.6'))
        self.assertEqual(rows[1]['patra'], Decimal('1.6'))
        self.assertEqual(rows[1]['sarze'], Decimal('.4'))

    def test_original_dashboard_assigns_whole_loading_to_its_start_shift(self):
        step = self.create_loading(
            ['2026-11-24T17:00', '2026-11-24T19:00'], '2026-11-24T20:00',
        )
        self.add_floor(step, 1, '2026-11-24T17:10')
        old = _build_vyroba_dashboard_context(date_value=self.day)['vyroba_dashboard']['shifts']
        self.assertEqual(old['day']['counts']['sarze'], 1)
        self.assertEqual(old['day']['counts']['patra'], 2)
        self.assertEqual(old['night']['counts']['sarze'], 0)
        self.assertEqual(old['night']['counts']['patra'], 0)
        new = self.scheme(self.report(), 'twelve')['rows']
        self.assertEqual(new[0]['patra'], Decimal('.5'))
        self.assertEqual(new[1]['patra'], Decimal('1.5'))
        self.assertEqual(new[0]['sarze'], Decimal('.25'))
        self.assertEqual(new[1]['sarze'], Decimal('.75'))

    def test_batch_denominator_is_calculated_separately_for_each_loading(self):
        self.create_loading(['2026-11-24T17:00'], '2026-11-24T19:00')
        self.create_loading(['2026-11-24T07:00', '2026-11-24T08:00'], '2026-11-24T09:00')
        rows = self.scheme(self.report(), 'twelve')['rows']
        day_share = Decimal(3600) / (7200 + self.minute_tail)
        self.assertAlmostEqual(rows[0]['patra'], 2 + day_share, places=20)
        self.assertAlmostEqual(rows[0]['sarze'], 1 + day_share, places=20)
        self.assertAlmostEqual(rows[1]['sarze'], 1 - day_share, places=20)

    def test_first_history_survives_replacing_rows_and_multiple_items_on_one_floor(self):
        step = self.create_loading(['2026-11-24T17:00', '2026-11-24T19:00'], '2026-11-24T20:00')
        self.add_floor(step, 1, '2026-11-24T17:10')
        for item in step.krok_bedny.filter(patro=1):
            item._history_date = self.instant('2026-11-24T19:30')
            item.delete()
        self.add_floor(step, 1, '2026-11-24T19:31')
        report = self.report()
        self.assertEqual(report['details'][0]['start'], self.instant('2026-11-24T17:00'))
        self.assertEqual(self.scheme(report, 'twelve')['rows'][0]['patra'], Decimal('.5'))
        self.assertEqual(self.scheme(report, 'twelve')['total']['patra'], 2)

    def test_explicitly_deleted_floor_starts_again_when_recreated(self):
        step = self.create_loading(['2026-11-24T16:00'], '2026-11-24T20:00')
        item = step.krok_bedny.get()
        item._history_date = self.instant('2026-11-24T16:30')
        item._change_reason = FLOOR_DELETED_REASON
        item.delete()
        self.add_floor(step, 1, '2026-11-24T19:00')
        report = self.report()
        self.assertEqual(report['details'][0]['start'], self.instant('2026-11-24T19:00'))
        self.assertEqual(self.scheme(report, 'twelve')['rows'][0]['patra'], 0)
        self.assertEqual(self.scheme(report, 'twelve')['rows'][1]['patra'], 1)

    def test_open_loading_counts_closed_floor_but_waits_to_compute_batch_share(self):
        step = self.create_loading(['2026-11-24T17:00', '2026-11-24T19:00'])
        report = self.report()
        total = self.scheme(report, 'twelve')['total']
        self.assertEqual(total['patra'], 1)
        self.assertEqual(total['sarze'], 0)
        self.assertEqual(total['hours'], 2)
        self.assertEqual(report['incomplete_steps'], 1)
        self.assertIsNone(report['details'][-1]['end'])
        step.datum_konce = self.day
        step.konec = time(20)
        step.save()
        total = self.scheme(self.report(), 'twelve')['total']
        self.assertEqual(total['patra'], 2)
        self.assertEqual(total['sarze'], 1)

    def test_all_shift_boundaries_midnight_and_adjacent_days(self):
        intervals = [
            ('2026-11-23T22:00', '2026-11-24T06:00'),
            ('2026-11-24T06:00', '2026-11-24T14:00'),
            ('2026-11-24T14:00', '2026-11-24T18:00'),
            ('2026-11-24T18:00', '2026-11-24T22:00'),
            ('2026-11-24T22:00', '2026-11-25T00:00'),
            ('2026-11-25T00:00', '2026-11-25T06:00'),
            ('2026-11-25T06:00', '2026-11-25T07:00'),
        ]
        for start, end in intervals:
            self.create_loading([start], end)
        report = self.report()
        eight_hours = Fraction(28_800_000_000, 28_859_999_999)
        four_hours = Fraction(14_400_000_000, 14_459_999_999)
        six_hours = Fraction(21_600_000_000, 21_659_999_999)
        # Předešlá noční přispěje minutou po 06:00, poslední minuta následující
        # noční už patří dalšímu dni. Konce v 14/18/22 zasahují do další směny.
        day = 1 + (1 - eight_hours) + four_hours
        night = 2 + (1 - four_hours) + six_hours
        for key, expected in (('twelve', (day, night)), ('eight', (1, day, night - 1))):
            for row, share in zip(self.scheme(report, key)['rows'], expected):
                share = Fraction(share)
                self.assertAlmostEqual(row['patra'], Decimal(share.numerator) / share.denominator, places=20)
        self.assertAlmostEqual(
            self.scheme(report, 'twelve')['total']['hours'],
            24 + 5 * self.minute_tail / 3600, places=20,
        )
        self.assertEqual(len(report['details']), 6)

    def test_floor_started_before_report_window_is_split_between_report_days(self):
        self.create_loading(['2026-11-23T18:00'], '2026-11-24T18:00')
        total = self.scheme(self.report(), 'twelve')['total']
        previous = self.scheme(self.report(self.day - timedelta(days=1)), 'twelve')['total']
        share = (43200 + self.minute_tail) / (86400 + self.minute_tail)
        self.assertEqual(total['patra'], share)
        self.assertEqual(total['sarze'], share)
        self.assertEqual(total['patra'] + previous['patra'], 1)

    def test_missing_history_nonincreasing_times_and_invalid_end_are_not_guessed(self):
        missing = self.create_loading(['2026-11-24T09:00'], '2026-11-24T10:00')
        SarzeKrokBedna.history.filter(krok_id=missing.pk).delete()
        self.create_loading(['2026-11-24T12:00', '2026-11-24T11:00'], '2026-11-24T13:00')
        self.create_loading(['2026-11-24T15:00'], '2026-11-24T14:59')
        report = self.report()
        self.assertEqual(report['invalid_steps'], 3)
        self.assertEqual(self.scheme(report, 'twelve')['total']['patra'], 0)
        self.assertTrue(all(row['invalid'] for row in report['details']))
        self.assertTrue(any(row['start'] is None for row in report['details']))

    def test_empty_loading_has_warning_and_does_not_add_a_batch(self):
        step = self.create_loading(['2026-11-24T09:00'], '2026-11-24T10:00')
        step.krok_bedny.all().delete()
        report = self.report()
        self.assertEqual(report['invalid_steps'], 1)
        self.assertEqual(self.scheme(report, 'twelve')['total']['sarze'], 0)

    def test_other_workstation_types_are_excluded(self):
        device = Zarizeni.objects.create(
            kod_zarizeni='TQF_XL1', nazev_zarizeni='Pec', zkraceny_nazev_zarizeni='XL1',
            typ_zarizeni=TypZarizeniChoice.VICEUCELOVKA,
        )
        self.create_loading(['2026-11-24T09:00'], '2026-11-24T10:00', device=device)
        self.assertEqual(self.report()['details'], [])

    def test_dst_night_uses_real_elapsed_time(self):
        for day, end, expected in (
            ('2026-03-28', '2026-03-29', 7), ('2026-10-24', '2026-10-25', 9),
        ):
            with self.subTest(day=day):
                self.create_loading([f'{day}T22:00'], f'{end}T06:00')
                report = self.report(date.fromisoformat(day))
                for scheme in report['schemes']:
                    share = Decimal(expected * 3600) / (expected * 3600 + self.minute_tail)
                    self.assertEqual(scheme['rows'][-1]['patra'], share)
                    self.assertEqual(scheme['rows'][-1]['hours'], expected)
                following = self.scheme(self.report(date.fromisoformat(end)), 'twelve')['total']
                self.assertEqual(self.scheme(report, 'twelve')['total']['patra'] + following['patra'], 1)

    def test_last_floor_saved_at_fractional_second_59_is_included_without_changing_evidence(self):
        step = self.create_loading(
            ['2026-11-24T07:01:00', '2026-11-24T07:02:59.500000'], '2026-11-24T07:02',
        )
        history_count = step.history.count() + SarzeKrokBedna.history.filter(krok_id=step.pk).count()
        report = self.report()
        self.assertEqual(report['invalid_steps'], 0)
        self.assertEqual(self.scheme(report, 'twelve')['total']['patra'], 2)
        self.assertEqual(report['details'][0]['end'], self.instant('2026-11-24T07:02:59.500000'))
        self.assertEqual(report['details'][-1]['end'], self.instant('2026-11-24T07:02:59.999999'))
        self.assertEqual(report['details'][-1]['recorded_end'], self.instant('2026-11-24T07:02:00'))
        step.refresh_from_db()
        self.assertEqual(step.konec, time(7, 2))
        self.assertEqual(history_count, step.history.count() + SarzeKrokBedna.history.filter(krok_id=step.pk).count())

    def test_just_closed_loading_is_not_rejected_for_the_calculated_future_seconds(self):
        self.create_loading(['2026-11-24T07:01', '2026-11-24T07:02:10'], '2026-11-24T07:02')
        now = self.instant('2026-11-24T07:02:40')
        report = build_casy_nakladani_prehled(date_value=self.day, now=now)
        self.assertEqual(report['invalid_steps'], 0)
        self.assertGreater(report['details'][-1]['end'], now)
        self.assertEqual(self.scheme(report, 'twelve')['total']['patra'], 2)

    def test_original_future_end_still_is_rejected_within_the_same_minute(self):
        self.create_loading(['2026-11-24T07:01'], '2026-11-24T07:02:50')
        report = build_casy_nakladani_prehled(
            date_value=self.day, now=self.instant('2026-11-24T07:02:40'),
        )
        self.assertEqual(report['invalid_steps'], 1)
        self.assertEqual(report['details'][0]['status'], 'Konec nakládání je v budoucnosti.')

    def test_query_count_does_not_grow_per_step_or_floor(self):
        for _ in range(3):
            self.create_loading(['2026-11-24T09:00', '2026-11-24T10:00'], '2026-11-24T11:00')
        with self.assertNumQueries(3):
            report = self.report()
        self.assertEqual(len(report['details']), 6)

    def test_conflicting_end_uses_exact_closing_history_and_ignores_later_saves(self):
        step = self.create_loading(
            ['2026-11-24T17:00', '2026-11-24T17:59:10'], created_at='2026-11-24T16:59',
        )
        self.save_loading_end(step, '2026-11-24T17:58', '2026-11-24T18:00:10')
        step.operator = 'Pozdější úprava'
        step._history_date = self.instant('2026-11-24T18:30')
        step.save()
        history_count = step.history.count() + SarzeKrokBedna.history.filter(krok_id=step.pk).count()
        report = self.report()
        self.assertEqual(report['invalid_steps'], 0)
        self.assertEqual(report['historical_end_steps'], 1)
        self.assertEqual(report['details'][-1]['end'], self.instant('2026-11-24T18:00:10'))
        self.assertEqual(report['details'][-1]['recorded_end'], self.instant('2026-11-24T17:58'))
        self.assertTrue(report['details'][-1]['end_from_history'])
        self.assertFalse(report['details'][0]['end_from_history'])
        self.assertIn('konec podle historie uzavření', report['details'][-1]['status'])
        twelve = self.scheme(report, 'twelve')
        self.assertEqual(twelve['total']['patra'], 2)
        self.assertEqual(twelve['total']['sarze'], 1)
        self.assertEqual(twelve['rows'][1]['patra'], Decimal(1) / 6)
        step.refresh_from_db()
        self.assertEqual(step.konec, time(17, 58))
        self.assertEqual(history_count, step.history.count() + SarzeKrokBedna.history.filter(krok_id=step.pk).count())
        self.client.force_login(self.user)
        with patch('orders.views.timezone.now', return_value=self.now):
            response = self.client.get(self.url, {'datum': self.day.isoformat()})
        self.assertContains(response, 'Započteno; konec podle historie uzavření.')

    def test_history_is_not_used_when_the_closing_minute_already_gives_valid_interval(self):
        step = self.create_loading(['2026-11-24T09:00'], created_at='2026-11-24T08:59')
        self.save_loading_end(step, '2026-11-24T09:00', '2026-11-24T10:00')
        with self.assertNumQueries(3):
            report = self.report()
        self.assertEqual(report['details'][0]['end'], self.instant('2026-11-24T09:00:59.999999'))
        self.assertEqual(report['historical_end_steps'], 0)

    def test_created_closed_and_closed_to_closed_corrections_remain_invalid(self):
        for correction in (False, True):
            step = self.create_loading(
                ['2026-11-24T10:02'], '2026-11-24T10:00', created_at='2026-11-24T09:00',
            )
            self.save_loading_end(
                step, '2026-11-24T10:01' if correction else '2026-11-24T10:00',
                '2026-11-24T10:03',
            )
        report = self.report()
        self.assertEqual(report['invalid_steps'], 2)
        self.assertEqual(report['historical_end_steps'], 0)
        self.assertEqual(self.scheme(report, 'twelve')['total']['patra'], 0)

    def test_history_must_end_after_the_last_floor_and_not_in_the_future(self):
        for saved_at in ('2026-11-24T10:01', '2026-11-24T10:02', '2026-11-27T10:03'):
            step = self.create_loading(['2026-11-24T10:02'], created_at='2026-11-24T09:00')
            self.save_loading_end(step, '2026-11-24T10:00', saved_at)
        report = self.report()
        self.assertEqual(report['invalid_steps'], 3)
        self.assertEqual(report['historical_end_steps'], 0)

    def test_changing_recorded_end_invalidates_earlier_closing_event(self):
        step = self.create_loading(['2026-11-24T10:02'], created_at='2026-11-24T09:00')
        self.save_loading_end(step, '2026-11-24T10:00', '2026-11-24T10:03')
        self.save_loading_end(step, '2026-11-24T10:01', '2026-11-24T10:04')
        self.assertEqual(self.report()['invalid_steps'], 1)

    def test_reopening_requires_a_new_valid_closing_event(self):
        step = self.create_loading(['2026-11-24T10:02'], created_at='2026-11-24T09:00')
        self.save_loading_end(step, '2026-11-24T10:00', '2026-11-24T10:03')
        self.save_loading_end(step, None, '2026-11-24T10:04')
        self.save_loading_end(step, '2026-11-24T10:01', '2026-11-24T10:05')
        report = self.report()
        self.assertEqual(report['invalid_steps'], 0)
        self.assertEqual(report['details'][0]['end'], self.instant('2026-11-24T10:05'))

    def test_missing_open_history_does_not_prove_a_closing_transition(self):
        step = self.create_loading(['2026-11-24T10:02'], created_at='2026-11-24T09:00')
        self.save_loading_end(step, '2026-11-24T10:00', '2026-11-24T10:03')
        step.history.filter(history_type='+').delete()
        self.assertEqual(self.report()['invalid_steps'], 1)

    def test_history_fallback_is_batched_and_conserves_floors_across_reporting_days(self):
        for _ in range(3):
            step = self.create_loading(['2026-11-24T05:59:30'], created_at='2026-11-24T05:00')
            self.save_loading_end(step, '2026-11-24T05:58', '2026-11-24T06:00:30')
        with self.assertNumQueries(4):
            report = self.report()
        previous = self.report(self.day - timedelta(days=1))
        self.assertEqual(report['historical_end_steps'], 3)
        self.assertEqual(previous['historical_end_steps'], 3)
        for key in ('twelve', 'eight'):
            current_total = self.scheme(report, key)['total']
            previous_total = self.scheme(previous, key)['total']
            self.assertEqual(current_total['patra'], Decimal('1.5'))
            self.assertEqual(current_total['sarze'], Decimal('1.5'))
            self.assertEqual(current_total['patra'] + previous_total['patra'], 3)

    def test_anonymous_users_are_redirected(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('next=', response.url)

    def test_full_and_htmx_report_date_filter_and_old_dashboard(self):
        self.create_loading(['2026-11-24T17:00'], '2026-11-24T19:00')
        self.client.force_login(self.user)
        with patch('orders.views.timezone.now', return_value=self.now):
            response = self.client.get(self.url, {'datum': self.day.isoformat()})
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, 'orders/dashboard_casy_nakladani.html')
            self.assertEqual(response.context['db_table'], 'dashboard_casy_nakladani')
            self.assertContains(response, '12hodinové směny')
            self.assertContains(response, '8hodinové směny')
            self.assertContains(response, 'datum=2026-11-24')
            self.assertContains(response, '<td class="text-center">0,5</td>', html=True)
            self.assertContains(response, '<td class="text-center">2,0</td>', html=True)
            self.assertNotContains(response, '0,500')
            partial = self.client.get(self.url, {'datum': self.day.isoformat()}, HTTP_HX_REQUEST='true')
            self.assertTemplateUsed(partial, 'orders/partials/dashboard_casy_nakladani_content.html')
            self.assertNotContains(partial, '<html')
            other_day = self.client.get(self.url, {'datum': '2026-11-23'})
            self.assertContains(other_day, 'Pro vybraný den nejsou evidovaná nakládání.')
            old = self.client.get(reverse('dashboard_vyroba'))
            self.assertContains(old, 'Počet naložených šarží a pater')
            self.assertContains(old, 'Dočasně pro porovnání')
            self.assertContains(old, 'Počet vsázek včerejších směn')

    def test_default_date_invalid_date_and_future_date(self):
        self.client.force_login(self.user)
        with patch('orders.views.timezone.now', return_value=self.now):
            response = self.client.get(self.url)
            self.assertEqual(response.context['casy_nakladani']['date'], date(2026, 11, 25))
            for value in ('bad-date', '2026-02-30', '', '9999-12-31'):
                with self.subTest(value=value):
                    response = self.client.get(self.url, {'datum': value})
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, 'Zadejte platné datum')
                    self.assertEqual(response.context['casy_nakladani']['date'], date(2026, 11, 25))

    def test_admin_entry_is_in_production_reports_and_opens_a_new_tab(self):
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.get(reverse('admin:index'))
        html = response.content.decode()
        section = html.split('Přehledy výroby', 1)[1].split('</table>', 1)[0]
        self.assertIn(self.url, section)
        self.assertContains(
            response,
            f'<a href="{self.url}" target="_blank" rel="noopener">Přehled časů nakládání a vykládání</a>',
            html=True,
        )
