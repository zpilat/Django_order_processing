from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from orders.models import (
	Zakaznik, Odberatel, Kamion, Zakazka, Bedna, Predpis, TypHlavy, Pozice, PoziceZakazkaOrder
)
from orders.choices import StavBednyChoice, KamionChoice, TryskaniChoice, RovnaniChoice, PrioritaChoice
from orders.views import _get_bedny_k_navezeni_groups


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
		resp = self.client.get(reverse("dashboard_kamiony"), {"rok": year})
		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/dashboard_kamiony.html")
		data = resp.context["mesicni_pohyby"]
		month = self.k_prijem_eur.datum.month
		eur_key = self.z_eur.zkratka
		self.assertIn(month, data)
		# pro EUR zákazníka v daném měsíci existuje příjem i výdej
		# Pozn.: příjem sčítá všechny bedny navázané na příjmový kamion EUR v daném měsíci,
		# včetně beden ze zakázek, které mají zároveň kamion_vydej nastavený (self.b_vydej).
		expected_prijem = self.b_eur_pr.hmotnost + self.b_vydej.hmotnost
		self.assertEqual(data[month][eur_key]["prijem"], expected_prijem)
		self.assertEqual(data[month][eur_key]["vydej"], self.b_vydej.hmotnost)
		# CELKEM pro měsíc sčítá příjmy a výdeje
		self.assertGreaterEqual(data[month]["CELKEM"]["prijem"], 5)

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

