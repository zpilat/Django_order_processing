from decimal import Decimal
from unittest.mock import PropertyMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from orders.choices import StavBednyChoice, TypZkouskyChoice, UvolneniKontrolyChoice, VysledekKontrolyChoice
from orders.models import Bedna, KontrolaBedny, MereniBedny
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class KontrolaBednyFormTests(KontrolaBednyTestBase):
    def setUp(self):
        self.user.user_permissions.add(
            Permission.objects.get(codename='mark_bedna_zkontrolovano'),
            Permission.objects.get(codename='view_bedna'),
        )
        self.client.force_login(self.user)
        self.url = reverse('bedna_kontrola', args=[self.bedna.cislo_bedny])

    def payload(self, response, **overrides):
        form = response.context['form']
        data = {name: '' if form[name].value() is None else form[name].value() for name in form.fields}
        data['snapshot'] = response.context['snapshot']
        data.update(overrides)
        return data

    def test_scan_button_follows_scanning_and_has_no_measurement_overview(self):
        response = self.client.get(reverse('bedna_scan', args=[self.bedna.cislo_bedny]))
        self.assertContains(response, self.url)
        self.assertNotContains(response, 'id="mereni-bedny"')
        self.assertNotContains(response, reverse('bedna_mereni_zkousky', args=[self.bedna.cislo_bedny, TypZkouskyChoice.OHYB]))
        html = response.content.decode('utf-8')
        self.assertLess(html.index(reverse('bedna_skener_ctecka')), html.index(self.url))

    def test_get_has_defaults_measurements_before_form_and_does_not_create_control(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'orders/bedna_kontrola.html')
        self.assertEqual(response.context['form']['uvolneni'].value(), UvolneniKontrolyChoice.NEROZHODNUTO)
        self.assertFalse(KontrolaBedny.objects.exists())
        html = response.content.decode('utf-8')
        header = html.split('<section class="card rounded-2">', 1)[1].split('</section>', 1)[0]
        self.assertIn(f'Bedna {self.bedna.cislo_bedny} · 1/1', header)
        self.assertIn(self.bedna.zakazka.popis, header)
        self.assertLess(html.index('id="mereni-bedny"'), html.index('<form method="post" novalidate>'))
        for kind in TypZkouskyChoice:
            measurement_url = reverse('bedna_mereni_zkousky', args=[self.bedna.cislo_bedny, kind])
            self.assertContains(response, measurement_url)

    def test_control_overview_shows_customer_bending_limits(self):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        for code, length, normal, release in (
            ('EUR', '100', '0,6', None), ('ROT', '123.4', '0,4936', '0,7404'),
            ('SWG', '300', '1,8', None), ('SWG', '400', '1,8', None),
            ('TST', '100', None, None),
        ):
            with self.subTest(customer=code, length=length):
                customer.zkratka = code
                customer.save(update_fields=['zkratka'])
                self.bedna.zakazka.delka = Decimal(length)
                self.bedna.zakazka.save(update_fields=['delka'])
                response = self.client.get(self.url)
                if normal is None:
                    self.assertNotContains(response, 'max.')
                else:
                    self.assertContains(response, f'max. {normal} mm', count=3)
                if release is None:
                    self.assertNotContains(response, 'QS max.')
                else:
                    self.assertContains(response, f'QS max. {release} mm', count=3)
                self.assertNotContains(response, 'None')

    def test_control_overview_colors_all_bending_types_using_customer_limits(self):
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna)
        for kind in (
            TypZkouskyChoice.PROHYB_PO_TZ, TypZkouskyChoice.PROHYB_PO_KOULENI,
            TypZkouskyChoice.PROHYB_PO_ROVNANI,
        ):
            for order, value in enumerate(('0.4', '0.4001', '0.6', '0.6001'), start=1):
                MereniBedny.objects.create(
                    kontrola=kontrola, typ_zkousky=kind, hodnota=Decimal(value),
                    poradi=order, zmeril=self.user,
                )
        MereniBedny.objects.create(
            kontrola=kontrola, typ_zkousky=TypZkouskyChoice.OHYB,
            hodnota=Decimal('0.6001'), poradi=1, zmeril=self.user,
        )
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        for code, states in (
            ('ROT', ('', 'odchylka', 'odchylka', 'nevyhovuje')),
            ('EUR', ('', '', '', 'nevyhovuje')),
            ('TST', ('', '', '', '')),
        ):
            with self.subTest(customer=code):
                customer.zkratka = code
                customer.save(update_fields=['zkratka'])
                response = self.client.get(self.url)
                for value, state in zip(('0,4', '0,4001', '0,6', '0,6001'), states):
                    suffix = f' prohyb-{state}' if state else ''
                    expected_count = 4 if value == '0,6001' and not state else 3
                    self.assertContains(response, f'<span class="badge text-bg-light border me-1 mb-1{suffix}">{value}</span>', count=expected_count)
                self.assertContains(response, '<span class="badge text-bg-light border me-1 mb-1">0,6001</span>')
                html = response.content.decode('utf-8')
                self.assertEqual(html.count(' prohyb-odchylka">'), states.count('odchylka') * 3)
                self.assertEqual(html.count(' prohyb-nevyhovuje">'), states.count('nevyhovuje') * 3)

    def test_other_customers_hide_hardness_for_subsequent_containers(self):
        next_bedna = Bedna.objects.create(zakazka=self.bedna.zakazka)
        response = self.client.get(reverse('bedna_kontrola', args=[next_bedna.cislo_bedny]))

        for kind in TypZkouskyChoice:
            measurement_url = reverse('bedna_mereni_zkousky', args=[next_bedna.cislo_bedny, kind])
            if kind in (TypZkouskyChoice.TVRDOST_POVRCHU, TypZkouskyChoice.TVRDOST_JADRA):
                self.assertNotContains(response, measurement_url)
                self.assertNotContains(response, kind.label)
            else:
                self.assertContains(response, measurement_url)

    def test_ssh_and_rot_hardness_tests_are_shown_only_for_selected_containers(self):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        middle = Bedna.objects.create(zakazka=self.bedna.zakazka)
        last = Bedna.objects.create(zakazka=self.bedna.zakazka)

        for code in ('SSH', 'ROT'):
            customer.zkratka = code
            customer.save(update_fields=['zkratka'])
            for bedna, selected in [(self.bedna, True), (middle, False), (last, True)]:
                with self.subTest(customer=code, container=bedna.cislo_bedny):
                    response = self.client.get(reverse('bedna_kontrola', args=[bedna.cislo_bedny]))
                    self.assertEqual(response.status_code, 200)
                    for kind in TypZkouskyChoice:
                        measurement_url = reverse('bedna_mereni_zkousky', args=[bedna.cislo_bedny, kind])
                        if not selected and kind in (TypZkouskyChoice.TVRDOST_POVRCHU, TypZkouskyChoice.TVRDOST_JADRA):
                            self.assertNotContains(response, measurement_url)
                            self.assertNotContains(response, kind.label)
                        else:
                            self.assertContains(response, measurement_url)

    def test_eur_full_thread_shows_hardness_for_all_containers(self):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        customer.zkratka = 'EUR'
        customer.save(update_fields=['zkratka'])
        bedny = [self.bedna] + [Bedna.objects.create(zakazka=self.bedna.zakazka) for _ in range(2)]
        hardness = (TypZkouskyChoice.TVRDOST_POVRCHU, TypZkouskyChoice.TVRDOST_JADRA)
        for bedna in bedny:
            kontrola = KontrolaBedny.objects.create(bedna=bedna)
            for kind, value in zip(hardness, ('580.25', '320.75')):
                MereniBedny.objects.create(
                    kontrola=kontrola, typ_zkousky=kind, hodnota=Decimal(value),
                    poradi=1, zmeril=self.user,
                )
        for full_thread in (False, True, False):
            self.bedna.zakazka.celozavit = full_thread
            self.bedna.zakazka.save(update_fields=['celozavit'])
            for index, bedna in enumerate(bedny):
                with self.subTest(full_thread=full_thread, container=bedna.cislo_bedny):
                    response = self.client.get(reverse('bedna_kontrola', args=[bedna.cislo_bedny]))
                    self.assertEqual(response.status_code, 200)
                    visible = full_thread or index == 0
                    html = response.content.decode('utf-8')
                    for kind, value in zip(hardness, ('580,25', '320,75')):
                        self.assertEqual(kind.label in html, visible)
                        self.assertEqual(value in html, visible)
                        self.assertEqual(reverse('bedna_mereni_zkousky', args=[bedna.cislo_bedny, kind]) in html, visible)
        self.assertEqual(MereniBedny.objects.count(), 6)

    def test_hardness_visibility_uses_property_for_other_customers(self):
        with patch.object(Bedna, 'bedna_k_mereni_tvrdosti_a_povrchu', new_callable=PropertyMock, return_value=True):
            response = self.client.get(self.url)

        for kind in (TypZkouskyChoice.TVRDOST_POVRCHU, TypZkouskyChoice.TVRDOST_JADRA):
            self.assertContains(response, kind.label)
            self.assertContains(response, reverse('bedna_mereni_zkousky', args=[self.bedna.cislo_bedny, kind]))

    def test_next_bedna_button_opens_scanner_in_control_mode(self):
        response = self.client.get(self.url)

        scanner_url = f"{reverse('bedna_skener_ctecka')}?cil=kontrola"
        self.assertContains(response, 'Další bedna ke kontrole')
        self.assertContains(response, scanner_url)
        html = response.content.decode('utf-8')
        self.assertLess(html.index(scanner_url), html.index('id="mereni-bedny"'))

    def test_mark_checked_button_is_immediately_before_back_to_detail(self):
        self.bedna.stav_bedny = StavBednyChoice.ZAKALENO
        self.bedna.hmotnost = Decimal('10')
        self.bedna.tara = Decimal('1')
        self.bedna.mnozstvi = 100
        self.bedna.save(update_fields=['stav_bedny', 'hmotnost', 'tara', 'mnozstvi'])
        response = self.client.get(self.url)

        mark_url = reverse('bedna_scan_zkontrolovano', args=[self.bedna.cislo_bedny])
        detail_url = reverse('bedna_scan', args=[self.bedna.cislo_bedny])
        html = response.content.decode('utf-8')
        mark_link = f'href="{mark_url}"'
        detail_link = f'href="{detail_url}"'
        self.assertLess(html.index('Výstupní kontrola'), html.index(mark_link))
        self.assertLess(html.index(mark_link), html.index(detail_link))

    def test_first_save_creates_control_and_history(self):
        response = self.client.get(self.url)
        result = self.client.post(self.url, self.payload(
            response, cistota=VysledekKontrolyChoice.OK, ulozeni=VysledekKontrolyChoice.NOK,
            uvolneni=UvolneniKontrolyChoice.POZASTAVENO, poznamka='Zkontrolovat uložení',
        ))
        self.assertRedirects(result, self.url)
        kontrola = KontrolaBedny.objects.get(bedna=self.bedna)
        self.assertEqual(kontrola.cistota, VysledekKontrolyChoice.OK)
        self.assertEqual(kontrola.ulozeni, VysledekKontrolyChoice.NOK)
        self.assertEqual(kontrola.uvolneni, UvolneniKontrolyChoice.POZASTAVENO)
        self.assertEqual(kontrola.poznamka, 'Zkontrolovat uložení')
        self.assertEqual(kontrola.history.first().history_user, self.user)
        self.assertIsNone(kontrola.uvolnil)
        self.bedna.refresh_from_db()
        self.assertFalse(self.bedna.pozastaveno)

    def test_bent_screw_inputs_are_in_output_control_with_customer_sample_size(self):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        for total, label in ((25, '25'), (50, '50'), (None, '—')):
            with self.subTest(total=total):
                customer.pocet_vrutu_pro_kontrolu_prohybu = total
                customer.save(update_fields=['pocet_vrutu_pro_kontrolu_prohybu'])
                response = self.client.get(self.url)
                self.assertContains(response, f'<span class="input-group-text">z {label} ks</span>', count=2)
                html = response.content.decode('utf-8')
                before_form, form_html = html.split('<form method="post" novalidate>', 1)
                for name in ('pocet_krivych_vrutu_prvni_mereni', 'pocet_krivych_vrutu_druhe_mereni'):
                    self.assertNotIn(f'name="{name}"', before_form)
                    self.assertIn(f'name="{name}"', form_html)
                    model_field = KontrolaBedny._meta.get_field(name)
                    self.assertEqual(response.context['form'].fields[name].label, model_field.verbose_name)
                    self.assertEqual(response.context['form'].fields[name].help_text, model_field.help_text)
        self.assertFalse(KontrolaBedny.objects.exists())

    def test_bent_screw_counts_save_edit_and_clear_independently_with_history(self):
        for first, second in ((2, 0), (None, 1), (0, None), (None, None)):
            with self.subTest(first=first, second=second):
                response = self.client.get(self.url)
                result = self.client.post(self.url, self.payload(
                    response,
                    pocet_krivych_vrutu_prvni_mereni='' if first is None else first,
                    pocet_krivych_vrutu_druhe_mereni='' if second is None else second,
                ))
                self.assertRedirects(result, self.url)
                kontrola = KontrolaBedny.objects.get(bedna=self.bedna)
                self.assertEqual(kontrola.pocet_krivych_vrutu_prvni_mereni, first)
                self.assertEqual(kontrola.pocet_krivych_vrutu_druhe_mereni, second)
                self.assertEqual(kontrola.history.first().pocet_krivych_vrutu_prvni_mereni, first)
                self.assertEqual(kontrola.history.first().pocet_krivych_vrutu_druhe_mereni, second)
                self.assertEqual(kontrola.history.first().history_user, self.user)
                response = self.client.get(self.url)
                self.assertEqual(response.context['form']['pocet_krivych_vrutu_prvni_mereni'].value(), first)
                self.assertEqual(response.context['form']['pocet_krivych_vrutu_druhe_mereni'].value(), second)
        self.assertEqual(kontrola.history.count(), 4)
        self.assertFalse(MereniBedny.objects.exists())

    def test_invalid_bent_screw_count_saves_nothing_and_preserves_input(self):
        for name in ('pocet_krivych_vrutu_prvni_mereni', 'pocet_krivych_vrutu_druhe_mereni'):
            for value in ('-1', '1.5', 'abc'):
                with self.subTest(field=name, value=value):
                    response = self.client.get(self.url)
                    result = self.client.post(self.url, self.payload(response, **{name: value}))
                    self.assertEqual(result.status_code, 200)
                    self.assertIn(name, result.context['form'].errors)
                    self.assertEqual(result.context['form'][name].value(), value)
                    self.assertFalse(KontrolaBedny.objects.exists())

    def test_concurrent_bent_screw_count_edit_cannot_be_overwritten(self):
        kontrola = KontrolaBedny.objects.create(
            bedna=self.bedna, pocet_krivych_vrutu_prvni_mereni=0, pocet_krivych_vrutu_druhe_mereni=0,
        )
        for name in ('pocet_krivych_vrutu_prvni_mereni', 'pocet_krivych_vrutu_druhe_mereni'):
            with self.subTest(field=name):
                response = self.client.get(self.url)
                setattr(kontrola, name, 3)
                kontrola.save()
                history_count = kontrola.history.count()
                result = self.client.post(self.url, self.payload(response, **{name: 5}))
                self.assertEqual(result.status_code, 200)
                self.assertTrue(result.context['form'].non_field_errors())
                self.assertEqual(result.context['form'][name].value(), '5')
                kontrola.refresh_from_db()
                self.assertEqual(getattr(kontrola, name), 3)
                self.assertEqual(kontrola.history.count(), history_count)

    def test_explicit_save_of_defaults_creates_control(self):
        response = self.client.get(self.url)
        self.assertEqual(self.client.post(self.url, self.payload(response)).status_code, 302)
        self.assertEqual(KontrolaBedny.objects.filter(bedna=self.bedna).count(), 1)

    def test_reuses_control_created_by_measurement_and_preserves_measurements(self):
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna)
        item = MereniBedny.objects.create(
            kontrola=kontrola, typ_zkousky=TypZkouskyChoice.KRUT,
            hodnota=Decimal('12.5'), poradi=1, zmeril=self.user,
        )
        response = self.client.get(self.url)
        self.assertContains(response, '>12,5</span>')
        result = self.client.post(self.url, self.payload(response, cistota=VysledekKontrolyChoice.OK))
        self.assertEqual(result.status_code, 302)
        self.assertEqual(KontrolaBedny.objects.count(), 1)
        item.refresh_from_db()
        self.assertEqual(item.kontrola_id, kontrola.pk)
        self.assertEqual(item.hodnota, Decimal('12.5'))
        self.assertEqual(item.history.count(), 1)

    def test_release_metadata_is_automatic_and_preserved_on_other_edits(self):
        response = self.client.get(self.url)
        self.client.post(self.url, self.payload(
            response, uvolneni=UvolneniKontrolyChoice.UVOLNENO,
            uvolnil='999', uvolneno_at='2000-01-01',
        ))
        kontrola = KontrolaBedny.objects.get()
        self.assertEqual(kontrola.uvolnil, self.user)
        self.assertIsNotNone(kontrola.uvolneno_at)
        release_date = kontrola.uvolneno_at
        response = self.client.get(self.url)
        self.client.post(self.url, self.payload(response, poznamka='Doplněná poznámka'))
        kontrola.refresh_from_db()
        self.assertEqual(kontrola.uvolneno_at, release_date)
        self.assertEqual(kontrola.uvolnil, self.user)
        for status in [UvolneniKontrolyChoice.POZASTAVENO, UvolneniKontrolyChoice.NEROZHODNUTO]:
            response = self.client.get(self.url)
            self.client.post(self.url, self.payload(response, uvolneni=status))
            kontrola.refresh_from_db()
            self.assertIsNone(kontrola.uvolnil)
            self.assertIsNone(kontrola.uvolneno_at)

    def test_unchanged_save_does_not_add_history(self):
        kontrola = KontrolaBedny.objects.create(
            bedna=self.bedna, pocet_krivych_vrutu_prvni_mereni=0, pocet_krivych_vrutu_druhe_mereni=2,
        )
        response = self.client.get(self.url)
        self.assertEqual(self.client.post(self.url, self.payload(response)).status_code, 302)
        self.assertEqual(kontrola.history.count(), 1)

    def test_invalid_choice_saves_nothing(self):
        response = self.client.get(self.url)
        result = self.client.post(self.url, self.payload(response, uvolneni='DZ'))
        self.assertEqual(result.status_code, 200)
        self.assertIn('uvolneni', result.context['form'].errors)
        self.assertFalse(KontrolaBedny.objects.exists())

    def test_concurrent_edit_and_creation_are_rejected(self):
        response = self.client.get(self.url)
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna, poznamka='První kontrolor')
        result = self.client.post(self.url, self.payload(response, poznamka='Druhý kontrolor'))
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, 'Kontrolu mezitím změnil jiný uživatel.')
        kontrola.refresh_from_db()
        self.assertEqual(kontrola.poznamka, 'První kontrolor')
        response = self.client.get(self.url)
        kontrola.poznamka = 'Aktuální poznámka'
        kontrola.save()
        self.client.post(self.url, self.payload(response, poznamka='Zastaralá poznámka'))
        kontrola.refresh_from_db()
        self.assertEqual(kontrola.poznamka, 'Aktuální poznámka')

    def test_view_only_user_sees_disabled_form_and_cannot_post(self):
        reader = get_user_model().objects.create_user(username='ctenar_kontroly')
        reader.user_permissions.add(Permission.objects.get(codename='view_bedna'))
        self.client.force_login(reader)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<fieldset disabled>')
        self.assertNotContains(response, 'Zadat / upravit hodnoty')
        self.assertNotContains(response, reverse('bedna_scan_zkontrolovano', args=[self.bedna.cislo_bedny]))
        self.assertEqual(self.client.post(self.url, self.payload(response)).status_code, 403)
        self.assertFalse(KontrolaBedny.objects.exists())

    def test_paused_bedna_can_be_viewed_but_not_edited_without_special_permission(self):
        self.bedna.pozastaveno = True
        self.bedna.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<fieldset disabled>')
        self.assertNotContains(response, reverse('bedna_scan_zkontrolovano', args=[self.bedna.cislo_bedny]))
        self.assertEqual(self.client.post(self.url, self.payload(response)).status_code, 403)
        self.user.user_permissions.add(Permission.objects.get(codename='change_pozastavena_bedna'))
        response = self.client.get(self.url)
        self.assertEqual(self.client.post(self.url, self.payload(response)).status_code, 302)

    def test_login_and_permissions_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        user = get_user_model().objects.create_user(username='bez_kontroly')
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {}).status_code, 403)
        response = self.client.get(reverse('bedna_scan', args=[self.bedna.cislo_bedny]))
        self.assertNotContains(response, self.url)
