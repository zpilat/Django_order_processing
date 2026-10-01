from datetime import timedelta

from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from orders.choices import UvolneniKontrolyChoice
from orders.models import Bedna, KontrolaBedny
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class NeshodyPrehledTests(KontrolaBednyTestBase):
    def setUp(self):
        self.url = reverse('neshody_prehled')
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(
            response, f'{reverse("login")}?next={self.url}',
            fetch_redirect_response=False,
        )

    def test_empty_overview(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'orders/neshody_prehled.html')
        self.assertEqual(response.context['items'], [])
        self.assertContains(response, 'Momentálně není evidována žádná bedna ve stavu Neshoda.')

    def test_shows_both_bent_screw_ratios_including_zero(self):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        customer.pocet_vrutu_pro_kontrolu_prohybu = 25
        customer.save(update_fields=['pocet_vrutu_pro_kontrolu_prohybu'])
        KontrolaBedny.objects.create(
            bedna=self.bedna,
            uvolneni=UvolneniKontrolyChoice.NESHODA,
            pocet_krivych_vrutu_prvni_mereni=0,
            pocet_krivych_vrutu_druhe_mereni=3,
        )

        response = self.client.get(self.url)
        item = response.context['items'][0]
        self.assertEqual(item['pomer_krivych_vrutu_prvni_mereni'], '0 / 25')
        self.assertEqual(item['pomer_krivych_vrutu_druhe_mereni'], '3 / 25')
        self.assertContains(response, '<div class="col-md-1">Křivých</div>')
        self.assertContains(response, '<div>0 / 25</div>')
        self.assertContains(response, '<div>3 / 25</div>')

        customer.pocet_vrutu_pro_kontrolu_prohybu = None
        customer.save(update_fields=['pocet_vrutu_pro_kontrolu_prohybu'])
        response = self.client.get(self.url)
        item = response.context['items'][0]
        self.assertEqual(item['pomer_krivych_vrutu_prvni_mereni'], '0 / —')
        self.assertEqual(item['pomer_krivych_vrutu_druhe_mereni'], '3 / —')

    def test_shows_placeholder_when_bent_screw_counts_are_empty(self):
        KontrolaBedny.objects.create(bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.NESHODA)

        response = self.client.get(self.url)
        item = response.context['items'][0]
        self.assertIsNone(item['pomer_krivych_vrutu_prvni_mereni'])
        self.assertIsNone(item['pomer_krivych_vrutu_druhe_mereni'])
        self.assertContains(response, '<div class="text-muted">—</div>')

    def test_shows_only_current_nonconformities_newest_first_with_missing_times_last(self):
        self.user.first_name = 'Jan'
        self.user.last_name = 'Novák'
        self.user.save(update_fields=['first_name', 'last_name'])
        older = timezone.now() - timedelta(days=2)
        newer = timezone.now() - timedelta(hours=1)
        first = KontrolaBedny.objects.create(
            bedna=self.bedna,
            uvolneni=UvolneniKontrolyChoice.NESHODA,
            uvolneni_zmeneno_at=older,
            uvolneni_zmenil=self.user,
            neshoda_krivost=True,
            neshoda_jine=True,
            poznamka='Poškozený závit',
        )
        newest_bedna = Bedna.objects.create(zakazka=self.bedna.zakazka)
        KontrolaBedny.objects.create(
            bedna=newest_bedna,
            uvolneni=UvolneniKontrolyChoice.NESHODA,
            uvolneni_zmeneno_at=newer,
            neshoda_cistota=True,
        )
        without_time_bedna = Bedna.objects.create(zakazka=self.bedna.zakazka)
        KontrolaBedny.objects.create(
            bedna=without_time_bedna,
            uvolneni=UvolneniKontrolyChoice.NESHODA,
        )
        released_bedna = Bedna.objects.create(zakazka=self.bedna.zakazka)
        KontrolaBedny.objects.create(
            bedna=released_bedna,
            uvolneni=UvolneniKontrolyChoice.UVOLNENO,
            uvolneni_zmeneno_at=timezone.now(),
        )

        # Pozdější úprava důvodů nemá změnit čas rozhodnutí ani pořadí.
        first.poznamka = 'Poškozený závit · doplněno'
        first.save(update_fields=['poznamka'])

        response = self.client.get(self.url)
        items = response.context['items']
        self.assertEqual(
            [item['cislo_bedny'] for item in items],
            [newest_bedna.cislo_bedny, self.bedna.cislo_bedny, without_time_bedna.cislo_bedny],
        )
        self.assertEqual(items[1]['duvody'], ['Křivost', 'Jiné'])
        self.assertEqual(items[1]['poznamka'], 'Poškozený závit · doplněno')
        self.assertEqual(items[1]['oznaceno_at'], older)
        self.assertEqual(items[1]['oznacil'], 'Jan Novák')
        self.assertContains(response, 'Jan Novák')
        self.assertContains(response, 'Čas nezjištěn')
        self.assertNotContains(response, reverse('bedna_kontrola', args=[self.bedna.cislo_bedny]))

        self.user.user_permissions.add(Permission.objects.get(codename='view_bedna'))
        response = self.client.get(self.url)
        self.assertContains(response, reverse('bedna_kontrola', args=[self.bedna.cislo_bedny]))
        self.assertContains(response, reverse('bedna_kontrola', args=[newest_bedna.cislo_bedny]))

    def test_admin_index_groups_control_overviews_below_workplace_overviews(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=['is_staff', 'is_superuser'])

        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertLess(html.index('Přehledy pracovišť'), html.index('Přehledy kontroly'))
        self.assertLess(html.index('Přehledy kontroly'), html.index('Přehledy výroby'))
        section = html.split('Přehledy kontroly', 1)[1].split('</table>', 1)[0]
        self.assertIn(reverse('kontrola_prehled'), section)
        self.assertIn(self.url, section)
        self.assertLess(section.index('Přehled kontroly'), section.index('Přehled neshod'))
