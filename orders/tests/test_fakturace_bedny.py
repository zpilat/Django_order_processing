from datetime import date
from decimal import Decimal

from django import forms
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.template.loader import render_to_string
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from orders.models import Bedna, Cena, Kamion
from orders.actions import _validate_proforma_pricing
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class FakturaceBednyTests(KontrolaBednyTestBase):
    def test_admin_creation_copies_defaults_and_explains_later_edits(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        customer.fakturovat_rovnani = True
        customer.save()
        url = reverse('admin:orders_bedna_add')
        response = self.client.get(url, {'zakazka': self.bedna.zakazka_id})
        self.assertContains(response, 'při založení převezmou ze zákazníka')
        form = response.context['adminform'].form
        self.assertNotIn('fakturovat_rovnani', form.fields)
        data = {'_save': 'Uložit'}
        for field in form:
            value = field.value()
            if isinstance(field.field.widget, forms.CheckboxInput):
                if value:
                    data[field.html_name] = 'on'
            else:
                data[field.html_name] = '' if value is None else value
        result = self.client.post(url, data)
        self.assertEqual(result.status_code, 302)
        created = Bedna.objects.exclude(pk=self.bedna.pk).get()
        self.assertTrue(created.fakturovat_rovnani)
        self.assertFalse(created.fakturovat_zinkovani)

    def test_defaults_are_copied_once_and_explicit_values_are_preserved(self):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        customer.fakturovat_rovnani = customer.fakturovat_zinkovani = True
        customer.save()
        crate = Bedna.objects.create(zakazka=self.bedna.zakazka)
        self.assertEqual((crate.fakturovat_kaleni, crate.fakturovat_rovnani, crate.fakturovat_tryskani, crate.fakturovat_zinkovani), (True, True, False, True))
        customer.fakturovat_rovnani = False
        customer.save()
        crate.save()
        crate.refresh_from_db()
        self.assertTrue(crate.fakturovat_rovnani)
        explicit = Bedna.objects.create(zakazka=crate.zakazka, fakturovat_zinkovani=False, fakturovat_rovnani=True)
        self.assertFalse(explicit.fakturovat_zinkovani)
        self.assertTrue(explicit.fakturovat_rovnani)

    def test_crate_can_bill_straightening_despite_customer_default_no(self):
        order = self.bedna.zakazka
        customer = order.kamion_prijem.zakaznik
        self.assertFalse(customer.fakturovat_rovnani)
        price = Cena.objects.create(zakaznik=customer, popis='Test', delka_min=0, delka_max=1000, cena_za_kg=3, cena_rovnani_za_kg=2)
        price.predpis.add(order.predpis)
        truck = Kamion.objects.create(zakaznik=customer, datum=date(2026, 11, 13), prijem_vydej='V')
        order.kamion_vydej = truck
        order.save()
        self.bedna.fakturovat_rovnani = True
        self.bedna.fakturovat_kaleni = False
        self.bedna.rovnat = 'VY'
        self.bedna.hmotnost = 10
        self.bedna.save()
        self.assertEqual(self.bedna.cena_rovnani_za_bednu, Decimal('20'))
        self.assertEqual(_validate_proforma_pricing(truck), [])
        for template in ('proforma_faktura_po_bednach', 'proforma_faktura_po_zakazkach'):
            html = render_to_string(f'orders/{template}.html', {'kamion': truck})
            self.assertIn('20,00', html)
        price.cena_rovnani_za_kg = None
        price.save()
        self.assertTrue(_validate_proforma_pricing(truck))


class FakturaceMigrationTests(TransactionTestCase):
    def test_complete_postgresql_migration_path_preserves_history_and_master_switch(self):
        self.assertEqual(connection.vendor, 'postgresql')
        def restore():
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
        self.addCleanup(restore)
        before = [('orders', '0248_atypicky_prubeh_a_fakturace')]
        after = [('orders', '0250_vychozi_fakturace_beden')]
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        apps = executor.loader.project_state(before).apps
        Customer = apps.get_model('orders', 'Zakaznik')
        Truck = apps.get_model('orders', 'Kamion')
        Order = apps.get_model('orders', 'Zakazka')
        Crate = apps.get_model('orders', 'Bedna')
        History = apps.get_model('orders', 'HistoricalBedna')
        customer = Customer.objects.create(nazev='Migration', zkraceny_nazev='MIG', zkratka='MIG', ciselna_rada=900000, fakturovat_rovnani=True)
        truck = Truck.objects.create(zakaznik=customer, datum=date(2026, 11, 13))
        head = apps.get_model('orders', 'TypHlavy').objects.create(nazev='Test')
        spec = apps.get_model('orders', 'Predpis').objects.create(nazev='Test', zakaznik=customer)
        order = Order.objects.create(kamion_prijem=truck, typ_hlavy=head, predpis=spec, prumer=10, delka=100)
        regular = Crate.objects.create(zakazka=order, cislo_bedny=900001, fakturovat=False, nefakturovat_tryskani=True)
        atypical = Crate.objects.create(zakazka=order, cislo_bedny=900002, atypicky_prubeh=True)
        history_fields = {field.attname for field in History._meta.fields}
        values = {field.attname: getattr(regular, field.attname) for field in Crate._meta.fields if field.attname in history_fields}
        History.objects.create(**values, history_type='+', history_date=timezone.now())
        MigrationExecutor(connection).migrate(after)
        apps = MigrationExecutor(connection).loader.project_state(after).apps
        regular = apps.get_model('orders', 'Bedna').objects.get(pk=regular.pk)
        fields = ('fakturovat_kaleni', 'fakturovat_rovnani', 'fakturovat_tryskani', 'fakturovat_zinkovani')
        self.assertEqual(tuple(getattr(regular, f) for f in fields), (True, True, False, False))
        self.assertFalse(regular.fakturovat)
        atypical = apps.get_model('orders', 'Bedna').objects.get(pk=atypical.pk)
        self.assertFalse(any(getattr(atypical, f) for f in fields))
        historical = apps.get_model('orders', 'HistoricalBedna').objects.get(id=regular.pk)
        self.assertEqual(tuple(getattr(historical, f) for f in fields), (True, True, False, True))
        self.assertFalse(apps.get_model('orders', 'Zakaznik').objects.get(pk=customer.pk).fakturovat_zinkovani)
        MigrationExecutor(connection).migrate(before)
        old = MigrationExecutor(connection).loader.project_state(before).apps.get_model('orders', 'HistoricalBedna').objects.get(id=regular.pk)
        self.assertTrue(old.nefakturovat_tryskani)
        self.assertFalse(old.nefakturovat_rovnani)
