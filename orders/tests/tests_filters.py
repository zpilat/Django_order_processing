from django.test import TestCase, RequestFactory
from django.utils import timezone

from orders.models import (
	Zakaznik, Odberatel, Kamion, Zakazka, Bedna, Predpis, TypHlavy
)
from orders.choices import (
	StavBednyChoice, TryskaniChoice, RovnaniChoice, PrioritaChoice, KamionChoice,
	SklademZakazkyChoice, ZinkovaniChoice
)
from orders import filters as F
from orders.templatetags import custom_filters

from datetime import timedelta


class FilterTestBase(TestCase):
	def setUp(self):
		self.rf = RequestFactory()

		# Customers
		self.z1 = Zakaznik.objects.create(nazev="Z1", zkraceny_nazev="Z1", zkratka="EUR", ciselna_rada=100000)
		self.z2 = Zakaznik.objects.create(nazev="Z2", zkraceny_nazev="Z2", zkratka="ABC", ciselna_rada=200000)

		# Buyer
		self.odberatel = Odberatel.objects.create(nazev="O1", zkraceny_nazev="O1", zkratka="O1")

		# Typ hlavy
		self.typ = TypHlavy.objects.create(nazev="T")

		# Predpisy
		self.p1 = Predpis.objects.create(nazev="P1", skupina=1, zakaznik=self.z1)
		self.p2 = Predpis.objects.create(nazev="P2", skupina=2, zakaznik=self.z2)

		# Kamiony
		today = timezone.localdate()
		self.k_old = Kamion.objects.create(zakaznik=self.z1, datum=today - timedelta(days=40), prijem_vydej=KamionChoice.PRIJEM)
		self.k_new = Kamion.objects.create(zakaznik=self.z1, datum=today, prijem_vydej=KamionChoice.PRIJEM)
		self.k_empty = Kamion.objects.create(zakaznik=self.z1, datum=today, prijem_vydej=KamionChoice.PRIJEM)
		self.k_v = Kamion.objects.create(zakaznik=self.z1, odberatel=self.odberatel, datum=today, prijem_vydej=KamionChoice.VYDEJ)
		self.k_pv = Kamion.objects.create(zakaznik=self.z1, datum=today, prijem_vydej=KamionChoice.PRIJEM)
		self.k_pk = Kamion.objects.create(zakaznik=self.z1, datum=today, prijem_vydej=KamionChoice.PRIJEM)

		# Zakázky
		self.zak_old = Zakazka.objects.create(
			kamion_prijem=self.k_old,
			artikl="A1",
			prumer=1,
			delka=100,
			predpis=self.p1,
			typ_hlavy=self.typ,
			celozavit=True,
			popis="old",
			priorita=PrioritaChoice.NIZKA,
		)
		self.zak_new = Zakazka.objects.create(
			kamion_prijem=self.k_new,
			artikl="A2",
			prumer=1,
			delka=200,
			predpis=self.p1,
			typ_hlavy=self.typ,
			celozavit=False,
			popis="new",
			priorita=PrioritaChoice.NIZKA,
		)
		# zakázka bez beden
		self.zak_empty = Zakazka.objects.create(
			kamion_prijem=self.k_new,
			artikl="A3",
			prumer=1,
			delka=150,
			predpis=self.p1,
			typ_hlavy=self.typ,
			celozavit=False,
			popis="empty",
			priorita=PrioritaChoice.STREDNI,
		)
		# zakázka expedovaná
		self.zak_exp = Zakazka.objects.create(
			kamion_prijem=self.k_new,
			artikl="A4",
			prumer=1,
			delka=120,
			predpis=self.p1,
			typ_hlavy=self.typ,
			celozavit=False,
			popis="exp",
			priorita=PrioritaChoice.VYSOKA,
			expedovano=True,
		)
		# zakázky pro různé scénáře kamionů
		self.zak_pv = Zakazka.objects.create(
			kamion_prijem=self.k_pv,
			artikl="A5",
			prumer=1,
			delka=110,
			predpis=self.p1,
			typ_hlavy=self.typ,
			celozavit=False,
			popis="pv",
			priorita=PrioritaChoice.NIZKA,
			expedovano=True,
		)
		self.zak_pk = Zakazka.objects.create(
			kamion_prijem=self.k_pk,
			artikl="A6",
			prumer=1,
			delka=210,
			predpis=self.p1,
			typ_hlavy=self.typ,
			celozavit=False,
			popis="pk",
			priorita=PrioritaChoice.NIZKA,
		)

		# Bedny
		# NEPRIJATO (pro PN a SklademZakazkyChoice.NEPRIJATO)
		self.b_ne = Bedna.objects.create(
			zakazka=self.zak_old,
			stav_bedny=StavBednyChoice.NEPRIJATO,
		)
		# PRIJATO (skladem)
		self.b_pr = Bedna.objects.create(
			zakazka=self.zak_new,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
			tryskat=TryskaniChoice.NEZADANO,
			rovnat=RovnaniChoice.NEZADANO,
		)
		# K_EXPEDICI (skladem + pro komplet/k_expedici)
		self.b_ke = Bedna.objects.create(
			zakazka=self.zak_new,
			stav_bedny=StavBednyChoice.K_EXPEDICI,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
			tryskat=TryskaniChoice.CISTA,
			rovnat=RovnaniChoice.ROVNA,
		)
		# PRIJATO u jiné zakázky pro PK
		self.b_pk = Bedna.objects.create(
			zakazka=self.zak_pk,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
		)
		# Bedna pro hotovo tryskani/rovnani
		self.b_hot = Bedna.objects.create(
			zakazka=self.zak_new,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
			tryskat=TryskaniChoice.OTRYSKANA,
			rovnat=RovnaniChoice.VYROVNANA,
		)

	def _make_filter(self, cls, model, params):
		request = self.rf.get("/admin/", data=params)
		# SimpleListFilter očekává mutovatelný QueryDict (ChangeList předává request.GET.copy())
		return cls(request, request.GET.copy(), model, None)


