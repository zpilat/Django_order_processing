from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from django.urls import reverse

from orders.choices import TypZkouskyChoice
from orders.models import KontrolaBedny, MereniBedny
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
        predpis.popis_ohyb = 'Bez trhlin'
        predpis.save()

        bedna_admin = admin.site._registry[type(self.bedna)]
        html = str(bedna_admin.get_mereni_bedny(self.bedna))

        self.assertIn('Předepsáno', html)
        self.assertIn('Naměřeno', html)
        self.assertIn('min. 30°', html)
        self.assertIn('Bez trhlin', html)
        self.assertIn('12,5', html)
        self.assertIn('kontrolor', html)
        self.assertIn('Interní poznámka', html)
        self.assertIn(reverse('bedna_kontrola', args=[self.bedna.cislo_bedny]), html)

        response = self.client.get(self.url(type(self.bedna), 'change', self.bedna.pk))
        self.assertContains(response, 'Kontrola kvality')
        self.assertContains(response, 'min. 30°')
        self.assertContains(response, '12,5')

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
