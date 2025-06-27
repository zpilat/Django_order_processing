from django.db import models
from simple_history.models import HistoricalRecords
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.db.models import Sum

from decimal import Decimal, ROUND_HALF_UP

from .choices import (
    StavBednyChoice, RovnaniChoice, TryskaniChoice, PrioritaChoice, KamionChoice
)

class Zakaznik(models.Model):
    nazev = models.CharField(max_length=100, verbose_name='Název zákazníka', unique=True)
    zkraceny_nazev = models.CharField(max_length=15, verbose_name='Zkrácený název', unique=True,
                                       help_text='Zkrácený název zákazníka, např. pro zobrazení v kartě bedny a v přehledech.')
    zkratka = models.CharField(max_length=3, verbose_name='Zkratka', unique=True)
    adresa = models.CharField(max_length=100, blank=True, null=True, verbose_name='Adresa')
    mesto = models.CharField(max_length=50, blank=True, null=True, verbose_name='Město')
    psc = models.CharField(max_length=10, blank=True, null=True, verbose_name='PSČ')
    stat = models.CharField(max_length=50, blank=True, null=True, verbose_name='Stát')
    kontaktni_osoba = models.CharField(max_length=50, blank=True, null=True, verbose_name='Kontaktní osoba')
    telefon = models.CharField(max_length=50, blank=True, null=True, verbose_name='Telefon')
    email = models.EmailField(max_length=100, blank=True, null=True, verbose_name='E-mail')
    vse_tryskat = models.BooleanField(default=False, verbose_name='Vše tryskat',
                                        help_text='Zákazník požaduje všechny bedny tryskat')
    pouze_komplet = models.BooleanField(default=False, verbose_name='Pouze komplet',
                                        help_text='Zákazník může expedovat pouze kompletní zakázky, které mají všechny bedny ve stavu K_EXPEDICI.')
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
                                       help_text='Zkrácený název odběratele, např. pro zobrazení v kartě bedny a v přehledech.')
    zkratka = models.CharField(max_length=3, verbose_name='Zkratka', unique=True)
    adresa = models.CharField(max_length=100, blank=True, null=True, verbose_name='Adresa')
    mesto = models.CharField(max_length=50, blank=True, null=True, verbose_name='Město')
    psc = models.CharField(max_length=10, blank=True, null=True, verbose_name='PSČ')
    stat = models.CharField(max_length=50, blank=True, null=True, verbose_name='Stát')
    kontaktni_osoba = models.CharField(max_length=50, blank=True, null=True, verbose_name='Kontaktní osoba')
    telefon = models.CharField(max_length=50, blank=True, null=True, verbose_name='Telefon')
    email = models.EmailField(max_length=100, blank=True, null=True, verbose_name='E-mail')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Odběratel'
        verbose_name_plural = 'odběratelé'
        ordering = ['nazev']

    def __str__(self):
        return self.zkraceny_nazev


