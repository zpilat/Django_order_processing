from datetime import date, datetime, timezone as datetime_timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings
from django.urls import reverse

from orders.choices import StavBednyChoice as State, UvolneniKontrolyChoice as Release
from orders.models import Bedna, KontrolaBedny
from orders.services.kontrolori_prehled_service import (
    build_kontrolori_prehled, DOKONCENI_KONTROLY_REASON, RUCNI_ZKONTROLOVANO_REASON,
)
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


@override_settings(TIME_ZONE='Europe/Prague', SECURE_SSL_REDIRECT=False)
class KontroloriPrehledTests(KontrolaBednyTestBase):
    today = date(2026, 11, 18)

    def setUp(self):
        self.finisher = get_user_model().objects.create_user('dokoncujici', first_name='Jan', last_name='Novák')
        self.control = KontrolaBedny.objects.create(bedna=self.bedna)
        self.templates = {}
        for model in (Bedna, KontrolaBedny):
            values = model.history.values().first()
            values.pop('history_id')
            self.templates[model] = values
            model.history.all().delete()
        self.url = reverse('kontrolori_prehled')

    def event(self, model, timestamp, value, *, user='default', kind='~', **overrides):
        values = dict(self.templates[model])
        instant = datetime.fromisoformat(timestamp)
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=ZoneInfo('Europe/Prague'))
        values.update(
            history_date=instant, history_type=kind,
            history_user_id=self.user.pk if user == 'default' else user,
            history_change_reason=None,
        )
        values['stav_bedny' if model is Bedna else 'uvolneni'] = value
        values.update(overrides)
        return model.history.model.objects.create(**values)

    def report(self):
        return build_kontrolori_prehled(today=self.today)

    def test_each_completion_belongs_to_finisher_without_counting_saves_or_dispatch_returns(self):
        self.event(Bedna, '2026-11-01T09:00', State.ZAKALENO, kind='+')
        self.event(Bedna, '2026-11-02T09:00', State.ZAKALENO)
        self.event(Bedna, '2026-11-03T09:00', State.ZKONTROLOVANO, user=self.finisher.pk,
                   history_change_reason=DOKONCENI_KONTROLY_REASON)
        self.event(Bedna, '2026-11-04T09:00', State.ZKONTROLOVANO)
        self.event(Bedna, '2026-11-05T09:00', State.K_EXPEDICI)
        self.event(Bedna, '2026-11-06T09:00', State.ZKONTROLOVANO)
        self.event(Bedna, '2026-11-07T09:00', State.ZAKALENO)
        self.event(Bedna, '2026-11-08T09:00', State.ZKONTROLOVANO)

        report = self.report()
        self.assertEqual(report['completed'], 2)
        self.assertEqual(report['summary'], [
            {'user_id': self.finisher.pk, 'name': 'Jan Novák', 'completed': 1, 'resolved': 0},
            {'user_id': self.user.pk, 'name': 'kontrolor', 'completed': 1, 'resolved': 0},
        ])
        day = next(day for day in report['days'] if day['date'] == date(2026, 11, 3))
        self.assertEqual(day['rows'][0]['completed'], 1)
        self.assertEqual(sum(day['completed'] for day in report['days']), 2)
        self.assertEqual(len(report['days']), 30)
        self.assertEqual(report['days'][0]['date'], self.today)
        self.assertEqual(report['days'][-1]['date'], date(2026, 10, 20))
        self.assertEqual(report['days'][0]['rows'][0]['completed'], 0)

    def test_repeat_in_period_counts_even_when_first_completion_is_before_period(self):
        self.event(Bedna, '2026-10-01T09:00', State.ZAKALENO, kind='+')
        self.event(Bedna, '2026-10-02T09:00', State.ZKONTROLOVANO)
        self.event(Bedna, '2026-11-01T09:00', State.ZAKALENO)
        self.event(Bedna, '2026-11-02T09:00', State.ZKONTROLOVANO)
        self.assertEqual(self.report()['completed'], 1)

    def test_same_crate_can_be_completed_multiple_times_per_day_by_different_users(self):
        self.event(Bedna, '2026-11-01T09:00', State.ZAKALENO, kind='+')
        for hour, author in ((10, self.finisher.pk), (12, self.user.pk), (14, self.user.pk)):
            self.event(Bedna, f'2026-11-01T{hour:02d}:00', State.ZKONTROLOVANO, user=author,
                       history_change_reason=DOKONCENI_KONTROLY_REASON)
            self.event(Bedna, f'2026-11-01T{hour:02d}:30', State.ZKONTROLOVANO, user=author)
            self.event(Bedna, f'2026-11-01T{hour + 1:02d}:00', State.ZAKALENO)
        report = self.report()
        self.assertEqual(report['completed'], 3)
        totals = {row['user_id']: row['completed'] for row in report['summary']}
        self.assertEqual(totals, {self.finisher.pk: 1, self.user.pk: 2})
        day = next(day for day in report['days'] if day['date'] == date(2026, 11, 1))
        self.assertEqual(day['completed'], 3)
        self.assertEqual({row['user_id']: row['completed'] for row in day['rows']}, totals)

    def test_noncompletion_transitions_and_new_manual_admin_changes_are_excluded(self):
        self.event(Bedna, '2026-11-01T09:00', State.ZKONTROLOVANO, kind='+')
        self.event(Bedna, '2026-11-02T09:00', State.ZKONTROLOVANO)
        self.event(Bedna, '2026-11-03T09:00', State.PRIJATO)
        self.event(Bedna, '2026-11-04T09:00', State.ZKONTROLOVANO,
                   history_change_reason='Převod na atypický průběh.')
        self.event(Bedna, '2026-11-05T09:00', State.K_EXPEDICI)
        self.event(Bedna, '2026-11-06T09:00', State.ZKONTROLOVANO)
        self.event(Bedna, '2026-11-07T09:00', State.ZAKALENO)
        self.event(Bedna, '2026-11-08T09:00', State.ZKONTROLOVANO,
                   history_change_reason=RUCNI_ZKONTROLOVANO_REASON)
        self.event(Bedna, '2026-11-09T09:00', State.ZAKALENO)
        self.event(Bedna, '2026-11-10T09:00', State.ZKONTROLOVANO, kind='-')
        self.assertEqual(self.report()['completed'], 0)

    def test_each_resolution_cycle_counts_but_changes_between_released_states_do_not(self):
        self.event(KontrolaBedny, '2026-10-01T09:00', Release.NESHODA, kind='+')
        self.event(KontrolaBedny, '2026-11-01T09:00', Release.UVOLNENO, user=self.finisher.pk)
        self.event(KontrolaBedny, '2026-11-01T10:00', Release.UVOLNENO)
        self.event(KontrolaBedny, '2026-11-01T11:00', Release.UVOLNENO_S_ODCHYLKOU)
        self.event(KontrolaBedny, '2026-11-01T12:00', Release.NESHODA)
        self.event(KontrolaBedny, '2026-11-01T13:00', Release.UVOLNENO_S_ODCHYLKOU, user=self.finisher.pk)
        self.event(KontrolaBedny, '2026-11-02T09:00', Release.NEROZHODNUTO)
        self.event(KontrolaBedny, '2026-11-02T10:00', Release.UVOLNENO)
        report = self.report()
        self.assertEqual(report['resolved'], 2)
        self.assertEqual(report['summary'][0]['user_id'], self.finisher.pk)
        self.assertEqual(report['summary'][0]['resolved'], 2)

    def test_equal_timestamps_are_ordered_by_history_id(self):
        self.event(Bedna, '2026-11-01T09:00', State.ZAKALENO, kind='+')
        self.event(Bedna, '2026-11-01T09:00', State.ZKONTROLOVANO)
        self.event(KontrolaBedny, '2026-11-01T09:00', Release.NESHODA, kind='+')
        self.event(KontrolaBedny, '2026-11-01T09:00', Release.UVOLNENO)
        self.event(KontrolaBedny, '2026-11-01T09:00', Release.NESHODA)
        self.event(KontrolaBedny, '2026-11-01T09:00', Release.UVOLNENO_S_ODCHYLKOU)
        self.assertEqual(self.report()['completed'], 1)
        self.assertEqual(self.report()['resolved'], 2)

    def test_local_date_bounds_include_30_days_across_dst_change(self):
        self.event(Bedna, '2026-10-19T20:00+00:00', State.ZAKALENO, kind='+')
        self.event(Bedna, '2026-10-19T22:00+00:00', State.ZKONTROLOVANO)
        self.event(KontrolaBedny, '2026-10-19T20:00+00:00', Release.NESHODA, kind='+')
        self.event(KontrolaBedny, '2026-10-19T21:59:59+00:00', Release.UVOLNENO)
        self.event(KontrolaBedny, '2026-11-17T21:00+00:00', Release.NESHODA)
        self.event(KontrolaBedny, '2026-11-17T23:30+00:00', Release.UVOLNENO)
        self.event(KontrolaBedny, '2026-11-18T22:00+00:00', Release.NESHODA)
        self.event(KontrolaBedny, '2026-11-18T23:00+00:00', Release.UVOLNENO)
        report = self.report()
        self.assertEqual(report['completed'], 1)
        self.assertEqual(report['resolved'], 1)
        self.assertEqual(report['days'][-1]['completed'], 1)
        self.assertEqual(report['days'][0]['resolved'], 1)
        with patch('orders.services.kontrolori_prehled_service.timezone.now', return_value=datetime(
            2026, 11, 17, 23, 30, tzinfo=datetime_timezone.utc,
        )):
            self.assertEqual(build_kontrolori_prehled()['end_date'], self.today)

    def test_unknown_author_is_not_attributed_to_creator_and_duplicate_names_stay_separate(self):
        self.user.first_name, self.user.last_name = 'Jan', 'Novák'
        self.user.save()
        self.event(KontrolaBedny, '2026-11-01T09:00', Release.NESHODA, kind='+')
        for hour, author in ((10, self.user.pk), (12, self.finisher.pk), (14, None)):
            self.event(KontrolaBedny, f'2026-11-01T{hour:02d}:00', Release.UVOLNENO, user=author)
            self.event(KontrolaBedny, f'2026-11-01T{hour + 1:02d}:00', Release.NESHODA)
        report = self.report()
        self.assertEqual(report['resolved'], 3)
        self.assertEqual(len(report['summary']), 3)
        self.assertEqual(report['summary'][-1], {
            'user_id': None, 'name': 'Neznámý uživatel', 'completed': 0, 'resolved': 1,
        })

    def test_empty_report_has_all_days_and_handles_year_boundary(self):
        report = build_kontrolori_prehled(today=date(2026, 1, 10))
        self.assertEqual(report['start_date'], date(2025, 12, 12))
        self.assertEqual(len(report['days']), 30)
        self.assertEqual(report['summary'], [])
        self.assertTrue(all(day['completed'] == day['resolved'] == 0 for day in report['days']))

    def test_login_required_and_full_page_partial_navigation_and_no_cache(self):
        self.assertRedirects(self.client.get(self.url), f'/accounts/login/?next={self.url}',
                             fetch_redirect_response=False)
        self.client.force_login(self.user)
        with patch('orders.services.kontrolori_prehled_service.timezone.localdate', return_value=self.today):
            response = self.client.get(self.url, {'rok': 1999, 'od': '1999-01-01'})
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, 'orders/kontrolori_prehled.html')
            self.assertContains(response, f'href="{self.url}"')
            self.assertContains(response, '20.10.2026')
            self.assertContains(response, '18.11.2026')
            self.assertContains(response, 'nebyly zaznamenány')
            self.assertContains(response, 'hx-trigger="every 60s"')
            self.assertIn('no-store', response['Cache-Control'])
            partial = self.client.get(self.url, HTTP_HX_REQUEST='true')
            self.assertTemplateUsed(partial, 'orders/partials/kontrolori_prehled_content.html')
            self.assertNotContains(partial, '<html')

    def test_admin_detail_completion_is_marked_as_manual(self):
        self.bedna.stav_bedny = State.ZKONTROLOVANO
        self.bedna.hmotnost, self.bedna.tara, self.bedna.mnozstvi = 10, 1, 100
        request = RequestFactory().post('/')
        request.user = self.user
        admin.site._registry[Bedna].save_model(
            request, self.bedna, SimpleNamespace(changed_data=['stav_bedny']), change=True,
        )
        self.assertEqual(self.bedna.history.first().history_change_reason, RUCNI_ZKONTROLOVANO_REASON)
