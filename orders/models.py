from django.db import models
from django.db.models.deletion import ProtectedError
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Sum
from django.db.models import Q

from simple_history.models import HistoricalRecords

import re
from decimal import Decimal, ROUND_HALF_UP

from .choices import (
    StavBednyChoice,
    RovnaniChoice,
    TryskaniChoice,
    ZinkovaniChoice,
    PrioritaChoice,
    KamionChoice,
    AlphabetChoice,
    STAV_BEDNY_SKLADEM,
    STAV_BEDNY_ROZPRACOVANOST,
)

import logging
logger = logging.getLogger('orders')

class Zakaznik(models.Model):
    nazev = models.CharField(max_length=100, verbose_name='Název zákazníka', unique=True)
    zkraceny_nazev = models.CharField(max_length=15, verbose_name='Zkrácený název', unique=True,
                                       help_text='Zkrácený název zákazníka, např. pro zobrazení v kartě bedny a v přehledech.')
    zkratka = models.CharField(max_length=3, verbose_name='Zkratka', unique=True,
                               help_text='Zkratka zákazníka, např. pro automatické číslování beden a kamionů a pro programové použití.'
                               ' Zkratka po vytvoření nemůže být změněna.')
    adresa = models.CharField(max_length=100, blank=True, null=True, verbose_name='Adresa')
    mesto = models.CharField(max_length=50, blank=True, null=True, verbose_name='Město')
    psc = models.CharField(max_length=10, blank=True, null=True, verbose_name='PSČ')
    stat = models.CharField(max_length=50, blank=True, null=True, verbose_name='Stát')
    zkratka_statu = models.CharField(max_length=3, blank=True, null=True, verbose_name='Zkratka státu')
    kontaktni_osoba = models.CharField(max_length=50, blank=True, null=True, verbose_name='Kontaktní osoba')
    telefon = models.CharField(max_length=50, blank=True, null=True, verbose_name='Telefon')
    email = models.EmailField(max_length=100, blank=True, null=True, verbose_name='E-mail')
    proforma_po_bednach = models.BooleanField(default=False, verbose_name='Proforma po bednách',
                                              help_text='Zákazník požaduje vystavení faktury po jednotlivých bednách.')
    vse_tryskat = models.BooleanField(default=False, verbose_name='Vše tryskat',
                                        help_text='Zákazník požaduje všechny bedny tryskat')
    pouze_komplet = models.BooleanField(default=False, verbose_name='Pouze komplet',
                                        help_text='Zákazník může expedovat pouze kompletní zakázky, které mají všechny bedny ve stavu K_EXPEDICI.')
    fakturovat_rovnani = models.BooleanField(default=False, verbose_name='Fakturovat rovnání',
                                             help_text='Zákazníkovi se bude fakturovat rovnání pokud byla bedna vyrovnána.')
    fakturovat_tryskani = models.BooleanField(default=False, verbose_name='Fakturovat tryskání',
                                              help_text='Zákazníkovi se bude fakturovat tryskání pokud byla bedna otryskána.')
    ciselna_rada = models.PositiveIntegerField(verbose_name='Číselná řada', default=100000, unique=True,
                                               help_text='Číselná řada pro automatické číslování beden - např. 100000, 200000, 300000 atd.')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Zákazník'
        verbose_name_plural = 'zákazníci'
        ordering = ['nazev']

    def __str__(self):
        return self.zkraceny_nazev
    

class Odberatel(models.Model):
    """
    Model pro odběratele, který je spojen s kamionem výdej.
    Může se nastavit i jako položka pro zakázku, pokud je předem určeno,
    ke kterému odběrateli musí zakázka odejít.
    """
    nazev = models.CharField(max_length=100, verbose_name='Název odběratele', unique=True)
    zkraceny_nazev = models.CharField(max_length=15, verbose_name='Zkrácený název', unique=True,
                                       help_text='Zkrácený název odběratele.')
    zkratka = models.CharField(max_length=3, verbose_name='Zkratka', unique=True,
                               help_text='Zkratka odběratele, např. pro programové použití.'
                               ' Zkratka po vytvoření nemůže být změněna.')
    adresa = models.CharField(max_length=100, blank=True, null=True, verbose_name='Adresa')
    mesto = models.CharField(max_length=50, blank=True, null=True, verbose_name='Město')
    psc = models.CharField(max_length=10, blank=True, null=True, verbose_name='PSČ')
    stat = models.CharField(max_length=50, blank=True, null=True, verbose_name='Stát')
    zkratka_statu = models.CharField(max_length=3, blank=True, null=True, verbose_name='Zkratka státu')
    kontaktni_osoba = models.CharField(max_length=50, blank=True, null=True, verbose_name='Kontaktní osoba')
    telefon = models.CharField(max_length=50, blank=True, null=True, verbose_name='Telefon')
    email = models.EmailField(max_length=100, blank=True, null=True, verbose_name='E-mail')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Odběratel'
        verbose_name_plural = 'odběratelé'
        ordering = ['nazev']

    def __str__(self):
        return  f"{self.zkraceny_nazev} ({self.adresa}, {self.zkratka_statu}-{self.psc} {self.mesto})"


