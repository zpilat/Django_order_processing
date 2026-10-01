from datetime import timedelta
from decimal import Decimal
from unittest.mock import PropertyMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django import forms
from django.urls import reverse
from django.utils import timezone

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
        data = {}
        for name, field in form.fields.items():
            value = form[name].value()
            if isinstance(field.widget, forms.CheckboxInput):
                if value:
                    data[name] = 'on'
            else:
                data[name] = '' if value is None else value
        data['snapshot'] = response.context['snapshot']
        data.update(overrides)
        return data

    def measurement_html(self, response):
        return response.content.decode('utf-8').split('id="mereni-bedny">', 1)[1].split('</section>', 1)[0]

    def test_nonconformity_reasons_render_only_when_relevant(self):
        response = self.client.get(self.url)
        self.assertFalse(response.context['form'].zobrazit_duvody_neshody)
        self.assertContains(response, 'id="duvody-neshody" class="mb-3 col-12 d-none"')
        for name in KontrolaBedny.NESHODA_FIELDS:
            self.assertContains(response, f'name="{name}"', count=1)

        for status, selected in (
            (UvolneniKontrolyChoice.NESHODA, False),
            (UvolneniKontrolyChoice.UVOLNENO, True),
        ):
            with self.subTest(status=status):
                KontrolaBedny.objects.update_or_create(
                    bedna=self.bedna,
                    defaults={'uvolneni': status, 'neshoda_cistota': selected},
                )
                response = self.client.get(self.url)
                self.assertTrue(response.context['form'].zobrazit_duvody_neshody)
                self.assertContains(response, 'id="duvody-neshody" class="mb-3 col-12"')

    def test_layer_nonconformity_reason_is_saved_in_history(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'name="neshoda_vrstva"')
        result = self.client.post(self.url, self.payload(
            response, uvolneni=UvolneniKontrolyChoice.NESHODA, neshoda_vrstva='on',
        ))
        self.assertRedirects(result, self.url)
        kontrola = KontrolaBedny.objects.get(bedna=self.bedna)
        self.assertTrue(kontrola.neshoda_vrstva)
        self.assertTrue(kontrola.history.first().neshoda_vrstva)

    def test_layer_measurement_and_requirements_appear_in_control_overview(self):
        predpis = self.bedna.zakazka.predpis
        predpis.vrstva = '7–10 µm'
        predpis.vrstva_2 = '15–20 µm'
        predpis.popis_vrstva = 'Místo měření'
        predpis.popis_vrstva_2 = 'Druhý popis vrstvy'
        predpis.save(update_fields=['vrstva', 'vrstva_2', 'popis_vrstva', 'popis_vrstva_2'])
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna)
        MereniBedny.objects.create(
            kontrola=kontrola, typ_zkousky=TypZkouskyChoice.VRSTVA,
            hodnota=Decimal('8.5'), poradi=1, zmeril=self.user,
        )

        response = self.client.get(self.url)
        section = self.measurement_html(response)
        self.assertIn('Vrstva', section)
        self.assertIn('7–10 µm', section)
        self.assertIn('15–20 µm', section)
        self.assertIn('<span class="fw-normal">· 7–10 µm 15–20 µm</span>', section)
        self.assertIn('8,5', section)
        self.assertNotIn('Místo měření', section)
        self.assertNotIn('Druhý popis vrstvy', section)

    def test_multiple_nonconformity_reasons_save_edit_and_history(self):
        response = self.client.get(self.url)
        result = self.client.post(self.url, self.payload(
            response,
            uvolneni=UvolneniKontrolyChoice.NESHODA,
            neshoda_krut_nizky='on', neshoda_krivost='on', neshoda_jine='on',
            poznamka='Jiné: poškozený závit',
        ))
        self.assertRedirects(result, self.url)
        kontrola = KontrolaBedny.objects.get(bedna=self.bedna)
        self.assertTrue(kontrola.neshoda_krut_nizky)
        self.assertTrue(kontrola.neshoda_krivost)
        self.assertTrue(kontrola.neshoda_jine)
        self.assertFalse(kontrola.neshoda_cistota)
        self.assertEqual(kontrola.poznamka, 'Jiné: poškozený závit')
        self.assertTrue(kontrola.history.first().neshoda_jine)
        self.assertEqual(kontrola.history.first().history_user, self.user)

        response = self.client.get(self.url)
        self.assertTrue(response.context['form'].zobrazit_duvody_neshody)
        result = self.client.post(self.url, self.payload(
            response, uvolneni=UvolneniKontrolyChoice.UVOLNENO,
            neshoda_krut_nizky='', neshoda_jine='',
        ))
        self.assertRedirects(result, self.url)
        kontrola.refresh_from_db()
        self.assertFalse(kontrola.neshoda_krut_nizky)
        self.assertFalse(kontrola.neshoda_jine)
        self.assertTrue(kontrola.neshoda_krivost)
        self.assertTrue(self.client.get(self.url).context['form'].zobrazit_duvody_neshody)

    def test_nonconformity_requires_a_reason_but_other_statuses_do_not(self):
        response = self.client.get(self.url)
        result = self.client.post(self.url, self.payload(
            response, uvolneni=UvolneniKontrolyChoice.NESHODA,
        ))
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, 'Při neshodě vyberte alespoň jeden důvod neshody.')
        self.assertContains(result, 'Kontrolu bedny se nepodařilo uložit. Příčinu najdete ve formuláři Výstupní kontrola.', count=1)
        html = result.content.decode('utf-8')
        self.assertLess(html.index('Kontrolu bedny se nepodařilo uložit.'), html.index('<form method="post" novalidate>'))
        self.assertTrue(result.context['form'].zobrazit_duvody_neshody)
        self.assertFalse(KontrolaBedny.objects.exists())

        response = self.client.get(self.url)
        self.assertRedirects(self.client.post(self.url, self.payload(
            response, uvolneni=UvolneniKontrolyChoice.NESHODA, neshoda_cistota='on',
        )), self.url)
        response = self.client.get(self.url)
        result = self.client.post(self.url, self.payload(response, neshoda_cistota=''))
        self.assertEqual(result.status_code, 200)
        self.assertIn('uvolneni', result.context['form'].errors)
        kontrola = KontrolaBedny.objects.get(bedna=self.bedna)
        self.assertTrue(kontrola.neshoda_cistota)

        response = self.client.get(self.url)
        self.assertRedirects(self.client.post(self.url, self.payload(
            response, uvolneni=UvolneniKontrolyChoice.UVOLNENO,
            neshoda_cistota='',
        )), self.url)
        kontrola.refresh_from_db()
        self.assertFalse(kontrola.neshoda_cistota)

    def test_other_nonconformity_reason_requires_nonblank_note(self):
        for note in ('', ' \t\n '):
            with self.subTest(note=note):
                response = self.client.get(self.url)
                result = self.client.post(self.url, self.payload(
                    response, uvolneni=UvolneniKontrolyChoice.NESHODA,
                    neshoda_jine='on', poznamka=note,
                ))
                self.assertEqual(result.status_code, 200)
                self.assertIn('poznamka', result.context['form'].errors)
                self.assertNotIn('uvolneni', result.context['form'].errors)
                self.assertTrue(result.context['form']['neshoda_jine'].value())
                self.assertTrue(result.context['form'].zobrazit_duvody_neshody)
                self.assertFalse(KontrolaBedny.objects.exists())

        response = self.client.get(self.url)
        result = self.client.post(self.url, self.payload(
            response, uvolneni=UvolneniKontrolyChoice.NESHODA,
            neshoda_jine='on', poznamka='Poškozený závit',
        ))
        self.assertRedirects(result, self.url)
        kontrola = KontrolaBedny.objects.get(bedna=self.bedna)
        self.assertTrue(kontrola.neshoda_jine)
        self.assertEqual(kontrola.poznamka, 'Poškozený závit')

    def test_other_reason_note_on_edit_and_after_status_change(self):
        kontrola = KontrolaBedny.objects.create(
            bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
            neshoda_jine=True, poznamka='Původní důvod',
        )
        for status in (UvolneniKontrolyChoice.NESHODA, UvolneniKontrolyChoice.UVOLNENO):
            with self.subTest(status=status):
                response = self.client.get(self.url)
                result = self.client.post(self.url, self.payload(
                    response, uvolneni=status, poznamka='',
                ))
                self.assertEqual(result.status_code, 200)
                self.assertIn('poznamka', result.context['form'].errors)
                kontrola.refresh_from_db()
                self.assertEqual(kontrola.uvolneni, UvolneniKontrolyChoice.NESHODA)
                self.assertEqual(kontrola.poznamka, 'Původní důvod')

        response = self.client.get(self.url)
        result = self.client.post(self.url, self.payload(
            response, uvolneni=UvolneniKontrolyChoice.UVOLNENO,
            neshoda_jine='', poznamka='',
        ))
        self.assertRedirects(result, self.url)
        kontrola.refresh_from_db()
        self.assertFalse(kontrola.neshoda_jine)
        self.assertEqual(kontrola.poznamka, '')
        self.assertEqual(kontrola.uvolneni, UvolneniKontrolyChoice.UVOLNENO)

    def test_concurrent_nonconformity_reason_edit_cannot_be_overwritten(self):
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna)
        response = self.client.get(self.url)
        kontrola.neshoda_cistota = True
        kontrola.save()
        result = self.client.post(self.url, self.payload(response, neshoda_krivost='on'))
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.context['form'].non_field_errors())
        self.assertContains(result, 'Kontrolu bedny se nepodařilo uložit. Příčinu najdete ve formuláři Výstupní kontrola.')
        self.assertTrue(result.context['form'].zobrazit_duvody_neshody)
        kontrola.refresh_from_db()
        self.assertTrue(kontrola.neshoda_cistota)
        self.assertFalse(kontrola.neshoda_krivost)

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
                self.assertNotIn(kind.label, self.measurement_html(response))
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
                            self.assertNotIn(kind.label, self.measurement_html(response))
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
                    html = self.measurement_html(response)
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

    def test_mark_checked_button_is_above_measurements_with_label_for_state(self):
        self.bedna.hmotnost = Decimal('10')
        self.bedna.tara = Decimal('1')
        self.bedna.mnozstvi = 100
        self.bedna.save(update_fields=['hmotnost', 'tara', 'mnozstvi'])
        mark_url = reverse('bedna_scan_zkontrolovano', args=[self.bedna.cislo_bedny])
        scanner_url = f"{reverse('bedna_skener_ctecka')}?cil=kontrola"
        for state, label, other_label in (
            (StavBednyChoice.ZAKALENO, 'Označit bednu jako zkontrolovanou', 'Upravit stav rovnání a tryskání'),
            (StavBednyChoice.ZKONTROLOVANO, 'Upravit stav rovnání a tryskání', 'Označit bednu jako zkontrolovanou'),
        ):
            with self.subTest(state=state):
                self.bedna.stav_bedny = state
                self.bedna.save(update_fields=['stav_bedny'])
                response = self.client.get(self.url)
                html = response.content.decode('utf-8')
                self.assertContains(response, mark_url, count=1)
                self.assertContains(response, label)
                self.assertNotContains(response, other_label)
                self.assertLess(html.index(f'href="{mark_url}"'), html.index(scanner_url))
                self.assertLess(html.index(scanner_url), html.index('id="mereni-bedny"'))

    def test_first_save_creates_control_and_history(self):
        response = self.client.get(self.url)
        result = self.client.post(self.url, self.payload(
            response, cistota=VysledekKontrolyChoice.OK, ulozeni=VysledekKontrolyChoice.NOK,
            uvolneni=UvolneniKontrolyChoice.NESHODA, neshoda_jine='on',
            poznamka='Zkontrolovat uložení',
        ))
        self.assertRedirects(result, self.url)
        kontrola = KontrolaBedny.objects.get(bedna=self.bedna)
        self.assertEqual(kontrola.cistota, VysledekKontrolyChoice.OK)
        self.assertEqual(kontrola.ulozeni, VysledekKontrolyChoice.NOK)
        self.assertEqual(kontrola.uvolneni, UvolneniKontrolyChoice.NESHODA)
        self.assertEqual(kontrola.poznamka, 'Zkontrolovat uložení')
        self.assertEqual(kontrola.history.first().history_user, self.user)
        self.assertEqual(kontrola.uvolneni_zmenil, self.user)
        self.assertIsNotNone(kontrola.uvolneni_zmeneno_at)
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
            uvolneni_zmenil='999', uvolneni_zmeneno_at='2000-01-01',
        ))
        kontrola = KontrolaBedny.objects.get()
        self.assertEqual(kontrola.uvolneni_zmenil, self.user)
        self.assertIsNotNone(kontrola.uvolneni_zmeneno_at)
        release_date = kontrola.uvolneni_zmeneno_at
        response = self.client.get(self.url)
        self.client.post(self.url, self.payload(response, poznamka='Doplněná poznámka'))
        kontrola.refresh_from_db()
        self.assertEqual(kontrola.uvolneni_zmeneno_at, release_date)
        self.assertEqual(kontrola.uvolneni_zmenil, self.user)
        for status in [UvolneniKontrolyChoice.NEROZHODNUTO]:
            response = self.client.get(self.url)
            self.client.post(self.url, self.payload(response, uvolneni=status))
            kontrola.refresh_from_db()
            self.assertIsNone(kontrola.uvolneni_zmenil)
            self.assertIsNone(kontrola.uvolneni_zmeneno_at)

    def test_release_with_deviation_records_metadata_preserves_it_on_edits_and_clears_it(self):
        for nonreleased in (UvolneniKontrolyChoice.NESHODA, UvolneniKontrolyChoice.NEROZHODNUTO):
            with self.subTest(nonreleased=nonreleased):
                response = self.client.get(self.url)
                self.assertContains(response, '<option value="UO"')
                self.assertContains(response, '<option value="NE"')
                self.assertNotContains(response, '<option value="PO">')
                result = self.client.post(self.url, self.payload(
                    response, uvolneni=UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU,
                ))
                self.assertRedirects(result, self.url)
                kontrola = KontrolaBedny.objects.get(bedna=self.bedna)
                released_at = kontrola.uvolneni_zmeneno_at
                self.assertEqual(kontrola.uvolneni_zmenil, self.user)
                self.assertIsNotNone(released_at)
                response = self.client.get(self.url)
                self.client.post(self.url, self.payload(response, poznamka=f'Odchylka {nonreleased}'))
                kontrola.refresh_from_db()
                self.assertEqual(kontrola.uvolneni_zmeneno_at, released_at)
                self.assertEqual(kontrola.uvolneni_zmenil, self.user)
                response = self.client.get(self.url)
                self.client.post(self.url, self.payload(
                    response, uvolneni=nonreleased,
                    **({'neshoda_cistota': 'on'} if nonreleased == UvolneniKontrolyChoice.NESHODA else {}),
                ))
                kontrola.refresh_from_db()
                if nonreleased == UvolneniKontrolyChoice.NESHODA:
                    self.assertEqual(kontrola.uvolneni_zmenil, self.user)
                    self.assertIsNotNone(kontrola.uvolneni_zmeneno_at)
                    self.assertNotEqual(kontrola.uvolneni_zmeneno_at, released_at)
                else:
                    self.assertIsNone(kontrola.uvolneni_zmenil)
                    self.assertIsNone(kontrola.uvolneni_zmeneno_at)

    def test_switching_release_type_records_new_user_and_time(self):
        originally_released_at = timezone.now() - timedelta(days=1)
        kontrola = KontrolaBedny.objects.create(
            bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.UVOLNENO,
            uvolneni_zmenil=self.user, uvolneni_zmeneno_at=originally_released_at,
        )
        editor = get_user_model().objects.create_user(username='uvolnujici_odchylku')
        editor.user_permissions.add(Permission.objects.get(codename='mark_bedna_zkontrolovano'))
        for index, (status, user) in enumerate((
            (UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU, editor),
            (UvolneniKontrolyChoice.UVOLNENO, self.user),
            (UvolneniKontrolyChoice.NESHODA, editor),
            (UvolneniKontrolyChoice.UVOLNENO, self.user),
            (UvolneniKontrolyChoice.NESHODA, self.user),
        ), start=1):
            with self.subTest(status=status):
                self.client.force_login(user)
                response = self.client.get(self.url)
                decision_time = timezone.now() + timedelta(hours=index)
                with patch('orders.views.timezone.now', return_value=decision_time):
                    result = self.client.post(self.url, self.payload(
                        response, uvolneni=status,
                        **({'neshoda_cistota': 'on'} if status == UvolneniKontrolyChoice.NESHODA else {}),
                    ))
                self.assertRedirects(result, self.url)
                kontrola.refresh_from_db()
                self.assertEqual(kontrola.uvolneni, status)
                self.assertEqual(kontrola.uvolneni_zmenil, user)
                self.assertEqual(kontrola.uvolneni_zmeneno_at, decision_time)
                self.assertEqual(kontrola.history.first().history_user, user)

    def test_nonconformity_note_and_count_edits_preserve_decision_metadata(self):
        decision_time = timezone.now() - timedelta(hours=1)
        kontrola = KontrolaBedny.objects.create(
            bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
            neshoda_jine=True,
            uvolneni_zmenil=self.user, uvolneni_zmeneno_at=decision_time,
        )
        editor = get_user_model().objects.create_user(username='doplnujici_poznamku')
        editor.user_permissions.add(Permission.objects.get(codename='mark_bedna_zkontrolovano'))
        self.client.force_login(editor)
        response = self.client.get(self.url)
        self.assertContains(response, 'Stav uvolnění změnil: kontrolor')
        result = self.client.post(self.url, self.payload(
            response, poznamka='Doplnění k neshodě', pocet_krivych_vrutu_prvni_mereni=0,
        ))
        self.assertRedirects(result, self.url)
        kontrola.refresh_from_db()
        self.assertEqual(kontrola.uvolneni_zmenil, self.user)
        self.assertEqual(kontrola.uvolneni_zmeneno_at, decision_time)
        self.assertEqual(kontrola.history.first().history_user, editor)

    def test_reset_to_undecided_clears_current_metadata_but_preserves_history(self):
        decision_time = timezone.now() - timedelta(hours=1)
        kontrola = KontrolaBedny.objects.create(
            bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
            uvolneni_zmenil=self.user, uvolneni_zmeneno_at=decision_time,
        )
        editor = get_user_model().objects.create_user(username='vracejici_na_nerozhodnuto')
        editor.user_permissions.add(Permission.objects.get(codename='mark_bedna_zkontrolovano'))
        self.client.force_login(editor)
        response = self.client.get(self.url)
        result = self.client.post(self.url, self.payload(response, uvolneni=UvolneniKontrolyChoice.NEROZHODNUTO))
        self.assertRedirects(result, self.url)
        kontrola.refresh_from_db()
        self.assertIsNone(kontrola.uvolneni_zmenil)
        self.assertIsNone(kontrola.uvolneni_zmeneno_at)
        latest, original = kontrola.history.all()
        self.assertEqual(latest.uvolneni, UvolneniKontrolyChoice.NEROZHODNUTO)
        self.assertEqual(latest.history_user, editor)
        self.assertIsNotNone(latest.history_date)
        self.assertEqual(original.uvolneni, UvolneniKontrolyChoice.NESHODA)
        self.assertEqual(original.uvolneni_zmenil, self.user)
        self.assertEqual(original.uvolneni_zmeneno_at, decision_time)
        self.assertNotContains(self.client.get(self.url), 'Stav uvolnění změnil:')

    def test_unchanged_save_does_not_add_history(self):
        kontrola = KontrolaBedny.objects.create(
            bedna=self.bedna, pocet_krivych_vrutu_prvni_mereni=0, pocet_krivych_vrutu_druhe_mereni=2,
        )
        response = self.client.get(self.url)
        self.assertEqual(self.client.post(self.url, self.payload(response)).status_code, 302)
        self.assertEqual(kontrola.history.count(), 1)

    def test_invalid_choice_saves_nothing(self):
        for status in ('DZ', 'PO'):
            with self.subTest(status=status):
                response = self.client.get(self.url)
                result = self.client.post(self.url, self.payload(response, uvolneni=status))
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
