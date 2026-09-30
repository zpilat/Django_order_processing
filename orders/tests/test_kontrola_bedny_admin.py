from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from orders.choices import TypZkouskyChoice, UvolneniKontrolyChoice
from orders.models import Bedna, KontrolaBedny, MereniBedny
from orders.templatetags.admin_sections import orders_admin_sections
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class KontrolaBednyAdminTests(KontrolaBednyTestBase):
    def setUp(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        self.kontrola = KontrolaBedny(bedna=self.bedna, poznamka='Poznámka kontroly')
        self.kontrola._history_user = self.user
        self.kontrola.save()
        self.mereni = MereniBedny(
            kontrola=self.kontrola, typ_zkousky=TypZkouskyChoice.OHYB,
            hodnota=Decimal('12.5000'), poradi=1, zmeril=self.user,
        )
        self.mereni._history_user = self.user
        self.mereni.save()

    def request(self, user=None):
        request = RequestFactory().get('/admin/')
        request.user = user or self.user
        return request

    def url(self, model, action, pk=None):
        return reverse(f'admin:orders_{model._meta.model_name}_{action}', args=[pk] if pk else None)

    def test_quality_section_contains_only_live_models_and_has_working_lists(self):
        models = (KontrolaBedny, MereniBedny)
        self.assertNotIn(KontrolaBedny.history.model, admin.site._registry)
        self.assertNotIn(MereniBedny.history.model, admin.site._registry)
        apps = admin.site.get_app_list(self.request())
        app = next(app for app in apps if app['app_label'] == 'orders')
        sections = orders_admin_sections(app['models'])
        quality = next(section for section in sections if section['key'] == 'kontrola_kvality')
        self.assertEqual([model['object_name'] for model in quality['models']], [model.__name__ for model in models])
        for model in quality['models']:
            self.assertIsNone(model['add_url'])
            self.assertTrue(model['view_only'])
        for model in models:
            with self.subTest(model=model.__name__):
                response = self.client.get(self.url(model, 'changelist'))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['cl'].result_count, 1)
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'Kontrola kvality')
        self.assertNotContains(response, 'Historie měření beden')
        self.assertNotContains(response, 'historicalmerenibedny')

    def test_live_details_link_to_existing_workflow_using_container_number(self):
        for obj, workflow_url in (
            (self.kontrola, reverse('bedna_kontrola', args=[self.bedna.cislo_bedny])),
            (self.mereni, reverse('bedna_mereni_zkousky', args=[self.bedna.cislo_bedny, self.mereni.typ_zkousky])),
        ):
            with self.subTest(model=type(obj).__name__):
                response = self.client.get(self.url(type(obj), 'change', obj.pk))
                self.assertContains(response, f'href="{workflow_url}"')
                self.assertContains(response, f'href="{self.url(type(obj), "history", obj.pk)}"')
                response = self.client.get(self.url(type(obj), 'history', obj.pk))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'kontrolor')

    def test_bedna_detail_embeds_quality_control_summary(self):
        predpis = self.bedna.zakazka.predpis
        predpis.ohyb = 'min. 30°'
        predpis.popis_ohyb = 'Nazev typu zkousky'
        predpis.popis_ohyb_2 = 'Bez trhlin'
        predpis.save()

        bedna_admin = admin.site._registry[type(self.bedna)]
        html = str(bedna_admin.get_mereni_bedny(self.bedna))

        self.assertNotIn('Nazev typu zkousky', html)
        self.assertIn('Předepsáno', html)
        self.assertIn('Naměřeno', html)
        self.assertIn('min. 30°', html)
        self.assertIn('Bez trhlin', html)
        self.assertIn('12,5', html)
        self.assertIn('kontrolor', html)
        self.assertIn('Interní poznámka', html)
        self.assertIn(reverse('bedna_kontrola', args=[self.bedna.cislo_bedny]), html)

        response = self.client.get(self.url(type(self.bedna), 'change', self.bedna.pk))
        self.assertContains(response, predpis.popis_ohyb_2)
        self.assertNotContains(response, predpis.popis_ohyb)
        self.assertContains(response, 'Kontrola kvality')
        self.assertContains(response, 'min. 30°')
        self.assertContains(response, '12,5')

    def test_summary_displays_release_types_and_nonconformity(self):
        for status, css, released in (
            (UvolneniKontrolyChoice.UVOLNENO, 'qc-good', True),
            (UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU, 'qc-warning', True),
            (UvolneniKontrolyChoice.NESHODA, 'qc-bad', True),
            (UvolneniKontrolyChoice.NEROZHODNUTO, '', False),
        ):
            with self.subTest(status=status):
                self.kontrola.uvolneni = status
                self.kontrola.uvolneni_zmenil = self.user if released else None
                self.kontrola.uvolneni_zmeneno_at = timezone.now() if released else None
                self.kontrola.save()
                html = str(admin.site._registry[Bedna].get_mereni_bedny(self.bedna))
                self.assertIn(f'<div class="qc-status {css}">', html)
                details = html.split('<span class="qc-label">Uvolnění</span>', 1)[1].split('</div>', 1)[0]
                self.assertIn(status.label, details)
                self.assertEqual('class="qc-detail"' in details, released)

    def test_summary_shows_selected_nonconformity_reasons_before_note_only_for_nonconformity(self):
        bedna_admin = admin.site._registry[Bedna]
        self.kontrola.uvolneni = UvolneniKontrolyChoice.NESHODA
        self.kontrola.neshoda_cistota = True
        self.kontrola.neshoda_tvrdost_povrchu_nizka = True
        self.kontrola.neshoda_jine = True
        self.kontrola.save()

        html = str(bedna_admin.get_mereni_bedny(self.bedna))
        reasons = '<strong>Důvody neshody:</strong> Čistota, Tvrdost povrchu nízká, Jiné'
        self.assertIn(reasons, html)
        self.assertLess(html.index(reasons), html.index('<strong>Interní poznámka:</strong>'))
        self.assertNotIn('Krut nízký', html)

        self.kontrola.uvolneni = UvolneniKontrolyChoice.UVOLNENO
        self.kontrola.save()
        html = str(bedna_admin.get_mereni_bedny(self.bedna))
        self.assertNotIn('Důvody neshody:', html)
        self.assertIn('<strong>Interní poznámka:</strong>', html)

        self.kontrola.uvolneni = UvolneniKontrolyChoice.NESHODA
        for name in KontrolaBedny.NESHODA_FIELDS:
            setattr(self.kontrola, name, False)
        self.kontrola.save()
        html = str(bedna_admin.get_mereni_bedny(self.bedna))
        self.assertNotIn('Důvody neshody:', html)

    def test_bedna_summary_shows_bending_limits_and_optional_release_limit(self):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        bedna_admin = admin.site._registry[Bedna]
        for code, length, normal, release in (
            ('EUR', '100', '0,6', None), ('ROT', '100', '0,4', '0,6'),
            ('ROT', '123.4', '0,4936', '0,7404'), ('SWG', '300', '1,8', None),
            ('SWG', '400', '1,8', None), ('TST', '100', None, None),
        ):
            with self.subTest(customer=code, length=length):
                customer.zkratka = code
                self.bedna.zakazka.delka = Decimal(length)
                html = str(bedna_admin.get_mereni_bedny(self.bedna))

                if normal is None:
                    self.assertNotIn('<strong>max.', html)
                else:
                    self.assertEqual(html.count(f'<strong>max. {normal} mm</strong>'), 3)
                if release is None:
                    self.assertNotIn('QS max.', html)
                else:
                    self.assertEqual(html.count(f'QS max. {release} mm'), 3)
                self.assertIn('12,5', html)
                self.assertNotIn('None', html)

    def test_summary_colors_all_bending_types_using_customer_limits(self):
        for kind in (
            TypZkouskyChoice.PROHYB_PO_TZ, TypZkouskyChoice.PROHYB_PO_KOULENI,
            TypZkouskyChoice.PROHYB_PO_ROVNANI,
        ):
            for order, value in enumerate(('0.4', '0.4001', '0.6', '0.6001'), start=1):
                MereniBedny.objects.create(
                    kontrola=self.kontrola, typ_zkousky=kind, hodnota=Decimal(value),
                    poradi=order, zmeril=self.user,
                )
        MereniBedny.objects.create(
            kontrola=self.kontrola, typ_zkousky=TypZkouskyChoice.OHYB,
            hodnota=Decimal('0.6001'), poradi=2, zmeril=self.user,
        )
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        for code, states in (
            ('ROT', ('', 'odchylka', 'odchylka', 'nevyhovuje')),
            ('EUR', ('', '', '', 'nevyhovuje')),
            ('TST', ('', '', '', '')),
        ):
            with self.subTest(customer=code):
                customer.zkratka = code
                html = str(admin.site._registry[Bedna].get_mereni_bedny(self.bedna))
                for value, state in zip(('0,4', '0,4001', '0,6', '0,6001'), states):
                    suffix = f' prohyb-{state}' if state else ''
                    expected_count = 4 if value == '0,6001' and not state else 3
                    self.assertEqual(html.count(f'<span class="qc-measurement{suffix}">{value}</span>'), expected_count)
                self.assertIn('<span class="qc-measurement">0,6001</span>', html)
                self.assertEqual(html.count(' prohyb-odchylka">'), states.count('odchylka') * 3)
                self.assertEqual(html.count(' prohyb-nevyhovuje">'), states.count('nevyhovuje') * 3)

    def test_bedna_summary_shows_hardness_only_for_selected_containers(self):
        bedny = [self.bedna] + [Bedna.objects.create(zakazka=self.bedna.zakazka) for _ in range(2)]
        predpis = self.bedna.zakazka.predpis
        predpis.povrch = '550-650 HV'
        predpis.jadro = '300-350 HV'
        predpis.save(update_fields=['povrch', 'jadro'])
        hardness = (
            (TypZkouskyChoice.TVRDOST_POVRCHU, Decimal('580.25'), '580,25', predpis.povrch),
            (TypZkouskyChoice.TVRDOST_JADRA, Decimal('320.75'), '320,75', predpis.jadro),
        )
        for bedna in bedny:
            kontrola, _ = KontrolaBedny.objects.get_or_create(bedna=bedna)
            for kind, value, _, _ in hardness:
                MereniBedny.objects.create(
                    kontrola=kontrola, typ_zkousky=kind, hodnota=value, poradi=1, zmeril=self.user,
                )

        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        bedna_admin = admin.site._registry[Bedna]
        for code, full_thread, selected in (
            ('SSH', False, (True, False, True)), ('SWG', False, (True, False, True)),
            ('ROT', False, (True, False, True)),
            ('SPX', False, (True, True, True)), ('EUR', False, (True, False, False)),
            ('EUR', True, (True, True, True)),
        ):
            customer.zkratka = code
            customer.save(update_fields=['zkratka'])
            self.bedna.zakazka.celozavit = full_thread
            self.bedna.zakazka.save(update_fields=['celozavit'])
            for bedna, visible in zip(bedny, selected):
                with self.subTest(customer=code, full_thread=full_thread, container=bedna.cislo_bedny):
                    html = str(bedna_admin.get_mereni_bedny(bedna))
                    for kind, _, formatted_value, requirement in hardness:
                        self.assertEqual(kind.label in html, visible)
                        self.assertEqual(formatted_value in html, visible)
                        self.assertEqual(requirement in html, visible)
                    for kind in TypZkouskyChoice:
                        if kind not in (TypZkouskyChoice.TVRDOST_POVRCHU, TypZkouskyChoice.TVRDOST_JADRA):
                            self.assertIn(kind.label, html)
                    self.assertIn(reverse('bedna_kontrola', args=[bedna.cislo_bedny]), html)
                    if bedna.pk == self.bedna.pk:
                        self.assertIn('12,5', html)

        self.assertEqual(MereniBedny.objects.count(), 7)

    def test_live_admin_cannot_modify_or_delete_records(self):
        for obj in (self.kontrola, self.mereni):
            with self.subTest(model=type(obj).__name__):
                model = type(obj)
                self.assertEqual(self.client.get(self.url(model, 'change', obj.pk)).status_code, 200)
                self.assertEqual(self.client.post(self.url(model, 'change', obj.pk), {'hodnota': '99', '_save': 'Uložit'}).status_code, 403)
                self.assertEqual(self.client.get(self.url(model, 'add')).status_code, 403)
                self.assertEqual(self.client.post(self.url(model, 'delete', obj.pk), {'post': 'yes'}).status_code, 403)
        self.mereni.refresh_from_db()
        self.assertEqual(self.mereni.hodnota, Decimal('12.5'))
        self.assertEqual(KontrolaBedny.history.count(), 1)
        self.assertEqual(MereniBedny.history.count(), 1)

    def test_deleted_measurement_remains_visible_in_model_history(self):
        measurement_id = self.mereni.pk
        self.mereni.delete()
        event = MereniBedny.history.first()
        self.assertEqual(event.history_type, '-')
        response = self.client.get(self.url(MereniBedny, 'history', measurement_id))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'kontrolor')
        self.assertEqual(response.context['page_obj'].paginator.count, 2)

    def test_simple_history_versions_are_read_only_and_cannot_be_reverted_by_post(self):
        for obj in (self.kontrola, self.mereni):
            with self.subTest(model=type(obj).__name__):
                event = obj.history.first()
                url = reverse(f'admin:orders_{obj._meta.model_name}_simple_history', args=[obj.pk, event.history_id])
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['revert_disabled'])
                self.assertEqual(self.client.post(url, {'_save': 'Uložit'}).status_code, 403)
                self.assertEqual(obj.history.count(), 1)

    def test_quality_section_respects_each_model_view_permission(self):
        viewer = get_user_model().objects.create_user(username='viewer', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_kontrolabedny'))
        apps = admin.site.get_app_list(self.request(viewer))
        app = next(app for app in apps if app['app_label'] == 'orders')
        quality = next(section for section in orders_admin_sections(app['models']) if section['key'] == 'kontrola_kvality')
        self.assertEqual([model['object_name'] for model in quality['models']], ['KontrolaBedny'])
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(self.url(KontrolaBedny, 'changelist')).status_code, 200)
        self.assertEqual(self.client.get(self.url(KontrolaBedny, 'history', self.kontrola.pk)).status_code, 200)
        self.assertEqual(self.client.get(self.url(MereniBedny, 'changelist')).status_code, 403)