class Kamion(models.Model):
    zakaznik = models.ForeignKey(Zakaznik, on_delete=models.CASCADE, related_name='kamiony', verbose_name='Zákazník')
    odberatel = models.ForeignKey(Odberatel, on_delete=models.SET_NULL, related_name='kamiony', verbose_name='Odběratel', blank=True, null=True)
    datum = models.DateField(verbose_name='Datum')
    cislo_dl_zakaznika = models.CharField(max_length=50, verbose_name='Číslo DL', blank=True, null=True)
    prijem_vydej = models.CharField(choices=KamionChoice.choices, max_length=1, verbose_name='Přijem/Výdej', default=KamionChoice.PRIJEM)
    poradove_cislo = models.PositiveIntegerField(verbose_name='Pořadové číslo', blank=True, null=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Kamión'
        verbose_name_plural = 'kamióny'
        ordering = ['id']

    def __str__(self):
        """
        Vrací řetězec reprezentující kamion. Datum je upraveno do formátu YY-MM.
        """
        return f'{self.poradove_cislo}.{self.zakaznik.zkratka} {self.datum.strftime("%d.%m")}'
    
    @property
    def celkova_hmotnost_netto(self):
        """
        Vrací celkovou hmotnost netto všech beden spojených s tímto kamionem.
        """
        # Pokud je kamion pro výdej, vrací hmotnost beden spojených s výdejem.
        if self.prijem_vydej == KamionChoice.VYDEJ:
            return Bedna.objects.filter(
                zakazka__kamion_vydej=self
            ).aggregate(suma=Sum('hmotnost'))['suma'] or 0
        # Pokud je kamion pro příjem, vrací hmotnost beden spojených s příjmem.
        elif self.prijem_vydej == KamionChoice.PRIJEM:
            return Bedna.objects.filter(
                zakazka__kamion_prijem=self
            ).aggregate(suma=Sum('hmotnost'))['suma'] or 0
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
            ).aggregate(suma=Sum('tara'))['suma'] or 0
        # Pokud je kamion pro příjem, vrací hmotnost beden spojených s příjmem.
        elif self.prijem_vydej == KamionChoice.PRIJEM:
            celkova_tara = Bedna.objects.filter(
                zakazka__kamion_prijem=self
            ).aggregate(suma=Sum('tara'))['suma'] or 0
        else:
            raise ValidationError(_("Neplatný typ kamionu. Musí být buď 'Přijem' nebo 'Výdej'."))
        return celkova_tara + self.celkova_hmotnost_netto
    
    @property
    def cena_za_kamion(self):
        """
        Vrací cenu za kamion na základě zákazníka, předpisu a délky, pouze pro kamionu výdej.
        Celkovou cenu vypočte podle property cena_za_zakazku pro jednotlivé zakázky v kamionu.
        Pokud není cena nalezena, vrací 0.
        """
        if self.prijem_vydej == KamionChoice.VYDEJ:
            # Získá všechny bedny obsažené v kamionu.
            zakazky = self.zakazky.all()
            if not zakazky.exists():
                return 0
            return Decimal(
                sum(
                    Decimal(zakazka.cena_za_zakazku) for zakazka in zakazky if zakazka.cena_za_zakazku
                ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            )
        return 0

    @property
    def pocet_beden_skladem(self):
        '''
        Vrací celkový počet beden spojených s tímto kamionem, které nejsou ve stavu EXPEDOVANO.
        '''
        if self.prijem_vydej == KamionChoice.PRIJEM:
            return Bedna.objects.filter(
                zakazka__kamion_prijem=self
                ).exclude(
                stav_bedny=StavBednyChoice.EXPEDOVANO
                ).count()
        return 0


    def get_admin_url(self):
        """
        Vrací URL pro zobrazení detailu kamionu v administraci.
        """
        return reverse("admin:orders_kamion_change", args=[self.pk])    
    
    def save(self, *args, **kwargs):
        """
        Uloží instanci Kamion.
        - Pokud se jedná o novou instanci (bez PK):
          * Před uložením nastaví `poradove_cislo` na další číslo v řadě pro daného zákazníka, typ kamionu (prijem_vydej) a daný rok.
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

        super().save(*args, **kwargs)
    

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
    popousteni = models.CharField(max_length=50, verbose_name='Popouštění', blank=True, null=True)
    sarzovani = models.CharField(max_length=50, verbose_name='Šaržování', blank=True, null=True)
    pletivo = models.CharField(max_length=50, verbose_name='Pletivo', blank=True, null=True)
    popis_povrch = models.CharField(max_length=50, verbose_name='Povrch - popis', blank=True, null=True)
    popis_jadro = models.CharField(max_length=50, verbose_name='Jádro - popis', blank=True, null=True)
    popis_vrstva = models.CharField(max_length=50, verbose_name='Vrstva - popis', blank=True, null=True)
    popis_ohyb = models.CharField(max_length=50, verbose_name='Ohyb - popis', blank=True, null=True)
    popis_krut = models.CharField(max_length=50, verbose_name='Krut - popis', blank=True, null=True)
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
        return f'{self.nazev} ({self.zakaznik.zkratka})'
    
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
    kamion_vydej = models.ForeignKey(Kamion, on_delete=models.CASCADE, related_name='zakazky_vydej', verbose_name='Kamión výdej', null=True, blank=True)
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
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Zakázka'
        verbose_name_plural = 'zakázky'
        ordering = ['id']

    def __str__(self):
        return f'{self.kamion_prijem.id}-{self.kamion_prijem.zakaznik.zkratka} {self.kamion_prijem.datum.strftime("%d.%m.%y")}-{self.artikl}'

    @property
    def celkova_hmotnost(self):
        return self.bedny.aggregate(suma=Sum('hmotnost'))['suma'] or 0
    
    @property
    def pocet_beden(self):
        """
        Vrací počet beden spojených s touto zakázkou.
        """
        if not hasattr(self, 'bedny'):
            return 0
        return self.bedny.count()

    def get_admin_url(self):
        """
        Vrací URL pro zobrazení detailu zakázky v administraci.
        """
        return reverse("admin:orders_zakazka_change", args=[self.pk])

    @property
    def cena_za_zakázku(self):
        """
        Vrací cenu zboží v zakázce v EUR/bednu.
        Výpočet ceny se provádí na základě předpisu, délky a zákazníka.
        """
        predpis = self.predpis
        zakaznik = self.kamion_prijem.zakaznik
        delka = self.delka

        # Pokud není předpis nebo zákazník, vrací 0
        if not predpis or not zakaznik:
            return 0

        # Zákazník Eurotec
        if zakaznik.zkratka == 'EUR':
            cena = Cena.objects.filter(
                predpis=predpis,
                delka_min__lte=delka,
                delka_max__gt=delka,
                zakaznik=zakaznik
            ).first()
            cena_za_zakazku = Decimal(cena.cena_za_kg * self.celkova_hmotnost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if cena else 0
            return cena_za_zakazku
        # Pro ostatní zákazníky zatím není výpočet ceny implementován
        else:
            return 0    
    

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
    cena_za_kg = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Cena (EUR/kg)')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Cena'
        verbose_name_plural = 'ceny'
        ordering = ['popis', 'delka_min']

    def __str__(self):
        return f'{self.zakaznik.zkratka} {self.popis}x{int(self.delka_min)}-{int(self.delka_max)}'    


class Bedna(models.Model):
    zakazka = models.ForeignKey(Zakazka, on_delete=models.CASCADE, related_name='bedny', verbose_name='Zakázka')
    cislo_bedny = models.PositiveIntegerField(blank=True, verbose_name='Číslo bedny', unique=True,)
    hmotnost = models.DecimalField(max_digits=5, decimal_places=1, blank=True, verbose_name='Netto')
    tara = models.DecimalField(max_digits=5, blank=True, decimal_places=1, verbose_name='Tára')
    material = models.CharField(max_length=20, null=True, blank=True, verbose_name='Materiál')
    sarze = models.CharField(max_length=20, null=True, blank=True, verbose_name='Šarže mat. / Charge')
    behalter_nr = models.PositiveIntegerField(null=True, blank=True, verbose_name='Č.bed. zák.')
    dodatecne_info = models.CharField(max_length=100, null=True, blank=True, verbose_name='Sonder / Zusatzinfo')
    dodavatel_materialu = models.CharField(max_length=10, null=True, blank=True, verbose_name='Lief.')
    vyrobni_zakazka = models.CharField(max_length=20, null=True, blank=True, verbose_name='Fertigungs-auftrags Nr.')
    tryskat = models.CharField(choices=TryskaniChoice.choices, max_length=5, default=TryskaniChoice.NEZADANO, verbose_name='Tryskání')
    rovnat = models.CharField(choices=RovnaniChoice.choices, max_length=5, default=RovnaniChoice.NEZADANO, verbose_name='Rovnání')
    stav_bedny = models.CharField(choices=StavBednyChoice.choices, max_length=2, default=StavBednyChoice.PRIJATO, verbose_name='Stav bedny')    
    mnozstvi = models.PositiveIntegerField(null=True, blank=True, verbose_name='Mn. ks')
    poznamka = models.CharField(max_length=100, null=True, blank=True, verbose_name='Poznámka HPM')
    odfosfatovat = models.BooleanField(default=False, verbose_name='Odfos.')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Bedna'
        verbose_name_plural = 'bedny'
        ordering = ['id']

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

    def save(self, *args, **kwargs):
        """
        Uloží instanci Bedna.
        - Pokud se jedná o novou instanci (bez PK):
          * Před uložením nastaví `cislo_bedny` na další číslo v řadě pro daného zákazníka.
          * Pro zákazníka s příznakem `vse_tryskat` nastaví `tryskat` na `SPINAVA`.
        """
        is_existing_instance = bool(self.pk)

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

            # Pokud je zákazník s příznakem `vse_tryskat`, nastavíme tryskat na SPINAVA
            if zakaznik.vse_tryskat:
                self.tryskat = TryskaniChoice.SPINAVA

        super().save(*args, **kwargs)

    def get_allowed_stav_bedny_choices(self):
        """
        Vrátí seznam tuple (value,label) pro pole `stav_bedny`
        podle aktuálního stavu a hodnot `tryskat`/`rovnat`.
        Pravidla pro výběr:
        - Pokud je stav `EXPEDOVANO`, nabídne pouze tento stav.
        - Pokud je stav `K_EXPEDICI`, nabídne předchozí stav a aktuální stav.
        - Pokud je stav `ZKONTROLOVANO`, nabídne předchozí stav a aktuální stav,    
            a pokud zároveň `tryskat` ∈ {CISTA, OTRYSKANA} a 
            `rovnat` ∈ {ROVNA, VYROVNANA}, doplní i následující stav.
        - Pokud je stav `PRIJATO`, nabídne tento stav a následující stav.
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
        # ZKONTROLOVANO
        if curr == StavBednyChoice.ZKONTROLOVANO:
            allowed = [choices[idx - 1], choices[idx]]
            if (self.tryskat in (TryskaniChoice.CISTA, TryskaniChoice.OTRYSKANA)
             and self.rovnat in (RovnaniChoice.ROVNA, RovnaniChoice.VYROVNANA)):
                allowed.append(choices[idx + 1])
            return allowed
        # PRIJATO
        if curr == StavBednyChoice.PRIJATO:
            return [choices[idx], choices[idx + 1]]
        # ostatní
        before = [choices[idx - 1]] if idx > 0 else []
        after  = [choices[idx + 1]] if idx < len(choices) - 1 else []
        return before + [choices[idx]] + after
    
    def get_allowed_tryskat_choices(self):
        """
        Vrátí seznam tuple (value,label) pro pole `tryskat` podle aktuálního stavu.
        Pravidla pro výběr:
        - Pokud je stav_bedny K_EXPEDICI, nabídne pouze aktuální stav, stav tryskání už nejde měnit.
        - Pokud je tryskání nezadáno ('-------'), nabídne všechny možnosti (může přijít z výroby rovnou otryskaná).
        - Pokud je tryskání špinavá, nabídne nezadáno, špinavá a otryskaná.
        - Pokud je tryskání čistá, nabídne nezadáno a čistá.
        - Pokud je tryskání otryskaná, nabídne špinavá a otryskaná.
        """
        curr = self.tryskat
        curr_choice = (curr, dict(TryskaniChoice.choices).get(curr, 'Neznámý stav'))

        # stav bedny K_EXPEDICI
        if self.stav_bedny == StavBednyChoice.K_EXPEDICI:
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
        - Pokud je stav_bedny K_EXPEDICI, nabídne pouze aktuální stav, stav rovnání už nejde měnit.
        - Pokud je rovnat nezadáno ('--------'), nabídne možnosti nezadáno, rovná a křivá.
        - Pokud je rovnat křivá, nabídne nezadáno, křivá a vyrovnaná.
        - Pokud je rovnat rovná, nabídne nezadáno a rovná.
        - Pokud je rovnat vyrovnaná, nabídne křivá a vyrovnaná.
        """
        curr = self.rovnat
        curr_choice = (curr, dict(RovnaniChoice.choices).get(curr, 'Neznámý stav'))

        # stav bedny K_EXPEDICI
        if self.stav_bedny == StavBednyChoice.K_EXPEDICI:
            return [curr_choice]        
        # NEZADANO
        if curr == RovnaniChoice.NEZADANO:
            return [choice for choice in RovnaniChoice.choices if choice[0] != RovnaniChoice.VYROVNANA]
        # KRIVA
        if curr == RovnaniChoice.KRIVA:
            return [choice for choice in RovnaniChoice.choices if choice[0] != RovnaniChoice.ROVNA]
        # ROVNA
        if curr == RovnaniChoice.ROVNA:
            return [choice for choice in RovnaniChoice.choices if choice[0] not in (RovnaniChoice.KRIVA, RovnaniChoice.VYROVNANA)]
        # VYROVNANA
        if curr == RovnaniChoice.VYROVNANA:
            return [choice for choice in RovnaniChoice.choices if choice[0] not in (RovnaniChoice.ROVNA, RovnaniChoice.NEZADANO)]
        # fallback: všechno
        return list(RovnaniChoice.choices)
    
    @property
    def cena_za_kg(self):
        """
        Vrací cenu zboží v bedně v EUR/kg.
        Výpočet ceny se provádí na základě předpisu, délky a zákazníka.
        """
        predpis = self.zakazka.predpis
        zakaznik = self.zakazka.kamion_prijem.zakaznik
        delka = self.zakazka.delka

        # Pokud není předpis nebo zákazník, vrací 0
        if not predpis or not zakaznik:
            return 0

        # Zákazník Eurotec      
        if zakaznik.zkratka == 'EUR':
            cena = Cena.objects.filter(
                predpis=predpis,
                delka_min__lte=delka,
                delka_max__gt=delka,
                zakaznik=zakaznik
            ).first()
            return cena.cena_za_kg if cena else 0
        # Pro ostatní zákazníky zatím není výpočet ceny implementován
        else:
            return 0
        
    @property
    def cena_za_bednu(self):
        """
        Vrací cenu zboží v bedně v EUR/bednu.
        Výpočet ceny se provádí na základě předpisu, délky a zákazníka.
        """
        predpis = self.zakazka.predpis
        zakaznik = self.zakazka.kamion_prijem.zakaznik
        delka = self.zakazka.delka

        # Pokud není předpis nebo zákazník, vrací 0
        if not predpis or not zakaznik:
            return 0

        # Zákazník Eurotec
        if zakaznik.zkratka == 'EUR':
            cena = Cena.objects.filter(
                predpis=predpis,
                delka_min__lte=delka,
                delka_max__gt=delka,
                zakaznik=zakaznik
            ).first()
            cena_za_bednu = Decimal(cena.cena_za_kg * self.hmotnost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if cena else 0
            return cena_za_bednu
        # Pro ostatní zákazníky zatím není výpočet ceny implementován
        else:
            return 0