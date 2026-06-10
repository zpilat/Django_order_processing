from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone
from django.template.loader import render_to_string
from datetime import date, time, timedelta
from decimal import Decimal

from orders.models import (
	Zakaznik, Odberatel, Kamion, Zakazka, Bedna, Predpis, TypHlavy, Pozice, PoziceZakazkaOrder, Zarizeni, Sarze, SarzeKrok, SarzeKrokBedna
)
from orders.choices import StavBednyChoice, KamionChoice, TryskaniChoice, RovnaniChoice, PrioritaChoice, TypZarizeniChoice
from orders.views import (
	_get_bedny_k_navezeni_groups,
	_split_bedny_k_navezeni_groups_by_nasledne,
	_build_vyroba_dashboard_context,
	_build_vyroba_historie_context,
)


class ViewsTestBase(TestCase):
	def setUp(self):
		# User and login
		User = get_user_model()
		self.user = User.objects.create_user(username="tester", password="pass1234")
		self.client.login(username="tester", password="pass1234")

		# Basic data
		self.z_eur = Zakaznik.objects.create(nazev="Eurotec", zkraceny_nazev="EUR", zkratka="EUR", ciselna_rada=100000)
		self.z_abc = Zakaznik.objects.create(nazev="Abc", zkraceny_nazev="ABC", zkratka="ABC", ciselna_rada=200000)
		self.odberatel = Odberatel.objects.create(nazev="O1", zkraceny_nazev="O1", zkratka="O1")
		self.typ = TypHlavy.objects.create(nazev="T")
		self.predpis_eur = Predpis.objects.create(nazev="P1", zakaznik=self.z_eur)

		today = timezone.localdate()
		# Kamiony
		self.k_prijem_eur = Kamion.objects.create(zakaznik=self.z_eur, datum=today, prijem_vydej=KamionChoice.PRIJEM)
		self.k_prijem_abc = Kamion.objects.create(zakaznik=self.z_abc, datum=today, prijem_vydej=KamionChoice.PRIJEM)
		self.k_vydej_eur = Kamion.objects.create(zakaznik=self.z_eur, odberatel=self.odberatel, datum=today, prijem_vydej=KamionChoice.VYDEJ)

		# Zakázky
		self.zak_eur = Zakazka.objects.create(
			kamion_prijem=self.k_prijem_eur,
			artikl="A1",
			prumer=1,
			delka=100,
			predpis=self.predpis_eur,
			typ_hlavy=self.typ,
			celozavit=False,
			popis="eur",
			priorita=PrioritaChoice.NIZKA,
		)
		self.zak_abc = Zakazka.objects.create(
			kamion_prijem=self.k_prijem_abc,
			artikl="A2",
			prumer=1,
			delka=120,
			predpis=self.predpis_eur,
			typ_hlavy=self.typ,
			celozavit=False,
			popis="abc",
			priorita=PrioritaChoice.NIZKA,
		)
		# Zakázka pro vydej (má i kamion_prijem kvůli bezpečnému __str__ na Bedna)
		self.zak_vydej_eur = Zakazka.objects.create(
			kamion_prijem=self.k_prijem_eur,
			kamion_vydej=self.k_vydej_eur,
			artikl="A3",
			prumer=1,
			delka=130,
			predpis=self.predpis_eur,
			typ_hlavy=self.typ,
			celozavit=False,
			popis="vydej",
			priorita=PrioritaChoice.NIZKA,
		)

		# Bedny pro různé stavy
		self.b_eur_pr = Bedna.objects.create(
			zakazka=self.zak_eur,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=5,
			tara=1,
			mnozstvi=1,
			tryskat=TryskaniChoice.NEZADANO,
			rovnat=RovnaniChoice.NEZADANO,
		)
		self.b_abc_ex = Bedna.objects.create(
			zakazka=self.zak_abc,
			stav_bedny=StavBednyChoice.EXPEDOVANO,
			hmotnost=2,
			tara=1,
			mnozstvi=1,
			tryskat=TryskaniChoice.CISTA,
			rovnat=RovnaniChoice.ROVNA,
		)
		# Bedna pro vydej agregace
		self.b_vydej = Bedna.objects.create(
			zakazka=self.zak_vydej_eur,
			stav_bedny=StavBednyChoice.K_EXPEDICI,
			hmotnost=4,
			tara=1,
			mnozstvi=1,
			tryskat=TryskaniChoice.OTRYSKANA,
			rovnat=RovnaniChoice.VYROVNANA,
		)


class DashboardBednyViewTests(ViewsTestBase):
	def test_requires_login(self):
		self.client.logout()
		resp = self.client.get(reverse("dashboard_bedny"))
		self.assertEqual(resp.status_code, 302)
		self.assertIn("login", resp.url)

	def test_full_template_and_context(self):
		resp = self.client.get(reverse("dashboard_bedny"))
		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/dashboard_bedny.html")
		self.assertIn("prehled_beden_zakaznika", resp.context)
		self.assertIn("stavy_bedny_list", resp.context)
		self.assertEqual(resp.context["db_table"], "dashboard_bedny")
		# Přítomnost CELKEM v přehledu
		prehled = resp.context["prehled_beden_zakaznika"]
		self.assertIn("CELKEM", prehled)

	def test_htmx_partial_template(self):
		resp = self.client.get(reverse("dashboard_bedny"), HTTP_HX_REQUEST="true")
		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/partials/dashboard_bedny_content.html")


