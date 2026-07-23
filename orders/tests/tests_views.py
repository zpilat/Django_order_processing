from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.utils import timezone
from django.template.loader import render_to_string
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch
import json

from orders.models import (
	Zakaznik, Odberatel, Kamion, Zakazka, Bedna, Predpis, TypHlavy, Pozice, PoziceZakazkaOrder, Zarizeni, Sarze, SarzeKrok, SarzeKrokBedna, Cena
)
from orders.choices import StavBednyChoice, KamionChoice, TryskaniChoice, RovnaniChoice, PrioritaChoice, TypZarizeniChoice
from orders.views import (
	_get_bedny_k_navezeni_groups,
	_split_bedny_k_navezeni_groups_by_nasledne,
	_build_vyroba_dashboard_context,
	_build_vyroba_historie_context,
	_build_vyroba_zakaznici_vyuziti_context,
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


class AuthenticationRoutingTests(TestCase):
	def setUp(self):
		self.User = get_user_model()

	def test_home_redirects_anonymous_user_to_regular_login(self):
		response = self.client.get(reverse("home"))

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, f"{reverse('login')}?next={reverse('home')}")

	def test_home_redirects_staff_to_admin(self):
		user = self.User.objects.create_user(
			username="staff",
			password="pass1234",
			is_staff=True,
		)
		self.client.force_login(user)

		response = self.client.get(reverse("home"))

		self.assertRedirects(response, reverse("admin:index"), fetch_redirect_response=False)

	def test_home_renders_operational_overview_for_quick_batch_user(self):
		user = self.User.objects.create_user(username="quick", password="pass1234")
		user.user_permissions.add(*Permission.objects.filter(
			content_type__app_label="orders",
			codename__in=(
				"add_sarze",
				"change_sarze",
				"add_sarzekrok",
				"change_sarzekrok",
				"view_sarzekrok",
				"add_sarzekrokbedna",
				"change_sarzekrokbedna",
				"view_sarzekrokbedna",
			),
		))
		self.client.force_login(user)

		response = self.client.get(reverse("home"))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/home.html")
		self.assertContains(response, "Přehled nakládání")
		self.assertNotContains(response, "Provozní přehledy")
		self.assertNotContains(response, "Akce")
		self.assertContains(response, "Pracoviště nakládání")
		self.assertContains(response, "PRACOVIŠTĚ 1")
		self.assertContains(response, "PRACOVIŠTĚ 6")

	def test_home_renders_operational_overview_for_regular_user(self):
		user = self.User.objects.create_user(username="regular", password="pass1234")
		self.client.force_login(user)

		response = self.client.get(reverse("home"))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/home.html")
		self.assertContains(response, "Přehled nakládání")
		self.assertNotContains(response, "Provozní přehledy")
		self.assertNotContains(response, "Akce")
		self.assertNotContains(response, reverse("rychle_zalozeni_sarze"))

	def test_provozni_prehledy_renders_for_staff_user(self):
		user = self.User.objects.create_superuser(username="admin", password="pass1234")
		self.client.force_login(user)

		response = self.client.get(reverse("provozni_prehledy"))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/home.html")
		self.assertContains(response, "Přehled nakládání")

	def test_admin_index_links_to_provozni_prehledy(self):
		user = self.User.objects.create_superuser(username="admin", password="pass1234")
		self.client.force_login(user)

		response = self.client.get(reverse("admin:index"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Přehled pracovišť nakládání")
		self.assertContains(response, reverse("provozni_prehledy"))
		self.assertContains(response, "Seznam beden")
		self.assertContains(response, reverse("bedny_list"))

	def test_navbar_links_to_bedny_list_for_view_bedna_user(self):
		user = self.User.objects.create_user(username="bedny-user", password="pass1234")
		user.user_permissions.add(
			Permission.objects.get(
				content_type__app_label="orders",
				codename="view_bedna",
			)
		)
		self.client.force_login(user)

		response = self.client.get(reverse("dashboard_bedny"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Seznam beden")
		self.assertContains(response, reverse("bedny_list"))

	def test_bedny_list_requires_view_bedna_permission(self):
		user = self.User.objects.create_user(username="no-bedny", password="pass1234")
		self.client.force_login(user)

		response = self.client.get(reverse("bedny_list"))

		self.assertEqual(response.status_code, 403)

	def test_login_respects_next_parameter(self):
		user = self.User.objects.create_user(username="regular", password="pass1234")
		target = reverse("dashboard_bedny")

		response = self.client.post(
			f"{reverse('login')}?next={target}",
			{
				"username": user.username,
				"password": "pass1234",
				"next": target,
			},
		)

		self.assertRedirects(response, target, fetch_redirect_response=False)

	def test_password_change_link_is_visible_outside_home(self):
		user = self.User.objects.create_user(username="regular", password="pass1234")
		self.client.force_login(user)

		response = self.client.get(reverse("dashboard_bedny"))

		self.assertContains(response, reverse("password_change"))

	@override_settings(DEBUG=True)
	def test_navbar_marks_debug_environment(self):
		user = self.User.objects.create_user(username="regular", password="pass1234")
		self.client.force_login(user)

		response = self.client.get(reverse("dashboard_bedny"))

		self.assertContains(response, "DEV DEBUG")
		self.assertContains(response, "#7a001f")

	@override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
	def test_navbar_uses_production_colors_without_debug_badge(self):
		user = self.User.objects.create_user(username="regular", password="pass1234")
		self.client.force_login(user)

		response = self.client.get(reverse("dashboard_bedny"))

		self.assertNotContains(response, "DEV DEBUG")
		self.assertContains(response, "#214290")

	def test_logout_redirects_regular_user_to_regular_login(self):
		user = self.User.objects.create_user(username="regular", password="pass1234")
		self.client.force_login(user)

		response = self.client.post(reverse("logout"), {"next": reverse("login")})

		self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)

	def test_logout_redirects_staff_to_regular_login(self):
		user = self.User.objects.create_user(
			username="staff",
			password="pass1234",
			is_staff=True,
		)
		self.client.force_login(user)

		response = self.client.post(reverse("logout"), {"next": reverse("admin:login")})

		self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)

	def test_admin_logout_offers_regular_login(self):
		user = self.User.objects.create_user(
			username="staff-admin-logout",
			password="pass1234",
			is_staff=True,
		)
		self.client.force_login(user)

		response = self.client.post(reverse("admin:logout"))

		self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
		self.assertNotEqual(response.url, reverse("admin:login"))


class BednaScanViewTests(ViewsTestBase):
	def test_scan_detail_shows_bedna_information_without_action_permission(self):
		self.b_eur_pr.stav_bedny = StavBednyChoice.K_NAVEZENI
		self.b_eur_pr.save(update_fields=["stav_bedny"])

		response = self.client.get(reverse("bedna_scan", args=[self.b_eur_pr.cislo_bedny]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Bedna")
		self.assertContains(response, str(self.b_eur_pr.cislo_bedny))
		self.assertContains(response, "Pohyb bedny")
		self.assertContains(response, reverse("bedna_scan_pohyb", args=[self.b_eur_pr.cislo_bedny]))
		self.assertNotContains(response, "Označit navezeno")

	def test_scan_detail_shows_bedna_scanner_link_for_view_bedna_user(self):
		self.user.user_permissions.add(Permission.objects.get(codename="view_bedna"))

		response = self.client.get(reverse("bedna_scan", args=[self.b_eur_pr.cislo_bedny]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Skenování bedny")
		self.assertContains(response, reverse("bedna_skener_ctecka"))

	def test_scan_detail_shows_mark_navezeno_action_with_permission(self):
		self.b_eur_pr.stav_bedny = StavBednyChoice.K_NAVEZENI
		self.b_eur_pr.save(update_fields=["stav_bedny"])
		permission = Permission.objects.get(codename="mark_bedna_navezeno")
		self.user.user_permissions.add(permission)

		response = self.client.get(reverse("bedna_scan", args=[self.b_eur_pr.cislo_bedny]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Označit navezeno")
		self.assertContains(response, reverse("bedna_scan_navezeni", args=[self.b_eur_pr.cislo_bedny]))

	def test_scan_detail_shows_mark_zakaleno_action_with_permission(self):
		self.b_eur_pr.stav_bedny = StavBednyChoice.DO_ZPRACOVANI
		self.b_eur_pr.save(update_fields=["stav_bedny"])
		permission = Permission.objects.get(codename="mark_bedna_zakaleno")
		self.user.user_permissions.add(permission)

		response = self.client.get(reverse("bedna_scan", args=[self.b_eur_pr.cislo_bedny]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Označit zakaleno")
		self.assertContains(response, reverse("bedna_scan_zakaleno", args=[self.b_eur_pr.cislo_bedny]))

	def test_scan_detail_shows_mark_zkontrolovano_action_with_controller_permission(self):
		self.b_eur_pr.stav_bedny = StavBednyChoice.ZAKALENO
		self.b_eur_pr.save(update_fields=["stav_bedny"])
		permission = Permission.objects.get(codename="mark_bedna_zkontrolovano")
		self.user.user_permissions.add(permission)

		response = self.client.get(reverse("bedna_scan", args=[self.b_eur_pr.cislo_bedny]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Označit zkontrolováno")
		self.assertContains(response, reverse("bedna_scan_zkontrolovano", args=[self.b_eur_pr.cislo_bedny]))

	def test_scan_navezeni_get_renders_position_selection(self):
		self.b_eur_pr.stav_bedny = StavBednyChoice.K_NAVEZENI
		pozice = Pozice.objects.create(kod="A", kapacita=10)
		self.b_eur_pr.pozice = pozice
		self.b_eur_pr.save(update_fields=["stav_bedny", "pozice"])
		permission = Permission.objects.get(codename="mark_bedna_navezeno")
		self.user.user_permissions.add(permission)

		response = self.client.get(
			reverse("bedna_scan_navezeni", args=[self.b_eur_pr.cislo_bedny])
		)

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/bedna_scan_navezeni.html")
		self.assertContains(response, "Potvrdit navezení")
		self.assertContains(response, pozice.kod)

	def test_scan_navezeni_updates_prijato_bedna_state_and_position(self):
		pozice = Pozice.objects.create(kod="A", kapacita=10)
		permission = Permission.objects.get(codename="mark_bedna_navezeno")
		self.user.user_permissions.add(permission)

		response = self.client.post(
			reverse("bedna_scan_navezeni", args=[self.b_eur_pr.cislo_bedny]),
			{"action": "mark_navezeno", "pozice_id": pozice.pk},
		)

		self.assertRedirects(
			response,
			reverse("bedna_scan", args=[self.b_eur_pr.cislo_bedny]),
			fetch_redirect_response=False,
		)
		self.b_eur_pr.refresh_from_db()
		self.assertEqual(self.b_eur_pr.stav_bedny, StavBednyChoice.NAVEZENO)
		self.assertEqual(self.b_eur_pr.pozice, pozice)

	def test_scan_navezeni_can_change_position_for_k_navezeni_bedna(self):
		pozice_a = Pozice.objects.create(kod="A", kapacita=10)
		pozice_b = Pozice.objects.create(kod="B", kapacita=10)
		self.b_eur_pr.stav_bedny = StavBednyChoice.K_NAVEZENI
		self.b_eur_pr.pozice = pozice_a
		self.b_eur_pr.save(update_fields=["stav_bedny", "pozice"])
		permission = Permission.objects.get(codename="mark_bedna_navezeno")
		self.user.user_permissions.add(permission)

		response = self.client.post(
			reverse("bedna_scan_navezeni", args=[self.b_eur_pr.cislo_bedny]),
			{"action": "mark_navezeno", "pozice_id": pozice_b.pk},
		)

		self.assertRedirects(
			response,
			reverse("bedna_scan", args=[self.b_eur_pr.cislo_bedny]),
			fetch_redirect_response=False,
		)
		self.b_eur_pr.refresh_from_db()
		self.assertEqual(self.b_eur_pr.stav_bedny, StavBednyChoice.NAVEZENO)
		self.assertEqual(self.b_eur_pr.pozice, pozice_b)

	def test_scan_navezeni_redirects_mobile_to_scanner(self):
		pozice = Pozice.objects.create(kod="A", kapacita=10)
		self.b_eur_pr.stav_bedny = StavBednyChoice.K_NAVEZENI
		self.b_eur_pr.pozice = pozice
		self.b_eur_pr.save(update_fields=["stav_bedny", "pozice"])
		permission = Permission.objects.get(codename="mark_bedna_navezeno")
		self.user.user_permissions.add(permission)

		response = self.client.post(
			reverse("bedna_scan_navezeni", args=[self.b_eur_pr.cislo_bedny]),
			{"action": "mark_navezeno", "pozice_id": pozice.pk},
			HTTP_USER_AGENT=(
				"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
				"AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
			),
		)

		self.assertRedirects(
			response,
			reverse("bedna_skener"),
			fetch_redirect_response=False,
		)
		self.b_eur_pr.refresh_from_db()
		self.assertEqual(self.b_eur_pr.stav_bedny, StavBednyChoice.NAVEZENO)

	def test_scan_navezeni_requires_position(self):
		permission = Permission.objects.get(codename="mark_bedna_navezeno")
		self.user.user_permissions.add(permission)

		response = self.client.post(
			reverse("bedna_scan_navezeni", args=[self.b_eur_pr.cislo_bedny]),
			{"action": "mark_navezeno"},
		)

		self.assertRedirects(
			response,
			reverse("bedna_scan_navezeni", args=[self.b_eur_pr.cislo_bedny]),
			fetch_redirect_response=False,
		)
		self.b_eur_pr.refresh_from_db()
		self.assertEqual(self.b_eur_pr.stav_bedny, StavBednyChoice.PRIJATO)
		self.assertIsNone(self.b_eur_pr.pozice)

	def test_scan_navezeni_requires_permission(self):
		self.b_eur_pr.stav_bedny = StavBednyChoice.K_NAVEZENI
		self.b_eur_pr.save(update_fields=["stav_bedny"])

		response = self.client.post(
			reverse("bedna_scan_navezeni", args=[self.b_eur_pr.cislo_bedny]),
			{"action": "mark_navezeno", "pozice_id": 1},
		)

		self.assertEqual(response.status_code, 403)
		self.b_eur_pr.refresh_from_db()
		self.assertEqual(self.b_eur_pr.stav_bedny, StavBednyChoice.K_NAVEZENI)

	def test_scan_pohyb_renders_bedna_processing_history(self):
		sarze = Sarze.objects.create(datum_zalozeni=timezone.localdate(), cislo_pripravku=1)
		zarizeni = Zarizeni.objects.create(
			kod_zarizeni="Z1",
			nazev_zarizeni="Zařízení 1",
			zkraceny_nazev_zarizeni="Z1",
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			zarizeni=zarizeni,
			zacatek=time(6, 0),
			konec=time(7, 0),
			operator="Novak",
			program="P1",
		)
		krok_2 = SarzeKrok.objects.create(
			sarze=sarze,
			zarizeni=zarizeni,
			zacatek=time(8, 0),
			konec=time(9, 0),
			operator="Svoboda",
			program="P2",
		)
		SarzeKrokBedna.objects.create(
			krok=krok,
			bedna=self.b_eur_pr,
			patro=1,
			procent_z_patra=40,
		)
		SarzeKrokBedna.objects.create(
			krok=krok,
			bedna=self.b_abc_ex,
			patro=1,
			procent_z_patra=60,
		)
		SarzeKrokBedna.objects.create(
			krok=krok,
			bedna=self.b_eur_pr,
			patro=2,
			procent_z_patra=30,
		)
		other_bedna = Bedna.objects.create(
			zakazka=self.zak_abc,
			stav_bedny=StavBednyChoice.EXPEDOVANO,
			hmotnost=3,
			tara=1,
			mnozstvi=1,
			tryskat=TryskaniChoice.CISTA,
			rovnat=RovnaniChoice.ROVNA,
		)
		SarzeKrokBedna.objects.create(
			krok=krok,
			bedna=other_bedna,
			patro=2,
			procent_z_patra=70,
		)
		SarzeKrokBedna.objects.create(
			krok=krok_2,
			bedna=self.b_eur_pr,
			patro=1,
			procent_z_patra=100,
		)

		response = self.client.get(reverse("bedna_scan_pohyb", args=[self.b_eur_pr.cislo_bedny]))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/bedna_scan_pohyb.html")
		self.assertContains(response, "Pohyb bedny")
		self.assertContains(response, 'class="movement-header"', html=False)
		self.assertContains(response, 'data-bs-toggle="collapse"', html=False)
		self.assertContains(response, 'data-bs-target="#movement-body-1"', html=False)
		self.assertContains(response, 'aria-expanded="false"', html=False)
		self.assertContains(response, 'class="collapse"', html=False)
		self.assertContains(response, str(sarze))
		self.assertContains(response, "2 kroků")
		self.assertContains(response, "(krok 1)")
		self.assertContains(response, "(krok 2)")
		self.assertContains(response, str(self.b_eur_pr.cislo_bedny))
		self.assertContains(response, str(self.b_abc_ex.cislo_bedny))
		self.assertContains(response, str(other_bedna.cislo_bedny))
		self.assertContains(response, "Patro 1")
		self.assertContains(response, "Patro 2")
		self.assertContains(response, "40 %")
		self.assertContains(response, "60 %")
		self.assertContains(response, "30 %")
		self.assertContains(response, "70 %")
		self.assertContains(response, "100 %")
		self.assertContains(response, "Z1")
		self.assertContains(response, "Novak")
		self.assertContains(response, "Svoboda")

	def test_scan_pohyb_requires_login(self):
		self.client.logout()

		response = self.client.get(reverse("bedna_scan_pohyb", args=[self.b_eur_pr.cislo_bedny]))

		self.assertEqual(response.status_code, 302)
		self.assertIn("login", response.url)

	def test_sarze_scan_renders_steps_floors_and_bedny(self):
		sarze = Sarze.objects.create(datum_zalozeni=timezone.localdate(), cislo_pripravku=1)
		zarizeni = Zarizeni.objects.create(
			kod_zarizeni="Z1",
			nazev_zarizeni="Zařízení 1",
			zkraceny_nazev_zarizeni="Z1",
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			zarizeni=zarizeni,
			zacatek=time(6, 0),
			konec=time(7, 0),
			operator="Novak",
			program="P1",
		)
		krok_2 = SarzeKrok.objects.create(
			sarze=sarze,
			zarizeni=zarizeni,
			zacatek=time(8, 0),
			konec=time(9, 0),
			operator="Svoboda",
			program="P2",
		)
		SarzeKrokBedna.objects.create(krok=krok, bedna=self.b_eur_pr, patro=1, procent_z_patra=40)
		SarzeKrokBedna.objects.create(krok=krok, bedna=self.b_abc_ex, patro=1, procent_z_patra=60)
		SarzeKrokBedna.objects.create(krok=krok_2, bedna=self.b_eur_pr, patro=2, procent_z_patra=100)

		response = self.client.get(reverse("sarze_scan", args=[sarze.cislo_sarze]))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/sarze_scan_detail.html")
		self.assertContains(response, str(sarze))
		self.assertContains(response, "(krok 1)")
		self.assertContains(response, "(krok 2)")
		self.assertContains(response, "Patro 1")
		self.assertContains(response, "Patro 2")
		self.assertContains(response, str(self.b_eur_pr.cislo_bedny))
		self.assertContains(response, str(self.b_abc_ex.cislo_bedny))
		self.assertContains(response, "40 %")
		self.assertContains(response, "60 %")
		self.assertContains(response, "100 %")
		self.assertContains(response, "Novak")
		self.assertContains(response, "Svoboda")
		self.assertContains(response, 'data-bs-toggle="collapse"', html=False)
		self.assertContains(response, f'data-bs-target="#sarze-step-body-{krok.pk}"', html=False)
		self.assertContains(response, f'id="sarze-step-body-{krok.pk}"', html=False)
		self.assertIn("no-cache", response["Cache-Control"])
		self.assertIn("no-store", response["Cache-Control"])

	def test_sarze_scan_orders_steps_newest_first(self):
		sarze = Sarze.objects.create(datum_zalozeni=timezone.localdate(), cislo_pripravku=1)
		zarizeni = Zarizeni.objects.create(
			kod_zarizeni="Z1",
			nazev_zarizeni="Zařízení 1",
			zkraceny_nazev_zarizeni="Z1",
		)
		krok_1 = SarzeKrok.objects.create(
			sarze=sarze,
			zarizeni=zarizeni,
			zacatek=time(6, 0),
			konec=time(7, 0),
			operator="Novak",
		)
		krok_2 = SarzeKrok.objects.create(
			sarze=sarze,
			zarizeni=zarizeni,
			zacatek=time(8, 0),
			konec=time(9, 0),
			operator="Svoboda",
		)

		response = self.client.get(reverse("sarze_scan", args=[sarze.cislo_sarze]))

		self.assertEqual(
			[group["krok"].pk for group in response.context["kroky"]],
			[krok_2.pk, krok_1.pk],
		)
		content = response.content.decode(response.charset)
		self.assertLess(content.find("(krok 2)"), content.find("(krok 1)"))

	def test_sarze_skener_ctecka_requires_login(self):
		self.client.logout()

		response = self.client.get(reverse("sarze_skener_ctecka"))

		self.assertEqual(response.status_code, 302)
		self.assertIn("login", response.url)

	def test_sarze_skener_ctecka_get_renders_form(self):
		response = self.client.get(reverse("sarze_skener_ctecka"))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/sarze_skener_ctecka.html")
		self.assertContains(response, 'name="cislo_sarze"', html=False)
		self.assertContains(response, "autofocus", html=False)
		self.assertContains(response, 'type="submit"', html=False)
		self.assertContains(response, "Otevřít")

	def test_sarze_skener_ctecka_post_redirects_to_sarze_scan(self):
		sarze = Sarze.objects.create(
			cislo_sarze=25,
			datum_zalozeni=timezone.localdate(),
			cislo_pripravku=1,
		)

		response = self.client.post(
			reverse("sarze_skener_ctecka"),
			{"cislo_sarze": "S00025"},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response["Location"], reverse("sarze_scan", args=[sarze.cislo_sarze]))

	def test_sarze_skener_ctecka_post_rejects_invalid_code(self):
		response = self.client.post(
			reverse("sarze_skener_ctecka"),
			{"cislo_sarze": "ABC"},
		)

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/sarze_skener_ctecka.html")
		self.assertIn("cislo_sarze", response.context["form"].errors)
		self.assertIn(
			"Neplatné číslo šarže.",
			[str(message) for message in get_messages(response.wsgi_request)],
		)

	def test_sarze_skener_ctecka_post_redirects_back_for_missing_sarze(self):
		response = self.client.post(
			reverse("sarze_skener_ctecka"),
			{"cislo_sarze": "S99999"},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response["Location"], reverse("sarze_skener_ctecka"))
		self.assertIn(
			"Šarže 99999 neexistuje.",
			[str(message) for message in get_messages(response.wsgi_request)],
		)

	def test_bedna_skener_ctecka_requires_login(self):
		self.client.logout()

		response = self.client.get(reverse("bedna_skener_ctecka"))

		self.assertEqual(response.status_code, 302)
		self.assertIn("login", response.url)

	def test_bedna_skener_ctecka_requires_view_bedna_permission(self):
		response = self.client.get(reverse("bedna_skener_ctecka"))

		self.assertEqual(response.status_code, 403)

	def test_bedna_skener_ctecka_get_renders_form(self):
		self.user.user_permissions.add(Permission.objects.get(codename="view_bedna"))

		response = self.client.get(reverse("bedna_skener_ctecka"))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/bedna_skener_ctecka.html")
		self.assertContains(response, 'name="cislo_bedny"', html=False)
		self.assertContains(response, "autofocus", html=False)
		self.assertContains(response, 'type="submit"', html=False)
		self.assertContains(response, "Otevřít")

	def test_bedna_skener_ctecka_post_redirects_to_bedna_scan(self):
		self.user.user_permissions.add(Permission.objects.get(codename="view_bedna"))

		response = self.client.post(
			reverse("bedna_skener_ctecka"),
			{"cislo_bedny": str(self.b_eur_pr.cislo_bedny)},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response["Location"], reverse("bedna_scan", args=[self.b_eur_pr.cislo_bedny]))

	def test_bedna_skener_ctecka_post_rejects_invalid_code(self):
		self.user.user_permissions.add(Permission.objects.get(codename="view_bedna"))

		response = self.client.post(
			reverse("bedna_skener_ctecka"),
			{"cislo_bedny": "ABC"},
		)

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/bedna_skener_ctecka.html")
		self.assertIn("cislo_bedny", response.context["form"].errors)
		self.assertIn(
			"Neplatné číslo bedny.",
			[str(message) for message in get_messages(response.wsgi_request)],
		)

	def test_bedna_skener_ctecka_post_redirects_back_for_missing_bedna(self):
		self.user.user_permissions.add(Permission.objects.get(codename="view_bedna"))

		response = self.client.post(
			reverse("bedna_skener_ctecka"),
			{"cislo_bedny": "999999"},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response["Location"], reverse("bedna_skener_ctecka"))
		self.assertIn(
			"Bedna 999999 neexistuje.",
			[str(message) for message in get_messages(response.wsgi_request)],
		)

	def test_sarze_scan_shows_move_buttons_for_user_with_permissions(self):
		self.user.user_permissions.add(*Permission.objects.filter(
			codename__in=["add_sarzekrok", "add_sarzekrokbedna"],
		))
		sarze = Sarze.objects.create(datum_zalozeni=timezone.localdate(), cislo_pripravku=1)
		zarizeni = Zarizeni.objects.create(
			kod_zarizeni="Z1",
			nazev_zarizeni="Zařízení 1",
			zkraceny_nazev_zarizeni="Z1",
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			zarizeni=zarizeni,
			zacatek=time(6, 0),
			konec=time(7, 0),
			operator="Novak",
		)

		response = self.client.get(reverse("sarze_scan", args=[sarze.cislo_sarze]))

		self.assertEqual(response.status_code, 200)
		move_url = reverse("sarze_scan_presunout", args=[sarze.cislo_sarze, krok.pk])
		self.assertContains(response, move_url)
		self.assertContains(response, "Přesunout do dalšího kroku")
		self.assertContains(response, "Přesunout")

	def test_sarze_scan_top_move_button_uses_newest_step(self):
		self.user.user_permissions.add(*Permission.objects.filter(
			codename__in=["add_sarzekrok", "add_sarzekrokbedna"],
		))
		sarze = Sarze.objects.create(datum_zalozeni=timezone.localdate(), cislo_pripravku=1)
		zarizeni = Zarizeni.objects.create(
			kod_zarizeni="Z1",
			nazev_zarizeni="Zařízení 1",
			zkraceny_nazev_zarizeni="Z1",
		)
		krok_1 = SarzeKrok.objects.create(
			sarze=sarze,
			zarizeni=zarizeni,
			zacatek=time(6, 0),
			konec=time(7, 0),
			operator="Novak",
		)
		krok_2 = SarzeKrok.objects.create(
			sarze=sarze,
			zarizeni=zarizeni,
			zacatek=time(8, 0),
			konec=time(9, 0),
			operator="Svoboda",
		)

		response = self.client.get(reverse("sarze_scan", args=[sarze.cislo_sarze]))

		self.assertEqual(response.context["last_krok"].pk, krok_2.pk)
		self.assertContains(
			response,
			reverse("sarze_scan_presunout", args=[sarze.cislo_sarze, krok_2.pk]),
			count=2,
		)
		self.assertContains(
			response,
			reverse("sarze_scan_presunout", args=[sarze.cislo_sarze, krok_1.pk]),
			count=1,
		)

	def test_sarze_scan_shows_fill_end_button_for_open_steps(self):
		self.user.user_permissions.add(*Permission.objects.filter(
			codename__in=["change_sarzekrok", "change_sarzekrokbedna"],
		))
		sarze = Sarze.objects.create(datum_zalozeni=timezone.localdate(), cislo_pripravku=1)
		zarizeni = Zarizeni.objects.create(
			kod_zarizeni="Z1",
			nazev_zarizeni="Zařízení 1",
			zkraceny_nazev_zarizeni="Z1",
		)
		closed_krok = SarzeKrok.objects.create(
			sarze=sarze,
			zarizeni=zarizeni,
			zacatek=time(6, 0),
			konec=time(7, 0),
			operator="Novak",
		)
		open_krok = SarzeKrok.objects.create(
			sarze=sarze,
			zarizeni=zarizeni,
			zacatek=time(8, 0),
			operator="Svoboda",
		)

		response = self.client.get(reverse("sarze_scan", args=[sarze.cislo_sarze]))

		self.assertContains(response, "Doplnit konec kroku", count=1)
		self.assertContains(
			response,
			f'{reverse("sarze_scan_change_krok", args=[sarze.cislo_sarze, open_krok.pk])}#id_konec',
		)
		self.assertNotContains(
			response,
			f'{reverse("sarze_scan_change_krok", args=[sarze.cislo_sarze, closed_krok.pk])}#id_konec',
		)

	def test_sarze_scan_move_view_get_renders_form(self):
		self.user.user_permissions.add(*Permission.objects.filter(
			codename__in=["add_sarzekrok", "add_sarzekrokbedna"],
		))
		sarze = Sarze.objects.create(datum_zalozeni=timezone.localdate(), cislo_pripravku=1)
		zarizeni = Zarizeni.objects.create(
			kod_zarizeni="Z1",
			nazev_zarizeni="Zařízení 1",
			zkraceny_nazev_zarizeni="Z1",
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			zarizeni=zarizeni,
			zacatek=time(6, 0),
			konec=time(7, 0),
			operator="Novak",
		)
		SarzeKrokBedna.objects.create(krok=krok, bedna=self.b_eur_pr, patro=1, procent_z_patra=100)

		with patch("orders.views.timezone.localtime") as localtime_mock:
			localtime_mock.return_value = datetime(2026, 7, 20, 14, 35)
			response = self.client.get(reverse("sarze_scan_presunout", args=[sarze.cislo_sarze, krok.pk]))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/sarze_scan_presunout.html")
		self.assertEqual(response.context["form"].initial["zacatek"], "14:35")
		self.assertEqual(response.context["form"].initial["operator"], "tester")
		self.assertContains(response, "Nový krok šarže")
		self.assertContains(response, "Vytvořit další krok")
		self.assertContains(response, 'name="source_row_ids"', html=False)
		self.assertContains(response, str(self.b_eur_pr.cislo_bedny))

	def test_sarze_scan_move_view_post_creates_next_step_from_selected_step(self):
		self.user.user_permissions.add(*Permission.objects.filter(
			codename__in=["add_sarzekrok", "add_sarzekrokbedna"],
		))
		sarze = Sarze.objects.create(datum_zalozeni=timezone.localdate(), cislo_pripravku=1)
		source_zarizeni = Zarizeni.objects.create(
			kod_zarizeni="Z1",
			nazev_zarizeni="Zařízení 1",
			zkraceny_nazev_zarizeni="Z1",
		)
		target_zarizeni = Zarizeni.objects.create(
			kod_zarizeni="Z2",
			nazev_zarizeni="Zařízení 2",
			zkraceny_nazev_zarizeni="Z2",
		)
		source_krok = SarzeKrok.objects.create(
			sarze=sarze,
			zarizeni=source_zarizeni,
			zacatek=time(6, 0),
			konec=time(7, 0),
			operator="Novak",
		)
		row_1 = SarzeKrokBedna.objects.create(krok=source_krok, bedna=self.b_eur_pr, patro=1, procent_z_patra=40)
		row_2 = SarzeKrokBedna.objects.create(krok=source_krok, bedna=self.b_abc_ex, patro=1, procent_z_patra=60)

		response = self.client.post(
			reverse("sarze_scan_presunout", args=[sarze.cislo_sarze, source_krok.pk]),
			{
				"_sarzekrok_action_token": "scanmove000000000000000000000001",
				"datum": "2026-06-30",
				"zarizeni": target_zarizeni.pk,
				"zacatek": "08:00",
				"konec": "09:00",
				"operator": "Svoboda",
				"program": "P2",
				"alarm": "",
				"poznamka": "scan",
				"source_row_ids": [str(row_1.pk), str(row_2.pk)],
			},
		)

		self.assertRedirects(response, reverse("sarze_scan", args=[sarze.cislo_sarze]))
		target_krok = SarzeKrok.objects.get(sarze=sarze, poradi=2)
		self.assertEqual(target_krok.zarizeni, target_zarizeni)
		self.assertEqual(target_krok.operator, "Svoboda")
		copied_rows = list(target_krok.krok_bedny.order_by("bedna__cislo_bedny"))
		self.assertEqual(len(copied_rows), 2)
		self.assertEqual(copied_rows[0].bedna, self.b_eur_pr)
		self.assertEqual(copied_rows[0].patro, 1)
		self.assertEqual(copied_rows[0].procent_z_patra, 40)
		self.assertEqual(copied_rows[1].bedna, self.b_abc_ex)
		self.assertEqual(copied_rows[1].procent_z_patra, 60)

	def test_sarze_scan_move_view_post_copies_only_selected_rows(self):
		self.user.user_permissions.add(*Permission.objects.filter(
			codename__in=["add_sarzekrok", "add_sarzekrokbedna"],
		))
		sarze = Sarze.objects.create(datum_zalozeni=timezone.localdate(), cislo_pripravku=1)
		source_zarizeni = Zarizeni.objects.create(
			kod_zarizeni="Z1",
			nazev_zarizeni="ZaĹ™Ă­zenĂ­ 1",
			zkraceny_nazev_zarizeni="Z1",
		)
		target_zarizeni = Zarizeni.objects.create(
			kod_zarizeni="Z2",
			nazev_zarizeni="ZaĹ™Ă­zenĂ­ 2",
			zkraceny_nazev_zarizeni="Z2",
		)
		source_krok = SarzeKrok.objects.create(
			sarze=sarze,
			zarizeni=source_zarizeni,
			zacatek=time(6, 0),
			konec=time(7, 0),
			operator="Novak",
		)
		selected_row = SarzeKrokBedna.objects.create(krok=source_krok, bedna=self.b_eur_pr, patro=1, procent_z_patra=40)
		SarzeKrokBedna.objects.create(krok=source_krok, bedna=self.b_abc_ex, patro=1, procent_z_patra=60)

		response = self.client.post(
			reverse("sarze_scan_presunout", args=[sarze.cislo_sarze, source_krok.pk]),
			{
				"_sarzekrok_action_token": "scanmove000000000000000000000002",
				"datum": "2026-06-30",
				"zarizeni": target_zarizeni.pk,
				"zacatek": "08:00",
				"konec": "09:00",
				"operator": "Svoboda",
				"program": "P2",
				"alarm": "",
				"poznamka": "scan",
				"source_row_ids": [str(selected_row.pk)],
			},
		)

		self.assertRedirects(response, reverse("sarze_scan", args=[sarze.cislo_sarze]))
		target_krok = SarzeKrok.objects.get(sarze=sarze, poradi=2)
		copied_rows = list(target_krok.krok_bedny.order_by("pk"))
		self.assertEqual(len(copied_rows), 1)
		self.assertEqual(copied_rows[0].bedna, self.b_eur_pr)
		self.assertEqual(copied_rows[0].procent_z_patra, 40)

	def test_sarze_scan_change_krok_view_get_renders_form_and_bedny(self):
		self.user.user_permissions.add(*Permission.objects.filter(
			codename__in=["change_sarzekrok", "change_sarzekrokbedna"],
		))
		sarze = Sarze.objects.create(datum_zalozeni=timezone.localdate(), cislo_pripravku=1)
		zarizeni = Zarizeni.objects.create(
			kod_zarizeni="Z1",
			nazev_zarizeni="Zařízení 1",
			zkraceny_nazev_zarizeni="Z1",
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			zarizeni=zarizeni,
			zacatek=time(6, 0),
			konec=time(7, 0),
			operator="Novak",
			program="P1",
		)
		SarzeKrokBedna.objects.create(krok=krok, bedna=self.b_eur_pr, patro=1, procent_z_patra=100)

		response = self.client.get(reverse("sarze_scan_change_krok", args=[sarze.cislo_sarze, krok.pk]))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/sarze_scan_change_krok.html")
		self.assertContains(response, "Údaje kroku")
		self.assertContains(response, "Bedny v kroku")
		self.assertContains(response, str(self.b_eur_pr.cislo_bedny))
		self.assertContains(response, 'name="delete_row_ids"', html=False)

	def test_sarze_scan_change_krok_view_post_updates_krok_and_deletes_selected_rows(self):
		self.user.user_permissions.add(*Permission.objects.filter(
			codename__in=["change_sarzekrok", "change_sarzekrokbedna"],
		))
		sarze = Sarze.objects.create(datum_zalozeni=timezone.localdate(), cislo_pripravku=1)
		zarizeni = Zarizeni.objects.create(
			kod_zarizeni="Z1",
			nazev_zarizeni="Zařízení 1",
			zkraceny_nazev_zarizeni="Z1",
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			zarizeni=zarizeni,
			zacatek=time(6, 0),
			konec=time(7, 0),
			operator="Novak",
			program="P1",
		)
		deleted_row = SarzeKrokBedna.objects.create(krok=krok, bedna=self.b_eur_pr, patro=1, procent_z_patra=40)
		kept_row = SarzeKrokBedna.objects.create(krok=krok, bedna=self.b_abc_ex, patro=1, procent_z_patra=60)

		response = self.client.post(
			reverse("sarze_scan_change_krok", args=[sarze.cislo_sarze, krok.pk]),
			{
				"datum": "2026-06-30",
				"zarizeni": zarizeni.pk,
				"zacatek": "08:00",
				"konec": "09:00",
				"operator": "Svoboda",
				"program": "P2",
				"alarm": "A1",
				"poznamka": "upraveno",
				"delete_row_ids": [str(deleted_row.pk)],
			},
		)

		self.assertRedirects(response, reverse("sarze_scan", args=[sarze.cislo_sarze]))
		krok.refresh_from_db()
		self.assertEqual(krok.operator, "Svoboda")
		self.assertEqual(krok.program, "P2")
		self.assertEqual(krok.alarm, "A1")
		self.assertFalse(SarzeKrokBedna.objects.filter(pk=deleted_row.pk).exists())
		self.assertTrue(SarzeKrokBedna.objects.filter(pk=kept_row.pk).exists())

	def test_sarze_scan_requires_login(self):
		sarze = Sarze.objects.create(datum_zalozeni=timezone.localdate(), cislo_pripravku=1)
		self.client.logout()

		response = self.client.get(reverse("sarze_scan", args=[sarze.cislo_sarze]))

		self.assertEqual(response.status_code, 302)
		self.assertIn("login", response.url)

	def test_bedna_skener_requires_login(self):
		self.client.logout()

		response = self.client.get(reverse("bedna_skener"))

		self.assertEqual(response.status_code, 302)
		self.assertIn("login", response.url)

	def test_bedna_skener_renders_scanner_page(self):
		response = self.client.get(reverse("bedna_skener"))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/bedna_skener.html")
		self.assertContains(response, "Skener")
		self.assertContains(response, "html5-qrcode")
		self.assertContains(response, "scan_parser.js")
		self.assertContains(response, reverse("sarze_scan", args=[0]))
		self.assertContains(response, reverse("rychle_zalozeni_sarze_pracoviste_prehled", args=[0]))

	def _set_bedna_zkontrolovano_ready(self):
		"""Nastaví b_eur_pr do stavu ZAKALENO a přidá oprávnění kontrolora."""
		self.b_eur_pr.stav_bedny = StavBednyChoice.ZAKALENO
		self.b_eur_pr.rovnat = RovnaniChoice.NEZADANO
		self.b_eur_pr.tryskat = TryskaniChoice.NEZADANO
		self.b_eur_pr.save(update_fields=["stav_bedny", "rovnat", "tryskat"])
		permission = Permission.objects.get(codename="mark_bedna_zkontrolovano")
		self.user.user_permissions.add(permission)

	def _set_bedna_zakaleno_ready(self):
		self.b_eur_pr.stav_bedny = StavBednyChoice.DO_ZPRACOVANI
		self.b_eur_pr.save(update_fields=["stav_bedny"])
		permission = Permission.objects.get(codename="mark_bedna_zakaleno")
		self.user.user_permissions.add(permission)

	def test_scan_zakaleno_get_renders_confirmation(self):
		self._set_bedna_zakaleno_ready()

		response = self.client.get(
			reverse("bedna_scan_zakaleno", args=[self.b_eur_pr.cislo_bedny])
		)

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/bedna_scan_zakaleno.html")
		self.assertContains(response, str(self.b_eur_pr.cislo_bedny))
		self.assertContains(response, "Označit bednu jako zakalenou")

	def test_scan_zakaleno_get_requires_permission(self):
		self.b_eur_pr.stav_bedny = StavBednyChoice.DO_ZPRACOVANI
		self.b_eur_pr.save(update_fields=["stav_bedny"])

		response = self.client.get(
			reverse("bedna_scan_zakaleno", args=[self.b_eur_pr.cislo_bedny])
		)

		self.assertEqual(response.status_code, 403)

	def test_scan_zakaleno_requires_login(self):
		self.client.logout()

		response = self.client.get(
			reverse("bedna_scan_zakaleno", args=[self.b_eur_pr.cislo_bedny])
		)

		self.assertEqual(response.status_code, 302)
		self.assertIn("login", response.url)

	def test_scan_zakaleno_get_redirects_if_state_not_allowed(self):
		self.b_eur_pr.stav_bedny = StavBednyChoice.K_EXPEDICI
		self.b_eur_pr.save(update_fields=["stav_bedny"])
		permission = Permission.objects.get(codename="mark_bedna_zakaleno")
		self.user.user_permissions.add(permission)

		response = self.client.get(
			reverse("bedna_scan_zakaleno", args=[self.b_eur_pr.cislo_bedny])
		)

		self.assertRedirects(
			response,
			reverse("bedna_scan", args=[self.b_eur_pr.cislo_bedny]),
			fetch_redirect_response=False,
		)
		messages_list = list(response.wsgi_request._messages)
		self.assertTrue(any("povoleném pro změnu na zakaleno" in str(m) for m in messages_list))

	def test_scan_zakaleno_post_marks_bedna_zakaleno(self):
		self._set_bedna_zakaleno_ready()

		response = self.client.post(
			reverse("bedna_scan_zakaleno", args=[self.b_eur_pr.cislo_bedny]),
			{"action": "mark_zakaleno"},
		)

		self.assertRedirects(
			response,
			reverse("bedna_scan", args=[self.b_eur_pr.cislo_bedny]),
			fetch_redirect_response=False,
		)
		self.b_eur_pr.refresh_from_db()
		self.assertEqual(self.b_eur_pr.stav_bedny, StavBednyChoice.ZAKALENO)

	def test_scan_zkontrolovano_get_renders_form(self):
		self._set_bedna_zkontrolovano_ready()

		response = self.client.get(
			reverse("bedna_scan_zkontrolovano", args=[self.b_eur_pr.cislo_bedny])
		)

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/bedna_scan_zkontrolovano.html")
		self.assertContains(response, str(self.b_eur_pr.cislo_bedny))
		self.assertIn("form", response.context)
		self.assertIn("bedna", response.context)

	def test_scan_zkontrolovano_get_includes_current_disallowed_choices(self):
		self._set_bedna_zkontrolovano_ready()

		response = self.client.get(
			reverse("bedna_scan_zkontrolovano", args=[self.b_eur_pr.cislo_bedny])
		)

		form = response.context["form"]
		rovnat_values = [choice for choice, _label in form.fields["rovnat"].choices]
		tryskat_values = [choice for choice, _label in form.fields["tryskat"].choices]
		self.assertEqual(
			rovnat_values,
			[RovnaniChoice.NEZADANO, RovnaniChoice.ROVNA, RovnaniChoice.KRIVA],
		)
		self.assertIn(TryskaniChoice.NEZADANO, tryskat_values)

	def test_scan_zkontrolovano_get_requires_permission(self):
		self.b_eur_pr.stav_bedny = StavBednyChoice.ZAKALENO
		self.b_eur_pr.save(update_fields=["stav_bedny"])

		response = self.client.get(
			reverse("bedna_scan_zkontrolovano", args=[self.b_eur_pr.cislo_bedny])
		)

		self.assertEqual(response.status_code, 403)

	def test_scan_zkontrolovano_get_rejects_change_bedna_without_controller_permission(self):
		self.b_eur_pr.stav_bedny = StavBednyChoice.ZAKALENO
		self.b_eur_pr.save(update_fields=["stav_bedny"])
		self.user.user_permissions.add(Permission.objects.get(codename="change_bedna"))

		response = self.client.get(
			reverse("bedna_scan_zkontrolovano", args=[self.b_eur_pr.cislo_bedny])
		)

		self.assertEqual(response.status_code, 403)

	def test_scan_zkontrolovano_requires_login(self):
		self.client.logout()

		response = self.client.get(
			reverse("bedna_scan_zkontrolovano", args=[self.b_eur_pr.cislo_bedny])
		)

		self.assertEqual(response.status_code, 302)
		self.assertIn("login", response.url)

	def test_scan_zkontrolovano_get_redirects_if_pozastaveno(self):
		self.b_eur_pr.stav_bedny = StavBednyChoice.ZAKALENO
		self.b_eur_pr.pozastaveno = True
		self.b_eur_pr.save(update_fields=["stav_bedny", "pozastaveno"])
		permission = Permission.objects.get(codename="mark_bedna_zkontrolovano")
		self.user.user_permissions.add(permission)

		response = self.client.get(
			reverse("bedna_scan_zkontrolovano", args=[self.b_eur_pr.cislo_bedny])
		)

		self.assertRedirects(
			response,
			reverse("bedna_scan", args=[self.b_eur_pr.cislo_bedny]),
			fetch_redirect_response=False,
		)
		messages_list = list(response.wsgi_request._messages)
		self.assertTrue(any("pozastavená" in str(m) for m in messages_list))

	def test_scan_zkontrolovano_get_redirects_if_not_in_rozpracovanost(self):
		# b_eur_pr je ve stavu PRIJATO, který není v STAV_BEDNY_ROZPRACOVANOST
		permission = Permission.objects.get(codename="mark_bedna_zkontrolovano")
		self.user.user_permissions.add(permission)

		response = self.client.get(
			reverse("bedna_scan_zkontrolovano", args=[self.b_eur_pr.cislo_bedny])
		)

		self.assertRedirects(
			response,
			reverse("bedna_scan", args=[self.b_eur_pr.cislo_bedny]),
			fetch_redirect_response=False,
		)
		messages_list = list(response.wsgi_request._messages)
		self.assertTrue(any("rozpracovanosti" in str(m) for m in messages_list))

	def test_scan_zkontrolovano_post_marks_bedna_zkontrolovano(self):
		self._set_bedna_zkontrolovano_ready()

		response = self.client.post(
			reverse("bedna_scan_zkontrolovano", args=[self.b_eur_pr.cislo_bedny]),
			{"action": "mark_zkontrolovano", "rovnat": RovnaniChoice.ROVNA, "tryskat": TryskaniChoice.CISTA},
		)

		self.assertRedirects(
			response,
			reverse("bedna_scan", args=[self.b_eur_pr.cislo_bedny]),
			fetch_redirect_response=False,
		)
		self.b_eur_pr.refresh_from_db()
		self.assertEqual(self.b_eur_pr.stav_bedny, StavBednyChoice.ZKONTROLOVANO)
		self.assertEqual(self.b_eur_pr.rovnat, RovnaniChoice.ROVNA)
		self.assertEqual(self.b_eur_pr.tryskat, TryskaniChoice.CISTA)

	def test_scan_zkontrolovano_post_redirects_mobile_to_skener(self):
		self._set_bedna_zkontrolovano_ready()

		response = self.client.post(
			reverse("bedna_scan_zkontrolovano", args=[self.b_eur_pr.cislo_bedny]),
			{"action": "mark_zkontrolovano", "rovnat": RovnaniChoice.ROVNA, "tryskat": TryskaniChoice.CISTA},
			HTTP_USER_AGENT=(
				"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
				"AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
			),
		)

		self.assertRedirects(
			response,
			reverse("bedna_skener"),
			fetch_redirect_response=False,
		)
		self.b_eur_pr.refresh_from_db()
		self.assertEqual(self.b_eur_pr.stav_bedny, StavBednyChoice.ZKONTROLOVANO)

	def test_scan_zkontrolovano_post_invalid_action_returns_bad_request(self):
		self._set_bedna_zkontrolovano_ready()

		response = self.client.post(
			reverse("bedna_scan_zkontrolovano", args=[self.b_eur_pr.cislo_bedny]),
			{"action": "neplatna_akce", "rovnat": RovnaniChoice.ROVNA, "tryskat": TryskaniChoice.CISTA},
		)

		self.assertEqual(response.status_code, 400)
		self.b_eur_pr.refresh_from_db()
		self.assertEqual(self.b_eur_pr.stav_bedny, StavBednyChoice.ZAKALENO)

	def test_scan_zkontrolovano_post_rerenders_on_invalid_rovnat_bool(self):
		"""Rovnat=NEZADANO projde validací formuláře, ale selže při vlastní kontrole v pohledu."""
		self._set_bedna_zkontrolovano_ready()

		response = self.client.post(
			reverse("bedna_scan_zkontrolovano", args=[self.b_eur_pr.cislo_bedny]),
			{"action": "mark_zkontrolovano", "rovnat": RovnaniChoice.NEZADANO, "tryskat": TryskaniChoice.CISTA},
		)

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/bedna_scan_zkontrolovano.html")
		self.b_eur_pr.refresh_from_db()
		self.assertEqual(self.b_eur_pr.stav_bedny, StavBednyChoice.ZAKALENO)

	def test_scan_zkontrolovano_post_rerenders_on_invalid_tryskat_bool(self):
		"""Tryskat=NEZADANO projde validací formuláře, ale selže při vlastní kontrole v pohledu."""
		self._set_bedna_zkontrolovano_ready()

		response = self.client.post(
			reverse("bedna_scan_zkontrolovano", args=[self.b_eur_pr.cislo_bedny]),
			{"action": "mark_zkontrolovano", "rovnat": RovnaniChoice.ROVNA, "tryskat": TryskaniChoice.NEZADANO},
		)

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/bedna_scan_zkontrolovano.html")
		self.b_eur_pr.refresh_from_db()
		self.assertEqual(self.b_eur_pr.stav_bedny, StavBednyChoice.ZAKALENO)

	def test_scan_zkontrolovano_post_rerenders_on_invalid_form(self):
		"""Odeslání neplatné hodnoty rovnat způsobí chybu formuláře a překreslení šablony."""
		self._set_bedna_zkontrolovano_ready()

		response = self.client.post(
			reverse("bedna_scan_zkontrolovano", args=[self.b_eur_pr.cislo_bedny]),
			{"action": "mark_zkontrolovano", "rovnat": "NEPLATNA_HODNOTA", "tryskat": TryskaniChoice.CISTA},
		)

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "orders/bedna_scan_zkontrolovano.html")
		self.assertFalse(response.context["form"].is_valid())
		self.b_eur_pr.refresh_from_db()
		self.assertEqual(self.b_eur_pr.stav_bedny, StavBednyChoice.ZAKALENO)


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
		same_month_as_average_data = (
			self.k_prijem_eur.datum.year == yesterday.year
			and self.k_prijem_eur.datum.month == yesterday.month
		)
		expected_prijem = Decimal("2529") + (Decimal("2800") if same_month_as_average_data else Decimal("0"))
		expected_vydej = Decimal("4") + (Decimal("2520") if same_month_as_average_data else Decimal("0"))
		expected_rocni_vydej = Decimal("4") + (Decimal("2520") if self.k_prijem_eur.datum.year == yesterday.year else Decimal("0"))
		expected_hmotnost_krivych = Decimal("4")
		expected_procento_krivych = (expected_hmotnost_krivych / expected_vydej) * Decimal("100")
		expected_rocni_procento_krivych = (expected_hmotnost_krivych / expected_rocni_vydej) * Decimal("100")
		self.assertEqual(data[month][eur_key]["prijem"], expected_prijem)
		self.assertEqual(data[month][eur_key]["vydej"], expected_vydej)
		self.assertEqual(data[month][eur_key]["hmotnost_krivych"], expected_hmotnost_krivych)
		self.assertAlmostEqual(float(data[month][eur_key]["procento_krivych"]), float(expected_procento_krivych), places=4)
		# CELKEM pro měsíc sčítá příjmy a výdeje
		self.assertGreaterEqual(data[month]["CELKEM"]["prijem"], 5)
		self.assertEqual(data[month]["CELKEM"]["hmotnost_krivych"], expected_hmotnost_krivych)
		self.assertAlmostEqual(float(data[month]["CELKEM"]["procento_krivych"]), float(expected_procento_krivych), places=4)
		self.assertEqual(data["CELKEM"][eur_key]["hmotnost_krivych"], expected_hmotnost_krivych)
		self.assertAlmostEqual(float(data["CELKEM"][eur_key]["procento_krivych"]), float(expected_rocni_procento_krivych), places=4)
		self.assertEqual(data["CELKEM"]["CELKEM"]["hmotnost_krivych"], expected_hmotnost_krivych)
		self.assertAlmostEqual(float(data["CELKEM"]["CELKEM"]["procento_krivych"]), float(expected_rocni_procento_krivych), places=4)
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
	def setUp(self):
		super().setUp()
		self.user.user_permissions.add(
			Permission.objects.get(
				content_type__app_label="orders",
				codename="view_bedna",
			)
		)

	def test_default_excludes_non_skladem_states_and_htmx_partial(self):
		# default stav_filter=SKLAD => vrátí pouze STAV_BEDNY_SKLADEM
		neprijata_bedna = Bedna.objects.create(
			zakazka=self.zak_eur,
			stav_bedny=StavBednyChoice.NEPRIJATO,
		)

		resp = self.client.get(reverse("bedny_list"))
		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/bedny_list.html")
		self.assertEqual(resp.context["sort"], "")
		self.assertEqual(resp.context["order"], "")
		objects = list(resp.context["object_list"])
		self.assertIn(self.b_eur_pr, objects)
		self.assertNotIn(self.b_abc_ex, objects)
		self.assertNotIn(neprijata_bedna, objects)

		resp_sk = self.client.get(reverse("bedny_list"), {"stav_filter": "SK"})
		objects_sk = list(resp_sk.context["object_list"])
		self.assertIn(self.b_eur_pr, objects_sk)
		self.assertNotIn(self.b_abc_ex, objects_sk)
		self.assertNotIn(neprijata_bedna, objects_sk)

		self.assertEqual(resp.context["pozastaveno_filter"], "False")
		delka_choice_labels = [label for value, label in resp.context["delka_choices"]]
		self.assertIn(str(int(self.zak_eur.delka)), delka_choice_labels)
		self.assertIn(str(int(self.zak_vydej_eur.delka)), delka_choice_labels)
		self.assertNotIn(str(int(self.zak_abc.delka)), delka_choice_labels)
		table_rows = resp.context["table_rows"]
		self.assertFalse(table_rows[0]["starts_new_zakazka_group"])
		self.assertTrue(table_rows[1]["starts_new_zakazka_group"])
		self.assertContains(resp, 'class="bedna-group-separator"')
		self.assertContains(resp, "window.bednaPollConfig")
		self.assertContains(resp, reverse("bedny_changes_poll"))
		self.assertContains(resp, "orders/js/admin_bedna_change_poll.js")
		# HTMX partial vrací tabulku
		resp_hx = self.client.get(reverse("bedny_list"), HTTP_HX_REQUEST="true")
		self.assertEqual(resp_hx.status_code, 200)
		self.assertTemplateUsed(resp_hx, "orders/partials/bedny_list_content.html")
		self.assertContains(resp_hx, 'id="delka_filter"')
		self.assertContains(resp_hx, 'id="listview-table"')

	def test_list_colors_cislo_bedny_by_customer(self):
		self.predpis_eur.skupina = 1
		self.predpis_eur.save(update_fields=["skupina"])
		resp = self.client.get(reverse("bedny_list"))

		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'background-color: #dc3545')
		self.assertContains(resp, str(self.b_eur_pr.cislo_bedny))
		self.assertContains(resp, 'background-color: #f0f0f0')

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

		resp_delka = self.client.get(reverse("bedny_list"), {"delka_filter": str(self.zak_vydej_eur.delka)})
		self.assertEqual(resp_delka.status_code, 200)
		objs_delka = list(resp_delka.context["object_list"])
		self.assertIn(self.b_vydej, objs_delka)
		self.assertNotIn(self.b_eur_pr, objs_delka)
		self.assertEqual(Decimal(resp_delka.context["delka_filter"]), Decimal(str(self.zak_vydej_eur.delka)))

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

	def test_priority_fake_skupina_tz_and_pozastaveno_filters(self):
		self.predpis_eur.skupina = 1
		self.predpis_eur.save(update_fields=["skupina"])
		self.zak_vydej_eur.priorita = PrioritaChoice.VYSOKA
		self.zak_vydej_eur.save(update_fields=["priorita"])
		self.zak_eur.priorita = PrioritaChoice.STREDNI
		self.zak_eur.save(update_fields=["priorita"])
		self.zak_vydej_eur.refresh_from_db()
		self.zak_eur.refresh_from_db()
		self.b_vydej.pozastaveno = True
		self.b_vydej.save(update_fields=["pozastaveno"])

		resp_default = self.client.get(reverse("bedny_list"))
		default_objects = list(resp_default.context["object_list"])
		self.assertIn(self.b_eur_pr, default_objects)
		self.assertNotIn(self.b_vydej, default_objects)

		resp_paused = self.client.get(reverse("bedny_list"), {"pozastaveno_filter": "True"})
		paused_objects = list(resp_paused.context["object_list"])
		self.assertIn(self.b_vydej, paused_objects)
		self.assertNotIn(self.b_eur_pr, paused_objects)

		resp_priority = self.client.get(
			reverse("bedny_list"),
			{"zakazka_priorita_filter": PrioritaChoice.VYSOKA, "pozastaveno_filter": "True"},
		)
		priority_objects = list(resp_priority.context["object_list"])
		self.assertIn(self.b_vydej, priority_objects)
		self.assertNotIn(self.b_eur_pr, priority_objects)
		delka_choice_values = [value for value, label in resp_priority.context["delka_choices"]]
		self.assertIn(str(self.zak_vydej_eur.delka), delka_choice_values)
		self.assertNotIn(str(self.zak_eur.delka), delka_choice_values)

		resp_stale_delka = self.client.get(
			reverse("bedny_list"),
			{
				"zakazka_priorita_filter": PrioritaChoice.VYSOKA,
				"pozastaveno_filter": "True",
				"delka_filter": str(self.zak_eur.delka),
			},
		)
		stale_delka_objects = list(resp_stale_delka.context["object_list"])
		self.assertIn(self.b_vydej, stale_delka_objects)
		self.assertEqual(resp_stale_delka.context["delka_filter"], "")

		predpis_group_5 = Predpis.objects.create(nazev="P5", skupina=5, zakaznik=self.z_eur)
		zakazka_group_5 = Zakazka.objects.create(
			kamion_prijem=self.k_prijem_eur,
			artikl="A5",
			prumer=1,
			delka=150,
			predpis=predpis_group_5,
			typ_hlavy=self.typ,
			celozavit=False,
			popis="group 5",
			priorita=PrioritaChoice.NIZKA,
		)
		Bedna.objects.create(
			zakazka=zakazka_group_5,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
		)
		resp_priority_p2 = self.client.get(reverse("bedny_list"), {"zakazka_priorita_filter": PrioritaChoice.STREDNI})
		tz_choice_values = [value for value, label in resp_priority_p2.context["fake_skupina_TZ_choices"]]
		self.assertIn("1", tz_choice_values)
		self.assertIn("5", tz_choice_values)

		resp_tz = self.client.get(reverse("bedny_list"), {"fake_skupina_TZ_filter": "1"})
		tz_objects = list(resp_tz.context["object_list"])
		self.assertIn(self.b_eur_pr, tz_objects)
		self.assertNotIn(self.b_vydej, tz_objects)

		zakazka_p1 = Zakazka.objects.create(
			kamion_prijem=self.k_prijem_eur,
			artikl="A4",
			prumer=1,
			delka=140,
			predpis=self.predpis_eur,
			typ_hlavy=self.typ,
			celozavit=False,
			popis="p1",
			priorita=PrioritaChoice.VYSOKA,
		)
		bedna_p1 = Bedna.objects.create(
			zakazka=zakazka_p1,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
		)
		resp_priority_p1_p2 = self.client.get(
			reverse("bedny_list"),
			{"zakazka_priorita_filter": "P1_P2"},
		)
		priority_p1_p2_objects = list(resp_priority_p1_p2.context["object_list"])
		self.assertIn(self.b_eur_pr, priority_p1_p2_objects)
		self.assertIn(bedna_p1, priority_p1_p2_objects)
		self.assertNotIn(self.b_vydej, priority_p1_p2_objects)
		self.assertNotIn(self.b_abc_ex, priority_p1_p2_objects)

	def test_sort_header_cycles_to_default_sort(self):
		resp = self.client.get(reverse("bedny_list"), {"sort": "cislo_bedny", "order": "down"})

		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'href="?sort=&order=&"')

	def test_changes_poll_detects_bedna_update(self):
		initial_response = self.client.get(reverse("bedny_changes_poll"))
		self.assertEqual(initial_response.status_code, 200)
		initial_payload = json.loads(initial_response.content.decode("utf-8"))
		self.assertIn("timestamp", initial_payload)
		self.assertIn("history_id", initial_payload)
		self.assertFalse(initial_payload["changed"])

		self.b_eur_pr.poznamka = "Změna pro seznam beden"
		self.b_eur_pr.save(update_fields=["poznamka"])

		response = self.client.get(
			reverse("bedny_changes_poll"),
			{"since_id": initial_payload["history_id"]},
		)
		self.assertEqual(response.status_code, 200)
		payload = json.loads(response.content.decode("utf-8"))
		self.assertTrue(payload["changed"])
		self.assertGreater(payload["history_id"], initial_payload["history_id"])

	def test_sorts_tz_by_fake_skupina_tz_annotation(self):
		self.predpis_eur.skupina = 1
		self.predpis_eur.save(update_fields=["skupina"])
		self.b_eur_pr.material = "10B21"
		self.b_eur_pr.save(update_fields=["material"])
		predpis_group_5 = Predpis.objects.create(nazev="P5", skupina=5, zakaznik=self.z_eur)
		zakazka_group_5 = Zakazka.objects.create(
			kamion_prijem=self.k_prijem_eur,
			artikl="A5",
			prumer=1,
			delka=150,
			predpis=predpis_group_5,
			typ_hlavy=self.typ,
			celozavit=False,
			popis="group 5",
			priorita=PrioritaChoice.NIZKA,
		)
		bedna_group_5 = Bedna.objects.create(
			zakazka=zakazka_group_5,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
		)

		resp = self.client.get(reverse("bedny_list"), {"sort": "fake_skupina_TZ_ann", "order": "up"})

		self.assertEqual(resp.status_code, 200)
		objects = list(resp.context["object_list"])
		self.assertLess(objects.index(bedna_group_5), objects.index(self.b_eur_pr))
		annotated_bedna = next(bedna for bedna in objects if bedna.pk == self.b_eur_pr.pk)
		self.assertEqual(annotated_bedna.fake_skupina_TZ_ann, 10)


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
			Permission.objects.get(
				content_type__app_label="orders",
				codename="change_sarzekrokbedna",
			),
			Permission.objects.get(
				content_type__app_label="orders",
				codename="delete_sarzekrokbedna_patro",
			),
			Permission.objects.get(
				content_type__app_label="orders",
				codename="change_sarze",
			),
			Permission.objects.get(
				content_type__app_label="orders",
				codename="change_sarzekrok",
			),
			Permission.objects.get(
				content_type__app_label="orders",
				codename="view_sarzekrok",
			),
			Permission.objects.get(
				content_type__app_label="orders",
				codename="view_sarzekrokbedna",
			),
		)
		self.nakladani = Zarizeni.objects.create(
			kod_zarizeni="NAKL",
			nazev_zarizeni="Nakládání",
			zkraceny_nazev_zarizeni="Nakládání",
			typ_zarizeni=TypZarizeniChoice.NAKLADANI,
		)

	def _rychle_zalozeni_url(self, cislo_pracoviste=3):
		return f"{reverse('rychle_zalozeni_sarze')}?cislo_pracoviste={cislo_pracoviste}"

	def _response_messages(self, response):
		return [str(message) for message in get_messages(response.wsgi_request)]

	def test_requires_login(self):
		self.client.logout()
		resp = self.client.get(reverse("rychle_zalozeni_sarze"))
		self.assertEqual(resp.status_code, 302)
		self.assertIn("login", resp.url)

	def test_requires_add_permissions(self):
		self.user.user_permissions.clear()
		resp = self.client.get(reverse("rychle_zalozeni_sarze"))
		self.assertEqual(resp.status_code, 403)

	def test_get_requires_pracoviste_query_parameter(self):
		resp = self.client.get(reverse("rychle_zalozeni_sarze"))
		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp["Location"], reverse("provozni_prehledy"))
		self.assertIn(
			"Rychlé založení šarže spusťte přes konkrétní pracoviště.",
			self._response_messages(resp),
		)

	def test_get_renders_form(self):
		resp = self.client.get(self._rychle_zalozeni_url(3))
		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/rychle_zalozeni_sarze.html")
		self.assertEqual(resp.context["db_table"], "rychle_zalozeni_sarze")
		self.assertContains(resp, "ŠARŽE")
		self.assertContains(resp, "Číslo pracoviště")
		self.assertEqual(resp.context["form"].initial["cislo_pracoviste"], 3)
		self.assertContains(resp, 'name="cislo_pracoviste" value="3"', html=False)
		self.assertContains(resp, "readonly", html=False)
		self.assertNotIn("konec", resp.context["form"].fields)
		self.assertNotContains(resp, 'name="konec"', html=False)
		self.assertNotContains(resp, "Přehled poslední šarže")

	def test_get_prefills_pracoviste_from_query_parameter(self):
		resp = self.client.get(self._rychle_zalozeni_url(4))

		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp.context["form"].initial["cislo_pracoviste"], 4)
		self.assertContains(resp, 'name="cislo_pracoviste" value="4"', html=False)

	def test_get_uses_previous_page_as_cancel_url(self):
		cancel_url = reverse("dashboard_bedny")

		resp = self.client.get(
			self._rychle_zalozeni_url(3),
			HTTP_REFERER=cancel_url,
		)

		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp.context["cancel_url"], cancel_url)
		self.assertContains(resp, f'href="{cancel_url}"')
		self.assertContains(resp, f'name="next" value="{cancel_url}"')

	def test_get_ignores_external_previous_page_for_cancel_url(self):
		resp = self.client.get(
			self._rychle_zalozeni_url(3),
			HTTP_REFERER="https://example.invalid/evil/",
		)

		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp.context["cancel_url"], reverse("provozni_prehledy"))

	def test_invalid_post_preserves_cancel_url_from_next(self):
		cancel_url = reverse("dashboard_bedny")

		resp = self.client.post(
			self._rychle_zalozeni_url(3),
			{
				"next": cancel_url,
				"cislo_pripravku": "",
				"cislo_pracoviste": "3",
				"poznamka_sarze": "",
				"datum": "2026-06-05",
				"zacatek": "06:00",
				"konec": "",
				"operator": "Novak",
				"poznamka_kroku": "",
			},
		)

		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp.context["cancel_url"], cancel_url)
		self.assertContains(resp, f'href="{cancel_url}"')
		self.assertContains(resp, f'name="next" value="{cancel_url}"')

	def test_navbar_shows_open_nakladani_steps_by_pracoviste(self):
		sarze_1 = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok_1 = SarzeKrok.objects.create(
			sarze=sarze_1,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)
		sarze_2 = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=13,
			cislo_pracoviste=2,
			aktivni=True,
		)
		krok_2 = SarzeKrok.objects.create(
			sarze=sarze_2,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(7, 0),
			operator="Novak",
		)
		uzavrena_sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=14,
			cislo_pracoviste=3,
			aktivni=True,
		)
		SarzeKrok.objects.create(
			sarze=uzavrena_sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(8, 0),
			konec=time(9, 0),
			operator="Novak",
		)

		resp = self.client.get(reverse("provozni_prehledy"))

		self.assertContains(resp, "Pracoviště 1")
		self.assertContains(resp, "Pracoviště 2")
		self.assertContains(resp, "Pracoviště 3")
		self.assertContains(resp, "Pracoviště 4")
		self.assertContains(resp, "Pracoviště 5")
		self.assertContains(resp, "Pracoviště 6")
		self.assertContains(resp, reverse("rychle_zalozeni_sarze_pracoviste_prehled", args=[1]))
		self.assertContains(resp, reverse("rychle_zalozeni_sarze_pracoviste_prehled", args=[2]))
		self.assertContains(resp, reverse("rychle_zalozeni_sarze_pracoviste_prehled", args=[3]))
		self.assertContains(resp, reverse("rychle_zalozeni_sarze_pracoviste_prehled", args=[6]))
		self.assertNotContains(resp, "Přehled poslední šarže")

	def test_pracoviste_prehled_redirects_to_open_nakladani_step(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=2,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)

		resp = self.client.get(reverse("rychle_zalozeni_sarze_pracoviste_prehled", args=[2]))

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(
			resp["Location"],
			reverse("rychle_zalozeni_sarze_prehled", args=[krok.pk]),
		)

	def test_pracoviste_prehled_redirects_to_prefilled_create_when_no_open_step(self):
		resp = self.client.get(reverse("rychle_zalozeni_sarze_pracoviste_prehled", args=[5]))

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(
			resp["Location"],
			f"{reverse('rychle_zalozeni_sarze')}?cislo_pracoviste=5",
		)

	def test_post_creates_sarze_and_first_step(self):
		resp = self.client.post(
			self._rychle_zalozeni_url(3),
			{
				"cislo_pripravku": "12",
				"cislo_pracoviste": "3",
				"poznamka_sarze": "Poznámka k šarži",
				"datum": "2026-06-05",
				"zacatek": "06:00",
				"konec": "",
				"operator": "Novak",
				"poznamka_kroku": "Poznámka k nakládání",
			},
		)
		self.assertEqual(resp.status_code, 302)

		sarze = Sarze.objects.get(cislo_pripravku=12)
		self.assertIsNotNone(sarze.cislo_sarze)
		self.assertEqual(sarze.cislo_pripravku, 12)
		self.assertEqual(sarze.cislo_pracoviste, 3)
		self.assertTrue(sarze.aktivni)
		self.assertEqual(sarze.poznamka, "Poznámka k šarži")

		krok = SarzeKrok.objects.get(sarze=sarze)
		self.assertEqual(krok.poradi, 1)
		self.assertEqual(krok.zarizeni, self.nakladani)
		self.assertIsNone(krok.konec)
		self.assertEqual(krok.operator, "Novak")
		self.assertEqual(krok.poznamka, "Poznámka k nakládání")
		self.assertEqual(
			resp["Location"],
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
		)

	def test_post_rejects_end_time_on_create(self):
		resp = self.client.post(
			self._rychle_zalozeni_url(3),
			{
				"cislo_pripravku": "12",
				"cislo_pracoviste": "3",
				"poznamka_sarze": "",
				"datum": "2026-06-05",
				"zacatek": "06:00",
				"konec": "07:30",
				"operator": "Novak",
				"poznamka_kroku": "",
			},
		)

		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, "Při rychlém založení šarže se konec kroku nezadává.")
		self.assertFalse(Sarze.objects.exists())
		self.assertFalse(SarzeKrok.objects.exists())

	def test_post_rejects_changed_readonly_pracoviste(self):
		resp = self.client.post(
			self._rychle_zalozeni_url(3),
			{
				"cislo_pripravku": "12",
				"cislo_pracoviste": "4",
				"poznamka_sarze": "",
				"datum": "2026-06-05",
				"zacatek": "06:00",
				"konec": "",
				"operator": "Novak",
				"poznamka_kroku": "",
			},
		)

		self.assertEqual(resp.status_code, 200)
		self.assertIn("cislo_pracoviste", resp.context["form"].errors)
		self.assertContains(resp, "Šarži lze založit pouze pro pracoviště č.3.")
		self.assertFalse(Sarze.objects.exists())
		self.assertFalse(SarzeKrok.objects.exists())

	def test_post_creates_sarze_when_latest_nakladani_step_has_no_end(self):
		puvodni_sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 4),
			cislo_pripravku=10,
			aktivni=True,
		)
		puvodni_krok = SarzeKrok.objects.create(
			sarze=puvodni_sarze,
			poradi=1,
			datum=date(2026, 6, 4),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			konec=None,
			operator="Novak",
		)

		resp = self.client.post(
			self._rychle_zalozeni_url(4),
			{
				"cislo_pripravku": "12",
				"cislo_pracoviste": "4",
				"poznamka_sarze": "",
				"datum": "2026-06-05",
				"zacatek": "06:00",
				"konec": "",
				"operator": "Svoboda",
				"poznamka_kroku": "",
			},
		)

		self.assertEqual(resp.status_code, 302)
		self.assertNotEqual(
			resp["Location"],
			reverse("rychle_zalozeni_sarze_prehled", args=[puvodni_krok.pk]),
		)
		nova_sarze = Sarze.objects.exclude(pk=puvodni_sarze.pk).get()
		novy_krok = SarzeKrok.objects.get(sarze=nova_sarze)
		self.assertEqual(nova_sarze.cislo_pripravku, 12)
		self.assertEqual(nova_sarze.cislo_pracoviste, 4)
		self.assertEqual(novy_krok.operator, "Svoboda")
		self.assertEqual(
			resp["Location"],
			reverse("rychle_zalozeni_sarze_patro", args=[novy_krok.pk, 1]),
		)

	def test_create_requires_valid_pracoviste_query_parameter(self):
		base_data = {
			"cislo_pripravku": "12",
			"cislo_pracoviste": "3",
			"poznamka_sarze": "",
			"datum": "2026-06-05",
			"zacatek": "06:00",
			"konec": "",
			"operator": "Novak",
			"poznamka_kroku": "",
		}

		for value in ("", "0", "7", "abc"):
			with self.subTest(cislo_pracoviste=value):
				url = reverse("rychle_zalozeni_sarze")
				if value:
					url = f"{url}?cislo_pracoviste={value}"
				resp = self.client.post(url, base_data)

				self.assertEqual(resp.status_code, 302)
				self.assertEqual(resp["Location"], reverse("provozni_prehledy"))
				self.assertIn(
					"Rychlé založení šarže spusťte přes konkrétní pracoviště.",
					self._response_messages(resp),
				)
				self.assertFalse(Sarze.objects.exists())
				self.assertFalse(SarzeKrok.objects.exists())

	def test_post_rejects_open_nakladani_for_same_pracoviste(self):
		puvodni_sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 4),
			cislo_pripravku=10,
			cislo_pracoviste=3,
			aktivni=True,
		)
		SarzeKrok.objects.create(
			sarze=puvodni_sarze,
			poradi=1,
			datum=date(2026, 6, 4),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			konec=None,
			operator="Novak",
		)

		resp = self.client.post(
			self._rychle_zalozeni_url(3),
			{
				"cislo_pripravku": "12",
				"cislo_pracoviste": "3",
				"poznamka_sarze": "",
				"datum": "2026-06-05",
				"zacatek": "06:00",
				"konec": "",
				"operator": "Svoboda",
				"poznamka_kroku": "",
			},
		)

		self.assertEqual(resp.status_code, 200)
		self.assertIn("cislo_pracoviste", resp.context["form"].errors)
		self.assertEqual(Sarze.objects.count(), 1)
		self.assertEqual(SarzeKrok.objects.count(), 1)

	def test_post_allows_same_pracoviste_when_existing_nakladani_is_closed(self):
		puvodni_sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 4),
			cislo_pripravku=10,
			cislo_pracoviste=3,
			aktivni=True,
		)
		SarzeKrok.objects.create(
			sarze=puvodni_sarze,
			poradi=1,
			datum=date(2026, 6, 4),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			konec=time(7, 0),
			operator="Novak",
		)

		resp = self.client.post(
			self._rychle_zalozeni_url(3),
			{
				"cislo_pripravku": "12",
				"cislo_pracoviste": "3",
				"poznamka_sarze": "",
				"datum": "2026-06-05",
				"zacatek": "06:00",
				"konec": "",
				"operator": "Svoboda",
				"poznamka_kroku": "",
			},
		)

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(Sarze.objects.count(), 2)
		self.assertEqual(SarzeKrok.objects.count(), 2)

	def test_upravit_get_prefills_existing_sarze_and_first_step(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=2,
			aktivni=True,
			poznamka="Původní poznámka",
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			konec=time(7, 30),
			operator="Novak",
			poznamka="Původní krok",
		)

		resp = self.client.get(
			reverse("rychle_zalozeni_sarze_upravit", args=[krok.pk]),
		)

		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/rychle_zalozeni_sarze.html")
		self.assertTrue(resp.context["is_edit"])
		self.assertEqual(resp.context["form"].initial["cislo_pripravku"], 12)
		self.assertEqual(resp.context["form"].initial["cislo_pracoviste"], 2)
		self.assertEqual(resp.context["form"].initial["operator"], "Novak")
		self.assertEqual(
			resp.context["cancel_url"],
			reverse("rychle_zalozeni_sarze_prehled", args=[krok.pk]),
		)

	def test_upravit_post_updates_existing_objects(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=2,
			aktivni=True,
			poznamka="Původní poznámka",
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			konec=time(7, 30),
			operator="Novak",
			poznamka="Původní krok",
		)
		sarze_count = Sarze.objects.count()
		krok_count = SarzeKrok.objects.count()

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_upravit", args=[krok.pk]),
			{
				"cislo_pripravku": "24",
				"cislo_pracoviste": "6",
				"poznamka_sarze": "Upravená poznámka",
				"datum": "2026-06-06",
				"zacatek": "08:00",
				"konec": "",
				"operator": "Svoboda",
				"poznamka_kroku": "Upravený krok",
			},
		)

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(
			resp["Location"],
			reverse("rychle_zalozeni_sarze_prehled", args=[krok.pk]),
		)
		self.assertEqual(Sarze.objects.count(), sarze_count)
		self.assertEqual(SarzeKrok.objects.count(), krok_count)

		sarze.refresh_from_db()
		krok.refresh_from_db()
		self.assertEqual(sarze.cislo_pripravku, 24)
		self.assertEqual(sarze.cislo_pracoviste, 6)
		self.assertEqual(sarze.poznamka, "Upravená poznámka")
		self.assertEqual(krok.datum, date(2026, 6, 6))
		self.assertEqual(krok.zacatek, time(8, 0))
		self.assertIsNone(krok.konec)
		self.assertEqual(krok.operator, "Svoboda")
		self.assertEqual(krok.poznamka, "Upravený krok")
		self.assertEqual(krok.poradi, 1)

	def test_upravit_rejects_end_time_without_any_bedna(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=2,
			aktivni=True,
			poznamka="Původní poznámka",
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
			poznamka="Původní krok",
		)

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_upravit", args=[krok.pk]),
			{
				"cislo_pripravku": "12",
				"cislo_pracoviste": "2",
				"poznamka_sarze": "Původní poznámka",
				"datum": "2026-06-05",
				"zacatek": "06:00",
				"konec": "07:30",
				"operator": "Novak",
				"poznamka_kroku": "Původní krok",
			},
		)

		self.assertEqual(resp.status_code, 200)
		self.assertIn("konec", resp.context["form"].errors)
		self.assertContains(resp, "Konec kroku lze zadat až po zadání alespoň jedné bedny do šarže.")
		krok.refresh_from_db()
		self.assertIsNone(krok.konec)

	def test_upravit_allows_end_time_when_bedna_exists(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=2,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)
		SarzeKrokBedna.objects.create(
			krok=krok,
			bedna=self.b_eur_pr,
			patro=1,
			procent_z_patra=100,
		)

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_upravit", args=[krok.pk]),
			{
				"cislo_pripravku": "12",
				"cislo_pracoviste": "2",
				"poznamka_sarze": "",
				"datum": "2026-06-05",
				"zacatek": "06:00",
				"konec": "07:30",
				"operator": "Novak",
				"poznamka_kroku": "",
			},
		)

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp["Location"], reverse("provozni_prehledy"))
		krok.refresh_from_db()
		self.assertEqual(krok.konec, time(7, 30))

	def test_upravit_requires_change_permissions(self):
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
			operator="Novak",
		)
		self.user.user_permissions.remove(
			Permission.objects.get(
				content_type__app_label="orders",
				codename="change_sarze",
			),
		)

		resp = self.client.get(
			reverse("rychle_zalozeni_sarze_upravit", args=[krok.pk]),
		)

		self.assertEqual(resp.status_code, 403)

	def test_upravit_rejects_non_first_step(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=2,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(8, 0),
			operator="Novak",
		)

		resp = self.client.get(
			reverse("rychle_zalozeni_sarze_upravit", args=[krok.pk]),
		)

		self.assertEqual(resp.status_code, 404)

	def test_upravit_rejects_non_nakladani_device(self):
		predehrev = Zarizeni.objects.create(
			kod_zarizeni="PRED",
			nazev_zarizeni="Předehřev",
			zkraceny_nazev_zarizeni="Předehřev",
			typ_zarizeni=TypZarizeniChoice.PREDEHREV,
		)
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=predehrev,
			zacatek=time(6, 0),
			operator="Novak",
		)

		resp = self.client.get(
			reverse("rychle_zalozeni_sarze_upravit", args=[krok.pk]),
		)

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp["Location"], reverse("provozni_prehledy"))
		self.assertIn("Neplatný krok pro pracoviště Nakládání.", self._response_messages(resp))

	def test_upravit_rejects_workplace_outside_one_to_six(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=7,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)

		resp = self.client.get(
			reverse("rychle_zalozeni_sarze_upravit", args=[krok.pk]),
		)

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp["Location"], reverse("provozni_prehledy"))
		self.assertIn("Číslo pracoviště musí být v rozsahu 1 až 6.", self._response_messages(resp))

	def test_patro_post_saves_bedny_and_opens_next_floor(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)
		other_bedna = Bedna.objects.create(
			zakazka=self.zak_abc,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=3,
			tara=1,
			mnozstvi=1,
			tryskat=TryskaniChoice.NEZADANO,
			rovnat=RovnaniChoice.NEZADANO,
		)

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
			{
				"polozky-TOTAL_FORMS": "2",
				"polozky-INITIAL_FORMS": "0",
				"polozky-MIN_NUM_FORMS": "0",
				"polozky-MAX_NUM_FORMS": "5",
				"polozky-0-bedna": str(self.b_eur_pr.pk),
				"polozky-0-procent_z_patra": "50",
				"polozky-1-bedna": str(other_bedna.pk),
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
		self.assertEqual(items[1].bedna, other_bedna)
		self.assertEqual(items[1].procent_z_patra, 50)
		self.b_eur_pr.refresh_from_db()
		other_bedna.refresh_from_db()
		self.assertEqual(self.b_eur_pr.stav_bedny, StavBednyChoice.DO_ZPRACOVANI)
		self.assertEqual(other_bedna.stav_bedny, StavBednyChoice.DO_ZPRACOVANI)

	def test_patro_post_rejects_bedna_not_allowed_for_navezeni(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)
		self.b_eur_pr.stav_bedny = StavBednyChoice.K_EXPEDICI
		self.b_eur_pr.save(update_fields=["stav_bedny"])

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
			{
				"polozky-TOTAL_FORMS": "1",
				"polozky-INITIAL_FORMS": "0",
				"polozky-MIN_NUM_FORMS": "0",
				"polozky-MAX_NUM_FORMS": "5",
				"polozky-0-bedna": str(self.b_eur_pr.pk),
				"polozky-0-procent_z_patra": "100",
				"action": "save",
			},
		)

		self.assertEqual(resp.status_code, 200)
		self.assertFalse(SarzeKrokBedna.objects.filter(krok=krok, patro=1).exists())
		self.b_eur_pr.refresh_from_db()
		self.assertEqual(self.b_eur_pr.stav_bedny, StavBednyChoice.K_EXPEDICI)

	def test_patro_post_rejects_paused_bedna(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)
		self.b_eur_pr.pozastaveno = True
		self.b_eur_pr.save(update_fields=["pozastaveno"])

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
			{
				"polozky-TOTAL_FORMS": "1",
				"polozky-INITIAL_FORMS": "0",
				"polozky-MIN_NUM_FORMS": "0",
				"polozky-MAX_NUM_FORMS": "5",
				"polozky-0-bedna": str(self.b_eur_pr.pk),
				"polozky-0-procent_z_patra": "100",
				"action": "save",
			},
		)

		self.assertEqual(resp.status_code, 200)
		self.assertFalse(SarzeKrokBedna.objects.filter(krok=krok, patro=1).exists())
		self.b_eur_pr.refresh_from_db()
		self.assertEqual(self.b_eur_pr.stav_bedny, StavBednyChoice.PRIJATO)
		self.assertTrue(self.b_eur_pr.pozastaveno)

	def test_patro_post_rejects_mimo_db_without_bedna(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
			{
				"polozky-TOTAL_FORMS": "1",
				"polozky-INITIAL_FORMS": "0",
				"polozky-MIN_NUM_FORMS": "0",
				"polozky-MAX_NUM_FORMS": "5",
				"polozky-0-popis_mimo_db": "Tyce",
				"polozky-0-zakaznik_mimo_db": "Externi zakaznik",
				"polozky-0-zakazka_mimo_db": "ZAK-1",
				"polozky-0-cislo_bedny_mimo_db": "BED-1",
				"polozky-0-procent_z_patra": "100",
				"action": "save",
			},
		)

		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, "Vyplňte alespoň jednu bednu.")
		self.assertFalse(SarzeKrokBedna.objects.filter(krok=krok, patro=1).exists())

	def test_patro_post_allows_same_bedna_more_than_once(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)
		other_bedna = Bedna.objects.create(
			zakazka=self.zak_abc,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=3,
			tara=1,
			mnozstvi=1,
			tryskat=TryskaniChoice.NEZADANO,
			rovnat=RovnaniChoice.NEZADANO,
		)

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
			{
				"polozky-TOTAL_FORMS": "3",
				"polozky-INITIAL_FORMS": "0",
				"polozky-MIN_NUM_FORMS": "0",
				"polozky-MAX_NUM_FORMS": "5",
				"polozky-0-bedna": str(self.b_eur_pr.pk),
				"polozky-0-procent_z_patra": "25",
				"polozky-1-bedna": str(other_bedna.pk),
				"polozky-1-procent_z_patra": "50",
				"polozky-2-bedna": str(self.b_eur_pr.pk),
				"polozky-2-procent_z_patra": "25",
				"action": "save",
			},
		)

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(
			list(
				SarzeKrokBedna.objects
				.filter(krok=krok, patro=1)
				.order_by("pk")
				.values_list("bedna_id", "procent_z_patra")
			),
			[
				(self.b_eur_pr.pk, 25),
				(other_bedna.pk, 50),
				(self.b_eur_pr.pk, 25),
			],
		)

	def test_patro_post_accepts_incomplete_floor_outside_five_percent_steps(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)
		other_bedna = Bedna.objects.create(
			zakazka=self.zak_abc,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=3,
			tara=1,
			mnozstvi=1,
			tryskat=TryskaniChoice.NEZADANO,
			rovnat=RovnaniChoice.NEZADANO,
		)

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
			{
				"polozky-TOTAL_FORMS": "2",
				"polozky-INITIAL_FORMS": "0",
				"polozky-MIN_NUM_FORMS": "0",
				"polozky-MAX_NUM_FORMS": "5",
				"polozky-0-bedna": str(self.b_eur_pr.pk),
				"polozky-0-procent_z_patra": "37",
				"polozky-1-bedna": str(other_bedna.pk),
				"polozky-1-procent_z_patra": "43",
				"action": "save",
			},
		)

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(
			list(
				SarzeKrokBedna.objects
				.filter(krok=krok, patro=1)
				.order_by("pk")
				.values_list("procent_z_patra", flat=True)
			),
			[37, 43],
		)

	def test_patro_post_rejects_more_than_five_items(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)

		data = {
			"polozky-TOTAL_FORMS": "6",
			"polozky-INITIAL_FORMS": "0",
			"polozky-MIN_NUM_FORMS": "0",
			"polozky-MAX_NUM_FORMS": "5",
			"action": "save",
		}
		for index in range(6):
			data[f"polozky-{index}-bedna"] = str(self.b_eur_pr.pk)
			data[f"polozky-{index}-procent_z_patra"] = "5"

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
			data,
		)

		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, "Odešlete prosím nejvíce 5 formulářů.")
		self.assertFalse(SarzeKrokBedna.objects.filter(krok=krok, patro=1).exists())

	def test_patro_get_renders_formset(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)

		resp = self.client.get(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
		)

		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/rychle_zalozeni_sarze_patro.html")
		self.assertEqual(resp.context["patro"], 1)
		self.assertEqual(resp.context["formset"].total_form_count(), 5)

	def test_patro_rejects_non_nakladani_device_even_for_workplace_one(self):
		predehrev = Zarizeni.objects.create(
			kod_zarizeni="PRED",
			nazev_zarizeni="Předehřev",
			zkraceny_nazev_zarizeni="Předehřev",
			typ_zarizeni=TypZarizeniChoice.PREDEHREV,
		)
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=predehrev,
			zacatek=time(6, 0),
			operator="Novak",
		)

		resp = self.client.get(reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]))

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp["Location"], reverse("rychle_zalozeni_sarze_prehled", args=[krok.pk]))
		self.assertIn("Neplatný krok pro pracoviště Nakládání.", self._response_messages(resp))

	def test_patro_rejects_workplace_outside_one_to_six(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=7,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)

		resp = self.client.get(reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]))

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp["Location"], reverse("rychle_zalozeni_sarze_prehled", args=[krok.pk]))
		self.assertIn("Číslo pracoviště musí být v rozsahu 1 až 6.", self._response_messages(resp))

	def test_patro_post_rejects_closed_step(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=2,
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
				"polozky-MAX_NUM_FORMS": "5",
				"polozky-0-bedna": str(self.b_eur_pr.pk),
				"polozky-0-procent_z_patra": "100",
				"action": "save",
			},
		)

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp["Location"], reverse("rychle_zalozeni_sarze_prehled", args=[krok.pk]))
		self.assertIn("Krok pro dané pracoviště není otevřený.", self._response_messages(resp))
		self.assertFalse(SarzeKrokBedna.objects.filter(krok=krok, patro=1).exists())

	def test_existing_patro_get_adds_empty_forms_up_to_five_rows(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
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
		self.assertEqual(resp.context["formset"].total_form_count(), 5)

	def test_existing_patro_invalid_delete_keeps_deleted_row_hidden(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)
		SarzeKrokBedna.objects.create(
			krok=krok,
			bedna=self.b_eur_pr,
			patro=1,
			procent_z_patra=100,
		)

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
			{
				"polozky-TOTAL_FORMS": "2",
				"polozky-INITIAL_FORMS": "1",
				"polozky-MIN_NUM_FORMS": "0",
				"polozky-MAX_NUM_FORMS": "5",
				"polozky-0-bedna": str(self.b_eur_pr.pk),
				"polozky-0-procent_z_patra": "100",
				"polozky-0-DELETE": "on",
				"polozky-1-bedna": "",
				"polozky-1-procent_z_patra": "",
				"action": "save",
			},
		)

		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, "Vyplňte alespoň jednu bednu.")
		self.assertContains(resp, 'class="item-row is-removed"')
		self.assertTrue(SarzeKrokBedna.objects.filter(krok=krok, patro=1).exists())

	def test_delete_patro_deletes_last_floor(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)
		other_bedna = Bedna.objects.create(
			zakazka=self.zak_abc,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=3,
			tara=1,
			mnozstvi=1,
			tryskat=TryskaniChoice.NEZADANO,
			rovnat=RovnaniChoice.NEZADANO,
		)
		SarzeKrokBedna.objects.create(krok=krok, bedna=self.b_eur_pr, patro=1, procent_z_patra=100)
		SarzeKrokBedna.objects.create(krok=krok, bedna=other_bedna, patro=2, procent_z_patra=100)

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 2]),
			{"action": "delete_floor"},
		)

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp["Location"], reverse("rychle_zalozeni_sarze_prehled", args=[krok.pk]))
		self.assertTrue(SarzeKrokBedna.objects.filter(krok=krok, patro=1).exists())
		self.assertFalse(SarzeKrokBedna.objects.filter(krok=krok, patro=2).exists())

	def test_delete_patro_rejects_non_last_floor(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)
		other_bedna = Bedna.objects.create(
			zakazka=self.zak_abc,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=3,
			tara=1,
			mnozstvi=1,
			tryskat=TryskaniChoice.NEZADANO,
			rovnat=RovnaniChoice.NEZADANO,
		)
		SarzeKrokBedna.objects.create(krok=krok, bedna=self.b_eur_pr, patro=1, procent_z_patra=100)
		SarzeKrokBedna.objects.create(krok=krok, bedna=other_bedna, patro=2, procent_z_patra=100)

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
			{"action": "delete_floor"},
		)

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp["Location"], reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]))
		self.assertTrue(SarzeKrokBedna.objects.filter(krok=krok, patro=1).exists())
		self.assertTrue(SarzeKrokBedna.objects.filter(krok=krok, patro=2).exists())

	def test_delete_patro_requires_permission(self):
		self.user.user_permissions.remove(
			Permission.objects.get(
				content_type__app_label="orders",
				codename="delete_sarzekrokbedna_patro",
			)
		)
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)
		SarzeKrokBedna.objects.create(krok=krok, bedna=self.b_eur_pr, patro=1, procent_z_patra=100)

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
			{"action": "delete_floor"},
		)

		self.assertEqual(resp.status_code, 403)
		self.assertTrue(SarzeKrokBedna.objects.filter(krok=krok, patro=1).exists())

	def test_patro_save_redirects_to_batch_summary(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
			{
				"polozky-TOTAL_FORMS": "1",
				"polozky-INITIAL_FORMS": "0",
				"polozky-MIN_NUM_FORMS": "0",
				"polozky-MAX_NUM_FORMS": "5",
				"polozky-0-bedna": str(self.b_eur_pr.pk),
				"polozky-0-procent_z_patra": "100",
				"action": "save",
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
		self.assertContains(
			summary,
			reverse("rychle_zalozeni_sarze_tisk", args=[krok.pk]),
		)
		self.assertContains(summary, "Náhled tisku")

	def test_tisk_returns_inline_pdf_with_step_context(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)
		item = SarzeKrokBedna.objects.create(
			krok=krok,
			bedna=self.b_eur_pr,
			patro=1,
			procent_z_patra=100,
		)

		with patch("orders.views.HTML.write_pdf", return_value=b"%PDF-test"):
			response = self.client.get(
				reverse("rychle_zalozeni_sarze_tisk", args=[krok.pk]),
			)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response["Content-Type"], "application/pdf")
		self.assertEqual(
			response["Content-Disposition"],
			f'inline; filename="sarze_{sarze.pk}_krok_{krok.pk}.pdf"',
		)
		self.assertEqual(response.content, b"%PDF-test")

		html = render_to_string(
			"orders/print/rychle_zalozeni_sarze_print.html",
			{
				"krok": krok,
				"items": SarzeKrokBedna.objects.filter(pk=item.pk),
				"generated_at": timezone.now(),
			},
		)
		self.assertIn("1. patro", html)
		self.assertIn(str(self.b_eur_pr.cislo_bedny), html)
		self.assertIn("PRŮVODKA VRUTY", html)
		self.assertIn("sarze-barcode", html)
		self.assertIn("<svg", html)

	def test_tisk_rejects_closed_step(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=2,
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

		response = self.client.get(reverse("rychle_zalozeni_sarze_tisk", args=[krok.pk]))

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response["Location"], reverse("provozni_prehledy"))
		self.assertIn("Krok pro dané pracoviště není otevřený.", self._response_messages(response))

	def test_prehled_and_tisk_show_floors_in_descending_order(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)
		SarzeKrokBedna.objects.create(
			krok=krok,
			bedna=self.b_eur_pr,
			patro=1,
			procent_z_patra=100,
		)
		SarzeKrokBedna.objects.create(
			krok=krok,
			bedna=self.b_eur_pr,
			patro=2,
			procent_z_patra=100,
		)

		prehled = self.client.get(
			reverse("rychle_zalozeni_sarze_prehled", args=[krok.pk]),
		)
		prehled_html = prehled.content.decode()

		self.assertLess(prehled_html.index("2. patro"), prehled_html.index("1. patro"))

		with patch("orders.views.HTML") as html_mock:
			html_mock.return_value.write_pdf.return_value = b"%PDF-test"
			self.client.get(
				reverse("rychle_zalozeni_sarze_tisk", args=[krok.pk]),
			)

		tisk_html = html_mock.call_args.kwargs["string"]
		self.assertLess(tisk_html.index("2. patro"), tisk_html.index("1. patro"))

	def test_prehled_rejects_non_nakladani_device(self):
		predehrev = Zarizeni.objects.create(
			kod_zarizeni="PRED",
			nazev_zarizeni="Předehřev",
			zkraceny_nazev_zarizeni="Předehřev",
			typ_zarizeni=TypZarizeniChoice.PREDEHREV,
		)
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=predehrev,
			zacatek=time(6, 0),
			operator="Novak",
		)

		response = self.client.get(reverse("rychle_zalozeni_sarze_prehled", args=[krok.pk]))

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response["Location"], reverse("provozni_prehledy"))
		self.assertIn("Neplatný krok pro pracoviště Nakládání.", self._response_messages(response))

	def test_prehled_rejects_workplace_outside_one_to_six(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=7,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)

		response = self.client.get(reverse("rychle_zalozeni_sarze_prehled", args=[krok.pk]))

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response["Location"], reverse("provozni_prehledy"))
		self.assertIn("Číslo pracoviště musí být v rozsahu 1 až 6.", self._response_messages(response))

	def test_prehled_rejects_closed_step(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=2,
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

		response = self.client.get(reverse("rychle_zalozeni_sarze_prehled", args=[krok.pk]))

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response["Location"], reverse("provozni_prehledy"))
		self.assertIn("Krok pro dané pracoviště není otevřený.", self._response_messages(response))

	def test_tisk_requires_view_permissions(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)
		self.user.user_permissions.remove(
			Permission.objects.get(
				content_type__app_label="orders",
				codename="view_sarzekrokbedna",
			),
		)

		response = self.client.get(
			reverse("rychle_zalozeni_sarze_tisk", args=[krok.pk]),
		)

		self.assertEqual(response.status_code, 403)

	def test_patro_finish_redirects_without_saving_current_floor(self):
		sarze = Sarze.objects.create(
			datum_zalozeni=date(2026, 6, 5),
			cislo_pripravku=12,
			cislo_pracoviste=1,
			aktivni=True,
		)
		krok = SarzeKrok.objects.create(
			sarze=sarze,
			poradi=1,
			datum=date(2026, 6, 5),
			zarizeni=self.nakladani,
			zacatek=time(6, 0),
			operator="Novak",
		)
		existing_item = SarzeKrokBedna.objects.create(
			krok=krok,
			bedna=self.b_eur_pr,
			patro=1,
			procent_z_patra=100,
		)

		resp = self.client.post(
			reverse("rychle_zalozeni_sarze_patro", args=[krok.pk, 1]),
			{
				"action": "finish",
				"polozky-TOTAL_FORMS": "invalid",
			},
		)

		self.assertEqual(resp.status_code, 302)
		self.assertEqual(
			resp["Location"],
			reverse("rychle_zalozeni_sarze_prehled", args=[krok.pk]),
		)
		self.assertEqual(
			list(SarzeKrokBedna.objects.filter(krok=krok, patro=1)),
			[existing_item],
		)


