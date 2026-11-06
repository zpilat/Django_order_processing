import re
from datetime import date
from html import unescape
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import reverse

from orders.admin import BednaAdmin, KamionAdmin
from orders.choices import KamionChoice, RovnaniChoice, StavBednyChoice, TryskaniChoice
from orders.forms import BednaChangeListForm
from orders.models import Bedna, Kamion, Predpis, TypHlavy, Zakazka, Zakaznik


class FaufTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.superuser = User.objects.create_superuser('fauf-admin', password='test')
        cls.staff = User.objects.create(username='fauf-staff', is_staff=True)
        cls.staff.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='orders', codename__in=('view_bedna', 'change_bedna'),
        ))
        cls.spx = Zakaznik.objects.create(
            nazev='SPX', zkraceny_nazev='SPX', zkratka='SPX', ciselna_rada=200000,
        )
        cls.eur = Zakaznik.objects.create(
            nazev='EUR', zkraceny_nazev='EUR', zkratka='EUR', ciselna_rada=100000,
        )
        cls.head = TypHlavy.objects.create(nazev='SK')
        cls.specification = Predpis.objects.create(nazev='FAUF test', zakaznik=cls.spx)
        cls.incoming = Kamion.objects.create(zakaznik=cls.spx, datum=date.today())
        cls.outgoing = Kamion.objects.create(
            zakaznik=cls.spx, datum=date.today(), prijem_vydej=KamionChoice.VYDEJ,
        )
        cls.other_outgoing = Kamion.objects.create(
            zakaznik=cls.spx, datum=date.today(), prijem_vydej=KamionChoice.VYDEJ,
        )
        cls.order = cls.make_order(cls.incoming, cls.outgoing)
        cls.other_order = cls.make_order(cls.incoming, cls.other_outgoing)
        cls.crate = cls.make_crate(cls.order, StavBednyChoice.EXPEDOVANO)
        cls.second_crate = cls.make_crate(cls.order, StavBednyChoice.EXPEDOVANO)
        cls.other_crate = cls.make_crate(cls.other_order, StavBednyChoice.EXPEDOVANO)
        cls.unreceived = cls.make_crate(cls.make_order(cls.incoming))

    @classmethod
    def make_order(cls, incoming, outgoing=None):
        return Zakazka.objects.create(
            kamion_prijem=incoming, kamion_vydej=outgoing, artikl='ART-FAUF',
            prumer=6, delka=120, popis='SPX screws', predpis=cls.specification,
            typ_hlavy=cls.head,
        )

    @classmethod
    def make_crate(cls, order, state=StavBednyChoice.NEPRIJATO, **kwargs):
        return Bedna.objects.create(
            zakazka=order, stav_bedny=state, hmotnost=850, tara=25, mnozstvi=1,
            rovnat=RovnaniChoice.ROVNA, tryskat=TryskaniChoice.CISTA, **kwargs,
        )

    def setUp(self):
        self.client.force_login(self.superuser)
        self.crate_admin = BednaAdmin(Bedna, admin.site)
        self.truck_admin = KamionAdmin(Kamion, admin.site)

    def fauf_url(self, truck=None):
        return reverse('admin:orders_bedna_changelist', query={
            'fauf': '1', 'zakaznik': 'SPX', 'stav_bedny': StavBednyChoice.EXPEDOVANO,
            'zakazka__kamion_vydej__id__exact': (truck or self.outgoing).pk,
        })

    def post_fauf(self, crate, value, url=None, **extra):
        data = {
            'form-TOTAL_FORMS': '1', 'form-INITIAL_FORMS': '1',
            'form-0-id': str(crate.pk), 'form-0-fauf': value,
            '_save': 'Uložit', '_touched_enabled': '1',
            '_touched_field': 'form-0-fauf',
        }
        return self.client.post(url or self.fauf_url(), data | extra)

    def grant(self, codename):
        self.staff.user_permissions.add(Permission.objects.get(
            content_type__app_label='orders', codename=codename,
        ))

    def test_truck_links_select_correct_truck_and_dispatched_state(self):
        for truck, lookup in (
            (self.incoming, 'zakazka__kamion_prijem__id__exact'),
            (self.outgoing, 'zakazka__kamion_vydej__id__exact'),
        ):
            with self.subTest(truck=truck.pk):
                link = str(self.truck_admin.get_doplnit_fauf(truck))
                url = unescape(re.search(r'href="([^"]+)"', link).group(1))
                query = parse_qs(urlsplit(url).query)
                self.assertEqual(query[lookup], [str(truck.pk)])
                self.assertEqual(query['fauf'], ['1'])
                self.assertNotIn('chemie', query)
                if truck.prijem_vydej == KamionChoice.VYDEJ:
                    self.assertEqual(query['stav_bedny'], ['EX'])
                else:
                    self.assertNotIn('stav_bedny', query)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                ids = set(response.context['cl'].queryset.values_list('pk', flat=True))
                if truck.prijem_vydej == KamionChoice.VYDEJ:
                    self.assertIn(self.crate.pk, ids)
                    self.assertNotIn(self.other_crate.pk, ids)
                else:
                    self.assertIn(self.unreceived.pk, ids)

    def test_fauf_view_shows_only_spx_and_preserves_exit_filters(self):
        response = self.client.get(self.fauf_url())
        self.assertEqual(response.status_code, 200)
        columns = response.context['cl'].list_display
        self.assertEqual(columns[columns.index('zakazka_link') + 1], 'fauf')
        self.assertNotIn('poznamka', columns)
        self.assertContains(response, 'style="width: 12ch;"')
        exit_query = parse_qs(urlsplit(response.context['fauf_view_exit_url']).query)
        self.assertNotIn('fauf', exit_query)
        self.assertEqual(exit_query['stav_bedny'], ['EX'])
        self.assertEqual(exit_query['zakazka__kamion_vydej__id__exact'], [str(self.outgoing.pk)])

    def test_incoming_fauf_view_includes_unreceived_but_excludes_other_customers(self):
        incoming = Kamion.objects.create(zakaznik=self.eur, datum=date.today())
        eur_crate = self.make_crate(self.make_order(incoming))
        url = reverse('admin:orders_bedna_changelist', query={'fauf': '1'})
        response = self.client.get(url)
        ids = set(response.context['cl'].queryset.values_list('pk', flat=True))
        self.assertIn(self.unreceived.pk, ids)
        self.assertIn(self.crate.pk, ids)
        self.assertNotIn(eur_crate.pk, ids)

    def test_fauf_view_identifies_crates_by_manufacturing_order(self):
        self.crate.vyrobni_zakazka = 'WO-12345678'
        self.crate.behalter_nr = 'CONTAINER-HIDDEN'
        self.crate.save(update_fields=['vyrobni_zakazka', 'behalter_nr'])
        response = self.client.get(self.fauf_url())
        self.assertEqual(response.status_code, 200)
        columns = response.context['cl'].list_display
        self.assertEqual(columns[columns.index('get_cislo_bedny') + 1], 'vyrobni_zakazka')
        self.assertEqual(columns[columns.index('zakazka_link') + 1], 'fauf')
        self.assertNotIn('behalter_nr', columns)
        self.assertContains(response, 'WO-12345678')
        self.assertNotContains(response, 'CONTAINER-HIDDEN')
        self.assertNotContains(response, 'name="form-0-vyrobni_zakazka"')

    def test_manufacturing_order_column_is_present_in_all_fauf_states_only(self):
        for state in (None, 'NE', 'PR', 'ZK', 'EX'):
            with self.subTest(state=state):
                params = {'fauf': '1'}
                if state:
                    params['stav_bedny'] = state
                request = RequestFactory().get(reverse('admin:orders_bedna_changelist'), params)
                request.user = self.superuser
                columns = self.crate_admin.get_list_display(request)
                self.assertEqual(columns.count('vyrobni_zakazka'), 1)
                self.assertNotIn('behalter_nr', columns)
        request = RequestFactory().get(reverse('admin:orders_bedna_changelist'))
        request.user = self.superuser
        columns = self.crate_admin.get_list_display(request)
        self.assertIn('behalter_nr', columns)
        self.assertNotIn('vyrobni_zakazka', columns)

    def test_only_fauf_is_saved_on_dispatched_crate_with_history(self):
        response = self.post_fauf(
            self.crate, '12345678', **{'form-0-poznamka': 'tampered', 'form-0-stav_bedny': 'NE'},
        )
        self.assertEqual(response.status_code, 302)
        self.crate.refresh_from_db()
        self.assertEqual(self.crate.fauf, 12345678)
        self.assertEqual(self.crate.stav_bedny, StavBednyChoice.EXPEDOVANO)
        self.assertIsNone(self.crate.poznamka)
        history = self.crate.history.first()
        self.assertEqual(history.fauf, 12345678)
        self.assertEqual(history.history_user_id, self.superuser.pk)
        self.second_crate.refresh_from_db()
        self.assertIsNone(self.second_crate.fauf)

    def test_staff_requires_dispatched_permission(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.fauf_url())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="form-0-fauf"')
        self.post_fauf(self.crate, '12345678')
        self.crate.refresh_from_db()
        self.assertIsNone(self.crate.fauf)
        self.grant('change_expedovana_bedna')
        self.assertEqual(self.post_fauf(self.crate, '12345678').status_code, 302)
        self.crate.refresh_from_db()
        self.assertEqual(self.crate.fauf, 12345678)

    def test_bulk_fauf_updates_save_both_rows(self):
        response = self.post_fauf(self.crate, '12345678', **{
            'form-TOTAL_FORMS': '2', 'form-INITIAL_FORMS': '2',
            'form-1-id': str(self.second_crate.pk), 'form-1-fauf': '87654321',
            '_touched_field': ['form-0-fauf', 'form-1-fauf'],
        })
        self.assertEqual(response.status_code, 302)
        self.crate.refresh_from_db()
        self.second_crate.refresh_from_db()
        self.assertEqual((self.crate.fauf, self.second_crate.fauf), (12345678, 87654321))

    def test_permission_is_rechecked_against_current_locked_crate(self):
        self.client.force_login(self.staff)
        self.grant('change_expedovana_bedna')
        original_clean = BednaChangeListForm.clean

        def pause_after_validation(form):
            result = original_clean(form)
            Bedna.objects.filter(pk=form.instance.pk).update(pozastaveno=True)
            return result

        with patch.object(BednaChangeListForm, 'clean', pause_after_validation):
            response = self.post_fauf(self.crate, '12345678')
        self.assertEqual(response.status_code, 403)
        self.crate.refresh_from_db()
        self.assertIsNone(self.crate.fauf)

    def test_unreceived_note_permission_does_not_allow_fauf(self):
        self.client.force_login(self.staff)
        self.grant('change_poznamka_neprijata_bedna')
        url = reverse('admin:orders_bedna_changelist', query={'fauf': '1', 'stav_bedny': 'NE'})
        self.post_fauf(self.unreceived, '12345678', url)
        self.unreceived.refresh_from_db()
        self.assertIsNone(self.unreceived.fauf)
        self.grant('change_neprijata_bedna')
        self.assertEqual(self.post_fauf(self.unreceived, '12345678', url).status_code, 302)
        self.unreceived.refresh_from_db()
        self.assertEqual(self.unreceived.fauf, 12345678)

    def test_other_truck_id_cannot_be_updated(self):
        self.post_fauf(self.other_crate, '12345678')
        self.other_crate.refresh_from_db()
        self.assertIsNone(self.other_crate.fauf)

    def test_paused_dispatched_crate_requires_both_special_permissions(self):
        self.crate.pozastaveno = True
        self.crate.save(update_fields=['pozastaveno'])
        self.client.force_login(self.staff)
        self.grant('change_expedovana_bedna')
        self.post_fauf(self.crate, '12345678')
        self.crate.refresh_from_db()
        self.assertIsNone(self.crate.fauf)
        self.grant('change_pozastavena_bedna')
        self.assertEqual(self.post_fauf(self.crate, '12345678').status_code, 302)
        self.crate.refresh_from_db()
        self.assertEqual(self.crate.fauf, 12345678)

    def test_ordinary_dispatched_list_remains_readonly(self):
        response = self.client.get(reverse('admin:orders_bedna_changelist'), {'stav_bedny': 'EX'})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['cl'].formset)

    def test_invalid_integer_rejected_and_blank_clears_fauf(self):
        for value in ('-1', '1.5', 'abc', '2147483648'):
            with self.subTest(value=value):
                self.assertEqual(self.post_fauf(self.crate, value).status_code, 200)
                self.crate.refresh_from_db()
                self.assertIsNone(self.crate.fauf)
        self.post_fauf(self.crate, '12345678')
        self.assertEqual(self.post_fauf(self.crate, '').status_code, 302)
        self.crate.refresh_from_db()
        self.assertIsNone(self.crate.fauf)

    def test_chemistry_transition_removes_fauf(self):
        request = RequestFactory().get(self.fauf_url() + '&chemie=1')
        request.user = self.superuser
        self.assertFalse(self.crate_admin._is_chemistry_view(request))
        query = parse_qs(urlsplit(self.crate_admin._get_chemistry_view_toggle_url(request)).query)
        self.assertNotIn('fauf', query)
        self.assertEqual(query['chemie'], ['1'])
        self.assertEqual(query['stav_bedny'], ['EX'])

    @patch('orders.views.utilita_tisk_dl_a_proforma_faktury')
    def test_missing_fauf_warning_and_explicit_pdf_continuation(self, pdf):
        pdf.return_value = HttpResponse(b'%PDF', content_type='application/pdf')
        url = reverse('dodaci_list_kamion_vydej_pdf', args=[self.outgoing.pk])
        response = self.client.get(url)
        self.assertTemplateUsed(response, 'orders/dodaci_list_fauf_upozorneni.html')
        self.assertEqual(response.context['missing_fauf_count'], 2)
        pdf.assert_not_called()
        edit_url = response.context['doplnit_fauf_url']
        self.assertEqual(parse_qs(urlsplit(edit_url).query)['stav_bedny'], ['EX'])
        edit_response = self.client.get(edit_url)
        self.assertEqual(set(edit_response.context['cl'].queryset), {self.crate, self.second_crate})
        continued = self.client.get(response.context['pdf_url'])
        self.assertEqual(continued['Content-Type'], 'application/pdf')
        pdf.assert_called_once()

    @patch('orders.views.utilita_tisk_dl_a_proforma_faktury')
    def test_complete_fauf_and_other_customers_open_pdf_directly(self, pdf):
        pdf.return_value = HttpResponse(b'%PDF', content_type='application/pdf')
        Bedna.objects.filter(zakazka=self.order).update(fauf=12345678)
        url = reverse('dodaci_list_kamion_vydej_pdf', args=[self.outgoing.pk])
        self.assertEqual(self.client.get(url)['Content-Type'], 'application/pdf')
        self.outgoing.zakaznik = self.eur
        self.outgoing.save()
        Bedna.objects.filter(zakazka=self.order).update(fauf=None)
        self.assertEqual(self.client.get(url)['Content-Type'], 'application/pdf')
        self.assertEqual(pdf.call_count, 2)

    def test_warning_lists_only_first_twenty_crates(self):
        for _ in range(19):
            self.make_crate(self.order, StavBednyChoice.EXPEDOVANO)
        response = self.client.get(reverse('dodaci_list_kamion_vydej_pdf', args=[self.outgoing.pk]))
        self.assertEqual(response.context['missing_fauf_count'], 21)
        self.assertEqual(len(response.context['missing_fauf_numbers']), 20)

    def test_pdf_template_prints_plain_fauf_instead_of_container(self):
        self.crate.fauf = 12345678
        self.crate.behalter_nr = 'CONTAINER-OMITTED'
        self.crate.save()
        html = render_to_string('orders/dodaci_list/dodaci_list_spx.html', {'kamion': self.outgoing})
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S)
        cells = [re.findall(r'<td[^>]*>(.*?)</td>', row, re.S) for row in rows]
        self.assertEqual(cells[0][1:4], ['Beleg-Nr.', 'FAUF', 'Material-Nr.'])
        self.assertTrue(all(len(row) == 11 for row in cells))
        self.assertEqual([row[2] for row in cells[1:]], ['12345678', ''])
        self.assertNotIn('CONTAINER-OMITTED', html)