class DashboardKamionyViewTests(ViewsTestBase):
	def test_renders_and_aggregates(self):
		year = timezone.now().year
		yesterday = timezone.localdate() - timedelta(days=1)

		# Data for 14-day average section (import/export)
		k_prijem_avg = Kamion.objects.create(zakaznik=self.z_eur, datum=yesterday, prijem_vydej=KamionChoice.PRIJEM)
		zak_prijem_avg = Zakazka.objects.create(
			kamion_prijem=k_prijem_avg,
			artikl="AVG-IMP",
			prumer=1,
			delka=100,
			predpis=self.predpis_eur,
			typ_hlavy=self.typ,
			celozavit=False,
			popis="avg import",
			priorita=PrioritaChoice.NIZKA,
		)
		Bedna.objects.create(
			zakazka=zak_prijem_avg,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=2800,
			tara=1,
			mnozstvi=1,
		)
		Bedna.objects.create(
			zakazka=zak_prijem_avg,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=999,
			tara=1,
			mnozstvi=1,
			fakturovat=False,
		)

		k_vydej_avg = Kamion.objects.create(zakaznik=self.z_eur, odberatel=self.odberatel, datum=yesterday, prijem_vydej=KamionChoice.VYDEJ)
		zak_vydej_avg = Zakazka.objects.create(
			kamion_prijem=self.k_prijem_eur,
			kamion_vydej=k_vydej_avg,
			artikl="AVG-EXP",
			prumer=1,
			delka=100,
			predpis=self.predpis_eur,
			typ_hlavy=self.typ,
			celozavit=False,
			popis="avg export",
			priorita=PrioritaChoice.NIZKA,
		)
		Bedna.objects.create(
			zakazka=zak_vydej_avg,
			stav_bedny=StavBednyChoice.K_EXPEDICI,
			hmotnost=2520,
			tara=1,
			mnozstvi=1,
		)
		Bedna.objects.create(
			zakazka=zak_vydej_avg,
			stav_bedny=StavBednyChoice.K_EXPEDICI,
			hmotnost=888,
			tara=1,
			mnozstvi=1,
			fakturovat=False,
		)

		resp = self.client.get(reverse("dashboard_kamiony"), {"rok": year})
		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/dashboard_kamiony.html")
		data = resp.context["mesicni_pohyby"]
		prumery = resp.context["prumery_14_dni"]
		month = self.k_prijem_eur.datum.month
		eur_key = self.z_eur.zkratka
		self.assertIn(month, data)
		# pro EUR zákazníka v daném měsíci existuje příjem i výdej
		expected_prijem = Decimal("5329")
		expected_vydej = Decimal("2524")
		expected_hmotnost_krivych = Decimal("4")
		expected_procento_krivych = (expected_hmotnost_krivych / expected_vydej) * Decimal("100")
		self.assertEqual(data[month][eur_key]["prijem"], expected_prijem)
		self.assertEqual(data[month][eur_key]["vydej"], expected_vydej)
		self.assertEqual(data[month][eur_key]["hmotnost_krivych"], expected_hmotnost_krivych)
		self.assertAlmostEqual(float(data[month][eur_key]["procento_krivych"]), float(expected_procento_krivych), places=4)
		# CELKEM pro měsíc sčítá příjmy a výdeje
		self.assertGreaterEqual(data[month]["CELKEM"]["prijem"], 5)
		self.assertEqual(data[month]["CELKEM"]["hmotnost_krivych"], expected_hmotnost_krivych)
		self.assertAlmostEqual(float(data[month]["CELKEM"]["procento_krivych"]), float(expected_procento_krivych), places=4)
		self.assertEqual(data["CELKEM"][eur_key]["hmotnost_krivych"], expected_hmotnost_krivych)
		self.assertAlmostEqual(float(data["CELKEM"][eur_key]["procento_krivych"]), float(expected_procento_krivych), places=4)
		self.assertEqual(data["CELKEM"]["CELKEM"]["hmotnost_krivych"], expected_hmotnost_krivych)
		self.assertAlmostEqual(float(data["CELKEM"]["CELKEM"]["procento_krivych"]), float(expected_procento_krivych), places=4)
		self.assertAlmostEqual(float(prumery["import_t"]), 0.2, places=2)
		self.assertAlmostEqual(float(prumery["import_kamiony"]), 2.8 / 18.0, places=3)
		self.assertAlmostEqual(float(prumery["export_t"]), 0.18, places=2)
		self.assertAlmostEqual(float(prumery["export_kamiony"]), 2.52 / 18.0, places=3)

	def test_htmx_partial_template(self):
		resp = self.client.get(reverse("dashboard_kamiony"), HTTP_HX_REQUEST="true")
		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/partials/dashboard_kamiony_content.html")


