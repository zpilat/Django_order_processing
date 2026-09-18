from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, override_settings
from django.urls import reverse

from simple_history.admin import SimpleHistoryAdmin

from orders.models import TypHlavy
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class HistoryViewOnlyAdminTests(KontrolaBednyTestBase):
    def setUp(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        self.zakazka = self.bedna.zakazka
        self.hlava = self.zakazka.typ_hlavy

    def version_url(self, obj, record):
        return reverse(
            f'admin:{obj._meta.app_label}_{obj._meta.model_name}_simple_history',
            args=[obj.pk, record.pk],
        )

    def test_all_registered_history_admins_deny_reverting_even_for_superusers(self):
        request = RequestFactory().post('/admin/', {'_save': 'Uložit'})
        request.user = self.user
        for model, model_admin in admin.site._registry.items():
            if not isinstance(model_admin, SimpleHistoryAdmin):
                continue
            with self.subTest(model=model.__name__):
                self.assertFalse(model_admin.has_change_history_permission(request))
                with self.assertRaises(PermissionDenied):
                    model_admin.history_form_view(request, '1', '1')

    def test_existing_history_lists_and_versions_remain_viewable_without_revert_button(self):
        for obj in (
            self.bedna, self.zakazka, self.zakazka.kamion_prijem,
            self.zakazka.kamion_prijem.zakaznik, self.zakazka.predpis, self.hlava,
        ):
            with self.subTest(model=type(obj).__name__):
                history_url = reverse(f'admin:orders_{obj._meta.model_name}_history', args=[obj.pk])
                self.assertEqual(self.client.get(history_url).status_code, 200)
                record = obj.history.first()
                response = self.client.get(self.version_url(obj, record))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['revert_disabled'])
                self.assertFalse(response.context['has_change_permission'])
                self.assertNotRegex(response.content.decode(), r'<input\b[^>]*name="_save"')
                count = obj.history.count()
                self.assertEqual(self.client.post(self.version_url(obj, record), {'_save': 'Uložit'}).status_code, 403)
                self.assertEqual(obj.history.count(), count)

    def test_normal_admin_edits_still_save_and_record_the_user(self):
        count = self.hlava.history.count()
        change_url = reverse('admin:orders_typhlavy_change', args=[self.hlava.pk])
        response = self.client.post(change_url, {'nazev': 'Upravená', 'popis': 'Nový popis', '_save': 'Uložit'})
        self.assertEqual(response.status_code, 302)
        self.hlava.refresh_from_db()
        self.assertEqual(self.hlava.nazev, 'Upravená')
        self.assertEqual(self.hlava.history.count(), count + 1)
        self.assertEqual(self.hlava.history.first().history_user, self.user)

    def test_normal_admin_add_and_delete_remain_available(self):
        response = self.client.post(reverse('admin:orders_typhlavy_add'), {
            'nazev': 'Nová hlava', 'popis': '', '_save': 'Uložit',
        })
        self.assertEqual(response.status_code, 302)
        obj = TypHlavy.objects.get(nazev='Nová hlava')
        self.assertEqual(obj.history.first().history_user, self.user)
        delete_url = reverse('admin:orders_typhlavy_delete', args=[obj.pk])
        self.assertEqual(self.client.post(delete_url, {'post': 'yes'}).status_code, 302)
        self.assertFalse(TypHlavy.objects.filter(pk=obj.pk).exists())

    def test_viewer_can_view_versions_but_cannot_restore_them(self):
        viewer = get_user_model().objects.create_user(username='history_reader', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_typhlavy'))
        self.client.force_login(viewer)
        version_url = self.version_url(self.hlava, self.hlava.history.first())
        self.assertEqual(self.client.get(version_url).status_code, 200)
        self.assertEqual(self.client.post(version_url, {'_save': 'Uložit'}).status_code, 403)

    @override_settings(SIMPLE_HISTORY_ENFORCE_HISTORY_MODEL_PERMISSIONS=True)
    def test_history_change_permission_does_not_allow_restoring_versions(self):
        editor = get_user_model().objects.create_user(username='history_editor', is_staff=True)
        editor.user_permissions.add(*Permission.objects.filter(codename__in=(
            'view_historicaltyphlavy', 'change_historicaltyphlavy',
        )))
        self.client.force_login(editor)
        version_url = self.version_url(self.hlava, self.hlava.history.first())
        response = self.client.get(version_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['revert_disabled'])
        self.assertEqual(self.client.post(version_url, {'_save': 'Uložit'}).status_code, 403)

    def test_deleted_object_can_be_viewed_but_not_restored(self):
        obj = TypHlavy.objects.create(nazev='Smazaná')
        object_id = obj.pk
        record = obj.history.first()
        version_url = self.version_url(obj, record)
        obj.delete()
        self.assertEqual(self.client.get(version_url).status_code, 200)
        self.assertEqual(self.client.post(version_url, {'_save': 'Uložit'}).status_code, 403)
        self.assertFalse(TypHlavy.objects.filter(pk=object_id).exists())
