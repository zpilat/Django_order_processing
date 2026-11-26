from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from orders.choices import TypZarizeniChoice as DeviceType
from orders.models import Sarze, SarzeKrok, SarzeKrokBedna, Zarizeni
from orders.services.casy_vykladani_service import build_casy_vykladani_prehled


@override_settings(TIME_ZONE='Europe/Prague', SECURE_SSL_REDIRECT=False)
class CasyVykladaniTests(TestCase):
    day = date(2026, 11, 24)
    tz = ZoneInfo('Europe/Prague')
    now = datetime(2026, 11, 26, 12, tzinfo=tz)
    minute_tail = Decimal('59.999999')

    def setUp(self):
        self.devices = {}
        for kind in (DeviceType.TRYSKAC, DeviceType.VYKLADANI, DeviceType.NAKLADANI):
            self.devices[kind] = Zarizeni.objects.create(
                kod_zarizeni=kind, nazev_zarizeni=kind.label,
                zkraceny_nazev_zarizeni=kind, typ_zarizeni=kind,
            )

    def instant(self, text):
        return datetime.fromisoformat(text).replace(tzinfo=self.tz)

    def step(self, start, end=None, *, floors=3, kind=DeviceType.TRYSKAC, batch=None, order=1):
        start = self.instant(start)
        end = self.instant(end) if end else None
        batch = batch or Sarze.objects.create(datum_zalozeni=start.date())
        step = SarzeKrok.objects.create(
            sarze=batch, poradi=order, zarizeni=self.devices[kind],
            datum=start.date(), zacatek=start.time(), operator='Test',
            datum_konce=end.date() if end else None, konec=end.time() if end else None,
        )
        for floor in range(1, floors + 1):
            SarzeKrokBedna.objects.create(krok=step, patro=floor, popis_mimo_db='Test')
        return step

    def report(self, day=None):
        return build_casy_vykladani_prehled(date_value=day or self.day, now=self.now)

    def scheme(self, report, key='twelve'):
        return next(scheme for scheme in report['schemes'] if scheme['key'] == key)

    def test_uniform_step_splits_batch_and_actual_floor_count_across_eighteen(self):
        step = self.step('2026-11-24T17:30', '2026-11-24T19:00')
        # Více řádků na patře a jiné číslování nezvyšují počet skutečných pater.
        SarzeKrokBedna.objects.create(krok=step, patro=1, popis_mimo_db='Druhá položka')
        top = step.krok_bedny.get(patro=3)
        top.patro = 6
        top.save()
        report = self.report()
        day, night = self.scheme(report)['rows']
        day_share = Decimal(1800) / (5400 + self.minute_tail)
        self.assertEqual(day['sarze'], day_share)
        self.assertAlmostEqual(night['sarze'], 1 - day_share, places=20)
        self.assertAlmostEqual(day['patra'], 3 * day_share, places=20)
        self.assertAlmostEqual(night['patra'], 3 * (1 - day_share), places=20)
        self.assertEqual(day['hours'], Decimal('.5'))
        self.assertEqual(night['hours'], 1 + self.minute_tail / 3600)
        self.assertEqual(self.scheme(report)['total'], self.scheme(report, 'eight')['total'])
        self.assertEqual(report['details'][0]['floor_count'], 3)

    def test_both_device_types_use_the_same_rules_at_fourteen_and_twenty_two(self):
        self.step('2026-11-24T13:30', '2026-11-24T14:30', floors=4, kind=DeviceType.VYKLADANI)
        self.step('2026-11-24T21:30', '2026-11-24T22:30', floors=2)
        report = self.report()
        rows = self.scheme(report, 'eight')['rows']
        before_boundary = Decimal(1800) / (3600 + self.minute_tail)
        expected = ((4 * before_boundary, before_boundary),
                    (4 - 2 * before_boundary, Decimal(1)),
                    (2 * (1 - before_boundary), 1 - before_boundary))
        for row, (floors, batches) in zip(rows, expected):
            self.assertAlmostEqual(row['patra'], floors, places=20)
            self.assertAlmostEqual(row['sarze'], batches, places=20)
        self.assertEqual(self.scheme(report)['total']['patra'], 6)
        self.assertEqual(self.scheme(report)['total']['sarze'], 2)
        self.assertEqual(self.scheme(report)['total'], self.scheme(report, 'eight')['total'])

    def test_crossing_midnight_and_six_is_split_between_reporting_days(self):
        self.step('2026-11-24T22:00', '2026-11-25T07:00', floors=4)
        current = self.scheme(self.report())['total']
        following = self.scheme(self.report(self.day + timedelta(days=1)))['total']
        self.assertEqual(current['sarze'], Decimal(28800) / (32400 + self.minute_tail))
        self.assertEqual(current['hours'], 8)
        self.assertEqual(following['sarze'], (3600 + self.minute_tail) / (32400 + self.minute_tail))
        self.assertEqual(following['hours'], 1 + self.minute_tail / 3600)
        self.assertEqual(current['patra'] + following['patra'], 4)

    def test_step_started_before_selected_day_is_included(self):
        self.step('2026-11-23T22:00', '2026-11-24T10:00', floors=3)
        day, night = self.scheme(self.report())['rows']
        day_share = (14400 + self.minute_tail) / (43200 + self.minute_tail)
        self.assertEqual(day['sarze'], day_share)
        self.assertAlmostEqual(day['patra'], 3 * day_share, places=20)
        self.assertEqual(day['hours'], 4 + self.minute_tail / 3600)
        self.assertEqual(night['sarze'], 0)

    def test_closing_minute_at_six_belongs_to_the_next_reporting_day(self):
        self.step('2026-11-23T22:00', '2026-11-24T06:00')
        self.step('2026-11-24T06:00', '2026-11-24T07:00', floors=2)
        self.step('2026-11-25T06:00', '2026-11-25T07:00')
        report = self.report()
        self.assertEqual(len(report['details']), 2)
        tail_share = self.minute_tail / (28800 + self.minute_tail)
        self.assertEqual(self.scheme(report)['total']['sarze'], 1 + tail_share)
        self.assertAlmostEqual(self.scheme(report)['total']['patra'], 2 + 3 * tail_share, places=20)

    def test_open_step_waits_for_end_then_backfills_its_original_day(self):
        step = self.step('2026-11-24T17:30')
        report = self.report()
        self.assertEqual(report['incomplete_steps'], 1)
        self.assertEqual(report['invalid_steps'], 0)
        self.assertEqual(self.scheme(report)['total']['sarze'], 0)
        self.assertEqual(self.scheme(report)['total']['patra'], 0)
        self.assertEqual(self.scheme(report)['total']['hours'], 0)
        self.assertIsNone(report['details'][0]['end'])
        self.assertIsNone(report['details'][0]['hours'])
        step.datum_konce = self.day
        step.konec = self.instant('2026-11-24T19:00').time()
        step.save()
        report = self.report()
        self.assertEqual(report['incomplete_steps'], 0)
        self.assertEqual(self.scheme(report)['total']['sarze'], 1)
        self.assertEqual(self.scheme(report)['total']['patra'], 3)

    def test_missing_floors_and_invalid_times_do_not_contribute(self):
        self.step('2026-11-24T09:00', '2026-11-24T10:00', floors=0)
        self.step('2026-11-24T11:00', '2026-11-24T10:59')
        self.step('2026-11-24T13:00', '2026-11-24T12:00')
        self.step('2026-11-24T14:00', '2026-11-27T15:00')
        report = self.report()
        self.assertEqual(report['invalid_steps'], 4)
        self.assertEqual(self.scheme(report)['total']['sarze'], 0)
        self.assertEqual(self.scheme(report)['total']['patra'], 0)
        self.assertEqual(self.scheme(report)['total']['hours'], 0)
        self.assertTrue(all(row['invalid'] for row in report['details']))

    def test_floor_history_is_not_used_as_the_unloading_start(self):
        step = self.step('2026-11-24T17:30', '2026-11-24T19:00')
        SarzeKrokBedna.history.filter(krok_id=step.pk).delete()
        report = self.report()
        self.assertEqual(report['invalid_steps'], 0)
        self.assertEqual(report['details'][0]['start'], self.instant('2026-11-24T17:30'))
        self.assertEqual(self.scheme(report)['total']['sarze'], 1)

    def test_other_device_types_do_not_count_as_unloading(self):
        self.step('2026-11-24T09:00', '2026-11-24T10:00', kind=DeviceType.NAKLADANI)
        report = self.report()
        self.assertEqual(report['details'], [])
        self.assertEqual(self.scheme(report)['total']['sarze'], 0)

    def test_multiple_steps_for_same_batch_are_flagged_and_counted_as_separate_passes(self):
        first = self.step('2026-11-24T09:00', '2026-11-24T10:00')
        self.step('2026-11-24T11:00', '2026-11-24T12:00',
                  kind=DeviceType.VYKLADANI, batch=first.sarze, order=2)
        report = self.report()
        self.assertEqual(report['repeated_batches'], 1)
        self.assertTrue(all(row['repeated'] for row in report['details']))
        self.assertEqual(self.scheme(report)['total']['sarze'], 2)
        self.assertEqual(self.scheme(report)['total']['patra'], 6)

    def test_repeat_warning_also_checks_steps_outside_the_selected_day(self):
        first = self.step('2026-11-23T09:00', '2026-11-23T10:00')
        self.step('2026-11-24T11:00', '2026-11-24T12:00', batch=first.sarze, order=2)
        report = self.report()
        self.assertEqual(len(report['details']), 1)
        self.assertTrue(report['details'][0]['repeated'])
        self.assertEqual(report['repeated_batches'], 1)
        self.assertEqual(self.scheme(report)['total']['sarze'], 1)

    def test_dst_nights_use_real_elapsed_time(self):
        for day, next_day, expected in (
            ('2026-03-28', '2026-03-29', 7), ('2026-10-24', '2026-10-25', 9),
        ):
            with self.subTest(day=day):
                self.step(f'{day}T22:00', f'{next_day}T06:00', floors=2)
                report = self.report(date.fromisoformat(day))
                for scheme in report['schemes']:
                    self.assertEqual(scheme['rows'][-1]['hours'], expected)
                    share = Decimal(expected * 3600) / (expected * 3600 + self.minute_tail)
                    self.assertEqual(scheme['rows'][-1]['sarze'], share)
                    self.assertAlmostEqual(scheme['rows'][-1]['patra'], 2 * share, places=20)
                following = self.scheme(self.report(date.fromisoformat(next_day)))['total']
                self.assertEqual(self.scheme(report)['total']['sarze'] + following['sarze'], 1)

    def test_step_started_and_finished_in_the_same_minute_counts_the_whole_minute(self):
        step = self.step('2026-11-24T17:59:00', '2026-11-24T17:59:00')
        report = self.report()
        self.assertEqual(report['invalid_steps'], 0)
        self.assertEqual(self.scheme(report)['rows'][0]['sarze'], 1)
        self.assertEqual(self.scheme(report)['rows'][0]['patra'], 3)
        self.assertEqual(self.scheme(report)['rows'][1]['sarze'], 0)
        self.assertEqual(report['details'][0]['end'], self.instant('2026-11-24T17:59:59.999999'))
        step.refresh_from_db()
        self.assertEqual(step.konec, self.instant('2026-11-24T17:59:00').time())

    def test_original_seconds_are_replaced_instead_of_adding_another_minute(self):
        self.step('2026-11-24T09:59', '2026-11-24T10:00:40')
        row = self.report()['details'][0]
        self.assertEqual(row['end'], self.instant('2026-11-24T10:00:59.999999'))
        self.assertEqual(row['recorded_end'], self.instant('2026-11-24T10:00:40'))

    def test_future_validation_uses_original_end_for_just_closed_unloading(self):
        self.step('2026-11-24T17:00', '2026-11-24T17:59')
        now = self.instant('2026-11-24T17:59:20')
        report = build_casy_vykladani_prehled(date_value=self.day, now=now)
        self.assertEqual(report['invalid_steps'], 0)
        self.assertGreater(report['details'][0]['end'], now)
        self.step('2026-11-24T17:10', '2026-11-24T17:59:50')
        report = build_casy_vykladani_prehled(date_value=self.day, now=now)
        self.assertEqual(report['invalid_steps'], 1)
        self.assertEqual(report['details'][1]['status'], 'Konec vykládání je v budoucnosti.')

    def test_query_count_is_constant_and_report_does_not_modify_evidence(self):
        for _ in range(3):
            self.step('2026-11-24T09:00', '2026-11-24T10:00')
        history_count = SarzeKrok.history.count() + SarzeKrokBedna.history.count()
        with self.assertNumQueries(2):
            report = self.report()
        self.assertEqual(len(report['details']), 3)
        self.assertEqual(history_count, SarzeKrok.history.count() + SarzeKrokBedna.history.count())

    def test_combined_page_renders_both_sections_and_one_total_per_section(self):
        self.step('2026-11-24T17:30', '2026-11-24T19:00')
        user = get_user_model().objects.create_user('prehled')
        self.client.force_login(user)
        url = reverse('dashboard_casy_nakladani')
        with patch('orders.views.timezone.now', return_value=self.now):
            response = self.client.get(url, {'datum': self.day.isoformat()})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Přehled časů nakládání a vykládání')
            self.assertContains(response, 'id="loading-section"', count=1)
            self.assertContains(response, 'id="unloading-section"', count=1)
            for prefix in ('loading', 'unloading'):
                for scheme in ('twelve', 'eight'):
                    self.assertContains(response, f'id="{prefix}-{scheme}"', count=1)
            self.assertContains(response, '<tfoot>', count=2)
            self.assertContains(response, '<td class="text-center">0,3</td>', html=True)
            self.assertContains(response, '<td class="text-center">0,7</td>', html=True)
            self.assertContains(response, 'Časy vykládání šarží')
            self.assertContains(response, 'Tryskač')
            self.assertEqual(response.context['casy_nakladani']['date'], response.context['casy_vykladani']['date'])
            partial = self.client.get(url, {'datum': self.day.isoformat()}, HTTP_HX_REQUEST='true')
            self.assertEqual(partial.status_code, 200)
            self.assertContains(partial, 'Časy vykládání šarží')
            self.assertNotContains(partial, '<html')
            empty = self.client.get(url, {'datum': '2026-11-23'})
            self.assertContains(empty, 'Pro vybraný den nejsou evidovaná vykládání.')

    def test_page_marks_repeat_open_and_invalid_unloading(self):
        first = self.step('2026-11-24T09:00', '2026-11-24T10:00')
        self.step('2026-11-24T11:00', '2026-11-24T12:00', batch=first.sarze, order=2)
        self.step('2026-11-24T13:00')
        self.step('2026-11-24T14:00', '2026-11-24T15:00', floors=0)
        self.client.force_login(get_user_model().objects.create_user('upozorneni'))
        with patch('orders.views.timezone.now', return_value=self.now):
            response = self.client.get(reverse('dashboard_casy_nakladani'), {'datum': self.day.isoformat()})
        self.assertContains(response, 'Více průchodů šarže – ověřit evidenci.')
        self.assertContains(response, 'Každý platný dokončený krok je započtený samostatně.')
        self.assertContains(response, 'Rozpracováno, čeká na konec vykládání.')
        self.assertContains(response, 'Krok nemá evidovaná patra.')