class BednyKNavezeniViewTests(ViewsTestBase):
	def setUp(self):
		super().setUp()
		# Pozice a bedny K_NAVEZENI
		self.poz_a = Pozice.objects.create(kod="A", kapacita=10)
		self.poz_b = Pozice.objects.create(kod="B", kapacita=10)
		self.b_nav1 = Bedna.objects.create(
			zakazka=self.zak_eur,
			pozice=self.poz_a,
			stav_bedny=StavBednyChoice.K_NAVEZENI,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
		)
		self.b_nav2 = Bedna.objects.create(
			zakazka=self.zak_eur,
			pozice=self.poz_a,
			stav_bedny=StavBednyChoice.K_NAVEZENI,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
		)
		self.b_nav3 = Bedna.objects.create(
			zakazka=self.zak_abc,
			pozice=self.poz_b,
			stav_bedny=StavBednyChoice.K_NAVEZENI,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
		)

	def test_groups_structure(self):
		resp = self.client.get(reverse("dashboard_bedny_k_navezeni"))
		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/dashboard_bedny_k_navezeni.html")
		groups = resp.context["groups"]
		# dvě pozice A, B
		pozice_list = [g["pozice"] for g in groups]
		self.assertEqual(pozice_list, ["A", "B"])  # seřazeno podle kódu
		# a v A jsou 2 bedny v jedné zakázce
		a_group = groups[0]
		self.assertEqual(len(a_group["zakazky_group"]), 1)
		self.assertEqual(len(a_group["zakazky_group"][0]["bedny"]), 2)

	def test_groups_include_empty_positions_without_bedny(self):
		Bedna.objects.filter(pk__in=[self.b_nav1.pk, self.b_nav2.pk, self.b_nav3.pk]).update(
			stav_bedny=StavBednyChoice.PRIJATO,
			pozice=None,
		)

		groups = _get_bedny_k_navezeni_groups()
		pozice_list = [g["pozice"] for g in groups]
		self.assertEqual(pozice_list, ["A", "B"])
		self.assertEqual(groups[0]["zakazky_group"], [])
		self.assertEqual(groups[1]["zakazky_group"], [])

	def test_htmx_partial_and_pdf(self):
		# partial
		resp = self.client.get(reverse("dashboard_bedny_k_navezeni"), HTTP_HX_REQUEST="true")
		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/partials/dashboard_bedny_k_navezeni_content.html")
		# pdf
		pdf_resp = self.client.get(reverse("dashboard_bedny_k_navezeni_pdf"))
		self.assertEqual(pdf_resp.status_code, 200)
		self.assertEqual(pdf_resp["Content-Type"], "application/pdf")
		self.assertIn("inline; filename=\"bedny_k_navezeni.pdf\"", pdf_resp["Content-Disposition"]) 

	def test_get_groups_syncs_pozice_zakazka_order_table(self):
		# vytvoř ruční pořadí: jedno platné s dírou, jedno zastaralé bez beden
		PoziceZakazkaOrder.objects.create(
			pozice=self.poz_a,
			zakazka=self.zak_eur,
			poradi=3,
		)
		PoziceZakazkaOrder.objects.create(
			pozice=self.poz_b,
			zakazka=self.zak_eur,
			poradi=1,
		)

		groups = _get_bedny_k_navezeni_groups()

		orders = list(
			PoziceZakazkaOrder.objects.order_by("pozice__kod", "zakazka_id").values_list("pozice__kod", "zakazka_id", "poradi")
		)
		expected = [
			("A", self.zak_eur.id, 1),
			("B", self.zak_abc.id, 1),
		]
		self.assertEqual(orders, expected)
		# a groups reflektují aktualizovaná pořadí
		pozice_map = {group["pozice"]: group for group in groups}
		a_zakazky = pozice_map["A"]["zakazky_group"]
		self.assertEqual(a_zakazky[0]["poradi"], 1)
		b_zakazky = pozice_map["B"]["zakazky_group"]
		self.assertEqual(b_zakazky[0]["zakazka"].id, self.zak_abc.id)
		self.assertEqual(b_zakazky[0]["poradi"], 1)

	def test_dashboard_post_reorders_sequence(self):
		# přidej druhou zakázku do stejné pozice, aby bylo co posouvat
		Bedna.objects.create(
			zakazka=self.zak_abc,
			pozice=self.poz_a,
			stav_bedny=StavBednyChoice.K_NAVEZENI,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
		)
		_get_bedny_k_navezeni_groups()
		order_eur = PoziceZakazkaOrder.objects.get(pozice=self.poz_a, zakazka=self.zak_eur)
		order_abc = PoziceZakazkaOrder.objects.get(pozice=self.poz_a, zakazka=self.zak_abc)
		self.assertEqual(order_eur.poradi, 1)
		self.assertEqual(order_abc.poradi, 2)

		resp = self.client.post(
			reverse("dashboard_bedny_k_navezeni"),
			{
				"pozice_id": self.poz_a.id,
				"zakazka_id": self.zak_abc.id,
				"move": "up",
			},
		)
		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp["Location"], reverse("dashboard_bedny_k_navezeni"))
		order_eur.refresh_from_db()
		order_abc.refresh_from_db()
		self.assertEqual(order_abc.poradi, 1)
		self.assertEqual(order_eur.poradi, 2)

	def test_edge_move_down_moves_to_next_position_at_beginning(self):
		# inicializuj pořadí
		_get_bedny_k_navezeni_groups()
		order_a = PoziceZakazkaOrder.objects.get(pozice=self.poz_a, zakazka=self.zak_eur)
		order_a.poznamka_k_navezeni = "Poznámka A"
		order_a.save(update_fields=["poznamka_k_navezeni"])
		resp = self.client.post(
			reverse("dashboard_bedny_k_navezeni"),
			{
				"pozice_id": self.poz_a.id,
				"zakazka_id": self.zak_eur.id,
				"move": "down",
			},
		)
		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp["Location"], reverse("dashboard_bedny_k_navezeni"))

		# Bedny zakázky EUR se přesunuly do pozice B
		self.b_nav1.refresh_from_db()
		self.b_nav2.refresh_from_db()
		self.assertEqual(self.b_nav1.pozice_id, self.poz_b.id)
		self.assertEqual(self.b_nav2.pozice_id, self.poz_b.id)

		orders_b = list(
			PoziceZakazkaOrder.objects.filter(pozice=self.poz_b).order_by("poradi").values_list("zakazka_id", flat=True)
		)
		self.assertEqual(orders_b, [self.zak_eur.id, self.zak_abc.id])
		moved_order = PoziceZakazkaOrder.objects.get(pozice=self.poz_b, zakazka=self.zak_eur)
		self.assertEqual(moved_order.poznamka_k_navezeni, "Poznámka A")
		orders_a = list(PoziceZakazkaOrder.objects.filter(pozice=self.poz_a))
		self.assertEqual(len(orders_a), 0)

	def test_edge_move_down_merge_keeps_target_note(self):
		# Připrav stejnou zakázku i v cílové pozici B (nastane merge do jedné pozice+zakázka)
		Bedna.objects.create(
			zakazka=self.zak_eur,
			pozice=self.poz_b,
			stav_bedny=StavBednyChoice.K_NAVEZENI,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
		)

		_get_bedny_k_navezeni_groups()
		order_source = PoziceZakazkaOrder.objects.get(pozice=self.poz_a, zakazka=self.zak_eur)
		order_target = PoziceZakazkaOrder.objects.get(pozice=self.poz_b, zakazka=self.zak_eur)
		order_source.poznamka_k_navezeni = "Zdrojová poznámka"
		order_source.save(update_fields=["poznamka_k_navezeni"])
		order_target.poznamka_k_navezeni = "Cílová poznámka"
		order_target.save(update_fields=["poznamka_k_navezeni"])

		resp = self.client.post(
			reverse("dashboard_bedny_k_navezeni"),
			{
				"pozice_id": self.poz_a.id,
				"zakazka_id": self.zak_eur.id,
				"move": "down",
			},
		)
		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp["Location"], reverse("dashboard_bedny_k_navezeni"))

		merged_order = PoziceZakazkaOrder.objects.get(pozice=self.poz_b, zakazka=self.zak_eur)
		self.assertEqual(merged_order.poznamka_k_navezeni, "Cílová poznámka")

	def test_edge_move_down_merge_fills_empty_target_note_from_source(self):
		Bedna.objects.create(
			zakazka=self.zak_eur,
			pozice=self.poz_b,
			stav_bedny=StavBednyChoice.K_NAVEZENI,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
		)

		_get_bedny_k_navezeni_groups()
		order_source = PoziceZakazkaOrder.objects.get(pozice=self.poz_a, zakazka=self.zak_eur)
		order_target = PoziceZakazkaOrder.objects.get(pozice=self.poz_b, zakazka=self.zak_eur)
		order_source.poznamka_k_navezeni = "Zdrojová poznámka"
		order_source.save(update_fields=["poznamka_k_navezeni"])
		order_target.poznamka_k_navezeni = None
		order_target.save(update_fields=["poznamka_k_navezeni"])

		resp = self.client.post(
			reverse("dashboard_bedny_k_navezeni"),
			{
				"pozice_id": self.poz_a.id,
				"zakazka_id": self.zak_eur.id,
				"move": "down",
			},
		)
		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp["Location"], reverse("dashboard_bedny_k_navezeni"))

		merged_order = PoziceZakazkaOrder.objects.get(pozice=self.poz_b, zakazka=self.zak_eur)
		self.assertEqual(merged_order.poznamka_k_navezeni, "Zdrojová poznámka")

	def test_edge_move_down_preserves_nasledne_on_cross_position_move(self):
		_get_bedny_k_navezeni_groups()
		order_a = PoziceZakazkaOrder.objects.get(pozice=self.poz_a, zakazka=self.zak_eur)
		order_a.nasledne = True
		order_a.save(update_fields=["nasledne"])

		resp = self.client.post(
			reverse("dashboard_bedny_k_navezeni"),
			{
				"pozice_id": self.poz_a.id,
				"zakazka_id": self.zak_eur.id,
				"move": "down",
			},
		)
		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp["Location"], reverse("dashboard_bedny_k_navezeni"))

		moved_order = PoziceZakazkaOrder.objects.get(pozice=self.poz_b, zakazka=self.zak_eur)
		self.assertTrue(moved_order.nasledne)

	def test_edge_move_down_merge_keeps_target_nasledne(self):
		Bedna.objects.create(
			zakazka=self.zak_eur,
			pozice=self.poz_b,
			stav_bedny=StavBednyChoice.K_NAVEZENI,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
		)

		_get_bedny_k_navezeni_groups()
		order_source = PoziceZakazkaOrder.objects.get(pozice=self.poz_a, zakazka=self.zak_eur)
		order_target = PoziceZakazkaOrder.objects.get(pozice=self.poz_b, zakazka=self.zak_eur)
		order_source.nasledne = False
		order_source.save(update_fields=["nasledne"])
		order_target.nasledne = True
		order_target.save(update_fields=["nasledne"])

		resp = self.client.post(
			reverse("dashboard_bedny_k_navezeni"),
			{
				"pozice_id": self.poz_a.id,
				"zakazka_id": self.zak_eur.id,
				"move": "down",
			},
		)
		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp["Location"], reverse("dashboard_bedny_k_navezeni"))

		merged_order = PoziceZakazkaOrder.objects.get(pozice=self.poz_b, zakazka=self.zak_eur)
		self.assertTrue(merged_order.nasledne)

	def test_edge_move_up_moves_to_prev_position_at_end(self):
		# inicializuj pořadí
		_get_bedny_k_navezeni_groups()
		order_b = PoziceZakazkaOrder.objects.get(pozice=self.poz_b, zakazka=self.zak_abc)
		order_b.poznamka_k_navezeni = "Poznámka B"
		order_b.save(update_fields=["poznamka_k_navezeni"])
		resp = self.client.post(
			reverse("dashboard_bedny_k_navezeni"),
			{
				"pozice_id": self.poz_b.id,
				"zakazka_id": self.zak_abc.id,
				"move": "up",
			},
		)
		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp["Location"], reverse("dashboard_bedny_k_navezeni"))

		# Bedna zakázky ABC se přesunula do pozice A (na konec)
		self.b_nav3.refresh_from_db()
		self.assertEqual(self.b_nav3.pozice_id, self.poz_a.id)

		orders_a = list(
			PoziceZakazkaOrder.objects.filter(pozice=self.poz_a).order_by("poradi").values_list("zakazka_id", flat=True)
		)
		self.assertEqual(orders_a, [self.zak_eur.id, self.zak_abc.id])
		moved_order = PoziceZakazkaOrder.objects.get(pozice=self.poz_a, zakazka=self.zak_abc)
		self.assertEqual(moved_order.poznamka_k_navezeni, "Poznámka B")
		orders_b = list(PoziceZakazkaOrder.objects.filter(pozice=self.poz_b))
		self.assertEqual(len(orders_b), 0)

	def test_poznamka_htmx_get_and_post(self):
		_get_bedny_k_navezeni_groups()
		# GET form
		resp_get = self.client.get(
			reverse("dashboard_bedny_k_navezeni_poznamka"),
			{"pozice_id": self.poz_a.id, "zakazka_id": self.zak_eur.id, "mode": "form"},
			HTTP_HX_REQUEST="true",
		)
		self.assertEqual(resp_get.status_code, 200)
		self.assertIn("Uložit", resp_get.content.decode())

		# POST update
		note_text = "Nová poznámka"
		resp_post = self.client.post(
			reverse("dashboard_bedny_k_navezeni_poznamka"),
			{"pozice_id": self.poz_a.id, "zakazka_id": self.zak_eur.id, "poznamka": note_text},
			HTTP_HX_REQUEST="true",
		)
		self.assertEqual(resp_post.status_code, 200)
		self.assertIn(note_text, resp_post.content.decode())
		order = PoziceZakazkaOrder.objects.get(pozice=self.poz_a, zakazka=self.zak_eur)
		self.assertEqual(order.poznamka_k_navezeni, note_text)

	def test_poznamka_htmx_post_strips_whitespace_only_value(self):
		_get_bedny_k_navezeni_groups()
		resp_post = self.client.post(
			reverse("dashboard_bedny_k_navezeni_poznamka"),
			{"pozice_id": self.poz_a.id, "zakazka_id": self.zak_eur.id, "poznamka": "   "},
			HTTP_HX_REQUEST="true",
		)
		self.assertEqual(resp_post.status_code, 200)
		self.assertIn("vše", resp_post.content.decode())
		order = PoziceZakazkaOrder.objects.get(pozice=self.poz_a, zakazka=self.zak_eur)
		self.assertIsNone(order.poznamka_k_navezeni)

	def test_poznamka_pozice_htmx_get_and_post(self):
		# GET form
		resp_get = self.client.get(
			reverse("dashboard_bedny_k_navezeni_pozice_poznamka"),
			{"pozice_id": self.poz_a.id, "mode": "form"},
			HTTP_HX_REQUEST="true",
		)
		self.assertEqual(resp_get.status_code, 200)
		self.assertIn("Uložit", resp_get.content.decode())

		# POST update
		note_text = "Pozice A - k čelu"
		resp_post = self.client.post(
			reverse("dashboard_bedny_k_navezeni_pozice_poznamka"),
			{"pozice_id": self.poz_a.id, "poznamka": note_text},
			HTTP_HX_REQUEST="true",
		)
		self.assertEqual(resp_post.status_code, 200)
		self.assertIn(note_text, resp_post.content.decode())
		self.poz_a.refresh_from_db()
		self.assertEqual(self.poz_a.poznamka_k_pozici, note_text)

	def test_poznamka_pozice_htmx_post_strips_whitespace_only_value(self):
		self.poz_a.poznamka_k_pozici = "Původní"
		self.poz_a.save(update_fields=["poznamka_k_pozici"])

		resp_post = self.client.post(
			reverse("dashboard_bedny_k_navezeni_pozice_poznamka"),
			{"pozice_id": self.poz_a.id, "poznamka": "   "},
			HTTP_HX_REQUEST="true",
		)
		self.assertEqual(resp_post.status_code, 200)
		self.assertIn("Poznámka k pozici...", resp_post.content.decode())
		self.poz_a.refresh_from_db()
		self.assertIsNone(self.poz_a.poznamka_k_pozici)

	def test_groups_include_pozice_note(self):
		self.poz_a.poznamka_k_pozici = "Navezt až po čištění"
		self.poz_a.save(update_fields=["poznamka_k_pozici"])

		groups = _get_bedny_k_navezeni_groups()
		a_group = next(g for g in groups if g["pozice"] == "A")
		self.assertEqual(a_group["poznamka_k_pozici"], "Navezt až po čištění")

	def test_print_template_shows_pozice_note_only_when_non_empty(self):
		groups = _get_bedny_k_navezeni_groups()
		groups_false = [{
			"pozice": "A",
			"pozice_id": self.poz_a.id,
			"poznamka_k_pozici": "Poznámka pozice A",
			"zakazky_group": groups[0]["zakazky_group"],
		}]
		html_with_note = render_to_string("orders/print/bedny_k_navezeni_print.html", {
			"groups_false": groups_false,
			"groups_true": [],
			"current_time": timezone.now(),
		})
		self.assertIn("Poznámka pozice A", html_with_note)

		groups_false[0]["poznamka_k_pozici"] = None
		html_without_note = render_to_string("orders/print/bedny_k_navezeni_print.html", {
			"groups_false": groups_false,
			"groups_true": [],
			"current_time": timezone.now(),
		})
		self.assertNotIn("Poznámka k pozici A:", html_without_note)

	def test_split_keeps_position_note_in_now_group_even_without_bedny(self):
		groups = [{
			"pozice": "A",
			"pozice_id": self.poz_a.id,
			"poznamka_k_pozici": "Poznámka prázdné pozice",
			"zakazky_group": [],
		}]

		groups_false, groups_true = _split_bedny_k_navezeni_groups_by_nasledne(groups)
		self.assertEqual(len(groups_false), 1)
		self.assertEqual(groups_false[0]["poznamka_k_pozici"], "Poznámka prázdné pozice")
		self.assertEqual(groups_false[0]["zakazky_group"], [])
		self.assertEqual(groups_true, [])

	def test_split_hides_position_note_in_nasledne_group(self):
		groups = [{
			"pozice": "A",
			"pozice_id": self.poz_a.id,
			"poznamka_k_pozici": "Poznámka pouze pro nyní",
			"zakazky_group": [
				{"nasledne": True, "bedny": [], "zakazka": self.zak_eur},
			],
		}]

		groups_false, groups_true = _split_bedny_k_navezeni_groups_by_nasledne(groups)
		self.assertEqual(len(groups_false), 1)
		self.assertEqual(groups_false[0]["poznamka_k_pozici"], "Poznámka pouze pro nyní")
		self.assertEqual(groups_false[0]["zakazky_group"], [])
		self.assertEqual(len(groups_true), 1)
		self.assertIsNone(groups_true[0]["poznamka_k_pozici"])

	def test_groups_include_nasledne_flag(self):
		_get_bedny_k_navezeni_groups()
		order = PoziceZakazkaOrder.objects.get(pozice=self.poz_a, zakazka=self.zak_eur)
		order.nasledne = True
		order.save(update_fields=["nasledne"])

		groups = _get_bedny_k_navezeni_groups()
		a_group = next(g for g in groups if g["pozice"] == "A")
		eur_group = next(z for z in a_group["zakazky_group"] if z["zakazka"].id == self.zak_eur.id)
		self.assertTrue(eur_group["nasledne"])

	def test_nasledne_htmx_post_updates_flag(self):
		_get_bedny_k_navezeni_groups()
		resp = self.client.post(
			reverse("dashboard_bedny_k_navezeni_nasledne"),
			{"pozice_id": self.poz_a.id, "zakazka_id": self.zak_eur.id, "nasledne": "1"},
			HTTP_HX_REQUEST="true",
		)
		self.assertEqual(resp.status_code, 200)
		order = PoziceZakazkaOrder.objects.get(pozice=self.poz_a, zakazka=self.zak_eur)
		self.assertTrue(order.nasledne)

		resp_uncheck = self.client.post(
			reverse("dashboard_bedny_k_navezeni_nasledne"),
			{"pozice_id": self.poz_a.id, "zakazka_id": self.zak_eur.id},
			HTTP_HX_REQUEST="true",
		)
		self.assertEqual(resp_uncheck.status_code, 200)
		order.refresh_from_db()
		self.assertFalse(order.nasledne)


