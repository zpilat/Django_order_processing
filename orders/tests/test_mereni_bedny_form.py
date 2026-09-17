from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from orders.choices import StavBednyChoice, TypZkouskyChoice, UvolneniKontrolyChoice
from orders.models import KontrolaBedny, MereniBedny
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class MereniBednyFormTests(KontrolaBednyTestBase):
    def setUp(self):
        self.user.user_permissions.add(Permission.objects.get(codename='mark_bedna_zkontrolovano'))
        self.client.force_login(self.user)
        self.url = self.url_for(TypZkouskyChoice.TVRDOST_POVRCHU)

    def url_for(self, kind):
        return reverse('bedna_mereni_zkousky', args=[self.bedna.cislo_bedny, kind])

    def create_measurement(self, *, kind=TypZkouskyChoice.TVRDOST_POVRCHU, order=1, value='580'):
        kontrola, _ = KontrolaBedny.objects.get_or_create(bedna=self.bedna)
        return MereniBedny.objects.create(
            kontrola=kontrola, typ_zkousky=kind, poradi=order,
            hodnota=Decimal(value), zmeril=self.user,
        )

    def payload(self, response, rows):
        data = {
            'snapshot': response.context['snapshot'],
            'mereni-TOTAL_FORMS': str(len(rows)),
            'mereni-INITIAL_FORMS': str(len(response.context['formset'].measurements)),
        }
        for index, row in enumerate(rows):
            data.update({f'mereni-{index}-{key}': str(value) for key, value in row.items()})
        return data

    def test_get_shows_requirement_and_descriptions_without_creating_control(self):
        predpis = self.bedna.zakazka.predpis
        predpis.povrch = '550–650 HV'
        predpis.popis_povrch = 'Zkouška na hlavě'
        predpis.popis_povrch_2 = 'Rozsah měření dle předpisu'
        predpis.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '550–650 HV')
        self.assertContains(response, 'Zkouška na hlavě')
        self.assertContains(response, 'Rozsah měření dle předpisu')
        self.assertEqual(len(response.context['formset'].forms), 3)
        self.assertFalse(KontrolaBedny.objects.exists())

    def test_each_type_has_its_own_form(self):
        for kind in TypZkouskyChoice:
            response = self.client.get(self.url_for(kind))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, kind.label)
        response = self.client.get(self.url_for(TypZkouskyChoice.PROHYB_PO_TZ))
        self.assertContains(response, 'Požadavek pro tuto zkoušku není v předpisu uveden.')

    def test_decimal_comma_multiple_rows_blanks_and_zero(self):
        response = self.client.get(self.url)
        result = self.client.post(self.url, self.payload(response, [
            {'hodnota': '580,25'}, {'hodnota': '592.1234'}, {'hodnota': ''}, {'hodnota': '0'},
        ]))
        self.assertRedirects(result, reverse('bedna_kontrola', args=[self.bedna.cislo_bedny]))
        measurements = list(MereniBedny.objects.order_by('poradi'))
        self.assertEqual([item.hodnota for item in measurements], [Decimal('580.25'), Decimal('592.1234'), Decimal('0')])
        self.assertEqual([item.poradi for item in measurements], [1, 2, 3])
        self.assertTrue(all(item.zmeril == self.user for item in measurements))
        self.assertEqual(measurements[0].history.first().history_user, self.user)
        self.assertEqual(KontrolaBedny.objects.get().history.first().history_user, self.user)
        self.assertEqual(KontrolaBedny.objects.get().uvolneni, UvolneniKontrolyChoice.NEROZHODNUTO)

    def test_all_blank_rows_do_not_create_control(self):
        response = self.client.get(self.url)
        result = self.client.post(self.url, self.payload(response, [{'hodnota': ''}] * 3))
        self.assertEqual(result.status_code, 302)
        self.assertFalse(KontrolaBedny.objects.exists())

    def test_edit_delete_and_append_preserve_order_other_tests_and_original_metadata(self):
        first = self.create_measurement()
        second = self.create_measurement(order=2, value='590')
        other = self.create_measurement(kind=TypZkouskyChoice.KRUT, value='12')
        original_date = first.zmereno_at
        editor = get_user_model().objects.create_user(username='druhy_kontrolor')
        editor.user_permissions.add(Permission.objects.get(codename='mark_bedna_zkontrolovano'))
        self.client.force_login(editor)
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['formset'].measurements), 2)
        result = self.client.post(self.url, self.payload(response, [
            {'id': first.pk, 'hodnota': '581'},
            {'id': second.pk, 'hodnota': '', 'DELETE': 'on'},
            {'hodnota': '595'},
        ]))
        self.assertEqual(result.status_code, 302)
        first.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(first.hodnota, Decimal('581'))
        self.assertEqual(first.zmeril, self.user)
        self.assertEqual(first.zmereno_at, original_date)
        self.assertEqual(first.history.first().history_user, editor)
        self.assertEqual(other.hodnota, Decimal('12'))
        self.assertEqual(other.history.count(), 1)
        self.assertFalse(MereniBedny.objects.filter(pk=second.pk).exists())
        self.assertEqual(MereniBedny.history.filter(id=second.pk).first().history_type, '-')
        new = MereniBedny.objects.get(typ_zkousky=TypZkouskyChoice.TVRDOST_POVRCHU, poradi=3)
        self.assertEqual(new.zmeril, editor)

    def test_unchanged_submission_does_not_add_history(self):
        item = self.create_measurement()
        response = self.client.get(self.url)
        self.assertIn('value="580"', str(response.context['formset'].forms[0]['hodnota']))
        result = self.client.post(self.url, self.payload(response, [{'id': item.pk, 'hodnota': '580'}]))
        self.assertEqual(result.status_code, 302)
        self.assertEqual(item.history.count(), 1)

    def test_edit_shows_values_without_trailing_zeros_and_preserves_precision(self):
        values = [('12.5000', '12,5'), ('592.1234', '592,1234'), ('0.0000', '0'), ('100.0100', '100,01')]
        items = [self.create_measurement(order=index, value=value) for index, (value, _) in enumerate(values, 1)]
        response = self.client.get(self.url)
        forms = response.context['formset'].forms
        for form, (_, displayed) in zip(forms, values):
            self.assertIn(f'value="{displayed}"', str(form['hodnota']))
        self.assertNotIn('value=', str(forms[len(items)]['hodnota']))
        result = self.client.post(self.url, self.payload(response, [
            {'id': item.pk, 'hodnota': displayed} for item, (_, displayed) in zip(items, values)
        ]))
        self.assertEqual(result.status_code, 302)
        for item, (value, _) in zip(items, values):
            item.refresh_from_db()
            self.assertEqual(item.hodnota, Decimal(value))
            self.assertEqual(item.history.count(), 1)

    def test_invalid_number_or_precision_saves_nothing_and_preserves_input(self):
        for value in ['abc', '580.12345', '100000000']:
            response = self.client.get(self.url)
            result = self.client.post(self.url, self.payload(response, [{'hodnota': '580'}, {'hodnota': value}]))
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.context['formset'].errors[1])
            self.assertContains(result, value)
            self.assertFalse(MereniBedny.objects.exists())
            self.assertFalse(KontrolaBedny.objects.exists())

    def test_foreign_test_id_cannot_be_modified_or_deleted(self):
        item = self.create_measurement(kind=TypZkouskyChoice.KRUT, value='12')
        for extra in [{}, {'DELETE': 'on'}]:
            response = self.client.get(self.url)
            result = self.client.post(self.url, self.payload(response, [
                {'id': item.pk, 'hodnota': '999', **extra},
            ]))
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.context['formset'].non_form_errors())
            item.refresh_from_db()
            self.assertEqual(item.hodnota, Decimal('12'))

    def test_omitted_or_duplicate_existing_ids_are_rejected(self):
        item = self.create_measurement()
        for rows in [[], [{'id': item.pk, 'hodnota': '581'}, {'id': item.pk, 'hodnota': '582'}]]:
            response = self.client.get(self.url)
            result = self.client.post(self.url, self.payload(response, rows))
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.context['formset'].non_form_errors())
            item.refresh_from_db()
            self.assertEqual(item.hodnota, Decimal('580'))

    def test_stale_form_cannot_overwrite_a_concurrent_edit(self):
        item = self.create_measurement()
        response = self.client.get(self.url)
        item.hodnota = Decimal('599')
        item.save()
        result = self.client.post(self.url, self.payload(response, [{'id': item.pk, 'hodnota': '581'}]))
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, 'Měření mezitím změnil jiný uživatel.')
        item.refresh_from_db()
        self.assertEqual(item.hodnota, Decimal('599'))

    def test_stale_empty_form_cannot_append_after_concurrent_addition(self):
        response = self.client.get(self.url)
        self.create_measurement()
        result = self.client.post(self.url, self.payload(response, [{'hodnota': '581'}]))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(MereniBedny.objects.count(), 1)

    def test_missing_management_or_snapshot_is_rejected(self):
        response = self.client.get(self.url)
        for data in [{}, {'mereni-TOTAL_FORMS': '1', 'mereni-INITIAL_FORMS': '0', 'mereni-0-hodnota': '580'}]:
            result = self.client.post(self.url, data)
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.context['formset'].non_form_errors())
            self.assertFalse(MereniBedny.objects.exists())

    def test_login_and_permission_required_for_get_and_post(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        ordinary = get_user_model().objects.create_user(username='bez_opravneni')
        self.client.force_login(ordinary)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {}).status_code, 403)

    def test_paused_and_dispatched_bedna_require_special_permissions(self):
        self.bedna.pozastaveno = True
        self.bedna.save()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {}).status_code, 403)
        self.user.user_permissions.add(Permission.objects.get(codename='change_pozastavena_bedna'))
        self.assertEqual(self.client.get(self.url).status_code, 200)
        # QuerySet update isolates the permissions check from manufacturing prerequisites.
        type(self.bedna).objects.filter(pk=self.bedna.pk).update(
            pozastaveno=False, stav_bedny=StavBednyChoice.EXPEDOVANO,
            hmotnost=1, tara=1, mnozstvi=1,
        )
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.user.user_permissions.add(Permission.objects.get(codename='change_expedovana_bedna'))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_unknown_type_is_not_found(self):
        self.assertEqual(self.client.get(self.url_for('unknown')).status_code, 404)

    def test_detail_shows_values_and_links_without_row_numbers(self):
        self.create_measurement(value='580.25')
        self.create_measurement(order=3, value='590')
        response = self.client.get(reverse('bedna_kontrola', args=[self.bedna.cislo_bedny]))
        self.assertContains(response, self.url)
        self.assertContains(response, '>580,25</span>')
        self.assertContains(response, '>590</span>')
        self.assertNotContains(response, '1: 580,25')
        self.assertNotContains(response, '2: 590')
        self.assertNotContains(response, '3: 590')

    def test_admin_detail_links_to_measurements(self):
        admin_user = get_user_model().objects.create_user(
            username='admin_mereni', is_staff=True, is_superuser=True,
        )
        self.client.force_login(admin_user)
        response = self.client.get(reverse('admin:orders_bedna_change', args=[self.bedna.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('bedna_kontrola', args=[self.bedna.cislo_bedny]))
