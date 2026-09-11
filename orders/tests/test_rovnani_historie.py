from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.urls import reverse
from django.test import override_settings
from django.utils import timezone

from orders.choices import KamionChoice, RovnaniChoice, StavBednyChoice, TryskaniChoice
from orders.models import Bedna, Kamion, PoziceZakazkaOrder
from orders.services.history_service import history_transitions_to_qs
from orders.tests.tests_views import ViewsTestBase
from orders.views import _build_rovnani_historie_context


@override_settings(TIME_ZONE='Europe/Prague')
class RovnaniHistorieTests(ViewsTestBase):
    def setUp(self):
        super().setUp()
        self.snapshot = Bedna.history.filter(id=self.b_eur_pr.pk).values().first()
        self.snapshot.pop('history_id')
        Bedna.history.all().delete()

    def history(self, bedna, timestamp, state, kind='~', **overrides):
        values = dict(self.snapshot)
        values.update(
            id=bedna.pk, cislo_bedny=bedna.cislo_bedny,
            history_date=datetime.fromisoformat(timestamp).replace(tzinfo=ZoneInfo('Europe/Prague')),
            rovnat=state, history_type=kind,
        )
        values.update(overrides)
        return Bedna.history.model.objects.create(**values)

    def context(self, today=date(2026, 1, 11), year=2026, month=1):
        return _build_rovnani_historie_context(year, month, today)['rovnani_historie']

    def test_transition_helper_supports_another_tracked_field(self):
        bedna = self.b_eur_pr
        self.history(
            bedna, '2026-01-04T12:00', RovnaniChoice.NEZADANO, '+',
            tryskat=TryskaniChoice.SPINAVA,
        )
        transition = self.history(
            bedna, '2026-01-05T12:00', RovnaniChoice.NEZADANO,
            tryskat=TryskaniChoice.OTRYSKANA,
        )
        self.history(
            bedna, '2026-01-06T12:00', RovnaniChoice.NEZADANO,
            tryskat=TryskaniChoice.OTRYSKANA,
        )

        transitions = history_transitions_to_qs(
            model=Bedna,
            field_name='tryskat',
            target_value=TryskaniChoice.OTRYSKANA,
        )

        self.assertEqual(list(transitions.values_list('history_id', flat=True)), [transition.history_id])

    def test_transition_helper_supports_another_historical_model(self):
        kamion = self.k_prijem_abc
        kamion.prijem_vydej = KamionChoice.VYDEJ
        kamion.save(update_fields=['prijem_vydej'])
        transition = kamion.history.first()
        kamion.poznamka = 'Beze změny sledovaného pole'
        kamion.save(update_fields=['poznamka'])

        transitions = history_transitions_to_qs(
            model=Kamion,
            field_name='prijem_vydej',
            target_value=KamionChoice.VYDEJ,
        )

        self.assertEqual(list(transitions.values_list('history_id', flat=True)), [transition.history_id])

    def test_transition_helper_treats_multiple_targets_as_one_target_set(self):
        bedna = self.b_eur_pr
        self.history(
            bedna, '2026-01-01T12:00', RovnaniChoice.NEZADANO, '+',
            stav_bedny=StavBednyChoice.ZAKALENO,
        )
        entered_zkontrolovano = self.history(
            bedna, '2026-01-02T12:00', RovnaniChoice.NEZADANO,
            stav_bedny=StavBednyChoice.ZKONTROLOVANO,
        )
        self.history(
            bedna, '2026-01-03T12:00', RovnaniChoice.NEZADANO,
            stav_bedny=StavBednyChoice.K_EXPEDICI,
        )
        self.history(
            bedna, '2026-01-04T12:00', RovnaniChoice.NEZADANO,
            stav_bedny=StavBednyChoice.ZKONTROLOVANO,
        )
        self.history(
            bedna, '2026-01-05T12:00', RovnaniChoice.NEZADANO,
            stav_bedny=StavBednyChoice.ZAKALENO,
        )
        reentered_at_k_expedici = self.history(
            bedna, '2026-01-06T12:00', RovnaniChoice.NEZADANO,
            stav_bedny=StavBednyChoice.K_EXPEDICI,
        )

        direct_bedna = self.b_abc_ex
        self.history(
            direct_bedna, '2026-01-01T12:00', RovnaniChoice.ROVNA, '+',
            stav_bedny=StavBednyChoice.ZAKALENO,
        )
        direct_to_k_expedici = self.history(
            direct_bedna, '2026-01-02T12:00', RovnaniChoice.ROVNA,
            stav_bedny=StavBednyChoice.K_EXPEDICI,
        )

        expected_ids = {
            entered_zkontrolovano.history_id,
            reentered_at_k_expedici.history_id,
            direct_to_k_expedici.history_id,
        }
        for target_value in (
            (StavBednyChoice.ZKONTROLOVANO, StavBednyChoice.K_EXPEDICI),
            [StavBednyChoice.ZKONTROLOVANO, StavBednyChoice.K_EXPEDICI],
        ):
            with self.subTest(target_type=type(target_value).__name__):
                transitions = history_transitions_to_qs(
                    model=Bedna,
                    field_name='stav_bedny',
                    target_value=target_value,
                )
                self.assertSetEqual(
                    set(transitions.values_list('history_id', flat=True)),
                    expected_ids,
                )

    def test_transition_helper_validates_model_and_field(self):
        with self.assertRaisesRegex(ValueError, 'nemá nakonfigurovanou historii'):
            history_transitions_to_qs(
                model=PoziceZakazkaOrder,
                field_name='nasledne',
                target_value=True,
            )

        with self.assertRaisesRegex(ValueError, 'není sledováno'):
            history_transitions_to_qs(
                model=Bedna,
                field_name='neexistujici_pole',
                target_value='hodnota',
            )

        with self.assertRaisesRegex(ValueError, 'alespoň jedna cílová hodnota'):
            history_transitions_to_qs(
                model=Bedna,
                field_name='stav_bedny',
                target_value=[],
            )

    def test_only_actual_transitions_count_including_previous_year_and_equal_timestamps(self):
        bedna = self.b_eur_pr
        self.history(bedna, '2025-12-31T12:00', RovnaniChoice.ROVNA_SE, '+')
        self.history(bedna, '2026-01-05T12:00', RovnaniChoice.VYROVNANA)
        self.history(bedna, '2026-01-06T12:00', RovnaniChoice.VYROVNANA)
        self.history(bedna, '2026-01-06T12:00', RovnaniChoice.ROVNA_SE)
        self.history(bedna, '2026-01-06T12:00', RovnaniChoice.VYROVNANA)
        self.history(bedna, '2026-01-07T12:00', RovnaniChoice.VYROVNANA, '-')
        # Creation in VY and updates without a preceding snapshot aren't transitions.
        self.history(self.b_abc_ex, '2026-01-05T12:00', RovnaniChoice.VYROVNANA, '+')
        self.history(self.b_abc_ex, '2026-01-06T12:00', RovnaniChoice.VYROVNANA)
        self.history(self.b_vydej, '2026-01-05T12:00', RovnaniChoice.VYROVNANA)

        data = self.context()
        self.assertEqual(data['yearly']['count'], 1)
        self.assertEqual(data['monthly_rows'][0]['count'], 1)
        self.assertEqual(data['weekly_rows'][1]['count'], 1)
        days = {row['label']: row['count'] for row in data['month_detail']['rows']}
        self.assertEqual(days['05.01.2026'], 1)
        self.assertEqual(days['06.01.2026'], 1)
        self.assertEqual(days['07.01.2026'], 0)

    def test_weekdays_include_zero_production_days_and_holidays_but_not_weekends(self):
        for bedna, day in ((self.b_eur_pr, 1), (self.b_abc_ex, 5), (self.b_vydej, 10)):
            self.history(bedna, '2025-12-31T12:00', RovnaniChoice.KRIVA, '+')
            self.history(bedna, f'2026-01-{day:02d}T12:00', RovnaniChoice.VYROVNANA)
        data = self.context()
        self.assertEqual(data['yearly'], {'count': 3, 'avg': Decimal('0.43'), 'workdays': 7})
        self.assertEqual(data['monthly_rows'][0]['workdays'], 7)
        self.assertEqual(data['weekly_rows'][0]['date_range'], '01.01. - 04.01.')
        self.assertEqual(data['weekly_rows'][0]['workdays'], 2)
        self.assertEqual(data['weekly_rows'][1]['workdays'], 5)
        self.assertEqual(data['weekly_rows'][1]['avg'], Decimal('0.40'))
        self.assertEqual(data['weekly_rows'][2]['count'], 0)
        self.assertEqual(data['weekly_rows'][2]['workdays'], 0)

    def test_current_period_stops_today_and_future_month_is_empty(self):
        self.history(self.b_eur_pr, '2026-01-01T12:00', RovnaniChoice.KRIVA, '+')
        self.history(self.b_eur_pr, '2026-01-05T12:00', RovnaniChoice.VYROVNANA)
        self.history(self.b_abc_ex, '2026-01-01T12:00', RovnaniChoice.KRIVA, '+')
        self.history(self.b_abc_ex, '2026-01-09T12:00', RovnaniChoice.VYROVNANA)
        data = self.context(today=date(2026, 1, 7))
        self.assertEqual(data['weekly_rows'][1]['workdays'], 3)
        self.assertEqual(data['weekly_rows'][1]['avg'], Decimal('0.33'))
        self.assertEqual(len(data['weekly_chart']['points']), 2)
        self.assertIn('1 beden', data['weekly_chart']['points'][-1]['tooltip'])
        self.assertEqual(
            [tick['label'] for tick in data['weekly_chart']['ticks']],
            ['0', '1', '2', '3', '4'],
        )
        self.assertEqual(data['yearly']['count'], 1)
        self.assertEqual(len(data['month_detail']['rows']), 7)
        self.assertEqual(len(data['month_detail']['chart']['points']), 7)
        self.assertIn('05.01.2026: 1 beden', data['month_detail']['chart']['points'][4]['tooltip'])
        self.assertTrue(all(tick['label'].isdigit() for tick in data['month_detail']['chart']['ticks']))
        self.assertEqual(self.context(month=2)['month_detail']['rows'], [])
        self.assertEqual(self.context(month=2)['month_detail']['chart']['points'], [])

    def test_local_date_and_leap_year_and_historical_year_selection(self):
        self.history(self.b_eur_pr, '2024-02-28T12:00', RovnaniChoice.KRIVA, '+')
        event = self.history(self.b_eur_pr, '2024-02-29T00:30', RovnaniChoice.VYROVNANA)
        self.assertEqual(event.history_date.astimezone(ZoneInfo('UTC')).day, 28)
        data = self.context(year=2024, month=2)
        self.assertEqual(data['available_years'], [2026, 2024])
        self.assertEqual(data['yearly']['workdays'], 262)
        self.assertEqual(data['monthly_rows'][1]['workdays'], 21)
        self.assertEqual(len(data['month_detail']['rows']), 29)
        self.assertEqual(data['month_detail']['rows'][-1]['count'], 1)
        self.assertEqual(data['month_detail']['rows'][-2]['count'], 0)

    def test_weekend_only_period_does_not_divide_by_zero(self):
        self.history(self.b_eur_pr, '2021-12-31T12:00', RovnaniChoice.KRIVA, '+')
        self.history(self.b_eur_pr, '2022-01-01T12:00', RovnaniChoice.VYROVNANA)
        data = self.context(year=2022)
        self.assertEqual(data['weekly_rows'][0]['count'], 1)
        self.assertEqual(data['weekly_rows'][0]['workdays'], 0)
        self.assertEqual(data['weekly_rows'][0]['avg'], Decimal('0.00'))

    def test_empty_history_and_invalid_parameters(self):
        data = self.context(year='bad', month='bad')
        self.assertEqual(data['selected_year'], 2026)
        self.assertEqual(data['available_years'], [2026])
        self.assertEqual(data['yearly']['count'], 0)
        self.assertIsNone(data['month_detail'])
        for year in (0, 999999, 2027):
            self.assertEqual(self.context(year=year)['selected_year'], 2026)

    def test_full_and_htmx_pages_and_month_links(self):
        year = timezone.localdate().year
        for name in ('dashboard_rovnani_historie', 'dashboard_rovnani_historie_mesic'):
            for htmx in (False, True):
                with self.subTest(name=name, htmx=htmx):
                    response = self.client.get(reverse(name), {'rok': year, 'mesic': 1}, HTTP_HX_REQUEST=str(htmx).lower())
                    self.assertEqual(response.status_code, 200)
                    template = f'orders/partials/{name}_content.html' if htmx else f'orders/{name}.html'
                    self.assertTemplateUsed(response, template)
                    self.assertContains(response, 'Vyrovnané bedny')
                    self.assertContains(response, '<svg ', count=1)
                    self.assertContains(response, '<polyline points="')
                    if name == 'dashboard_rovnani_historie':
                        self.assertContains(response, f'{reverse("dashboard_rovnani_historie_mesic")}?rok={year}&mesic=1')
                    else:
                        self.assertNotContains(response, 'beden/den')

    def test_invalid_month_redirects_and_anonymous_user_requires_login(self):
        year = timezone.localdate().year
        for month in ('', 'bad', 0, 13):
            response = self.client.get(reverse('dashboard_rovnani_historie_mesic'), {'rok': year, 'mesic': month})
            self.assertRedirects(response, f'{reverse("dashboard_rovnani_historie")}?rok={year}', fetch_redirect_response=False)
        self.client.logout()
        for name in ('dashboard_rovnani_historie', 'dashboard_rovnani_historie_mesic'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)
