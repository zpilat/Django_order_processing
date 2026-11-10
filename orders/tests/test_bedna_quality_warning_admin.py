from django.contrib import admin
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from django.urls import reverse

from orders.choices import StavBednyChoice, UvolneniKontrolyChoice
from orders.models import Bedna, KontrolaBedny
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class BednaQualityWarningAdminTests(KontrolaBednyTestBase):
    def setUp(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        self.bedna_admin = admin.site._registry[Bedna]
        self.request = RequestFactory().get('/admin/orders/bedna/')
        self.request.user = self.user

    def warning_is_shown(self):
        bedna = self.bedna_admin.get_queryset(self.request).select_related(
            'zakazka__kamion_prijem__zakaznik',
        ).get(pk=self.bedna.pk)
        # Rendering must not issue another query for every row.
        with self.assertNumQueries(0):
            html = str(self.bedna_admin.get_cislo_bedny(bedna))
        return 'data-kontrola-neshoda="true"' in html

    def test_missing_control_has_no_warning(self):
        self.assertFalse(self.warning_is_shown())

    def test_only_bending_is_suppressed_and_mixed_reasons_still_warn(self):
        kontrola = KontrolaBedny.objects.create(
            bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
            neshoda_krivost=True,
        )
        self.assertFalse(self.warning_is_shown())
        for reason in KontrolaBedny.NESHODA_FIELDS:
            if reason == 'neshoda_krivost':
                continue
            for bending in (False, True):
                with self.subTest(reason=reason, bending=bending):
                    KontrolaBedny.objects.filter(pk=kontrola.pk).update(
                        neshoda_krivost=bending, **{reason: True},
                    )
                    self.assertTrue(self.warning_is_shown())
            KontrolaBedny.objects.filter(pk=kontrola.pk).update(**{reason: False})

    def test_unspecified_nonconformity_still_warns(self):
        KontrolaBedny.objects.create(
            bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
        )
        self.assertTrue(self.warning_is_shown())

    def test_releasing_or_resetting_control_removes_warning(self):
        kontrola = KontrolaBedny.objects.create(
            bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
            neshoda_cistota=True,
        )
        self.assertTrue(self.warning_is_shown())
        for release in (
            UvolneniKontrolyChoice.UVOLNENO,
            UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU,
            UvolneniKontrolyChoice.NEROZHODNUTO,
        ):
            with self.subTest(release=release):
                KontrolaBedny.objects.filter(pk=kontrola.pk).update(uvolneni=release)
                self.assertFalse(self.warning_is_shown())

    def test_changelist_includes_warning_with_and_without_filters_and_edit_permission(self):
        KontrolaBedny.objects.create(
            bedna=self.bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
            neshoda_cistota=True,
        )
        Bedna.objects.filter(pk=self.bedna.pk).update(
            stav_bedny=StavBednyChoice.ZKONTROLOVANO,
            hmotnost=10, tara=1, mnozstvi=100,
        )
        url = reverse('admin:orders_bedna_changelist')
        for editable in (True, False):
            self.user.is_superuser = editable
            self.user.save()
            if not editable:
                self.user.user_permissions.add(Permission.objects.get(codename='view_bedna'))
            for params in ({}, {'stav_bedny': StavBednyChoice.ZKONTROLOVANO}):
                with self.subTest(editable=editable, params=params):
                    response = self.client.get(url, params)
                    self.assertContains(response, 'data-kontrola-neshoda="true"', count=1)
                    self.assertContains(response, 'orders/js/admin_bedna_quality_warning.js')
                    self.assertContains(response, 'orders/css/admin_bedna_quality_warning.css')
                    self.assertEqual(bool(getattr(response.context['cl'], 'formset', None)), editable)