class BednyListViewTests(ViewsTestBase):
	def test_default_excludes_expedovano_and_htmx_partial(self):
		# default stav_filter=SKLAD => vyřadí EXPEDOVANO
		resp = self.client.get(reverse("bedny_list"))
		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/bedny_list.html")
		objects = list(resp.context["object_list"])
		self.assertIn(self.b_eur_pr, objects)
		self.assertNotIn(self.b_abc_ex, objects)
		# HTMX partial vrací tabulku
		resp_hx = self.client.get(reverse("bedny_list"), HTTP_HX_REQUEST="true")
		self.assertEqual(resp_hx.status_code, 200)
		self.assertTemplateUsed(resp_hx, "orders/partials/listview_table.html")

	def test_stav_and_zakaznik_filters_and_sort(self):
		# stav_filter na EXPEDOVANO
		resp_ex = self.client.get(reverse("bedny_list"), {"stav_filter": StavBednyChoice.EXPEDOVANO})
		self.assertEqual(resp_ex.status_code, 200)
		objs_ex = list(resp_ex.context["object_list"])
		self.assertIn(self.b_abc_ex, objs_ex)
		self.assertNotIn(self.b_eur_pr, objs_ex)

		# zakaznik_filter na EUR vrátí jen EURek
		resp_z = self.client.get(reverse("bedny_list"), {"zakaznik_filter": self.z_eur.zkratka})
		self.assertEqual(resp_z.status_code, 200)
		objs_z = list(resp_z.context["object_list"])
		self.assertIn(self.b_eur_pr, objs_z)

		# seřazení DESC podle id
		# vytvoříme další bednu pro EUR, aby bylo co řadit
		b2 = Bedna.objects.create(
			zakazka=self.zak_eur,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
		)
		resp_sort = self.client.get(reverse("bedny_list"), {"sort": "id", "order": "down"})
		ids = [b.id for b in resp_sort.context["object_list"]]
		self.assertEqual(ids, sorted(ids, reverse=True))