class Kamion(models.Model):
    zakaznik = models.ForeignKey(Zakaznik, on_delete=models.PROTECT, related_name='kamiony', verbose_name='Zákazník')
    odberatel = models.ForeignKey(Odberatel, on_delete=models.SET_NULL, related_name='kamiony', verbose_name='Odběratel', blank=True, null=True)
    datum = models.DateField(verbose_name='Datum')
    cislo_dl = models.CharField(max_length=50, verbose_name='Číslo DL', blank=True, null=True)
    prijem_vydej = models.CharField(choices=KamionChoice.choices, max_length=1, verbose_name='Přijem/Výdej', default=KamionChoice.PRIJEM)
    poradove_cislo = models.PositiveIntegerField(verbose_name='Pořadové číslo', blank=True, null=True)
    poznamka = models.TextField(verbose_name='Poznámka do DL', blank=True, null=True)
    text_upozorneni = models.CharField(max_length=100, verbose_name='Text upozornění na DL', blank=True, null=True,
                                        help_text='Text upozornění pro bedny, které se nefakturují. Je stejně podbarven jako tyto bedny v dodacím listu.')
    prepsani_hmotnosti_brutto = models.DecimalField(max_digits=8, decimal_places=1, verbose_name='Přepsání hmotnosti brutto', blank=True, null=True,
                                                    help_text='Pokud je vyplněno, použije se tato hmotnost brutto na dodacím listu místo vypočtené hodnoty.')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Kamión'
        verbose_name_plural = 'kamióny'
        ordering = ['-id']

    def __str__(self):
        """
        Vrací řetězec reprezentující kamion. Datum je upraveno do formátu YY-MM.
        """
        return f'{self.poradove_cislo}.{self.prijem_vydej} {self.zakaznik.zkratka} {self.datum.strftime("%Y")}'

    @property
    def celkova_hmotnost_netto(self):
        """
        Vrací celkovou hmotnost netto všech beden spojených s tímto kamionem.
        """
        # Pokud je kamion pro výdej, vrací hmotnost beden spojených s výdejem.
        if self.prijem_vydej == KamionChoice.VYDEJ:
            return Bedna.objects.filter(
                zakazka__kamion_vydej=self
            ).aggregate(suma=Sum('hmotnost'))['suma'] or Decimal('0.0')
        # Pokud je kamion pro příjem, vrací hmotnost beden spojených s příjmem.
        elif self.prijem_vydej == KamionChoice.PRIJEM:
            return Bedna.objects.filter(
                zakazka__kamion_prijem=self
            ).aggregate(suma=Sum('hmotnost'))['suma'] or Decimal('0.0')
        else:
            raise ValidationError(_("Neplatný typ kamionu. Musí být buď 'Přijem' nebo 'Výdej'."))
        
    @property
    def celkova_hmotnost_fakturovanych_netto(self):
        """
        Vrací celkovou hmotnost netto všech beden spojených s tímto kamionem,
        které jsou označeny jako fakturovat == True.
        """
        # Pokud je kamion pro výdej, vrací hmotnost beden spojených s výdejem.
        if self.prijem_vydej == KamionChoice.VYDEJ:
            return Bedna.objects.filter(
                zakazka__kamion_vydej=self,
                fakturovat=True
            ).aggregate(suma=Sum('hmotnost'))['suma'] or Decimal('0.0')
        # Pokud je kamion pro příjem, vrací hmotnost beden spojených s příjmem.
        elif self.prijem_vydej == KamionChoice.PRIJEM:
            return Bedna.objects.filter(
                zakazka__kamion_prijem=self,
                fakturovat=True
            ).aggregate(suma=Sum('hmotnost'))['suma'] or Decimal('0.0')
        else:
            raise ValidationError(_("Neplatný typ kamionu. Musí být buď 'Přijem' nebo 'Výdej'."))
    
    @property
    def celkova_hmotnost_brutto(self):
        """
        Vrací celkovou hmotnost brutto všech beden ve všech zakázkách spojených s tímto kamionem.
        """
        # Pokud je kamion pro výdej, vrací hmotnost beden spojených s výdejem.
        if self.prijem_vydej == KamionChoice.VYDEJ:
            celkova_tara = Bedna.objects.filter(
                zakazka__kamion_vydej=self
            ).aggregate(suma=Sum('tara'))['suma'] or Decimal('0.0')
        # Pokud je kamion pro příjem, vrací hmotnost beden spojených s příjmem.
        elif self.prijem_vydej == KamionChoice.PRIJEM:
            celkova_tara = Bedna.objects.filter(
                zakazka__kamion_prijem=self
            ).aggregate(suma=Sum('tara'))['suma'] or Decimal('0.0')
        else:
            raise ValidationError(_("Neplatný typ kamionu. Musí být buď 'Přijem' nebo 'Výdej'."))
        return celkova_tara + self.celkova_hmotnost_netto
    
    @property
    def cena_za_kamion_vydej(self):
        """
        Vrací cenu za kamion výdej na základě zákazníka, předpisu a délky, pouze pro kamionu výdej.
        Celkovou cenu vypočte podle property cena_za_zakazku pro jednotlivé zakázky v kamionu.
        Neobsahuje bedny, které mají fakturovat=False.
        Pokud není cena nalezena, vrací 0.
        """
        # Získá všechny zakázky obsažené v kamionu.        
        zakazky = self.zakazky_vydej.all()
        if zakazky.exists() and self.prijem_vydej == KamionChoice.VYDEJ:
            return Decimal(
                sum(
                    Decimal(zakazka.cena_za_zakazku) for zakazka in zakazky
                ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            )
        return Decimal('0.00')
    
    @property
    def cena_rovnani_za_kamion_vydej(self):
        """
        Vrací cenu rovnání za kamion výdej na základě zákazníka, předpisu a délky, pouze pro kamionu výdej.
        Celkovou cenu vypočte podle property cena_rovnani_za_zakazku pro jednotlivé zakázky v kamionu.
        Neobsahuje bedny, které mají fakturovat=False.
        Pokud není cena nalezena, vrací 0.
        """
        # Získá všechny zakázky obsažené v kamionu.        
        zakazky = self.zakazky_vydej.all()
        if zakazky.exists() and self.prijem_vydej == KamionChoice.VYDEJ:
            return Decimal(
                sum(
                    Decimal(zakazka.cena_rovnani_za_zakazku) for zakazka in zakazky
                ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            )
        return Decimal('0.00')

    @property
    def pocet_vyrovnanych_beden(self):
        """
        Vrací celkový počet vyrovnaných beden spojených s kamionem výdej.
        Neobsahuje bedny, které mají fakturovat=False.
        """
        if self.prijem_vydej == KamionChoice.VYDEJ:
            return Bedna.objects.filter(
                zakazka__kamion_vydej=self,
                rovnat=RovnaniChoice.VYROVNANA,
                fakturovat=True
            ).count()
        return 0
    
    @property
    def cena_tryskani_za_kamion_vydej(self):
        """
        Vrací cenu tryskání za kamion výdej na základě zákazníka, předpisu a délky, pouze pro kamionu výdej.
        Celkovou cenu vypočte podle property cena_tryskani_za_zakazku pro jednotlivé zakázky v kamionu.
        Neobsahuje bedny, které mají fakturovat=False.
        Pokud není cena nalezena, vrací 0.
        """
        # Získá všechny zakázky obsažené v kamionu.        
        zakazky = self.zakazky_vydej.all()
        if zakazky.exists() and self.prijem_vydej == KamionChoice.VYDEJ:
            return Decimal(
                sum(
                    Decimal(zakazka.cena_tryskani_za_zakazku) for zakazka in zakazky
                ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            )
        return Decimal('0.00')
    
    @property
    def pocet_otryskanych_beden(self):
        """
        Vrací celkový počet otryskaných beden spojených s kamionem výdej.
        Neobsahuje bedny, které mají fakturovat=False.
        """
        if self.prijem_vydej == KamionChoice.VYDEJ:
            return Bedna.objects.filter(
                zakazka__kamion_vydej=self,
                tryskat=TryskaniChoice.OTRYSKANA,
                fakturovat=True
            ).count()
        return 0

    @property
    def pocet_beden_skladem(self):
        """
        Vrací celkový počet beden spojených s tímto kamionem, které jsou ve stavu STAV_BEDNY_SKLADEM.
        """
        if self.prijem_vydej == KamionChoice.PRIJEM:
            return Bedna.objects.filter(
                zakazka__kamion_prijem=self,
                stav_bedny__in=STAV_BEDNY_SKLADEM,
            ).count()
        return 0

    @property
    def pocet_beden_expedovano(self):
        """
        Vrací počet beden spojených s tímto kamionem, které jsou ve stavu EXPEDOVANO.
        """
        # Pokud je kamion pro příjem, vrací počet beden ve stavu expedováno.
        if self.prijem_vydej == KamionChoice.PRIJEM:
            return Bedna.objects.filter(
                zakazka__kamion_prijem=self,
                stav_bedny=StavBednyChoice.EXPEDOVANO
            ).count()
        # Pokud je kamion pro výdej, vrací všechny bedny - všechny jsou expedovány.
        if self.prijem_vydej == KamionChoice.VYDEJ:
            return Bedna.objects.filter(
                zakazka__kamion_vydej=self,
            ).count()
        raise ValidationError(_("Neplatný typ kamionu. Musí být buď 'Přijem' nebo 'Výdej'."))
    
    @property
    def pocet_beden_expedovano_fakturovanych(self):
        """
        Vrací počet beden spojených s tímto kamionem, které jsou ve stavu EXPEDOVANO a mají fakturovat=True.
        """
        # Pokud je kamion pro příjem, vrací počet beden ve stavu expedováno.
        if self.prijem_vydej == KamionChoice.PRIJEM:
            return Bedna.objects.filter(
                zakazka__kamion_prijem=self,
                stav_bedny=StavBednyChoice.EXPEDOVANO,
                fakturovat=True
            ).count()
        # Pokud je kamion pro výdej, vrací všechny bedny s fakturovat=True - všechny jsou expedovány.
        if self.prijem_vydej == KamionChoice.VYDEJ:
            return Bedna.objects.filter(
                zakazka__kamion_vydej=self,
                fakturovat=True
            ).count()
        raise ValidationError(_("Neplatný typ kamionu. Musí být buď 'Přijem' nebo 'Výdej'."))
    
    @property
    def obsahuje_bedny_s_priznakem_nefakturovat(self):
        """
        Vrací True, pokud kamion obsahuje alespoň jednu bednu, která má fakturovat=False.
        Jinak vrací False.
        """
        if self.prijem_vydej == KamionChoice.VYDEJ:
            return Bedna.objects.filter(
                zakazka__kamion_vydej=self,
                fakturovat=False
            ).exists()
        elif self.prijem_vydej == KamionChoice.PRIJEM:
            return Bedna.objects.filter(
                zakazka__kamion_prijem=self,
                fakturovat=False
            ).exists()
        else:
            raise ValidationError(_("Neplatný typ kamionu. Musí být buď 'Přijem' nebo 'Výdej'."))

    @property
    def hmotnost_otryskanych_beden(self):
        """
        Vrací pro kamion výdej celkovou hmotnost beden, které mají stav tryskání: otryskaná a fakturovat=True.
        """
        if self.prijem_vydej == KamionChoice.VYDEJ:
            return Bedna.objects.filter(
                zakazka__kamion_vydej=self,
                tryskat=TryskaniChoice.OTRYSKANA,
                fakturovat=True
            ).aggregate(suma=Sum('hmotnost'))['suma'] or Decimal('0.0')
        raise ValidationError(_("Neplatný typ kamionu. Musí být buď 'Přijem' nebo 'Výdej'."))

    @property
    def hmotnost_vyrovnanych_beden(self):
        """
        Vrací pro kamion výdej celkovou hmotnost beden, které mají stav rovnání: vyrovnaná a fakturovat=True.
        """
        if self.prijem_vydej == KamionChoice.VYDEJ:
            return Bedna.objects.filter(
                zakazka__kamion_vydej=self,
                rovnat=RovnaniChoice.VYROVNANA,
                fakturovat=True
            ).aggregate(suma=Sum('hmotnost'))['suma'] or Decimal('0.0')
        raise ValidationError(_("Neplatný typ kamionu. Musí být buď 'Přijem' nebo 'Výdej'."))  

    def get_admin_url(self):
        """
        Vrací URL pro zobrazení detailu kamionu v administraci.
        """
        return reverse("admin:orders_kamion_change", args=[self.pk])    
    
    def save(self, *args, **kwargs):
        """
        Uloží instanci Kamion.
        - Pokud se jedná o novou instanci (bez PK), před uložením:
          * nastaví `poradove_cislo` na další číslo v řadě pro daného zákazníka, typ kamionu (prijem_vydej) a daný rok.
          * pokud je vytvářený kamion pro výdej, nastaví cislo_dl na požadovaný řetězec.
        """
        is_existing_instance = bool(self.pk)

        if not is_existing_instance:
            zakaznik = self.zakaznik
            typ_kamionu = self.prijem_vydej
            rok = self.datum.year

            # Při vytváření nového kamionu nastavíme pořadové číslo kamionu na další v řadě - pro daného zákazníka, typ kamionu a rok.
            posledni = (
                self.__class__.objects
                .filter(zakaznik=zakaznik, prijem_vydej=typ_kamionu, datum__year=rok)
                .order_by("-poradove_cislo")
                .first()
            )
            self.poradove_cislo = ((posledni.poradove_cislo + 1) if posledni else 1)

            if typ_kamionu == KamionChoice.VYDEJ:
                # Pokud je kamion pro výdej, nastavíme cislo_dl na požadovaný řetězec.
                self.cislo_dl = f"EXP-{int(self.poradove_cislo):03d}-{self.datum.year}-{self.zakaznik.zkratka}"

        super().save(*args, **kwargs)
    
    # --- Delete guards ---
    def delete(self, using=None, keep_parents=False):
        """
        Zamezí mazání kamionu příjem, pokud má bedny v jiném stavu než NEPRIJATO.
        """
        if self.prijem_vydej == KamionChoice.PRIJEM:
            if Bedna.objects.filter(zakazka__kamion_prijem=self).exclude(stav_bedny=StavBednyChoice.NEPRIJATO).exists():
                raise ProtectedError(
                    "Mazání zablokováno: Kamión příjem obsahuje bedny v jiném stavu než NEPRIJATO.",
                    [self],
                )
        return super().delete(using=using, keep_parents=keep_parents)
    

class Pletivo(models.Model):
    """
    Pletivo použité v předpisech.
    """
    nazev = models.CharField(max_length=1, verbose_name='Název pletiva', choices=AlphabetChoice.choices, unique=True)
    rozmer_oka = models.PositiveSmallIntegerField(verbose_name='Rozměr oka', validators=[MaxValueValidator(30)], blank=True, null=True)
    tloustka_dratu = models.DecimalField(verbose_name='Tloušťka drátu', max_digits=3, decimal_places=1, blank=True, null=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Pletivo'
        verbose_name_plural = 'pletiva'
        ordering = ['nazev']

    def __str__(self):
        return self.nazev


class Predpis(models.Model):
    """
    Předpis zákazníka pro tepelné zpracování pro přiřazení skupiny TZ.
    """
    nazev = models.CharField(max_length=50, verbose_name='Název předpisu',)
    skupina = models.PositiveSmallIntegerField(verbose_name='Skupina TZ', blank=True, null=True)
    ohyb = models.CharField(max_length=50, verbose_name='Ohyb', blank=True, null=True)
    krut = models.CharField(max_length=50, verbose_name='Krut', blank=True, null=True)
    povrch = models.CharField(max_length=50, verbose_name='Povrch', blank=True, null=True)
    jadro = models.CharField(max_length=50, verbose_name='Jádro', blank=True, null=True)
    vrstva = models.CharField(max_length=50, verbose_name='Vrstva', blank=True, null=True)
    vrstva_2 = models.CharField(max_length=50, verbose_name='Vrstva 2', blank=True, null=True)
    popousteni = models.CharField(max_length=50, verbose_name='Popouštění', blank=True, null=True)
    sarzovani = models.CharField(max_length=50, verbose_name='Šaržování', blank=True, null=True)
    pletivo = models.ForeignKey(Pletivo, on_delete=models.SET_NULL, related_name='predpisy', verbose_name='Pletivo', blank=True, null=True)
    popis_povrch = models.CharField(max_length=50, verbose_name='Povrch - popis', blank=True, null=True)
    popis_povrch_2 = models.CharField(max_length=50, verbose_name='Povrch - popis 2', blank=True, null=True)
    popis_jadro = models.CharField(max_length=50, verbose_name='Jádro - popis', blank=True, null=True)
    popis_jadro_2 = models.CharField(max_length=50, verbose_name='Jádro - popis 2', blank=True, null=True)
    popis_vrstva = models.CharField(max_length=50, verbose_name='Vrstva - popis', blank=True, null=True)
    popis_vrstva_2 = models.CharField(max_length=50, verbose_name='Vrstva - popis 2', blank=True, null=True)
    popis_ohyb = models.CharField(max_length=50, verbose_name='Ohyb - popis', blank=True, null=True)
    popis_ohyb_2 = models.CharField(max_length=50, verbose_name='Ohyb - popis 2', blank=True, null=True)
    popis_krut = models.CharField(max_length=50, verbose_name='Krut - popis', blank=True, null=True)
    popis_krut_2 = models.CharField(max_length=50, verbose_name='Krut - popis 2', blank=True, null=True)
    poznamka = models.CharField(max_length=50, verbose_name='Poznámka', blank=True, null=True)
    aktivni = models.BooleanField(default=True, verbose_name='Aktivní',
                                   help_text='Zda je předpis aktivní a může být přiřazen k zakázce.')
    zakaznik = models.ForeignKey(Zakaznik, on_delete=models.CASCADE, related_name='predpisy', verbose_name='Zákazník')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Předpis'
        verbose_name_plural = 'předpisy'
        ordering = ['-zakaznik__zkratka', 'nazev']

    def __str__(self):
        aktivni_text = 'A' if self.aktivni else 'N'
        return f'{self.nazev} ({self.zakaznik.zkratka}) - {aktivni_text}'
    
    def get_admin_url(self):
        """
        Vrací URL pro zobrazení detailu předpisu v administraci.
        """
        return reverse("admin:orders_predpis_change", args=[self.pk])    
        

class TypHlavy(models.Model):
    """
    Model pro typ hlavy.
    Umožňuje definovat různé typy hlav, které mohou být použity v zakázkách.
    """
    nazev = models.CharField(max_length=10, verbose_name='Typ hlavy', unique=True)
    popis = models.CharField(max_length=50, blank=True, null=True, verbose_name='Popis')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Typ hlavy'
        verbose_name_plural = 'typy hlav'
        ordering = ['nazev']

    def __str__(self):
        return self.nazev    
    
    def get_admin_url(self):
        """
        Vrací URL pro zobrazení detailu typu hlavy v administraci.
        """
        return reverse("admin:orders_typhlavy_change", args=[self.pk])  


class Zakazka(models.Model):
    kamion_prijem = models.ForeignKey(Kamion, on_delete=models.CASCADE, related_name='zakazky_prijem', verbose_name='Kamión příjem', null=True, blank=True)
    kamion_vydej = models.ForeignKey(Kamion, on_delete=models.PROTECT, related_name='zakazky_vydej', verbose_name='Kamión výdej', null=True, blank=True)
    puvodni_zakazka = models.ForeignKey('self', on_delete=models.SET_NULL, related_name='oddelene_zakazky', verbose_name='Původní zakázka', null=True, blank=True, help_text='Odkaz na původní zakázku, ze které byla tato oddělena při expedici.')
    artikl = models.CharField(max_length=50, verbose_name='Artikl / Zakázka')
    prumer = models.DecimalField(max_digits=4, decimal_places=1, verbose_name='Průměr')
    delka = models.DecimalField(max_digits=6, decimal_places=1, verbose_name='Délka')
    predpis = models.ForeignKey(Predpis, on_delete=models.PROTECT, related_name='zakazky', verbose_name='Předpis / Výkres')
    typ_hlavy = models.ForeignKey(TypHlavy, on_delete=models.PROTECT, related_name='zakazky', verbose_name='Typ hlavy')
    celozavit = models.BooleanField(default=False, verbose_name='Celozávit')
    popis = models.CharField(max_length=100, verbose_name='Popis')
    vrstva = models.CharField(max_length=20, null=True, blank=True, verbose_name='Beschichtung')
    povrch = models.CharField(max_length=20, null=True, blank=True, verbose_name='Oberfläche')
    prubeh = models.CharField(max_length=20, null=True, blank=True, verbose_name='Vorgang+')
    priorita = models.CharField(choices=PrioritaChoice.choices, max_length=5, default=PrioritaChoice.NIZKA, verbose_name='Priorita')
    odberatel = models.ForeignKey(Odberatel, on_delete=models.SET_NULL, related_name='zakazky', verbose_name='Odběratel', blank=True, null=True)
    expedovano = models.BooleanField(default=False, verbose_name='Expedováno')
    tvrdost_povrchu = models.CharField(max_length=50, blank=True, null=True, verbose_name='Tvrdost povrchu')
    tvrdost_jadra = models.CharField(max_length=50, blank=True, null=True, verbose_name='Tvrdost jádra')
    ohyb = models.CharField(max_length=50, blank=True, null=True, verbose_name='Ohyb')
    krut = models.CharField(max_length=50, blank=True, null=True, verbose_name='Krut')
    hazeni = models.CharField(max_length=50, blank=True, null=True, verbose_name='Házení')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Zakázka'
        verbose_name_plural = 'zakázky'
        ordering = ['id']
        permissions = (
            ('change_expedovana_zakazka', 'Může upravovat expedované zakázky'),
            ('change_mereni_zakazky', 'Může upravovat měření v zakázce'),
        )

    def __str__(self):
        return f'{self.artikl}-{self.kamion_prijem.datum.strftime("%d.%m.%y")}-{self.kamion_prijem.poradove_cislo}. {self.kamion_prijem.zakaznik.zkratka}'

    @property
    def celkova_hmotnost(self):
        return self.bedny.aggregate(suma=Sum('hmotnost'))['suma'] or 0
    
    @property
    def celkova_hmotnost_fakturovanych(self):
        return self.bedny.filter(fakturovat=True).aggregate(suma=Sum('hmotnost'))['suma'] or 0
    
    @property
    def pocet_beden(self):
        """
        Vrací počet beden spojených s touto zakázkou.
        """
        if not hasattr(self, 'bedny'):
            return 0
        return self.bedny.count()
    
    @property
    def pocet_beden_fakturovanych(self):
        """
        Vrací počet beden spojených s touto zakázkou, které mají fakturovat=True.
        """
        if not hasattr(self, 'bedny'):
            return 0
        return self.bedny.filter(fakturovat=True).count()

    def get_admin_url(self):
        """
        Vrací URL pro zobrazení detailu zakázky v administraci.
        """
        return reverse("admin:orders_zakazka_change", args=[self.pk])
    
    @property
    def zkraceny_popis(self):
        """
        Vrátí vše do prvního výskytu čísla v popisu zakázky.
        """
        match = re.match(r"^(.*?)(\s+\d+.*)?$", self.popis)
        return match.group(1).strip() if match else self.popis

    @property
    def cena_za_kg(self):
        """
        Vrací cenu zboží v zakázce v EUR/kg.
        Výpočet ceny se provádí na základě předpisu, délky a zákazníka.
        1. Najde se předpis, zákazník a délka z bedny/zakázky.
        2. Pokud není předpis nebo zákazník, vrací 0.
        3. Najde se cena v tabulce Cena podle předpisu, délky a zákazníka.
        4. Pokud je cena nalezena, vrátí se cena_za_kg, jinak 0.
        """
        predpis = self.predpis
        zakaznik = self.kamion_prijem.zakaznik
        delka = self.delka

        # Pokud není předpis nebo zákazník, vrací 0
        if not predpis or not zakaznik:
            return Decimal('0.00')

        try:
            cena = Cena.objects.get(
                predpis=predpis,
                delka_min__lte=delka,
                delka_max__gt=delka,
                zakaznik=zakaznik
            )
        except Cena.DoesNotExist:
            return Decimal('0.00')
        except Cena.MultipleObjectsReturned:
            logger.warning(
                f"Nalezeno více cen pro zakázku {self.pk} "
                f"(predpis={getattr(predpis, 'id', predpis)}, delka={delka}, zakaznik={getattr(zakaznik, 'id', zakaznik)})"
            )
            return Decimal('0.00')

        return cena.cena_za_kg or Decimal('0.00')
           
    @property
    def cena_za_zakazku(self):
        """
        Vrací cenu zboží v zakázce v EUR/bednu.
        Výpočet se provádí jakou součet ceny za bednu pro všechny bedny v zakázce,
        které mají nastaveno fakturovat=True.
        """
        return sum(
            (bedna.cena_za_bednu for bedna in self.bedny.filter(fakturovat=True)),
            Decimal('0.00'),
        )

    @property
    def prvni_bedna_v_zakazce(self):
        """
        Vrací první bednu v zakázce podle nejnižšího cisla_bedny.
        Pokud zakázka nemá žádné bedny, vrací None.
        """
        return self.bedny.order_by('cislo_bedny').first()

    @property
    def cena_rovnani_za_kg(self):
        """
        Vrací cenu za rovnání v zakázce v EUR/kg.
        Výpočet ceny se provádí na základě předpisu, délky a zákazníka.
        Výpočet funguje pouze pro zákazníky s příznakem fakturovat_rovnani = True, protože se jim účtuje rovnání zvlášť.
        1. Najde se předpis, zákazník a délka ze zakázky.
        2. Pokud není předpis nebo zákazník nebo zákazník nemá příznak fakturovat_rovnani, vrací 0.
        3. Najde se cena rovnání v tabulce Cena podle předpisu, délky a zákazníka.
        4. Pokud je cena nalezena, vrátí se cena_rovnani_za_kg, jinak 0.
        """
        predpis = self.predpis
        zakaznik = self.kamion_prijem.zakaznik
        delka = self.delka

        # Pokud není předpis nebo zákazník nebo nemá příznak fakturovat_rovnani, vrací 0
        if not predpis or not zakaznik or not zakaznik.fakturovat_rovnani:
            return Decimal('0.00')

        try:
            cena = Cena.objects.get(
                predpis=predpis,
                delka_min__lte=delka,
                delka_max__gt=delka,
                zakaznik=zakaznik
            )
        except Cena.DoesNotExist:
            return Decimal('0.00')
        except Cena.MultipleObjectsReturned:
            logger.warning(
                f"Nalezeno více cen rovnání pro zakázku {self.pk} "
                f"(predpis={getattr(predpis, 'id', predpis)}, delka={delka}, zakaznik={getattr(zakaznik, 'id', zakaznik)})"
            )
            return Decimal('0.00')

        return cena.cena_rovnani_za_kg or Decimal('0.00')    

    @property
    def cena_rovnani_za_zakazku(self):
        """
        Vrací cenu rovnání v zakázce v EUR/zakazka.
        Výpočet se provádí jakou součet ceny rovnani za bednu pro všechny bedny v zakázce,
        které mají nastaveno fakturovat=True.
        """
        return sum(
            (bedna.cena_rovnani_za_bednu for bedna in self.bedny.filter(fakturovat=True)),
            Decimal('0.00'),
        )

    @property
    def cena_tryskani_za_kg(self):
        """
        Vrací cenu tryskání zboží v zakázce v EUR/kg.
        Výpočet ceny se provádí na základě předpisu, délky a zákazníka.
        Výpočet funguje pouze pro zákazníky s příznakem fakturovat_tryskani = True, protože se jim účtuje tryskání zvlášť.
        1. Najde se předpis, zákazník a délka z bedny/zakázky.
        2. Pokud není předpis nebo zákazník nebo zákazník nemá příznak fakturovat_tryskani, vrací 0.
        3. Najde se cena tryskání v tabulce Cena podle předpisu, délky a zákazníka.
        4. Pokud je cena nalezena, vrátí se cena_tryskani_za_kg, jinak 0.
        """
        predpis = self.predpis
        zakaznik = self.kamion_prijem.zakaznik
        delka = self.delka

        # Pokud není předpis nebo zákazník nebo zákazník nemá příznak fakturovat_tryskani, vrací 0
        if not predpis or not zakaznik or not zakaznik.fakturovat_tryskani:
            return Decimal('0.00')

        try:
            cena = Cena.objects.get(
                predpis=predpis,
                delka_min__lte=delka,
                delka_max__gt=delka,
                zakaznik=zakaznik
            )
        except Cena.DoesNotExist:
            return Decimal('0.00')
        except Cena.MultipleObjectsReturned:
            logger.warning(
                f"Nalezeno více cen tryskání pro zakázku {self.pk} "
                f"(predpis={getattr(predpis, 'id', predpis)}, delka={delka}, zakaznik={getattr(zakaznik, 'id', zakaznik)})"
            )
            return Decimal('0.00')

        return cena.cena_tryskani_za_kg or Decimal('0.00')
            
    @property
    def cena_tryskani_za_zakazku(self):
        """
        Vrací cenu tryskání v zakázce v EUR/zakazka.
        Výpočet se provádí jakou součet ceny tryskani za bednu pro všechny bedny v zakázce,
        které mají nastaveno fakturovat=True.
        """
        return sum(
            (bedna.cena_tryskani_za_bednu for bedna in self.bedny.filter(fakturovat=True)),
            Decimal('0.00'),
        )

    @property
    def hmotnost_vyrovnanych_beden(self):
        """
        Vrací celkovou hmotnost vyrovnaných beden v zakázce, které mají nastaveno fakturovat=True.
        """
        return self.bedny.filter(
            rovnat=RovnaniChoice.VYROVNANA,
            fakturovat=True
        ).aggregate(suma=Sum('hmotnost'))['suma'] or Decimal('0.0')
    
    @property
    def hmotnost_otryskanych_beden(self):
        """
        Vrací celkovou hmotnost otryskaných beden v zakázce.
        """
        return self.bedny.filter(
            tryskat=TryskaniChoice.OTRYSKANA,
            fakturovat=True
        ).aggregate(suma=Sum('hmotnost'))['suma'] or Decimal('0.0')

    @property
    def pocet_vyrovnanych_beden(self):
        """
        Vrací počet vyrovnaných beden v zakázce, které mají nastaveno fakturovat=True.
        """
        return self.bedny.filter(
            rovnat=RovnaniChoice.VYROVNANA,
            fakturovat=True
        ).count()
    
    @property
    def pocet_otryskanych_beden(self):
        """
        Vrací počet otryskaných beden v zakázce, které mají nastaveno fakturovat=True.
        """
        return self.bedny.filter(
            tryskat=TryskaniChoice.OTRYSKANA,
            fakturovat=True
        ).count()
    
    @property
    def vyrobni_zakazky_beden(self):
        """
        Vrací seznam výrobních zakázek všech beden v zakázce jako řetězec oddělený čárkami.
        Pokud bedna nemá výrobní zakázku, je v seznamu nahrazeno textem "N/A".
        """
        vyrobni_zakazky = [
            bedna.vyrobni_zakazka if bedna.vyrobni_zakazka else "N/A"
            for bedna in self.bedny.all()
        ]
        return ", ".join(vyrobni_zakazky)

    # --- Delete guards ---
    def delete(self, using=None, keep_parents=False):
        """
        Zamezí mazání zakázky, pokud má bedny v jiném stavu než NEPRIJATO.
        """        
        if Bedna.objects.filter(zakazka=self).exclude(stav_bedny=StavBednyChoice.NEPRIJATO).exists():
            raise ProtectedError(
                "Mazání zablokováno: Zakázka obsahuje bedny v jiném stavu než NEPRIJATO.",
                [self],
            )
        return super().delete(using=using, keep_parents=keep_parents)
    

class Cena(models.Model):
    """
    Model pro cenu zakázky.
    Umožňuje přiřadit cenu k zakázce a sledovat historii změn cen.
    """
    popis = models.CharField(max_length=50, verbose_name='Popis ceny')
    zakaznik = models.ForeignKey(Zakaznik, on_delete=models.CASCADE, related_name='ceny', verbose_name='Zákazník')
    predpis = models.ManyToManyField(Predpis, related_name='ceny', verbose_name='Předpisy', blank=True,
                                        help_text='Předpisy, ke kterým se cena vztahuje. Může být více předpisů pro daný průměr a cenu.')
    delka_min = models.DecimalField(max_digits=6, decimal_places=1, verbose_name='Délka od (včetně)')
    delka_max = models.DecimalField(max_digits=6, decimal_places=1, verbose_name='Délka do (vyjma)')
    cena_za_kg = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Cena kalení (EUR/kg)')
    cena_rovnani_za_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Cena rovnání (EUR/kg)')
    cena_tryskani_za_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Cena tryskání (EUR/kg)')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Cena'
        verbose_name_plural = 'ceny'
        ordering = ['popis', 'delka_min']

    def __str__(self):
        return f'{self.zakaznik.zkratka} {self.popis}x{int(self.delka_min)}-{int(self.delka_max)}'    


class Pozice(models.Model):
    kod = models.CharField(max_length=1, choices=AlphabetChoice.choices, verbose_name='Kód pozice', unique=True)
    kapacita = models.PositiveIntegerField(verbose_name='Kapacita', default=15)

    class Meta:
        verbose_name = 'Pozice'
        verbose_name_plural = 'pozice'
        ordering = ['kod']

    def __str__(self):
        return f'{self.kod}'

    def get_admin_url(self):
        return reverse('admin:orders_pozice_change', args=[self.pk])

    @property
    def pocet_beden(self):
        return self.bedny.count()
    
    @property
    def vyuziti_procent(self):
        if self.kapacita == 0:
            return 0
        return round((self.pocet_beden / self.kapacita) * 100, 1)


class PoziceZakazkaOrder(models.Model):
    """
    Ukládá preferované umístění a pořadí zakázky v rámci konkrétní pozice
    pro potřeby řazení v dashboardu "Bedny k navezení" a tisku.

    Unikátní pro dvojici (pozice, zakazka).
    """
    pozice = models.ForeignKey('Pozice', on_delete=models.CASCADE, related_name='zakazky_poradi')
    zakazka = models.ForeignKey('Zakazka', on_delete=models.CASCADE, related_name='pozice_poradi')
    poradi = models.PositiveIntegerField(default=1, verbose_name='Pořadí v pozici')

    class Meta:
        verbose_name = 'Pořadí zakázky v pozici'
        verbose_name_plural = 'Pořadí zakázek v pozici'
        constraints = [
            models.UniqueConstraint(fields=['pozice', 'zakazka'], name='uniq_pozice_zakazka'),
            models.UniqueConstraint(fields=['pozice', 'poradi'], name='uniq_pozice_poradi'),
        ]
        ordering = ['pozice__kod', 'poradi', 'zakazka_id']

    def __str__(self):
        return f"{self.pozice.kod if self.pozice_id else '?'} – {self.zakazka_id}: #{self.poradi}"


hmotnost_validator = MinValueValidator(Decimal('0.0'), message='Hmotnost a tára musí být kladné číslo.')

class Bedna(models.Model):
    zakazka = models.ForeignKey(Zakazka, on_delete=models.CASCADE, related_name='bedny', verbose_name='Zakázka')
    pozice = models.ForeignKey(Pozice, on_delete=models.SET_NULL, null=True, blank=True, related_name='bedny', verbose_name='Pozice')
    cislo_bedny = models.PositiveIntegerField(blank=True, verbose_name='Číslo bedny', unique=True,)
    hmotnost = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name='Netto kg', validators=[hmotnost_validator],)
    tara = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name='Tára kg', validators=[hmotnost_validator],)
    material = models.CharField(max_length=20, null=True, blank=True, verbose_name='Materiál')
    sarze = models.CharField(max_length=20, null=True, blank=True, verbose_name='Šarže mat. / Charge')
    behalter_nr = models.CharField(max_length=20, null=True, blank=True, verbose_name='Č. b. zák.')
    dodatecne_info = models.CharField(max_length=100, null=True, blank=True, verbose_name='Sonder / Zusatzinfo')
    dodavatel_materialu = models.CharField(max_length=10, null=True, blank=True, verbose_name='Lief.')
    vyrobni_zakazka = models.CharField(max_length=20, null=True, blank=True, verbose_name='FA / Bestell-Nr.')
    tryskat = models.CharField(choices=TryskaniChoice.choices, max_length=5, default=TryskaniChoice.NEZADANO, verbose_name='Tryskání')
    rovnat = models.CharField(choices=RovnaniChoice.choices, max_length=5, default=RovnaniChoice.NEZADANO, verbose_name='Rovnání')
    # zatím default pro zinkovat je NEZINKOVAT, protože většina beden se nezinkuje, po rozjetí externího zinkování změnit na NEZADANO
    zinkovat = models.CharField(choices=ZinkovaniChoice.choices, max_length=5, default=ZinkovaniChoice.NEZINKOVAT, verbose_name='Zinkování')
    stav_bedny = models.CharField(choices=StavBednyChoice.choices, max_length=2, default=StavBednyChoice.NEPRIJATO, verbose_name='Stav bedny')
    mnozstvi = models.PositiveIntegerField(null=True, blank=True, verbose_name='Množ. ks')
    poznamka = models.CharField(max_length=100, null=True, blank=True, verbose_name='Poznámka HPM')
    odfosfatovat = models.BooleanField(default=False, verbose_name='Odfos.?')
    pozastaveno = models.BooleanField(default=False, verbose_name='Pozastaveno?',
                                       help_text='Pokud je bedna pozastavena, nelze s ní pracovat, dokud ji odpovědná osoba neuvolní.')
    fakturovat = models.BooleanField(default=True, verbose_name='Fakturovat?',
                                     help_text='Pokud není bedna určena k fakturaci, nebude zahrnuta do proforma faktury pro zákazníka.')    
    poznamka_k_navezeni = models.CharField(max_length=50, blank=True, null=True, verbose_name='Poznámka k navezení')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Bedna'
        verbose_name_plural = 'bedny'
        ordering = ['id']
        permissions = (
            ('change_expedovana_bedna', 'Může upravovat expedované bedny'),
            ('change_pozastavena_bedna', 'Může upravovat a uvolnit pozastavené bedny'),
            ('change_neprijata_bedna', 'Může upravovat bedny ve stavu NEPŘIJATO'),
            ('change_poznamka_neprijata_bedna', 'Může upravovat poznámku u bedny ve stavu NEPŘIJATO'),
            ('mark_bedna_navezeno', 'Může označit bednu jako navezenou a vrátit ji zpět na příjem'),
        )
        constraints = [models.CheckConstraint(
            name="bedna_valid_when_not_neprijato",
            check= Q(stav_bedny=StavBednyChoice.NEPRIJATO) | ( Q(hmotnost__isnull=False, tara__isnull=False, mnozstvi__isnull=False) & Q(hmotnost__gt=0, tara__gt=0, mnozstvi__gt=0) ),
            ),
        ]

    def __str__(self):
        return f'{self.zakazka.kamion_prijem.zakaznik.zkratka} {self.zakazka.kamion_prijem.datum.strftime("%d.%m.%y")}-{self.zakazka.artikl}-{self.zakazka.prumer}x{self.zakazka.delka}-{self.cislo_bedny}'
    
    def get_admin_url(self):
        """
        Vrací URL pro zobrazení detailu bedny v administraci.
        """
        return reverse("admin:orders_bedna_change", args=[self.pk])
    
    @property
    def poradi_bedny(self):
        """
        Vrací pořadí bedny v rámci zakázky - dle čísla bedny z celkového počtu beden v zakázce.
        """
        cisla_beden = self.zakazka.bedny.values_list('cislo_bedny', flat=True).order_by('cislo_bedny')
        if len(cisla_beden) == 0:
            return 0
        for i, cislo in enumerate(cisla_beden, start=1):
            if cislo == self.cislo_bedny:
                return i 
            
        return 0  # pokud není nalezeno, vrací 0
    
    @property
    def hmotnost_brutto(self):
        """
        Vrací hmotnost brutto bedny (hmotnost + tára).
        Pokud není hmotnost nebo tára zadána, vrací 0.
        """
        if self.hmotnost is not None and self.hmotnost > 0 and self.tara is not None and self.tara > 0:
            return self.hmotnost + self.tara
        return 0
    
    @property
    def postup_vyroby(self):
        """
        Vrací procenta postupu výroby bedny na základě stavu bedny, případně stavu rovnání a tryskání.

        PO ZMĚNĚ TÉTO PROPERTY AKTUALIZOVAT I FUNKCI build_postup_vyroby_cases v utils.py!!!
        
        - NEPRIJATO: 0%
        - PRIJATO: 10%
        - K_NAVEZENI: 20%
        - NAVEZENO: 30%
        - DO_ZPRACOVANI: 40%
        - ZAKALENO: 50%
        - ZKONTROLOVANO, rovnat není ROVNA nebo VYROVNANA a tryskat není CISTA nebo OTRYSKANA: 60%
        - ZKONTROLOVANO, rovnat není ROVNA nebo VYROVNANA nebo tryskat není CISTA nebo OTRYSKANA: 75%
        - ZKONTROLOVANO, rovnat je ROVNA nebo VYROVNANA a tryskat je CISTA nebo OTRYSKANA: 90%
        - K_EXPEDICI nebo EXPEDOVANO: 100%
        """
        if self.stav_bedny == StavBednyChoice.NEPRIJATO:
            return 0
        elif self.stav_bedny == StavBednyChoice.PRIJATO:
            return 10
        elif self.stav_bedny == StavBednyChoice.K_NAVEZENI:
            return 20
        elif self.stav_bedny == StavBednyChoice.NAVEZENO:
            return 30
        elif self.stav_bedny == StavBednyChoice.DO_ZPRACOVANI:
            return 40
        elif self.stav_bedny == StavBednyChoice.ZAKALENO:
            return 50
        elif self.stav_bedny == StavBednyChoice.ZKONTROLOVANO:
            final_rovnani = self.rovnat in [RovnaniChoice.ROVNA, RovnaniChoice.VYROVNANA]
            final_tryskani = self.tryskat in [TryskaniChoice.CISTA, TryskaniChoice.OTRYSKANA]
            final_zinkovani = self.zinkovat in [ZinkovaniChoice.NEZINKOVAT, ZinkovaniChoice.UVOLNENO]

            if final_rovnani and final_tryskani and final_zinkovani:
                return 95
            if (final_rovnani and final_tryskani) or (final_rovnani and final_zinkovani) or (final_tryskani and final_zinkovani):
                return 85
            if final_tryskani or final_rovnani or final_zinkovani:
                return 75
            return 60
        elif self.stav_bedny in [StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO]:
            return 100
        else:
            return 0  # Pro případ neznámého stavu bedny vrací 0%

    @property
    def barva_postupu_vyroby(self):
        """
        Vrací barvu postupu výroby bedny na základě stavu bedny.
        - NEPRIJATO: bez barvy
        - PRIJATO: světle zelená
        - K_NAVEZENI a NAVEZENO: světle modrá
        - DO_ZPRACOVANI: světle šedá
        - ZAKALENO: žlutá
        - ZKONTROLOVANO a zároveň rovnat je ROVNA nebo VYROVNANA a tryskat je CISTA nebo OTRYSKANA: trochu tmavější zelená
        - ZKONTROLOVANO ostatní případy: oranžová
        - K_EXPEDICI nebo EXPEDOVANO: tmavě zelená
        """
        if self.stav_bedny == StavBednyChoice.NEPRIJATO:
            return ''
        elif self.stav_bedny == StavBednyChoice.PRIJATO:
            return 'lightgreen'
        elif self.stav_bedny in [StavBednyChoice.K_NAVEZENI, StavBednyChoice.NAVEZENO]:
            return 'lightblue'
        elif self.stav_bedny == StavBednyChoice.DO_ZPRACOVANI:
            return 'lightgray'
        elif self.stav_bedny == StavBednyChoice.ZAKALENO:
            return 'yellow'
        elif self.stav_bedny == StavBednyChoice.ZKONTROLOVANO:
            final_rovnani = self.rovnat in [RovnaniChoice.ROVNA, RovnaniChoice.VYROVNANA]
            final_tryskani = self.tryskat in [TryskaniChoice.CISTA, TryskaniChoice.OTRYSKANA]
            final_zinkovani = self.zinkovat in [ZinkovaniChoice.NEZINKOVAT, ZinkovaniChoice.UVOLNENO]
            if final_rovnani and final_tryskani and final_zinkovani:
                return 'darkseagreen'
            else:
                return 'orange'
        elif self.stav_bedny in [StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO]:
            return 'darkgreen'
        else:
            return ''  # Pro případ neznámého stavu bedny vrací bez barvy

    def _containers_for_measurement_SSH(self, total):
        """Vrátí seznam vybraných čísel beden pro měření podle celkového počtu beden u zákazníka SSH."""
        if total <= 0:
            return []

        selected = {1, total}

        if total > 8:
            lower_middle = total // 2
            selected.update({lower_middle, lower_middle + 1})
        elif total >= 5:
            selected.add((total + 1) // 2)

        return sorted(selected)

    @property
    def bedna_k_mereni_tvrdosti_a_povrchu_SSH(self):
        """
        Vrací True, pokud je bedna určena k měření tvrdosti a povrchu pro zákazníka SSH.
        Výběr beden k měření je založen na celkovém počtu beden v zakázce podle pravidel zákazníka SSH:
        - Pokud je celkový počet beden menší nebo roven 0, žádná bedna není určena k měření.
        - Vždy se měří první a poslední bedna.
        - Pokud je celkový počet beden větší než 8, měří se také dvě střední bedny (dolní a horní střed).
        - Pokud je celkový počet beden mezi 5 a 8 (včetně), měří se prostřední bedna.
        """
        if self.zakazka.kamion_prijem.zakaznik.zkratka != 'SSH':
            return False

        total_bedny = self.zakazka.pocet_beden
        selected_bedny = self._containers_for_measurement_SSH(total_bedny)

        return self.poradi_bedny in selected_bedny

    def clean(self):
        """
        Validace stavu bedny a tryskání/rovnání/zinkování.
        - Pokud je stav bedny K_EXPEDICI nebo EXPEDOVANO, musí být tryskání buď Čistá nebo Otryskaná,
          rovnání buď Rovná nebo Vyrovnaná a zinkování buď Nezinkovat nebo Uvolněno (po zinkování).
        - Pokud je stav bedny K_NAVEZENI nebo NAVEZENO, musí být zadána pozice.
        - Pokud je stav bedny jakýkoliv jiný než NEPRIJATO, musí být zadána hmotnost, tára a množství a tyto nesmí být nula.
        - Pokud je zinkovat NA_ZINKOVANI, musí být stav bedny ZKONTROLOVANO.
        """
        super().clean()    
        if self.stav_bedny in [StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO]:
            text = _("Pro zadání stavu 'K expedici' nebo 'Expedováno' musí být tryskání buď Čistá nebo Otryskaná, rovnání buď Rovná nebo Vyrovnaná a zinkování buď Nezinkovat nebo Uvolněno (po zinkování).")
            if self.tryskat not in [TryskaniChoice.CISTA, TryskaniChoice.OTRYSKANA]:
                logger.warning(f'Uzivatel se pokusil uložit bednu ve stavu {self.stav_bedny} s neplatným stavem tryskání: {self.tryskat}')
                raise ValidationError(text)
            if self.rovnat not in [RovnaniChoice.ROVNA, RovnaniChoice.VYROVNANA]:
                logger.warning(f'Uzivatel se pokusil uložit bednu ve stavu {self.stav_bedny} s neplatným stavem rovnání: {self.rovnat}')
                raise ValidationError(text)
            if self.zinkovat not in [ZinkovaniChoice.NEZINKOVAT, ZinkovaniChoice.UVOLNENO]:
                logger.warning(f'Uzivatel se pokusil uložit bednu ve stavu {self.stav_bedny} s neplatným stavem zinkování: {self.zinkovat}')
                raise ValidationError(text)
        
        if self.stav_bedny in [StavBednyChoice.K_NAVEZENI, StavBednyChoice.NAVEZENO]:
            if not self.pozice:
                raise ValidationError(_("Pro stav 'K navezení' a 'Navezeno' musí být zadána pozice."))
                logger.warning(f'Uzivatel se pokusil uložit bednu ve stavu {self.stav_bedny} bez pozice.')

        if self.stav_bedny != StavBednyChoice.NEPRIJATO:
            warning_list = []
            if self.hmotnost is None or self.hmotnost <= 0:
                warning_list.append(f'neplatná hmotnost: {self.hmotnost}')
            if self.tara is None or self.tara <= 0:
                warning_list.append(f'neplatná tára: {self.tara}')
            if self.mnozstvi is None or self.mnozstvi <= 0:
                warning_list.append(f'neplatné množství: {self.mnozstvi}')
            if warning_list:
                logger.warning(f'Uživatel se pokusil uložit bednu ve stavu {self.stav_bedny} s neplatnými hodnotami: {", ".join(warning_list)}.')
                raise ValidationError(_(f'V jiném stavu než "NEPŘIJATO" nelze uložit bednu bez hmotnosti, táry a množství: {", ".join(warning_list)}.'))
        
        if self.zinkovat == ZinkovaniChoice.NA_ZINKOVANI and self.stav_bedny != StavBednyChoice.ZKONTROLOVANO:
            logger.warning(f'Uživatel se pokusil uložit bednu se zinkováním NA_ZINKOVANI ve stavu {self.stav_bedny}, což není povoleno.')
            raise ValidationError(_("Při změně zinkování na 'Na zinkování' musí být stav bedny 'Zkontrolováno'."))

    def save(self, *args, **kwargs):
        """
        Uloží instanci Bedna.
        - Pokud se jedná o novou instanci (bez PK):
          * Před uložením nastaví `cislo_bedny` na další číslo v řadě pro daného zákazníka.
          * Pro zákazníka s příznakem `vse_tryskat` nastaví `tryskat` na `SPINAVA`, ale pouze
            pokud je délka bedny menší než 900mm - delší díly se nevlezou do tryskače.
        - Pokud je stav bedny jiný než K_NAVEZENI nebo NAVEZENO, vymaže pozici a poznámku k navezení.
        """
        is_existing_instance = bool(self.pk)

        # Pokud se jedná o novou instanci, nastaví se číslo bedny a další hodnoty
        if not is_existing_instance:
            zakaznik = self.zakazka.kamion_prijem.zakaznik

            # Při vytváření nové bedny nastavíme číslo bedny na další v řadě
            posledni = (
                self.__class__.objects
                .filter(zakazka__kamion_prijem__zakaznik=zakaznik)
                .order_by("-cislo_bedny")
                .first()
            )
            self.cislo_bedny = ((posledni.cislo_bedny + 1) if posledni else zakaznik.ciselna_rada + 1)

            # Pokud je zákazník s příznakem `vse_tryskat`, nastavíme tryskat na SPINAVA, ale pouze
            # v případě, že je délka menší než 900mm - delší díly se nevlezou do tryskače
            if zakaznik.vse_tryskat and self.zakazka.delka and self.zakazka.delka < 900:
                self.tryskat = TryskaniChoice.SPINAVA

        # Pokud je stav bedny jiný než K_NAVEZENI nebo NAVEZENO, vymaže pozici a poznámku k navezení
        if self.stav_bedny not in [StavBednyChoice.K_NAVEZENI, StavBednyChoice.NAVEZENO]:
            self.pozice = None
            self.poznamka_k_navezeni = None

        super().save(*args, **kwargs)

    def get_allowed_stav_bedny_choices(self):
        """
        Vrátí seznam tuple (value,label) pro pole `stav_bedny`
        podle aktuálního stavu a hodnot `tryskat`/`rovnat`.
        Pravidla pro výběr:
        - Pokud je stav `EXPEDOVANO`, nabídne pouze tento stav.
        - Pokud je stav `K_EXPEDICI`, nabídne předchozí stav a aktuální stav.
        - Pokud je stav `ZAKALENO`, `DO_ZPRACOVANI` nebo `NAVEZENO` nabídne předchozí, aktuální stav
          a všechny následující až do K_EXPEDICI.
        - Pokud je stav `PRIJATO`, nabídne předchozí stav, aktuální stav a dva následující stavy.
        - Pokud je stav `NEPRIJATO`, nabídne tento stav a následující stav.
        - Ve všech ostatních stavech nabídne předchozí, aktuální a následující stav.
        """
        choices = list(StavBednyChoice.choices)
        curr = self.stav_bedny

        # najdi index
        try:
            idx = next(i for i, (val, _) in enumerate(choices) if val == curr)
        except StopIteration:
            return choices  # fallback: všechno
        # EXPEDOVANO
        if curr == StavBednyChoice.EXPEDOVANO:
            return [choices[idx]]
        # K_EXPEDICI
        if curr == StavBednyChoice.K_EXPEDICI:
            return [choices[idx - 1], choices[idx]]
        # ZAKALENO, DO_ZPRACOVANI, NAVEZENO
        if curr in (StavBednyChoice.ZAKALENO, StavBednyChoice.DO_ZPRACOVANI, StavBednyChoice.NAVEZENO):
            return choices[idx - 1 : choices.index((StavBednyChoice.K_EXPEDICI, 'K expedici')) + 1]
        # PRIJATO
        if curr == StavBednyChoice.PRIJATO:
            return choices[idx - 1 : idx + 3]
        # ostatní
        before = [choices[idx - 1]] if idx > 0 else []
        after  = [choices[idx + 1]] if idx < len(choices) - 1 else []
        return before + [choices[idx]] + after
    
    def get_allowed_tryskat_choices(self):
        """
        Vrátí seznam tuple (value,label) pro pole `tryskat` podle aktuálního stavu.
        Pravidla pro výběr:
        - Pokud je stav_bedny K_EXPEDICI nebo EXPEDOVANO, nabídne pouze aktuální stav, stav tryskání už nejde měnit.
        - Pokud je tryskání nezadáno ('-------'), nabídne všechny možnosti (může přijít z výroby rovnou otryskaná).
        - Pokud je tryskání špinavá, nabídne nezadáno, špinavá a otryskaná.
        - Pokud je tryskání čistá, nabídne nezadáno a čistá.
        - Pokud je tryskání otryskaná, nabídne špinavá a otryskaná.
        """
        curr = self.tryskat
        curr_choice = (curr, dict(TryskaniChoice.choices).get(curr, 'Neznámý stav'))

        # stav bedny K_EXPEDICI
        if self.stav_bedny == StavBednyChoice.K_EXPEDICI or self.stav_bedny == StavBednyChoice.EXPEDOVANO:
            return [curr_choice]
        # NEZADANO
        if curr == TryskaniChoice.NEZADANO:
            return TryskaniChoice.choices    
        # SPINAVA
        if curr == TryskaniChoice.SPINAVA:
            return [choice for choice in TryskaniChoice.choices if choice[0] != TryskaniChoice.CISTA]
        # CISTA
        if curr == TryskaniChoice.CISTA:
            return [choice for choice in TryskaniChoice.choices if choice[0] not in (TryskaniChoice.SPINAVA, TryskaniChoice.OTRYSKANA)]
        # OTRYSKANA
        if curr == TryskaniChoice.OTRYSKANA:
            return [choice for choice in TryskaniChoice.choices if choice[0] not in (TryskaniChoice.CISTA, TryskaniChoice.NEZADANO)]
        # fallback: všechno
        return list(TryskaniChoice.choices)

    def get_allowed_rovnat_choices(self):
        """
        Vrátí seznam tuple (value,label) pro pole `rovnat`
        podle aktuálního stavu.
        Pravidla pro výběr:
        - Pokud je stav_bedny K_EXPEDICI nebo EXPEDOVANO, nabídne pouze aktuální stav, stav rovnání už nejde měnit.
        - Pokud je rovnat nezadáno ('--------'), nabídne možnosti nezadáno, rovná a křivá.
        - Pokud je rovnat křivá, nabídne nezadáno, křivá, rovná se a vyrovnaná.
        - Pokud je rovnat rovná se, nabídne křivá, rovná se a vyrovnaná.
        - Pokud je rovnat rovná, nabídne nezadáno a rovná.
        - Pokud je rovnat vyrovnaná, nabídne rovná se a vyrovnaná.
        """
        curr = self.rovnat
        curr_choice = (curr, dict(RovnaniChoice.choices).get(curr, 'Neznámý stav'))

        # stav bedny K_EXPEDICI
        if self.stav_bedny == StavBednyChoice.K_EXPEDICI or self.stav_bedny == StavBednyChoice.EXPEDOVANO:
            return [curr_choice]        
        # NEZADANO
        if curr == RovnaniChoice.NEZADANO:
            return [choice for choice in RovnaniChoice.choices if choice[0] in (RovnaniChoice.NEZADANO, RovnaniChoice.ROVNA, RovnaniChoice.KRIVA)]
        # KRIVA
        if curr == RovnaniChoice.KRIVA:
            return [choice for choice in RovnaniChoice.choices if choice[0] in (RovnaniChoice.NEZADANO, RovnaniChoice.KRIVA, RovnaniChoice.ROVNA_SE, RovnaniChoice.VYROVNANA)]
        # ROVNA_SE
        if curr == RovnaniChoice.ROVNA_SE:
            return [choice for choice in RovnaniChoice.choices if choice[0] in (RovnaniChoice.KRIVA, RovnaniChoice.ROVNA_SE, RovnaniChoice.VYROVNANA)]
        # ROVNA
        if curr == RovnaniChoice.ROVNA:
            return [choice for choice in RovnaniChoice.choices if choice[0] in (RovnaniChoice.NEZADANO, RovnaniChoice.ROVNA)]
        # VYROVNANA
        if curr == RovnaniChoice.VYROVNANA:
            return [choice for choice in RovnaniChoice.choices if choice[0] in (RovnaniChoice.ROVNA_SE, RovnaniChoice.VYROVNANA)]
        # fallback: všechno
        return list(RovnaniChoice.choices)

    def get_allowed_zinkovat_choices(self):
        """
        Vrátí seznam tuple (value,label) pro pole `zinkovat` podle aktuálního stavu.
        Pravidla pro výběr:
        - Pokud je stav_bedny K_EXPEDICI nebo EXPEDOVANO, nabídne pouze aktuální stav (zinkování už nejde měnit).
        - Pokud je zinkovat nezadáno, nabídne nezadáno, nezinkovat, k zinkování.
        - Pokud je zinkovat nezinkovat, nabídne nezadáno, k_zinkovani a nezinkovat.
        - Pokud je zinkovat k zinkování, nabídne nezadano, nezinkovat, k zinkování a na zinkování.
        - Pokud je zinkovat na zinkování, nabídne k zinkování, na zinkování, po zinkování a uvolněno.
        - Pokud je zinkovat po zinkování, nabídne na zinkování, po zinkování a uvolněno.
        - Pokud je zinkovat uvolněno, nabídne po zinkování a uvolněno.
        """
        curr = self.zinkovat
        curr_choice = (curr, dict(ZinkovaniChoice.choices).get(curr, 'Neznámý stav'))

        if self.stav_bedny in (StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO):
            return [curr_choice]
        if curr == ZinkovaniChoice.NEZADANO:
            return [choice for choice in ZinkovaniChoice.choices if choice[0] in (
                ZinkovaniChoice.NEZADANO,
                ZinkovaniChoice.NEZINKOVAT,
                ZinkovaniChoice.K_ZINKOVANI,
            )]
        if curr == ZinkovaniChoice.NEZINKOVAT:
            return [choice for choice in ZinkovaniChoice.choices if choice[0] in (
                ZinkovaniChoice.NEZADANO,
                ZinkovaniChoice.K_ZINKOVANI,
                ZinkovaniChoice.NEZINKOVAT,
            )]
        if curr == ZinkovaniChoice.K_ZINKOVANI:
            return [choice for choice in ZinkovaniChoice.choices if choice[0] in (
                ZinkovaniChoice.NEZADANO,
                ZinkovaniChoice.NEZINKOVAT,
                ZinkovaniChoice.K_ZINKOVANI,
                ZinkovaniChoice.NA_ZINKOVANI,
            )]
        if curr == ZinkovaniChoice.NA_ZINKOVANI:
            return [choice for choice in ZinkovaniChoice.choices if choice[0] in (
                ZinkovaniChoice.K_ZINKOVANI,
                ZinkovaniChoice.NA_ZINKOVANI,
                ZinkovaniChoice.PO_ZINKOVANI,
                ZinkovaniChoice.UVOLNENO,
            )]
        if curr == ZinkovaniChoice.PO_ZINKOVANI:
            return [choice for choice in ZinkovaniChoice.choices if choice[0] in (
                ZinkovaniChoice.NA_ZINKOVANI,
                ZinkovaniChoice.PO_ZINKOVANI,
                ZinkovaniChoice.UVOLNENO,
            )]
        if curr == ZinkovaniChoice.UVOLNENO:
            return [choice for choice in ZinkovaniChoice.choices if choice[0] in (
                ZinkovaniChoice.PO_ZINKOVANI,
                ZinkovaniChoice.UVOLNENO
            )]
        # fallback: všechno
        return list(ZinkovaniChoice.choices)
    
    @property
    def cena_za_kg(self):
        """
        Vrací cenu zboží v bedně v EUR/kg.
        Pouze přebírá hodnotu z property zakazka.cena_za_kg.
        """
        return self.zakazka.cena_za_kg

    @property
    def cena_za_bednu(self):
        """
        Vrací cenu zboží v bedně v EUR/bednu.
        Výpočet ceny se provádí na základě property cena_za_kg.
        Pokud je bedna označena jako fakturovat == False, vrací 0.
        """
        if not self.fakturovat:
            return Decimal('0.00')
        return Decimal(self.cena_za_kg * self.hmotnost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if self.hmotnost else Decimal('0.00')
    
    @property
    def cena_rovnani_za_kg(self):
        """
        Vrací cenu zboží v bedně v EUR/kg.
        Přebírá se hodnotu z property cena_rovnani_za_kg zakázky, ale pouze pokud je bedna vyrovnaná, jinak je hodnota 0.
        """
        vyrovnana = self.rovnat == RovnaniChoice.VYROVNANA

        if vyrovnana:
            return self.zakazka.cena_rovnani_za_kg
        return Decimal('0.00')  

    @property
    def cena_rovnani_za_bednu(self):
        """
        Vrací cenu rovnání bedny v EUR/bedna.
        Výpočet ceny se provádí na základě property cena_rovnani_za_kg.
        Pokud je bedna označena jako fakturovat == False, vrací 0.
        """
        if not self.fakturovat:
            return Decimal('0.00')
        return Decimal(self.cena_rovnani_za_kg * self.hmotnost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if self.hmotnost else Decimal('0.00')

    @property
    def cena_tryskani_za_kg(self):
        """
        Vrací cenu zboží v bedně v EUR/kg.
        Přebírá se hodnotu z property cena_tryskani_za_kg zakázky, ale pouze pokud je bedna otryskaná, jinak je hodnota 0.
        """
        otryskana = self.tryskat == TryskaniChoice.OTRYSKANA

        if otryskana:
            return self.zakazka.cena_tryskani_za_kg
        return Decimal('0.00')

    @property
    def cena_tryskani_za_bednu(self):
        """
        Vrací cenu tryskání bedny v EUR/bedna.
        Výpočet ceny se provádí na základě property cena_tryskani_za_kg.
        Pokud je bedna označena jako fakturovat == False, vrací 0.
        """
        if not self.fakturovat:
            return Decimal('0.00')
        return Decimal(self.cena_tryskani_za_kg * self.hmotnost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if self.hmotnost else Decimal('0.00')

    # --- Delete guards ---
    def delete(self, using=None, keep_parents=False):
        """
        Zamezí mazání bedny, pokud má jiný stav než NEPRIJATO.
        """
        if self.stav_bedny != StavBednyChoice.NEPRIJATO:
            raise ProtectedError(
                "Mazání zablokováno: Bedna má jiný stav než NEPRIJATO.",
                [self],
            )
        return super().delete(using=using, keep_parents=keep_parents)


class Rozpracovanost(models.Model):
    cas_zaznamu = models.DateTimeField(auto_now_add=True, verbose_name='Čas záznamu')
    bedny = models.ManyToManyField('Bedna', related_name='rozpracovanost_zaznamy', verbose_name='Bedny')

    class Meta:
        verbose_name = 'Rozpracovanost'
        verbose_name_plural = 'rozpracovanosti'
        ordering = ['-cas_zaznamu']

    def __str__(self):
        return f"{self.cas_zaznamu:%Y.%m.%d %H:%M} – {self.bedny.count()} beden"

    @property
    def pocet_beden(self):
        return self.bedny.count()