class VyrobaDashboardContextTests(TestCase):
	def setUp(self):
		self.z_eur = Zakaznik.objects.create(nazev="Eurotec", zkraceny_nazev="EUR", zkratka="EUR", ciselna_rada=100000)
		self.z_spx = Zakaznik.objects.create(nazev="SPAX", zkraceny_nazev="SPX", zkratka="SPX", ciselna_rada=300000)
		self.typ = TypHlavy.objects.create(nazev="SK")
		self.predpis_eur = Predpis.objects.create(nazev="P-EUR", zakaznik=self.z_eur)
		self.predpis_spx = Predpis.objects.create(nazev="P-SPX", zakaznik=self.z_spx)
		self.cena_eur = Cena.objects.create(
			zakaznik=self.z_eur,
			popis="EUR",
			delka_min=0,
			delka_max=200,
			cena_za_kg=Decimal("2.00"),
		)
		self.cena_eur.predpis.add(self.predpis_eur)

		self.dev_xl1 = Zarizeni.objects.create(
			kod_zarizeni="TQF_XL1", nazev_zarizeni="XL1", zkraceny_nazev_zarizeni="XL1", typ_zarizeni=TypZarizeniChoice.VICEUCELOVKA
		)
		self.dev_xl2 = Zarizeni.objects.create(
			kod_zarizeni="TQF_XL2", nazev_zarizeni="XL2", zkraceny_nazev_zarizeni="XL2", typ_zarizeni=TypZarizeniChoice.VICEUCELOVKA
		)
		self.dev_nakladani = Zarizeni.objects.create(
			kod_zarizeni="NAK",
			nazev_zarizeni="Nakládání",
			zkraceny_nazev_zarizeni="Nakládání",
			typ_zarizeni=TypZarizeniChoice.NAKLADANI,
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

	def test_vyroba_dashboard_shift_counts_use_six_to_eighteen_boundaries(self):
		target_day = date(2026, 3, 3)
		next_day = target_day + timedelta(days=1)

		def create_step(step_date, start_time, device):
			sarze = Sarze.objects.create(
				datum_zalozeni=step_date,
				aktivni=True,
			)
			return SarzeKrok.objects.create(
				sarze=sarze,
				poradi=1,
				datum=step_date,
				zarizeni=device,
				zacatek=start_time,
				operator="op",
				program="p",
			)

		create_step(target_day, time(5, 59), self.dev_xl1)
		create_step(target_day, time(6, 0), self.dev_xl1)
		create_step(target_day, time(17, 59), self.dev_xl1)
		create_step(target_day, time(18, 0), self.dev_xl2)
		create_step(next_day, time(5, 59), self.dev_xl2)
		create_step(next_day, time(6, 0), self.dev_xl2)

		ctx = _build_vyroba_dashboard_context(date_value=target_day)
		shifts = ctx["vyroba_dashboard"]["shifts"]

		self.assertEqual(shifts["day"]["counts"]["xl1"], 2)
		self.assertEqual(shifts["day"]["counts"]["xl2"], 0)
		self.assertEqual(shifts["day"]["counts"]["total"], 2)
		self.assertEqual(shifts["night"]["counts"]["xl1"], 0)
		self.assertEqual(shifts["night"]["counts"]["xl2"], 2)
		self.assertEqual(shifts["night"]["counts"]["total"], 2)

	def test_vyroba_dashboard_counts_nakladani_sarze_and_distinct_patra_by_shift(self):
		target_day = date(2026, 3, 3)
		next_day = target_day + timedelta(days=1)

		def create_nakladani_step(step_date, start_time, patra):
			sarze = Sarze.objects.create(
				datum_zalozeni=step_date,
				aktivni=True,
			)
			krok = SarzeKrok.objects.create(
				sarze=sarze,
				poradi=1,
				datum=step_date,
				zarizeni=self.dev_nakladani,
				zacatek=start_time,
				operator="op",
				program="p",
			)
			for patro in patra:
				SarzeKrokBedna.objects.create(krok=krok, bedna=None, patro=patro, popis_mimo_db=f"Patro {patro}")
			return krok

		create_nakladani_step(target_day, time(6, 0), [1, 2, 2])
		create_nakladani_step(target_day, time(17, 59), [4])
		create_nakladani_step(target_day, time(18, 0), [1, 3])
		create_nakladani_step(next_day, time(5, 59), [1])
		create_nakladani_step(next_day, time(6, 0), [1, 2, 3])

		sarze_xl = Sarze.objects.create(datum_zalozeni=target_day, aktivni=True)
		krok_xl = SarzeKrok.objects.create(
			sarze=sarze_xl,
			poradi=1,
			datum=target_day,
			zarizeni=self.dev_xl1,
			zacatek=time(10, 0),
			operator="op",
			program="p",
		)
		SarzeKrokBedna.objects.create(krok=krok_xl, bedna=None, patro=1, popis_mimo_db="Ignorovat")

		ctx = _build_vyroba_dashboard_context(date_value=target_day)
		shifts = ctx["vyroba_dashboard"]["shifts"]

		self.assertEqual(shifts["day"]["counts"]["sarze"], 2)
		self.assertEqual(shifts["day"]["counts"]["patra"], 3)
		self.assertEqual(shifts["night"]["counts"]["sarze"], 2)
		self.assertEqual(shifts["night"]["counts"]["patra"], 3)

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
		self.assertEqual(yearly["cena_za_rost"]["display"], "1 000")
		self.assertEqual(yearly["prostoj_avg"]["xl1_display"], "0,8")
		self.assertEqual(yearly["prostoj_avg"]["xl2_display"], "1,8")
		self.assertEqual(yearly["prostoj_avg"]["total_display"], "2,6")
		self.assertEqual(monthly_rows[0]["vytizeni_rostu"]["display"], "750")
		self.assertEqual(monthly_rows[0]["cena_za_rost"]["display"], "1 000")
		self.assertEqual(weekly_rows[0]["vytizeni_rostu"]["display"], "750")
		self.assertEqual(weekly_rows[0]["cena_za_rost"]["display"], "1 000")
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
		self.assertEqual(row_by_label["05.01.2026"]["cena_za_rost"]["display"], "1 200")
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

	def test_vyroba_zakaznici_vyuziti_splits_weekly_usage_by_customer(self):
		today_value = date(2026, 1, 10)
		bedna_eur_shared = self._create_bedna(self.z_eur, 600)
		bedna_spx_shared = self._create_bedna(self.z_spx, 400)
		bedna_eur_full = self._create_bedna(self.z_eur, 1000)

		sarze_1 = Sarze.objects.create(cislo_sarze=601, datum_zalozeni=date(2026, 1, 1), aktivni=True)
		krok_1 = SarzeKrok.objects.create(
			sarze=sarze_1,
			poradi=1,
			datum=date(2026, 1, 1),
			zarizeni=self.dev_xl1,
			zacatek=time(8, 0),
			operator="op",
			program="p",
		)
		SarzeKrokBedna.objects.create(krok=krok_1, bedna=bedna_eur_shared, patro=1, procent_z_patra=25)
		SarzeKrokBedna.objects.create(krok=krok_1, bedna=bedna_spx_shared, patro=1, procent_z_patra=25)

		sarze_2 = Sarze.objects.create(cislo_sarze=602, datum_zalozeni=date(2026, 1, 2), aktivni=True)
		krok_2 = SarzeKrok.objects.create(
			sarze=sarze_2,
			poradi=1,
			datum=date(2026, 1, 2),
			zarizeni=self.dev_xl2,
			zacatek=time(9, 0),
			operator="op",
			program="p",
		)
		SarzeKrokBedna.objects.create(krok=krok_2, bedna=bedna_eur_full, patro=1, procent_z_patra=80)

		ctx = _build_vyroba_zakaznici_vyuziti_context(year_value=2026, today_value=today_value)
		data = ctx["vyroba_zakaznici_vyuziti"]
		rows = {row["customer"]: row for row in data["customer_rows"]}

		self.assertEqual(data["weeks"][0]["date_range"], "01.01. - 04.01.")
		self.assertEqual(data["weeks"][0]["step_count"], 2)
		self.assertEqual(rows["EUR"]["weeks"][0]["display"], "1 067")
		self.assertEqual(rows["SPX"]["weeks"][0]["display"], "800")
		self.assertEqual(data["total_row"]["weeks"][0]["display"], "1 000")
		self.assertEqual(data["total_row"]["total"]["display"], "1 000")

class VyrobaHistorieViewTests(ViewsTestBase):
	def test_zakaznici_vyuziti_view_renders_page(self):
		resp = self.client.get(reverse("dashboard_vyroba_zakaznici_vyuziti"), {"rok": timezone.localdate().year})
		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/dashboard_vyroba_zakaznici_vyuziti.html")

	def test_historie_mesic_view_renders_detail_page(self):
		resp = self.client.get(reverse("dashboard_vyroba_historie_mesic"), {"rok": timezone.localdate().year, "mesic": 1})
		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "orders/dashboard_vyroba_historie_mesic.html")

	def test_historie_mesic_view_redirects_without_month(self):
		resp = self.client.get(reverse("dashboard_vyroba_historie_mesic"), {"rok": timezone.localdate().year})
		self.assertEqual(resp.status_code, 302)
		self.assertIn(reverse("dashboard_vyroba_historie"), resp["Location"])