class RychleZalozeniSarzeViewTests(ViewsTestBase):
	def setUp(self):
		super().setUp()
		self.user.user_permissions.add(
			Permission.objects.get(
				content_type__app_label="orders",
				codename="add_sarze",
			),
			Permission.objects.get(
				content_type__app_label="orders",
				codename="add_sarzekrok",
			),
			Permission.objects.get(
				content_type__app_label="orders",
				codename="add_sarzekrokbedna",
			),
		)
		self.nakladani = Zarizeni.objects.create(
			kod_zarizeni="NAKL",
			nazev_zarizeni="Nakládání",
			zkraceny_nazev_zarizeni="Nakládání",
		)

	def test_requires_login(self):
		self.client.logout()
		resp = self.client.get(reverse("rychle_zalozeni_sarze"))
		self.assertEqual(resp.status_code, 302)
		self.assertIn("login", resp.url)

	def test_requires_add_permissions(self):
		self.user.user_permissions.clear()
		resp = self.client.get(reverse("rychle_zalozeni_sarze"))
		self.assertEqual(resp.status_code, 403)

	def test_get_renders_form(self):
		resp = self.client.get(reverse("rychle_zalozeni_sarze"))
		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/rychle_zalozeni_sarze.html")
		self.assertEqual(resp.context["db_table"], "rychle_zalozeni_sarze")

	def test_post_creates_sarze_and_first_step(self):
		resp = self.client.post(
			reverse("rychle_zalozeni_sarze"),
			{
				"cislo_pripravku": "12",
				"poznamka_sarze": "Poznámka k šarži",
				"datum": "2026-06-05",
				"zacatek": "06:00",
				"konec": "07:30",
				"operator": "Novak",
				"poznamka_kroku": "Poznámka k nakládání",
			},
		)
		self.assertEqual(resp.status_code, 302)

		sarze = Sarze.objects.get(cislo_pripravku=12)
		self.assertIsNotNone(sarze.cislo_sarze)
		self.assertEqual(sarze.cislo_pripravku, 12)
		self.assertTrue(sarze.aktivni)
		self.assertEqual(sarze.poznamka, "Poznámka k šarži")

		krok = SarzeKrok.objects.get(sarze=sarze)
		self.assertEqual(krok.poradi, 1)
		self.assertEqual(krok.zarizeni, self.nakladani)
		self.assertEqual(krok.operator, "Novak")
		self.assertEqual(krok.poznamka, "Poznámka k nakládání")
		self.assertEqual(
			resp["Location"],
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
		)

	def test_patro_post_saves_bedna_and_iron_and_opens_next_floor(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			konec=time(7, 30),
			operator="Novak",
		)

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
			{
				"polozky-TOTAL_FORMS": "2",
				"polozky-INITIAL_FORMS": "0",
				"polozky-MIN_NUM_FORMS": "0",
				"polozky-MAX_NUM_FORMS": "10",
				"polozky-0-bedna": str(self.b_eur_pr.pk),
				"polozky-0-procent_z_patra": "50",
				"polozky-1-popis_mimo_db": "Tyce",
				"polozky-1-zakaznik_mimo_db": "Externi zakaznik",
				"polozky-1-zakazka_mimo_db": "ZAK-1",
				"polozky-1-cislo_bedny_mimo_db": "BED-1",
				"polozky-1-procent_z_patra": "50",
				"action": "next",
			},
		)

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(
			resp["Location"],
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 2]),
		)

		items = list(SarzeKrokBedna.objects.filter(krok=krok, patro=1).order_by("pk"))
		self.assertEqual(len(items), 2)
		self.assertEqual(items[0].bedna, self.b_eur_pr)
		self.assertEqual(items[0].procent_z_patra, 50)
		self.assertIsNone(items[1].bedna)
		self.assertEqual(items[1].popis_mimo_db, "Tyce")
		self.assertEqual(items[1].zakaznik_mimo_db, "Externi zakaznik")
		self.assertEqual(items[1].zakazka_mimo_db, "ZAK-1")
		self.assertEqual(items[1].cislo_bedny_mimo_db, "BED-1")
		self.assertEqual(items[1].procent_z_patra, 50)

	def test_patro_get_renders_formset(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			konec=time(7, 30),
			operator="Novak",
		)

		resp = self.client.get(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
		)

		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/rychle_zalozeni_sarze_patro.html")
		self.assertEqual(resp.context["patro"], 1)
		self.assertEqual(resp.context["formset"].total_form_count(), 5)

	def test_existing_patro_get_does_not_add_extra_forms(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			konec=time(7, 30),
			operator="Novak",
		)
		SarzeKrokBedna.objects.create(
			krok=krok,
			bedna=self.b_eur_pr,
			patro=1,
			procent_z_patra=100,
		)

		resp = self.client.get(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
		)

		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp.context["formset"].initial_form_count(), 1)
		self.assertEqual(resp.context["formset"].total_form_count(), 1)

	def test_patro_finish_redirects_to_batch_summary(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			konec=time(7, 30),
			operator="Novak",
		)

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
			{
				"polozky-TOTAL_FORMS": "1",
				"polozky-INITIAL_FORMS": "0",
				"polozky-MIN_NUM_FORMS": "0",
				"polozky-MAX_NUM_FORMS": "10",
				"polozky-0-bedna": str(self.b_eur_pr.pk),
				"polozky-0-procent_z_patra": "100",
				"action": "finish",
			},
		)

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(
			resp["Location"],
			reverse("rychle_zalozeni_sarze_prehled", args=[krok.pk]),
		)

		summary = self.client.get(resp["Location"])
		self.assertEqual(summary.status_code, 200)
		self.assertTemplateUsed(summary, "orders/rychle_zalozeni_sarze_prehled.html")
		self.assertContains(summary, "100 %")


