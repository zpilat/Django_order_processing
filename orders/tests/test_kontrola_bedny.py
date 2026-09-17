from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from orders.choices import TypZkouskyChoice, UvolneniKontrolyChoice, VysledekKontrolyChoice
from orders.models import Bedna, Kamion, KontrolaBedny, MereniBedny, Predpis, TypHlavy, Zakazka, Zakaznik


class KontrolaBednyTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        zakaznik = Zakaznik.objects.create(
            nazev='Test kontroly', zkraceny_nazev='TEST', zkratka='TST', ciselna_rada=100000,
        )
        kamion = Kamion.objects.create(zakaznik=zakaznik, datum=date(2026, 9, 17))
        predpis = Predpis.objects.create(nazev='P1', zakaznik=zakaznik)
        hlava = TypHlavy.objects.create(nazev='Test')
        zakazka = Zakazka.objects.create(
            kamion_prijem=kamion, predpis=predpis, typ_hlavy=hlava,
            artikl='A1', prumer=Decimal('10'), delka=Decimal('100'), popis='Test kontroly',
        )
        cls.bedna = Bedna.objects.create(zakazka=zakazka)
        cls.user = get_user_model().objects.create_user(username='kontrolor')


class KontrolaBednyTests(KontrolaBednyTestBase):
    def measurement(self, kontrola, **overrides):
        values = dict(
            kontrola=kontrola, typ_zkousky=TypZkouskyChoice.PROHYB_PO_TZ,
            hodnota=Decimal('0.2501'), poradi=1, zmeril=self.user,
        )
        values.update(overrides)
        return MereniBedny.objects.create(**values)

    def test_bedna_can_exist_without_control(self):
        self.assertFalse(KontrolaBedny.objects.filter(bedna=self.bedna).exists())
        self.assertFalse(hasattr(self.bedna, 'kontrola'))

    def test_control_defaults_and_one_to_one(self):
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna)
        self.assertEqual(kontrola.cistota, VysledekKontrolyChoice.NEZADANO)
        self.assertEqual(kontrola.ulozeni, VysledekKontrolyChoice.NEZADANO)
        self.assertEqual(kontrola.uvolneni, UvolneniKontrolyChoice.NEROZHODNUTO)
        self.assertEqual(self.bedna.kontrola, kontrola)
        with self.assertRaises(IntegrityError), transaction.atomic():
            KontrolaBedny.objects.create(bedna=self.bedna)

    def test_multiple_values_and_independent_order_per_type(self):
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna)
        for order in range(1, 13):
            self.measurement(kontrola, poradi=order)
        self.measurement(kontrola, typ_zkousky=TypZkouskyChoice.PROHYB_PO_ROVNANI)
        self.assertEqual(kontrola.mereni.count(), 13)
        values = kontrola.mereni.filter(typ_zkousky=TypZkouskyChoice.PROHYB_PO_TZ)
        self.assertEqual(list(values.values_list('poradi', flat=True)), list(range(1, 13)))
        self.assertEqual(values.first().hodnota, Decimal('0.2501'))

    def test_duplicate_order_in_same_type_is_rejected(self):
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna)
        self.measurement(kontrola)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.measurement(kontrola)

    def test_deletion_preserves_remaining_order_and_history(self):
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna)
        self.measurement(kontrola, poradi=1)
        middle = self.measurement(kontrola, poradi=2)
        self.measurement(kontrola, poradi=3)
        deleted_id = middle.pk
        middle.delete()
        self.assertEqual(list(kontrola.mereni.values_list('poradi', flat=True)), [1, 3])
        deletion = MereniBedny.history.filter(id=deleted_id).first()
        self.assertEqual(deletion.history_type, '-')
        self.assertEqual(deletion.poradi, 2)

    def test_output_control_release_choices(self):
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna)
        for status in UvolneniKontrolyChoice:
            kontrola.uvolneni = status
            kontrola.full_clean()
            kontrola.save()
            kontrola.refresh_from_db()
            self.assertEqual(kontrola.uvolneni, status)
        self.assertEqual(
            UvolneniKontrolyChoice.labels, ['Nerozhodnuto', 'Pozastaveno', 'Uvolněno'],
        )

    def test_order_starts_at_one(self):
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.measurement(kontrola, poradi=0)

    def test_unknown_type_fails_validation(self):
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna)
        value = MereniBedny(kontrola=kontrola, typ_zkousky='unknown', hodnota=1, poradi=1)
        with self.assertRaises(ValidationError) as error:
            value.full_clean()
        self.assertIn('typ_zkousky', error.exception.message_dict)

    def test_history_preserves_previous_value_and_user(self):
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna)
        value = self.measurement(kontrola)
        value.hodnota = Decimal('0.3002')
        value._history_user = self.user
        value.save()
        self.assertEqual(value.history.count(), 2)
        self.assertEqual(value.history.first().history_user, self.user)
        self.assertEqual(value.history.last().hodnota, Decimal('0.2501'))
        kontrola.ulozeni = VysledekKontrolyChoice.OK
        kontrola.save()
        self.assertEqual(kontrola.history.last().ulozeni, VysledekKontrolyChoice.NEZADANO)

    def test_deleting_user_preserves_measurements_and_control(self):
        kontrola = KontrolaBedny.objects.create(bedna=self.bedna, uvolnil=self.user)
        value = self.measurement(kontrola)
        self.user.delete()
        kontrola.refresh_from_db()
        value.refresh_from_db()
        self.assertIsNone(kontrola.uvolnil)
        self.assertIsNone(value.zmeril)
        self.assertEqual(value.hodnota, Decimal('0.2501'))

    def test_control_protects_bedna_from_deletion(self):
        KontrolaBedny.objects.create(bedna=self.bedna)
        with self.assertRaises(ProtectedError):
            self.bedna.delete()
