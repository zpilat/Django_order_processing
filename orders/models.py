from django.db import models
from simple_history.models import HistoricalRecords
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from .choices import (
    TypHlavyChoice, StavBednyChoice, RovnaniChoice, TryskaniChoice,
    PrioritaChoice, ZinkovnaChoice, KamionChoice
)

# Create your models here.
class Zakaznik(models.Model):
    nazev = models.CharField(max_length=100, verbose_name='Název zákazníka', unique=True)
    zkratka = models.CharField(max_length=3, verbose_name='Zkratka', unique=True)
    adresa = models.CharField(max_length=100, blank=True, null=True, verbose_name='Adresa')
    mesto = models.CharField(max_length=50, blank=True, null=True, verbose_name='Město')
    stat = models.CharField(max_length=50, blank=True, null=True, verbose_name='Stát')
    kontaktni_osoba = models.CharField(max_length=50, blank=True, null=True, verbose_name='Kontaktní osoba')
    telefon = models.CharField(max_length=50, blank=True, null=True, verbose_name='Telefon')
    email = models.EmailField(max_length=100, blank=True, null=True, verbose_name='E-mail')
    vse_tryskat = models.BooleanField(default=False, verbose_name='Vše tryskat')
    cisla_beden_auto = models.BooleanField(default=False, verbose_name='Č. beden automaticky')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Zákazník'
        verbose_name_plural = 'zákazníci'
        ordering = ['nazev']

    def __str__(self):
        return self.nazev

