from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from orders.choices import TypZkouskyChoice, UvolneniKontrolyChoice, VysledekKontrolyChoice
from orders.models import KontrolaBedny, MereniBedny
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
        data = {name: form[name].value() or '' for name in form.fields}
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
        self.assertLess(html.index('id="mereni-bedny"'), html.index('<form method="post" novalidate>'))
        for kind in TypZkouskyChoice:
            self.assertContains(response, reverse('bedna_mereni_zkousky', args=[self.bedna.cislo_bedny, kind]))

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
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna)
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
