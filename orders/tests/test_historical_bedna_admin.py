from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from orders.choices import RovnaniChoice, StavBednyChoice
from orders.models import Bedna, Pozice
from orders.templatetags.admin_sections import orders_admin_sections
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class HistoricalBednaAdminTests(KontrolaBednyTestBase):
    def setUp(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        self.model = Bedna.history.model
        self.model_admin = admin.site._registry[self.model]
        self.list_url = reverse('admin:orders_historicalbedna_changelist')

    def request(self):
        request = RequestFactory().get(self.list_url)
        request.user = self.user
        return request

    def test_history_is_visible_in_logistics_menu_and_creation_has_no_delta(self):
        app = next(app for app in admin.site.get_app_list(self.request()) if app['app_label'] == 'orders')
        logistics = next(section for section in orders_admin_sections(app['models']) if section['key'] == 'logistika')
        history = next(model for model in logistics['models'] if model['object_name'] == 'HistoricalBedna')
        self.assertEqual(history['admin_url'], self.list_url)
        self.assertIsNone(history['add_url'])
        self.assertTrue(history['view_only'])
        self.assertContains(self.client.get(reverse('admin:index')), self.list_url)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        record = response.context['cl'].result_list[0]
        self.assertEqual(self.model_admin.changes(record), '—')

    def test_changes_use_choice_labels_user_and_escape_html(self):
        self.bedna.rovnat = RovnaniChoice.KRIVA
        self.bedna.poznamka = '<script>alert(1)</script>'
        self.bedna._history_user = self.user
        self.bedna.save()
        response = self.client.get(self.list_url)
        self.assertContains(response, 'Změny')
        self.assertContains(response, 'kontrolor')
        self.assertContains(response, '<strong>Rovnání:</strong> -------- → Křivá', html=True)
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')

    def test_previous_version_ignores_filters_pages_other_containers_and_time_ties(self):
        initial = self.bedna.history.first()
        self.bedna.poznamka = 'První'
        self.bedna.save()
        middle = self.bedna.history.first()
        Bedna.objects.create(zakazka=self.bedna.zakazka, poznamka='Jiná bedna')
        self.bedna.poznamka = 'Druhá'
        self.bedna.save()
        self.model.objects.update(history_date=timezone.now())

        with patch.object(self.model_admin, 'list_per_page', 1):
            response = self.client.get(self.list_url, {
                'q': self.bedna.cislo_bedny, 'history_type__exact': '~', 'p': 2,
            })
        self.assertEqual(response.status_code, 200)
        record = response.context['cl'].result_list[0]
        self.assertEqual(record.pk, middle.pk)
        self.assertEqual(record._previous_history_record.pk, initial.pk)
        self.assertContains(response, '<strong>Poznámka HPM:</strong> None → První', html=True)
        self.assertNotContains(response, 'Jiná bedna')

    def test_previous_versions_and_foreign_keys_are_loaded_before_rendering_changes(self):
        self.bedna.stav_bedny = StavBednyChoice.K_NAVEZENI
        self.bedna.hmotnost = self.bedna.tara = self.bedna.mnozstvi = 1
        for code in ('A', 'B', 'C', 'D'):
            self.bedna.pozice = Pozice.objects.create(kod=code)
            self.bedna.save()
        response = self.model_admin.changelist_view(self.request())
        records = list(response.context_data['cl'].result_list)
        with self.assertNumQueries(0):
            changes = [str(self.model_admin.changes(record)) for record in records]
        self.assertTrue(any('<strong>Pozice:</strong> C → D' in change for change in changes))

    def test_deleted_container_and_missing_related_objects_remain_viewable(self):
        self.bedna.poznamka = 'Archivovaná poznámka'
        self.bedna.save()
        zakazka = self.bedna.zakazka
        self.bedna.delete()
        zakazka.delete()
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        records = list(response.context['cl'].result_list)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0].history_type, '-')
        detail = reverse('admin:orders_historicalbedna_change', args=[records[0].pk])
        self.assertEqual(self.client.get(detail).status_code, 200)

    def test_historical_records_cannot_be_added_modified_or_deleted(self):
        record = self.bedna.history.first()
        detail = reverse('admin:orders_historicalbedna_change', args=[record.pk])
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(self.client.post(detail, {'poznamka': 'Přepsáno', '_save': 'Uložit'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:orders_historicalbedna_add')).status_code, 403)
        deletion = reverse('admin:orders_historicalbedna_delete', args=[record.pk])
        self.assertEqual(self.client.post(deletion, {'post': 'yes'}).status_code, 403)
        response = self.client.post(self.list_url, {'action': 'delete_selected', '_selected_action': record.pk})
        self.assertEqual(response.status_code, 200)
        record.refresh_from_db()
        self.assertIsNone(record.poznamka)
        self.assertEqual(self.model.objects.count(), 1)

    def test_history_requires_its_own_view_permission(self):
        viewer = get_user_model().objects.create_user(username='history_viewer', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_bedna'))
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        viewer.user_permissions.add(Permission.objects.get(codename='view_historicalbedna'))
        self.assertEqual(self.client.get(self.list_url).status_code, 200)
        detail = reverse('admin:orders_historicalbedna_change', args=[self.bedna.history.first().pk])
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(self.client.post(detail, {'_save': 'Uložit'}).status_code, 403)
