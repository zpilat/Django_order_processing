from orders.choices import KamionChoice, RovnaniChoice, StavBednyChoice, TryskaniChoice, ZinkovaniChoice
from orders.models import Bedna, Kamion, Zakazka
from orders.services.expedice_service import expedice_beden_do_existujiciho_kamionu
from orders.tests.test_kontrola_bedny import KontrolaBednyTestBase


class MereniTvrdostiVyberTests(KontrolaBednyTestBase):
    def set_customer(self, code):
        customer = self.bedna.zakazka.kamion_prijem.zakaznik
        customer.zkratka = code
        customer.save(update_fields=['zkratka'])

    def create_bedna(self, zakazka=None):
        return Bedna.objects.create(
            zakazka=zakazka or self.bedna.zakazka,
            hmotnost=1, tara=1, mnozstvi=1,
            stav_bedny=StavBednyChoice.K_EXPEDICI,
            rovnat=RovnaniChoice.ROVNA, tryskat=TryskaniChoice.CISTA,
            zinkovat=ZinkovaniChoice.NEZINKOVAT,
        )

    def selected_ids(self, ids):
        return {
            bedna.pk for bedna in Bedna.objects.filter(pk__in=ids).select_related(
                'zakazka__kamion_prijem__zakaznik',
            ) if bedna.bedna_k_mereni_tvrdosti_a_povrchu
        }

    def test_ssh_and_swg_selection_thresholds(self):
        expected_positions = (
            (1,), (1, 2), (1, 3), (1, 4), (1, 3, 5),
            (1, 3, 6), (1, 4, 7), (1, 4, 8), (1, 4, 5, 9), (1, 5, 6, 10),
        )
        ids = [self.bedna.pk]
        for total, positions in enumerate(expected_positions, start=1):
            if total > 1:
                ids.append(self.create_bedna().pk)
            for code in ('SSH', 'SWG'):
                with self.subTest(customer=code, total=total):
                    self.set_customer(code)
                    self.assertEqual(self.selected_ids(ids), {ids[position - 1] for position in positions})

    def test_rot_selection_thresholds(self):
        self.set_customer('ROT')
        self.assertEqual(self.bedna._containers_for_measurement_ROT(0), [])
        expected_positions = (
            (1,), (1, 2), (1, 3), (1, 4), (1, 5),
            (1, 3, 6), (1, 4, 7), (1, 4, 8), (1, 5, 9), (1, 5, 10),
        )
        ids = [self.bedna.pk]
        for total, positions in enumerate(expected_positions, start=1):
            if total > 1:
                ids.append(self.create_bedna().pk)
            with self.subTest(total=total):
                self.assertEqual(self.selected_ids(ids), {ids[position - 1] for position in positions})

    def assert_selection_survives_expedice(self, code, positions):
        self.set_customer(code)
        self.bedna.hmotnost = 1
        self.bedna.tara = 1
        self.bedna.mnozstvi = 1
        self.bedna.stav_bedny = StavBednyChoice.K_EXPEDICI
        self.bedna.rovnat = RovnaniChoice.ROVNA
        self.bedna.tryskat = TryskaniChoice.CISTA
        self.bedna.zinkovat = ZinkovaniChoice.NEZINKOVAT
        self.bedna.save()
        ids = [self.bedna.pk] + [self.create_bedna().pk for _ in range(9)]
        expected_ids = {ids[position - 1] for position in positions}
        root = self.bedna.zakazka
        self.assertEqual(self.selected_ids(ids), expected_ids)

        # An unrelated order with the same article and incoming truck must stay separate.
        unrelated = Zakazka.objects.create(
            kamion_prijem=root.kamion_prijem, predpis=root.predpis, typ_hlavy=root.typ_hlavy,
            artikl=root.artikl, prumer=root.prumer, delka=root.delka, popis=root.popis,
        )
        self.create_bedna(unrelated)

        for shipment, positions_to_ship in enumerate(((1, 2, 3), (5, 6, 9), (4, 7, 8, 10)), start=1):
            with self.subTest(customer=code, shipment=shipment):
                truck = Kamion.objects.create(
                    zakaznik=root.kamion_prijem.zakaznik, datum=root.kamion_prijem.datum,
                    prijem_vydej=KamionChoice.VYDEJ,
                )
                shipped_ids = [ids[position - 1] for position in positions_to_ship]
                expedice_beden_do_existujiciho_kamionu(
                    bedny_qs=Bedna.objects.filter(pk__in=shipped_ids), kamion_vydej=truck,
                )
                self.assertEqual(self.selected_ids(ids), expected_ids)

        root.refresh_from_db()
        self.assertTrue(root.expedovano)
        self.assertEqual(root.oddelene_zakazky.count(), 2)
        self.assertEqual(root.pocet_beden, 4)
        remaining_first = Bedna.objects.get(pk=ids[3])
        self.assertEqual(remaining_first.poradi_bedny, 1)
        self.assertEqual(remaining_first.poradi_a_pocet_beden_v_puvodni_zakazce, (4, 10))

    def test_ssh_selection_survives_multiple_partial_shipments(self):
        self.assert_selection_survives_expedice('SSH', (1, 5, 6, 10))

    def test_swg_selection_survives_multiple_partial_shipments(self):
        self.assert_selection_survives_expedice('SWG', (1, 5, 6, 10))

    def test_rot_selection_survives_multiple_partial_shipments(self):
        self.assert_selection_survives_expedice('ROT', (1, 5, 10))

    def test_other_customers_measure_only_original_first_container_after_shipments(self):
        self.assert_selection_survives_expedice('EUR', (1,))

    def test_spx_still_measures_all_containers_after_shipments(self):
        self.assert_selection_survives_expedice('SPX', tuple(range(1, 11)))