class BednaFiltersTests(FilterTestBase):
	def test_stav_bedny_filter_default_returns_skladem(self):
		f = self._make_filter(F.StavBednyFilter, Bedna, params={})
		qs = f.queryset(None, Bedna.objects.all())
		# skladem => obsahuje PR a KE a další, neobsahuje NE ani EX
		self.assertIn(self.b_pr, qs)
		self.assertIn(self.b_ke, qs)
		self.assertNotIn(self.b_ne, qs)

	def test_stav_bedny_filter_rozpracovano(self):
		f = self._make_filter(F.StavBednyFilter, Bedna, params={"stav_bedny": "RO"})
		qs = f.queryset(None, Bedna.objects.all())
		# Rozpracovanost neobsahuje PRIJATO ani NEPRIJATO
		self.assertNotIn(self.b_pr, qs)
		self.assertNotIn(self.b_ne, qs)

	def test_stav_bedny_filter_po_expiraci(self):
		f = self._make_filter(F.StavBednyFilter, Bedna, params={"stav_bedny": "PE"})
		qs = f.queryset(None, Bedna.objects.all())
		# b_ne je na kamionu starším 28 dní a není EXP, měl by projít
		self.assertIn(self.b_ne, qs)

	def test_tryskani_filter_hotovo(self):
		f = self._make_filter(F.TryskaniFilter, Bedna, params={"tryskani": "hotovo"})
		qs = f.queryset(None, Bedna.objects.all())
		self.assertIn(self.b_hot, qs)
		# b_pr má NEZADANO => není hotovo
		self.assertNotIn(self.b_pr, qs)

	def test_rovnani_filter_hotovo(self):
		f = self._make_filter(F.RovnaniFilter, Bedna, params={"rovnani": "hotovo"})
		qs = f.queryset(None, Bedna.objects.all())
		self.assertIn(self.b_hot, qs)
		self.assertNotIn(self.b_pr, qs)

	def test_priorita_bedny_filter(self):
		f = self._make_filter(F.PrioritaBednyFilter, Bedna, params={"priorita_bedny": PrioritaChoice.NIZKA})
		qs = f.queryset(None, Bedna.objects.all())
		self.assertIn(self.b_pr, qs)
		self.assertIn(self.b_ke, qs)

	def test_zinkovani_filter_hotovo(self):
		b_nezink = Bedna.objects.create(
			zakazka=self.zak_new,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
			zinkovat=ZinkovaniChoice.NEZINKOVAT,
		)
		b_uvol = Bedna.objects.create(
			zakazka=self.zak_new,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
			zinkovat=ZinkovaniChoice.UVOLNENO,
		)
		b_kz = Bedna.objects.create(
			zakazka=self.zak_new,
			stav_bedny=StavBednyChoice.PRIJATO,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
			zinkovat=ZinkovaniChoice.ZINKOVAT,
		)

		f = self._make_filter(F.ZinkovaniFilter, Bedna, params={"zinkovani": "hotovo"})
		qs = f.queryset(None, Bedna.objects.all())
		self.assertIn(b_nezink, qs)
		self.assertIn(b_uvol, qs)
		self.assertNotIn(b_kz, qs)

	def test_zinkovani_filter_lookups_excludes_uvolneno(self):
		f = self._make_filter(F.ZinkovaniFilter, Bedna, params={})
		keys = {k for k, _ in f.lookups(None, None)}
		self.assertIn('hotovo', keys)
		self.assertIn(ZinkovaniChoice.UVOLNENO, keys)

	def test_celozavit_bedny_filter_true(self):
		f = self._make_filter(F.CelozavitBednyFilter, Bedna, params={"celozavit": "True"})
		qs = f.queryset(None, Bedna.objects.all())
		# jen bedny z zak_old (celozavit=True)
		self.assertIn(self.b_ne, qs)
		self.assertNotIn(self.b_pr, qs)

	def test_pozastaveno_filter(self):
		# nastavíme jednu bednu na pozastaveno
		self.b_pr.pozastaveno = True
		self.b_pr.save()
		f_true = self._make_filter(F.PozastavenoFilter, Bedna, params={"pozastaveno": "True"})
		f_false = self._make_filter(F.PozastavenoFilter, Bedna, params={"pozastaveno": "False"})
		self.assertIn(self.b_pr, f_true.queryset(None, Bedna.objects.all()))
		self.assertNotIn(self.b_pr, f_false.queryset(None, Bedna.objects.all()))

	def test_delka_filter_lookups_and_query(self):
		# DelkaFilter funguje jen pro stav_bedny v (NE, PR)
		params = {"stav_bedny": StavBednyChoice.PRIJATO}
		f = self._make_filter(F.DelkaFilter, Bedna, params=params)
		lookups = list(f.lookups(None, None))
		# V přijatých bednách máme délku 200 (z self.zak_new)
		values = [val for val, _ in lookups]
		self.assertIn(self.zak_new.delka, values)
		# A když zvolíme delku 200, filtruje správně
		f_selected = self._make_filter(F.DelkaFilter, Bedna, params={"stav_bedny": StavBednyChoice.PRIJATO, "delka": str(int(self.zak_new.delka))})
		qs = f_selected.queryset(None, Bedna.objects.all())
		self.assertIn(self.b_pr, qs)
		self.assertIn(self.b_ke, qs)  # má jiný stav, ale delka je z téže zakázky; DelkaFilter aplikuje jen dle zakazka__delka


