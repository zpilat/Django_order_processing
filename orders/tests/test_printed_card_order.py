from django.template.loader import render_to_string

from orders.choices import (
    KamionChoice, RovnaniChoice, StavBednyChoice, TryskaniChoice, ZinkovaniChoice,
)
from orders.models import Bedna, Kamion
from orders.services.expedice_service import expedice_beden_do_existujiciho_kamionu
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class PrintedCardOrderTests(KontrolaBednyTestBase):
    def test_all_card_templates_keep_original_order_after_partial_shipment(self):
        original_order = self.bedna.zakazka
        shipment_fields = {
            'hmotnost': 1, 'tara': 1, 'mnozstvi': 1,
            'stav_bedny': StavBednyChoice.K_EXPEDICI,
            'rovnat': RovnaniChoice.ROVNA,
            'tryskat': TryskaniChoice.CISTA,
            'zinkovat': ZinkovaniChoice.NEZINKOVAT,
        }
        for field, value in shipment_fields.items():
            setattr(self.bedna, field, value)
        self.bedna.save()
        second = Bedna.objects.create(zakazka=original_order, **shipment_fields)
        third = Bedna.objects.create(zakazka=original_order, **shipment_fields)
        departure = Kamion.objects.create(
            zakaznik=original_order.kamion_prijem.zakaznik,
            datum=original_order.kamion_prijem.datum,
            prijem_vydej=KamionChoice.VYDEJ,
        )
        expedice_beden_do_existujiciho_kamionu(
            bedny_qs=Bedna.objects.filter(pk__in=(self.bedna.pk, third.pk)),
            kamion_vydej=departure,
        )
        boxes = [(Bedna.objects.get(pk=box.pk), f'{index}/3') for index, box in enumerate(
            (self.bedna, second, third), start=1,
        )]
        self.assertEqual(original_order.bedny.count(), 1)
        self.assertNotEqual(boxes[0][0].zakazka_id, original_order.pk)

        customer = original_order.kamion_prijem.zakaznik
        for code in ('eur', 'fis', 'hpm', 'rot', 'spx', 'ssh', 'swg'):
            customer.zkratka = code.upper()
            customer.save(update_fields=['zkratka'])
            for card_type, template_name in (
                ('bedna', f'orders/karta_bedny/karta_bedny_{code}.html'),
                ('kkk', f'orders/karta_kontroly_kvality/karta_kontroly_kvality_{code}.html'),
            ):
                for box, expected_order in boxes:
                    with self.subTest(customer=code, card=card_type, box=box.pk):
                        html = render_to_string(template_name, {'bedna': box})
                        self.assertIn(expected_order, html)