class VyrobaDashboardContextTests(TestCase):
	def setUp(self):
		self.z_eur = Zakaznik.objects.create(nazev="Eurotec", zkraceny_nazev="EUR", zkratka="EUR", ciselna_rada=100000)
		self.z_spx = Zakaznik.objects.create(nazev="SPAX", zkraceny_nazev="SPX", zkratka="SPX", ciselna_rada=300000)
		self.typ = TypHlavy.objects.create(nazev="SK")
		self.predpis_eur = Predpis.objects.create(nazev="P-EUR", zakaznik=self.z_eur)
		self.predpis_spx = Predpis.objects.create(nazev="P-SPX", zakaznik=self.z_spx)

		self.dev_xl1 = Zarizeni.objects.create(
			kod_zarizeni="TQF_XL1", nazev_zarizeni="XL1", zkraceny_nazev_zarizeni="XL1", typ_zarizeni=TypZarizeniChoice.VICEUCELOVKA
		)
		self.dev_xl2 = Zarizeni.objects.create(
			kod_zarizeni="TQF_XL2", nazev_zarizeni="XL2", zkraceny_nazev_zarizeni="XL2", typ_zarizeni=TypZarizeniChoice.VICEUCELOVKA
		)

	def _create_bedna(self, zakaznik, hmotnost):
		kamion = Kamion.objects.create(zakaznik=zakaznik, datum=date(2026, 3, 1), prijem_vydej=KamionChoice.PRIJEM)
		predpis = self.predpis_eur if zakaznik == self.z_eur else self.predpis_spx
		zakazka = Zakazka.objects.create(
			kamion_prijem=kamion,
			artikl=f"A-{zakaznik.zkratka}-{hmotnost}",
			prumer=1,
			delka=100,
			predpis=predpis,
			typ_hlavy=self.typ,
			popis="test",
		)
		return Bedna.objects.create(
			zakazka=zakazka,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=hmotnost,
			tara=1,
			mnozstvi=1,
		)

	def test_vcerejsi_produkce_vrutu_counts_only_first_use_and_by_customer(self):
		target_day = date(2026, 3, 3)
		prev_day = target_day - timedelta(days=1)

		bedna_repeat = self._create_bedna(self.z_eur, 1000)
		bedna_eur_new = self._create_bedna(self.z_eur, 1200)
		bedna_spx_new = self._create_bedna(self.z_spx, 700)

		sarze_prev = Sarze.objects.create(
			cislo_sarze=1,
			datum_zalozeni=prev_day,
			aktivni=True,
		)
		krok_prev = SarzeKrok.objects.create(
			sarze=sarze_prev,
			poradi=1,
			datum=prev_day,
			zarizeni=self.dev_xl1,
			zacatek=time(8, 0),
			operator="op",
			program="p",
		)
		SarzeKrokBedna.objects.create(krok=krok_prev, bedna=bedna_repeat, patro=1)

		sarze_day_xl1 = Sarze.objects.create(
			cislo_sarze=2,
			datum_zalozeni=target_day,
			aktivni=True,
		)
		krok_day_xl1 = SarzeKrok.objects.create(
			sarze=sarze_day_xl1,
			poradi=1,
			datum=target_day,
			zarizeni=self.dev_xl1,
			zacatek=time(7, 0),
			operator="op",
			program="p",
		)
		SarzeKrokBedna.objects.create(krok=krok_day_xl1, bedna=bedna_repeat, patro=1)
		SarzeKrokBedna.objects.create(krok=krok_day_xl1, bedna=bedna_eur_new, patro=1)
		SarzeKrokBedna.objects.create(krok=krok_day_xl1, bedna=bedna_eur_new, patro=2)

		sarze_day_xl2 = Sarze.objects.create(
			cislo_sarze=3,
			datum_zalozeni=target_day,
			aktivni=True,
		)
		krok_day_xl2 = SarzeKrok.objects.create(
			sarze=sarze_day_xl2,
			poradi=1,
			datum=target_day,
			zarizeni=self.dev_xl2,
			zacatek=time(9, 0),
			operator="op",
			program="p",
		)
		SarzeKrokBedna.objects.create(krok=krok_day_xl2, bedna=bedna_spx_new, patro=1)

		ctx = _build_vyroba_dashboard_context(date_value=target_day)
		prod = ctx["vyroba_dashboard"]["vcerejsi_produkce_vrutu"]

		self.assertEqual(prod["total_kg"], 1900)
		customer_values = {
			item["name"]: item["kg"]
			for row in prod["customer_rows"]
			for item in row
			if item
		}
		self.assertEqual(customer_values.get("EUR"), 1200)
		self.assertEqual(customer_values.get("SPX"), 700)

	def test_historie_produkce_vrutu_has_14_days_and_weekly_averages(self):
		target_day = date(2026, 3, 3)
		for idx in range(14):
			day = target_day - timedelta(days=13 - idx)
			bedna = self._create_bedna(self.z_eur, (idx + 1) * 100)
			sarze = Sarze.objects.create(
				cislo_sarze=100 + idx,
				datum_zalozeni=day,
				aktivni=True,
			)
			krok = SarzeKrok.objects.create(
				sarze=sarze,
				poradi=1,
				datum=day,
				zarizeni=self.dev_xl1,
				zacatek=time(8, 0),
				operator="op",
				program="p",
			)
			SarzeKrokBedna.objects.create(krok=krok, bedna=bedna, patro=1)

		ctx = _build_vyroba_dashboard_context(date_value=target_day)
		history = ctx["vyroba_dashboard"]["historie_produkce_vrutu"]["rows"]

		self.assertEqual(len(history), 14)
		self.assertEqual(history[0]["daily_kg"], 100)
		self.assertEqual(history[-1]["daily_kg"], 1400)
		self.assertEqual(history[0]["weekly_avg_display"], "400")
		self.assertEqual(history[7]["weekly_avg_display"], "1 100")
		self.assertEqual(history[0]["biweekly_avg_display"], "750")

	def test_vyroba_historie_yearly_average_uses_elapsed_days(self):
		today_value = date(2026, 1, 10)

		bedna_1 = self._create_bedna(self.z_eur, 1000)
		bedna_2 = self._create_bedna(self.z_spx, 500)

		# Předešlé kroky pro výpočet prostoje (prodleva) u kroků s bednami.
		sarze_prev_xl1 = Sarze.objects.create(cislo_sarze=300, datum_zalozeni=date(2026, 1, 1), aktivni=True)
		SarzeKrok.objects.create(
			sarze=sarze_prev_xl1,
			poradi=1,
			datum=date(2026, 1, 1),
			zarizeni=self.dev_xl1,
			zacatek=time(6, 0),
			konec=time(7, 0),
			operator="op",
			program="p",
		)

		sarze_1 = Sarze.objects.create(cislo_sarze=301, datum_zalozeni=date(2026, 1, 1), aktivni=True)
		krok_1 = SarzeKrok.objects.create(
			sarze=sarze_1,
			poradi=1,
			datum=date(2026, 1, 1),
			zarizeni=self.dev_xl1,
			zacatek=time(8, 0),
			operator="op",
			program="p",
		)
		SarzeKrokBedna.objects.create(krok=krok_1, bedna=bedna_1, patro=1)

		sarze_prev_xl2 = Sarze.objects.create(cislo_sarze=304, datum_zalozeni=date(2026, 1, 2), aktivni=True)
		SarzeKrok.objects.create(
			sarze=sarze_prev_xl2,
			poradi=1,
			datum=date(2026, 1, 2),
			zarizeni=self.dev_xl2,
			zacatek=time(6, 0),
			konec=time(7, 0),
			operator="op",
			program="p",
		)

		sarze_2 = Sarze.objects.create(cislo_sarze=302, datum_zalozeni=date(2026, 1, 2), aktivni=True)
		krok_2 = SarzeKrok.objects.create(
			sarze=sarze_2,
			poradi=1,
			datum=date(2026, 1, 2),
			zarizeni=self.dev_xl2,
			zacatek=time(9, 0),
			operator="op",
			program="p",
		)
		SarzeKrokBedna.objects.create(krok=krok_2, bedna=bedna_2, patro=1)

		# Krok bez bedny (typicky "železo") se nesmí započítat do vytížení roštu.
		sarze_3 = Sarze.objects.create(cislo_sarze=303, datum_zalozeni=date(2026, 1, 2), aktivni=True)
		SarzeKrok.objects.create(
			sarze=sarze_3,
			poradi=1,
			datum=date(2026, 1, 2),
			zarizeni=self.dev_xl2,
			zacatek=time(10, 0),
			operator="op",
			program="p",
		)

		ctx = _build_vyroba_historie_context(year_value=2026, today_value=today_value)
		yearly = ctx["vyroba_historie"]["yearly"]
		monthly_rows = ctx["vyroba_historie"]["monthly_rows"]
		weekly_rows = ctx["vyroba_historie"]["weekly_rows"]

		self.assertEqual(yearly["elapsed_days"], 10)
		self.assertEqual(yearly["avg"]["xl1_display"], "100")
		self.assertEqual(yearly["avg"]["xl2_display"], "50")
		self.assertEqual(yearly["avg"]["total_display"], "150")
		self.assertEqual(yearly["vytizeni_rostu"]["display"], "750")
		self.assertEqual(yearly["prostoj_avg"]["xl1_display"], "0,8")
		self.assertEqual(yearly["prostoj_avg"]["xl2_display"], "1,8")
		self.assertEqual(yearly["prostoj_avg"]["total_display"], "2,6")
		self.assertEqual(monthly_rows[0]["vytizeni_rostu"]["display"], "750")
		self.assertEqual(weekly_rows[0]["vytizeni_rostu"]["display"], "750")
		self.assertEqual(monthly_rows[0]["prostoj_avg"]["total_display"], "2,6")
		self.assertEqual(weekly_rows[0]["prostoj_avg"]["total_display"], "2,6")

	def test_vyroba_historie_month_detail_shows_only_elapsed_days(self):
		today_value = date(2026, 1, 10)

		bedna_elapsed = self._create_bedna(self.z_eur, 600)
		bedna_future = self._create_bedna(self.z_eur, 900)

		sarze_elapsed = Sarze.objects.create(cislo_sarze=401, datum_zalozeni=date(2026, 1, 5), aktivni=True)
		sarze_prev = Sarze.objects.create(cislo_sarze=400, datum_zalozeni=date(2026, 1, 5), aktivni=True)
		SarzeKrok.objects.create(
			sarze=sarze_prev,
			poradi=1,
			datum=date(2026, 1, 5),
			zarizeni=self.dev_xl1,
			zacatek=time(6, 0),
			konec=time(7, 0),
			operator="op",
			program="p",
		)
		krok_elapsed = SarzeKrok.objects.create(
			sarze=sarze_elapsed,
			poradi=1,
			datum=date(2026, 1, 5),
			zarizeni=self.dev_xl1,
			zacatek=time(8, 0),
			operator="op",
			program="p",
		)
		SarzeKrokBedna.objects.create(krok=krok_elapsed, bedna=bedna_elapsed, patro=1)

		sarze_future = Sarze.objects.create(cislo_sarze=402, datum_zalozeni=date(2026, 1, 20), aktivni=True)
		krok_future = SarzeKrok.objects.create(
			sarze=sarze_future,
			poradi=1,
			datum=date(2026, 1, 20),
			zarizeni=self.dev_xl2,
			zacatek=time(8, 0),
			operator="op",
			program="p",
		)
		SarzeKrokBedna.objects.create(krok=krok_future, bedna=bedna_future, patro=1)

		ctx = _build_vyroba_historie_context(year_value=2026, month_value=1, today_value=today_value)
		month_detail = ctx["vyroba_historie"]["month_detail"]

		self.assertEqual(len(month_detail["rows"]), 10)
		labels = [row["label"] for row in month_detail["rows"]]
		self.assertIn("05.01.2026", labels)
		self.assertNotIn("20.01.2026", labels)
		row_by_label = {row["label"]: row for row in month_detail["rows"]}
		self.assertEqual(row_by_label["05.01.2026"]["vytizeni_rostu"]["display"], "600")
		self.assertEqual(row_by_label["05.01.2026"]["prostoj_avg"]["xl1_display"], "0,8")
		self.assertEqual(row_by_label["05.01.2026"]["prostoj_avg"]["total_display"], "0,8")

	def test_vyroba_historie_weeks_start_on_monday_and_week_one_contains_jan_first(self):
		ctx = _build_vyroba_historie_context(year_value=2026, today_value=date(2026, 1, 10))
		weekly_rows = ctx["vyroba_historie"]["weekly_rows"]

		self.assertGreaterEqual(len(weekly_rows), 2)
		self.assertEqual(weekly_rows[0]["date_range"], "01.01. - 04.01.")
		self.assertEqual(weekly_rows[1]["date_range"], "05.01. - 11.01.")
		self.assertEqual(weekly_rows[0]["label"], "01")
		self.assertEqual(weekly_rows[1]["label"], "02")

	def test_vyroba_historie_prostoj_ignores_shutdown_longer_than_one_day(self):
		today_value = date(2026, 1, 10)
		bedna = self._create_bedna(self.z_eur, 500)

		sarze_prev = Sarze.objects.create(cislo_sarze=510, datum_zalozeni=date(2026, 1, 7), aktivni=True)
		SarzeKrok.objects.create(
			sarze=sarze_prev,
			poradi=1,
			datum=date(2026, 1, 7),
			zarizeni=self.dev_xl1,
			zacatek=time(6, 0),
			konec=time(7, 0),
			operator="op",
			program="p",
		)

		sarze_current = Sarze.objects.create(cislo_sarze=511, datum_zalozeni=date(2026, 1, 10), aktivni=True)
		krok_current = SarzeKrok.objects.create(
			sarze=sarze_current,
			poradi=1,
			datum=date(2026, 1, 10),
			zarizeni=self.dev_xl1,
			zacatek=time(8, 0),
			operator="op",
			program="p",
		)
		SarzeKrokBedna.objects.create(krok=krok_current, bedna=bedna, patro=1)

		ctx = _build_vyroba_historie_context(year_value=2026, month_value=1, today_value=today_value)
		month_detail = ctx["vyroba_historie"]["month_detail"]
		row_by_label = {row["label"]: row for row in month_detail["rows"]}

		self.assertEqual(row_by_label["10.01.2026"]["prostoj_avg"]["xl1_display"], "0,0")
		self.assertEqual(row_by_label["10.01.2026"]["prostoj_avg"]["total_display"], "0,0")

class VyrobaHistorieViewTests(ViewsTestBase):
	def test_historie_mesic_view_renders_detail_page(self):
		resp = self.client.get(reverse("dashboard_vyroba_historie_mesic"), {"rok": timezone.localdate().year, "mesic": 1})
		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/dashboard_vyroba_historie_mesic.html")

	def test_historie_mesic_view_redirects_without_month(self):
		resp = self.client.get(reverse("dashboard_vyroba_historie_mesic"), {"rok": timezone.localdate().year})
		self.assertEqual(resp.status_code, 302)
		self.assertIn(reverse("dashboard_vyroba_historie"), resp["Location"])