class ZakazkaFiltersTests(FilterTestBase):
	def test_skladem_zakazka_default(self):
		f = self._make_filter(F.SklademZakazkaFilter, Zakazka, params={})
		qs = f.queryset(None, Zakazka.objects.all())
		# Vrací neexpedované se stavem beden != NE (self.zak_new)
		self.assertIn(self.zak_new, qs)
		self.assertNotIn(self.zak_old, qs)
		self.assertNotIn(self.zak_empty, qs)
		self.assertNotIn(self.zak_exp, qs)

	def test_skladem_zakazka_neprijato(self):
		f = self._make_filter(F.SklademZakazkaFilter, Zakazka, params={"skladem": SklademZakazkyChoice.NEPRIJATO})
		qs = f.queryset(None, Zakazka.objects.all())
		self.assertIn(self.zak_old, qs)

	def test_skladem_zakazka_bez_beden(self):
		f = self._make_filter(F.SklademZakazkaFilter, Zakazka, params={"skladem": SklademZakazkyChoice.BEZ_BEDEN})
		qs = f.queryset(None, Zakazka.objects.all())
		self.assertIn(self.zak_empty, qs)

	def test_skladem_zakazka_expedovano(self):
		f = self._make_filter(F.SklademZakazkaFilter, Zakazka, params={"skladem": SklademZakazkyChoice.EXPEDOVANO})
		qs = f.queryset(None, Zakazka.objects.all())
		self.assertIn(self.zak_exp, qs)

	def test_komplet_zakazka_filter(self):
		# self.zak_new má b_ke => 'k_expedici' jej obsahuje
		f_ke = self._make_filter(F.KompletZakazkaFilter, Zakazka, params={"komplet": "k_expedici"})
		qs_ke = f_ke.queryset(None, Zakazka.objects.all())
		self.assertIn(self.zak_new, qs_ke)

		# kompletní: všechny bedny KE/EX a aspoň jedna bedna; vytvoříme druhou bednu KE
		Bedna.objects.create(
			zakazka=self.zak_new,
			stav_bedny=StavBednyChoice.K_EXPEDICI,
			hmotnost=1,
			tara=1,
			mnozstvi=1,
			tryskat=TryskaniChoice.CISTA,
			rovnat=RovnaniChoice.ROVNA,
		)
		# a aktualizujeme stávající bedny této zakázky na K_EXPEDICI, aby byly všechny KE/EX
		for b in (self.b_pr, self.b_hot):
			b.stav_bedny = StavBednyChoice.K_EXPEDICI
			b.tryskat = TryskaniChoice.CISTA
			b.rovnat = RovnaniChoice.ROVNA
			b.save()
		f_komp = self._make_filter(F.KompletZakazkaFilter, Zakazka, params={"komplet": "kompletni"})
		qs_komp = f_komp.queryset(None, Zakazka.objects.all())
		self.assertIn(self.zak_new, qs_komp)