class Kamion(models.Model):
    zakaznik_id = models.ForeignKey(Zakaznik, on_delete=models.CASCADE, related_name='kamiony', verbose_name='Zákazník')
    datum = models.DateField(verbose_name='Datum')
    cislo_dl = models.CharField(max_length=50, verbose_name='Číslo DL', blank=True, null=True)
    prijem_vydej = models.CharField(choices=KamionChoice.choices, max_length=1, verbose_name='Přijem/Výdej')
    misto_expedice = models.CharField(max_length=100, verbose_name='Místo expedice', blank=True, null=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Kamión'
        verbose_name_plural = 'kamióny'
        ordering = ['id']

    def __str__(self):
        return f'{self.id}. {self.zakaznik_id.zkratka} {self.datum}'
    
    def get_admin_url(self):
        """
        Vrací URL pro zobrazení detailu kamionu v administraci.
        """
        return reverse("admin:orders_kamion_change", args=[self.pk])    
    
class Zakazka(models.Model):
    kamion_prijem_id = models.ForeignKey(Kamion, on_delete=models.CASCADE, related_name='zakazky_prijem', verbose_name='Kamión příjem', null=True)
    kamion_vydej_id = models.ForeignKey(Kamion, on_delete=models.CASCADE, related_name='zakazky_vydej', verbose_name='Kamión výdej', null=True, blank=True)
    artikl = models.CharField(max_length=50, verbose_name='Artikl / Zakázka')
    prumer = models.DecimalField(max_digits=4, decimal_places=1, verbose_name='Průměr')
    delka = models.DecimalField(max_digits=6, decimal_places=1, verbose_name='Délka')
    predpis = models.CharField(max_length=30, verbose_name='Předpis/výkres')
    typ_hlavy = models.CharField(choices=TypHlavyChoice.choices, max_length=3, verbose_name='Typ hlavy')
    popis = models.CharField(max_length=100, verbose_name='Popis')
    prubeh = models.IntegerField(null=True, blank=True, verbose_name='Vorgang')
    vrstva = models.CharField(max_length=20, null=True, blank=True, verbose_name='Beschichtung')
    povrch = models.CharField(max_length=20, null=True, blank=True, verbose_name='Oberfläche')
    priorita = models.CharField(choices=PrioritaChoice.choices, max_length=5, default=PrioritaChoice.NIZKA, verbose_name='Priorita')
    zinkovna = models.CharField(choices=ZinkovnaChoice.choices, max_length=10, null=True, blank=True, verbose_name='Zinkovna')
    komplet = models.BooleanField(default=False, verbose_name='Kompletní')
    expedovano = models.BooleanField(default=False, verbose_name='Expedováno')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Zakázka'
        verbose_name_plural = 'zakázky'
        ordering = ['id']
        permissions = [
            ('change_expedovana_zakazka', 'Může měnit expedované zakázky'),
        ]

    def __str__(self):
        return f'{self.kamion_prijem_id.id}. {self.kamion_prijem_id.zakaznik_id.zkratka} {self.kamion_prijem_id.datum} - {self.artikl}'
    
    def get_admin_url(self):
        """
        Vrací URL pro zobrazení detailu zakázky v administraci.
        """
        return reverse("admin:orders_zakazka_change", args=[self.pk])
    

class Bedna(models.Model):
    zakazka_id = models.ForeignKey(Zakazka, on_delete=models.CASCADE, related_name='bedny', verbose_name='Zakázka')
    cislo_bedny = models.PositiveIntegerField(blank=True, verbose_name='Číslo bedny')
    hmotnost = models.DecimalField(max_digits=5, decimal_places=1, blank=True, verbose_name='Hm. netto')
    tara = models.DecimalField(max_digits=5, blank=True, decimal_places=1, verbose_name='Tára')
    material = models.CharField(max_length=20, null=True, blank=True, verbose_name='Materiál')
    sarze = models.CharField(max_length=20, null=True, blank=True, verbose_name='Šarže materiálu')
    dodavatel_materialu = models.CharField(max_length=10, null=True, blank=True, verbose_name='Lief.')
    vyrobni_zakazka = models.CharField(max_length=20, null=True, blank=True, verbose_name='Fertigungs-auftrags Nr.')
    operator = models.CharField(max_length=20, null=True, blank=True, verbose_name='Bediener')
    tryskat = models.CharField(choices=TryskaniChoice.choices, max_length=5, default=TryskaniChoice.NEZADANO, verbose_name='Tryskání')
    rovnat = models.CharField(choices=RovnaniChoice.choices, max_length=5, default=RovnaniChoice.NEZADANO, verbose_name='Rovnání')
    stav_bedny = models.CharField(choices=StavBednyChoice.choices, max_length=2, default=StavBednyChoice.PRIJATO, verbose_name='Stav bedny')    
    poznamka = models.CharField(max_length=100, null=True, blank=True, verbose_name='Poznámka')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Bedna'
        verbose_name_plural = 'bedny'
        ordering = ['id']

    def __str__(self):
        return f'{self.zakazka_id.kamion_prijem_id.zakaznik_id.zkratka} {self.zakazka_id.kamion_prijem_id.datum} - {self.zakazka_id.artikl} - {self.zakazka_id.delka}x{self.zakazka_id.prumer} - {self.cislo_bedny}'
    
    def get_admin_url(self):
        """
        Vrací URL pro zobrazení detailu bedny v administraci.
        """
        return reverse("admin:orders_bedna_change", args=[self.pk])
    
    def save(self, *args, **kwargs):
        """
        Uloží instanci Bedna a po aktualizaci přepočítá příznak `komplet` 
        na související Zakázce.

        - Pokud se jedná o novou instanci (bez PK), pouze uloží model.
        - Při změně existující Bedny:
            * Pokud je stav `K_EXPEDICI`, ověří, zda všechny ostatní bedny
            ve stejné zakázce jsou ve stavu `K_EXPEDICI`,
            a podle toho nastaví `zakazka.komplet` na True/False.
            * V ostatních případech (ne `K_EXPEDICI`) vždy nastaví
            `zakazka.komplet` na False.
        """
        is_update = bool(self.pk)
        super().save(*args, **kwargs)

        if is_update:            
            zak = self.zakazka_id
            siblings = Bedna.objects.filter(zakazka_id=zak).exclude(pk=self.pk)
            if self.stav_bedny == StavBednyChoice.K_EXPEDICI:
                zak.komplet = all(b.stav_bedny == StavBednyChoice.K_EXPEDICI for b in siblings)
            else:
                zak.komplet = False
            zak.save()
