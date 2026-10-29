from decimal import Decimal

from django.contrib.auth.models import Permission
from django.urls import reverse

from orders.choices import StavBednyChoice, TypZkouskyChoice, UvolneniKontrolyChoice
from orders.models import KontrolaBedny, MereniBedny
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class UvolneniProhybTests(KontrolaBednyTestBase):
    def setUp(self):
        self.customer = self.bedna.zakazka.kamion_prijem.zakaznik
        self.customer.zkratka = 'ROT'
        self.customer.max_krivych_vrutu = 1
        self.customer.save(update_fields=['zkratka', 'max_krivych_vrutu'])
        self.bedna.stav_bedny = StavBednyChoice.ZAKALENO
        self.bedna.hmotnost = Decimal('10')
        self.bedna.tara = Decimal('1')
        self.bedna.mnozstvi = 100
        self.bedna.save(update_fields=['stav_bedny', 'hmotnost', 'tara', 'mnozstvi'])
        self.kontrola = KontrolaBedny.objects.create(bedna=self.bedna)
        self.user.user_permissions.add(Permission.objects.get(codename='mark_bedna_zkontrolovano'))
        self.client.force_login(self.user)
        self.url = reverse('bedna_kontrola', args=[self.bedna.cislo_bedny])

    def measurements(self, values, kind=TypZkouskyChoice.PROHYB_PO_TZ):
        self.kontrola.mereni.filter(typ_zkousky=kind).delete()
        for order, value in enumerate(values, 1):
            MereniBedny.objects.create(
                kontrola=self.kontrola, typ_zkousky=kind, hodnota=Decimal(value), poradi=order,
            )

    def choices(self, response):
        return [value for value, label in response.context['form'].fields['uvolneni'].choices]

    def assert_measurement_highlight(self, response, kind=None, state=''):
        highlighted = {
            row['typ']: row['stav_prohybu']
            for row in response.context['zkousky'] if row['stav_prohybu']
        }
        self.assertEqual(highlighted, {kind: state} if kind is not None else {})
        html = response.content.decode('utf-8')
        for candidate in ('nevyhovuje', 'odchylka'):
            self.assertEqual(
                html.count(f'class="list-group-item mereni-{candidate}"'),
                1 if state == candidate else 0,
            )

    def payload(self, response, status, **overrides):
        data = {
            'snapshot': response.context['snapshot'],
            'cistota': '--', 'ulozeni': '--', 'uvolneni': status,
        }
        data.update(overrides)
        return data

    def test_above_qs_limit_only_nonconformity_is_offered_and_prefilled(self):
        self.measurements(['0.6001', '0.7', '0.2'])
        response = self.client.get(self.url)
        self.assertEqual(self.choices(response), [UvolneniKontrolyChoice.NESHODA])
        self.assert_measurement_highlight(response, TypZkouskyChoice.PROHYB_PO_TZ, 'nevyhovuje')
        form = response.context['form']
        self.assertEqual(form['uvolneni'].value(), UvolneniKontrolyChoice.NESHODA)
        self.assertTrue(form['neshoda_krivost'].value())
        self.assertTrue(form.zobrazit_duvody_neshody)
        self.assertContains(response, 'Prohyb po TZ: počet hodnot nad QS limitem je 2')
        self.kontrola.refresh_from_db()
        self.assertEqual(self.kontrola.uvolneni, UvolneniKontrolyChoice.NEROZHODNUTO)
        self.assertFalse(self.kontrola.neshoda_krivost)

    def test_without_qs_limit_normal_limit_requires_nonconformity(self):
        self.customer.zkratka = 'EUR'
        self.customer.save(update_fields=['zkratka'])
        self.measurements(['0.6001', '0.7'])
        response = self.client.get(self.url)
        self.assertEqual(self.choices(response), [UvolneniKontrolyChoice.NESHODA])
        self.assertContains(response, 'počet hodnot nad běžným limitem je 2')

    def test_excess_over_normal_limit_allows_qs_or_nonconformity(self):
        # One value above QS is still within the allowed count of one.
        self.measurements(['0.4001', '0.6', '0.6001'])
        response = self.client.get(self.url)
        self.assertEqual(self.choices(response), [
            UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU, UvolneniKontrolyChoice.NESHODA,
        ])
        self.assertTrue(response.context['form']['neshoda_krivost'].value())
        self.assert_measurement_highlight(response, TypZkouskyChoice.PROHYB_PO_TZ, 'odchylka')

    def test_limits_and_allowed_count_are_inclusive(self):
        for values, expected in (
            (['0.4', '0.4', '0.4001'], UvolneniKontrolyChoice.values),
            (['0.6001'], UvolneniKontrolyChoice.values),
            (['0.6', '0.6'], [UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU, UvolneniKontrolyChoice.NESHODA]),
            (['0.6001', '0.6001'], [UvolneniKontrolyChoice.NESHODA]),
        ):
            with self.subTest(values=values):
                self.measurements(values)
                self.assertEqual(self.choices(self.client.get(self.url)), expected)

    def test_zero_allowed_count_is_enforced(self):
        self.customer.max_krivych_vrutu = 0
        self.customer.save(update_fields=['max_krivych_vrutu'])
        for value, expected in (
            ('0.4', UvolneniKontrolyChoice.values),
            ('0.4001', [UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU, UvolneniKontrolyChoice.NESHODA]),
            ('0.6001', [UvolneniKontrolyChoice.NESHODA]),
        ):
            with self.subTest(value=value):
                self.measurements([value])
                self.assertEqual(self.choices(self.client.get(self.url)), expected)

    def test_missing_count_or_unknown_customer_does_not_restrict_release(self):
        self.measurements(['100', '100'])
        for code, count in (('ROT', None), ('TST', 0)):
            with self.subTest(code=code, count=count):
                self.customer.zkratka = code
                self.customer.max_krivych_vrutu = count
                self.customer.save(update_fields=['zkratka', 'max_krivych_vrutu'])
                self.assertEqual(self.choices(self.client.get(self.url)), UvolneniKontrolyChoice.values)

    def test_no_measurements_or_only_rolling_does_not_restrict_release(self):
        self.assertEqual(self.choices(self.client.get(self.url)), UvolneniKontrolyChoice.values)
        self.measurements(['100', '100'], TypZkouskyChoice.PROHYB_PO_KOULENI)
        response = self.client.get(self.url)
        self.assertEqual(self.choices(response), UvolneniKontrolyChoice.values)
        self.assert_measurement_highlight(response)

    def test_rolling_cannot_override_heat_treatment(self):
        self.measurements(['0.7', '0.7'])
        self.measurements(['0.1'], TypZkouskyChoice.PROHYB_PO_KOULENI)
        self.assertEqual(self.choices(self.client.get(self.url)), [UvolneniKontrolyChoice.NESHODA])

    def test_straightening_replaces_heat_treatment_for_all_results(self):
        self.measurements(['0.7', '0.7'])
        for values, expected, state in (
            (['0.1'], UvolneniKontrolyChoice.values, ''),
            (['0.5', '0.5'], [UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU, UvolneniKontrolyChoice.NESHODA], 'odchylka'),
            (['0.7', '0.7'], [UvolneniKontrolyChoice.NESHODA], 'nevyhovuje'),
        ):
            with self.subTest(values=values):
                self.measurements(values, TypZkouskyChoice.PROHYB_PO_ROVNANI)
                response = self.client.get(self.url)
                self.assertEqual(self.choices(response), expected)
                self.assert_measurement_highlight(
                    response, TypZkouskyChoice.PROHYB_PO_ROVNANI if state else None, state,
                )
                if len(expected) < 4:
                    self.assertContains(response, 'Prohyb po rovnání: počet hodnot')

    def test_bad_straightening_overrides_good_heat_treatment_and_rolling(self):
        self.measurements(['0.1'])
        self.measurements(['0.1'], TypZkouskyChoice.PROHYB_PO_KOULENI)
        self.measurements(['0.7', '0.7'], TypZkouskyChoice.PROHYB_PO_ROVNANI)
        self.assertEqual(self.choices(self.client.get(self.url)), [UvolneniKontrolyChoice.NESHODA])

    def test_removing_all_straightening_values_restores_heat_treatment_rule(self):
        self.measurements(['0.7', '0.7'])
        self.measurements(['0.1'], TypZkouskyChoice.PROHYB_PO_ROVNANI)
        self.assertEqual(self.choices(self.client.get(self.url)), UvolneniKontrolyChoice.values)
        self.measurements([], TypZkouskyChoice.PROHYB_PO_ROVNANI)
        self.assertEqual(self.choices(self.client.get(self.url)), [UvolneniKontrolyChoice.NESHODA])

    def test_manual_counts_do_not_replace_measured_values(self):
        self.measurements(['0.7', '0.7'])
        self.kontrola.pocet_krivych_vrutu_prvni_mereni = 0
        self.kontrola.pocet_krivych_vrutu_druhe_mereni = 0
        self.kontrola.save()
        self.assertEqual(self.choices(self.client.get(self.url)), [UvolneniKontrolyChoice.NESHODA])

    def test_forged_release_status_is_rejected_without_saving(self):
        self.measurements(['0.7', '0.7'])
        response = self.client.get(self.url)
        history_count = self.kontrola.history.count()
        for status in (UvolneniKontrolyChoice.UVOLNENO, UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU, '--', ''):
            with self.subTest(status=status):
                result = self.client.post(self.url, self.payload(response, status, neshoda_krivost='on'))
                self.assertEqual(result.status_code, 200)
                self.assertIn('uvolneni', result.context['form'].errors)
                self.kontrola.refresh_from_db()
                self.assertEqual(self.kontrola.uvolneni, UvolneniKontrolyChoice.NEROZHODNUTO)
                self.assertEqual(self.kontrola.history.count(), history_count)

    def test_both_restricted_results_require_curvature_even_with_another_reason(self):
        for values, status in (
            (['0.7', '0.7'], UvolneniKontrolyChoice.NESHODA),
            (['0.5', '0.5'], UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU),
            (['0.5', '0.5'], UvolneniKontrolyChoice.NESHODA),
        ):
            with self.subTest(values=values, status=status):
                self.measurements(values)
                response = self.client.get(self.url)
                result = self.client.post(self.url, self.payload(response, status, neshoda_cistota='on'))
                self.assertEqual(result.status_code, 200)
                self.assertIn('neshoda_krivost', result.context['form'].errors)
                self.assertFalse(result.context['form']['neshoda_krivost'].value())

    def test_restricted_decisions_save_curvature_and_history(self):
        for values, status in (
            (['0.7', '0.7'], UvolneniKontrolyChoice.NESHODA),
            (['0.5', '0.5'], UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU),
            (['0.5', '0.5'], UvolneniKontrolyChoice.NESHODA),
        ):
            with self.subTest(values=values, status=status):
                self.measurements(values)
                response = self.client.get(self.url)
                result = self.client.post(self.url, self.payload(response, status, neshoda_krivost='on'))
                self.assertRedirects(result, self.url)
                self.kontrola.refresh_from_db()
                self.assertEqual(self.kontrola.uvolneni, status)
                self.assertTrue(self.kontrola.neshoda_krivost)
                self.assertTrue(self.kontrola.history.first().neshoda_krivost)
                self.assertEqual(self.kontrola.history.first().history_user, self.user)

    def test_qs_range_rejects_unconditional_release(self):
        self.measurements(['0.5', '0.5'])
        response = self.client.get(self.url)
        result = self.client.post(self.url, self.payload(
            response, UvolneniKontrolyChoice.UVOLNENO, neshoda_krivost='on',
        ))
        self.assertIn('uvolneni', result.context['form'].errors)

    def test_passing_straightening_allows_release_without_curvature(self):
        self.measurements(['0.7', '0.7'])
        self.measurements(['0.1'], TypZkouskyChoice.PROHYB_PO_ROVNANI)
        response = self.client.get(self.url)
        self.assertFalse(response.context['form']['neshoda_krivost'].value())
        result = self.client.post(self.url, self.payload(response, UvolneniKontrolyChoice.UVOLNENO))
        self.assertRedirects(result, self.url)
        self.kontrola.refresh_from_db()
        self.assertEqual(self.kontrola.uvolneni, UvolneniKontrolyChoice.UVOLNENO)
        self.assertFalse(self.kontrola.neshoda_krivost)

    def test_post_rechecks_measurements_changed_since_form_was_opened(self):
        self.measurements(['0.1'])
        response = self.client.get(self.url)
        self.measurements(['0.7', '0.7'])
        result = self.client.post(self.url, self.payload(response, UvolneniKontrolyChoice.UVOLNENO))
        self.assertIn('uvolneni', result.context['form'].errors)
        self.assertIn('neshoda_krivost', result.context['form'].errors)

    def test_prefill_replaces_old_release_only_in_form_until_saved(self):
        self.kontrola.uvolneni = UvolneniKontrolyChoice.UVOLNENO
        self.kontrola.save()
        self.measurements(['0.7', '0.7'])
        response = self.client.get(self.url)
        self.assertEqual(response.context['form']['uvolneni'].value(), UvolneniKontrolyChoice.NESHODA)
        self.kontrola.refresh_from_db()
        self.assertEqual(self.kontrola.uvolneni, UvolneniKontrolyChoice.UVOLNENO)

    def test_readonly_form_preserves_saved_decision_and_reasons(self):
        self.kontrola.uvolneni = UvolneniKontrolyChoice.UVOLNENO
        self.kontrola.save()
        self.measurements(['0.7', '0.7'])
        self.bedna.pozastaveno = True
        self.bedna.save(update_fields=['pozastaveno'])
        response = self.client.get(self.url)
        self.assertContains(response, '<fieldset disabled>')
        self.assertEqual(self.choices(response), UvolneniKontrolyChoice.values)
        self.assertEqual(response.context['form']['uvolneni'].value(), UvolneniKontrolyChoice.UVOLNENO)
        self.assertFalse(response.context['form']['neshoda_krivost'].value())

    def test_existing_allowed_nonconformity_is_preserved_in_qs_range(self):
        self.kontrola.uvolneni = UvolneniKontrolyChoice.NESHODA
        self.kontrola.neshoda_krivost = True
        self.kontrola.save()
        self.measurements(['0.5', '0.5'])
        response = self.client.get(self.url)
        self.assertEqual(response.context['form']['uvolneni'].value(), UvolneniKontrolyChoice.NESHODA)