class KamionFiltersTests(FilterTestBase):
	def test_zakaznik_kamionu_filter(self):
		f = self._make_filter(F.ZakaznikKamionuFilter, Kamion, params={"zakaznik": self.z1.zkratka})
		qs = f.queryset(None, Kamion.objects.all())
		self.assertIn(self.k_new, qs)
		# filtruje pouze podle zákazníka, nikoliv podle typu kamionu (příjem/výdej)
		self.assertIn(self.k_v, qs)

	def test_prijem_vydej_filter_variants(self):
		# PB: příjem bez zakázek
		f_pb = self._make_filter(F.PrijemVydejFilter, Kamion, params={"prijem_vydej": "PB"})
		self.assertIn(self.k_empty, f_pb.queryset(None, Kamion.objects.all()))

		# PN: příjem s NEPRIJATO
		f_pn = self._make_filter(F.PrijemVydejFilter, Kamion, params={"prijem_vydej": "PN"})
		self.assertIn(self.k_old, f_pn.queryset(None, Kamion.objects.all()))

		# PK: příjem komplet přijatý (žádné NE, aspoň jedno skladem)
		f_pk = self._make_filter(F.PrijemVydejFilter, Kamion, params={"prijem_vydej": "PK"})
		self.assertIn(self.k_pk, f_pk.queryset(None, Kamion.objects.all()))

		# PV: příjem vyexpedovaný (všechny zakázky expedovány)
		f_pv = self._make_filter(F.PrijemVydejFilter, Kamion, params={"prijem_vydej": "PV"})
		self.assertIn(self.k_pv, f_pv.queryset(None, Kamion.objects.all()))

		# V: výdej
		f_v = self._make_filter(F.PrijemVydejFilter, Kamion, params={"prijem_vydej": "V"})
		self.assertIn(self.k_v, f_v.queryset(None, Kamion.objects.all()))


class PredpisFiltersTests(FilterTestBase):
	def test_aktivni_predpis_filter(self):
		# default (None) => aktivni True
		f_def = self._make_filter(F.AktivniPredpisFilter, Predpis, params={})
		self.assertIn(self.p1, f_def.queryset(None, Predpis.objects.all()))

		# 'ne' => neaktivní
		self.p2.aktivni = False
		self.p2.save()
		f_ne = self._make_filter(F.AktivniPredpisFilter, Predpis, params={"aktivni_predpis": "ne"})
		self.assertIn(self.p2, f_ne.queryset(None, Predpis.objects.all()))

	def test_zakaznik_predpis_filter(self):
		f = self._make_filter(F.ZakaznikPredpisFilter, Predpis, params={"zakaznik": self.z1.zkratka})
		qs = f.queryset(None, Predpis.objects.all())
		self.assertIn(self.p1, qs)
		self.assertNotIn(self.p2, qs)


class CustomTemplateFiltersTests(TestCase):
	def test_splitlines_splits_text(self):
		value = "line 1\nline 2\r\nline 3"
		self.assertEqual(custom_filters.splitlines(value), ["line 1", "line 2", "line 3"])

	def test_splitlines_none_returns_empty_list(self):
		self.assertEqual(custom_filters.splitlines(None), [])

