from django.db import models
from simple_history.models import HistoricalRecords

# Create your models here.
class TypHlavyChoice(models.TextChoices):
    TK = 'TK', 'TK'
    SK = 'SK', 'SK'
    ZK = 'ZK', 'ZK'

class StavBednyChoice(models.TextChoices):
    PRIJATO = 'PR', 'Přijato'
    NAVEZENO = 'NA', 'Navezeno'
    DO_ZPRACOVANI = 'DZ', 'Do zpracování'
    ZAKALENO = 'ZA', 'Zakaleno'
    ZKONTROLOVANO = 'ZK', 'Zkontrolováno'
    KRIVA = 'KR', 'Křivá'
    VYROVNANA = 'VY', 'Vyrovnaná'
    TRYSKAT = 'TR', 'K tryskání'
    OTRYSKANA = 'OT', 'Otryskaná'
    K_EXPEDICI = 'KE', 'K expedici'
    EXPEDOVANO = 'EX', 'Expedováno'

class PrioritaChoice(models.TextChoices):
    NIZKA = '-', 'Nízká'
    STREDNI = 'P2', 'Střední P2'
    VYSOKA = 'P1', 'Vysoká P1'

class Zakaznik(models.Model):
    nazev = models.CharField(max_length=100)
    zkratka = models.CharField(max_length=3, verbose_name='Zkratka')
    adresa = models.CharField(max_length=100, blank=True, null=True, verbose_name='Adresa')
    mesto = models.CharField(max_length=50, blank=True, null=True, verbose_name='Město')
    stat = models.CharField(max_length=50, blank=True, null=True, verbose_name='Stát')
    kontaktni_osoba = models.CharField(max_length=50, blank=True, null=True, verbose_name='Kontaktní osoba')
    telefon = models.CharField(max_length=50, blank=True, null=True, verbose_name='Telefon')
    email = models.EmailField(max_length=100, blank=True, null=True, verbose_name='E-mail')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Zákazník'
        verbose_name_plural = 'Zákazníci'
        ordering = ['nazev']

    def __str__(self):
        return self.nazev

class Kamion(models.Model):
    zakaznik_id = models.ForeignKey(Zakaznik, on_delete=models.CASCADE, related_name='kamiony')
    datum = models.DateField(verbose_name='Datum')
    cislo_dl = models.CharField(max_length=50, verbose_name='Číslo DL')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Kamión'
        verbose_name_plural = 'Kamióny'
        ordering = ['id']

    def __str__(self):
        return f'{self.id} {self.zakaznik_id.zkratka} - {self.datum}'
    
class Zakazka(models.Model):
    kamion_id = models.ForeignKey(Kamion, on_delete=models.CASCADE, related_name='zakazky', verbose_name='Kamión')
    artikl = models.CharField(max_length=50, verbose_name='Artikl')
    prumer = models.DecimalField(max_digits=4, decimal_places=1, verbose_name='Průměr')
    delka = models.DecimalField(max_digits=6, decimal_places=1, verbose_name='Délka')
    predpis = models.CharField(max_length=30, verbose_name='Předpis/výkres')
    typ_hlavy = models.CharField(choices=TypHlavyChoice.choices, max_length=3, verbose_name='Typ hlavy')
    popis = models.CharField(max_length=100, verbose_name='Popis')
    prubeh = models.IntegerField(null=True, blank=True, verbose_name='Vorgang')
    vrstva = models.CharField(max_length=20, null=True, blank=True, verbose_name='Beschichtung')
    povrch = models.CharField(max_length=20, null=True, blank=True, verbose_name='Oberfläche')
    priorita = models.CharField(choices=PrioritaChoice.choices, max_length=5, default=PrioritaChoice.NIZKA, verbose_name='Priorita')
    komplet = models.BooleanField(default=False, verbose_name='Kompletní')
    expedovano = models.BooleanField(default=False, verbose_name='Expedováno')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Zakázka'
        verbose_name_plural = 'Zakázky'
        ordering = ['id']

    def __str__(self):
        return f'{self.kamion_id.id} {self.kamion_id.zakaznik_id.zkratka} - {self.kamion_id.datum} - {self.artikl} - {self.prumer}x{self.delka}'
    
class Bedna(models.Model):
    zakazka_id = models.ForeignKey(Zakazka, on_delete=models.CASCADE, related_name='bedny')
    cislo_bedny = models.CharField(max_length=20, verbose_name='Číslo bedny')
    hmotnost = models.DecimalField(max_digits=5, decimal_places=1, verbose_name='Hm. netto')
    tara = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name='Tára')
    material = models.CharField(max_length=20, verbose_name='Materiál')
    sarze = models.CharField(max_length=20, verbose_name='Šarže')
    dodavatel_materialu = models.CharField(max_length=10, null=True, blank=True, verbose_name='Dod.mat.')
    vyrobni_zakazka = models.CharField(max_length=20, null=True, blank=True, verbose_name='Fert.-auf. Nr.')
    operator = models.CharField(max_length=20, null=True, blank=True, verbose_name='Bediener')
    tryskat = models.BooleanField(default=False, verbose_name='K tryskání')
    rovnat = models.BooleanField(default=False, verbose_name='K rovnání')
    poznamka = models.CharField(max_length=100, null=True, blank=True, verbose_name='Poznámka')
    stav_bedny = models.CharField(choices=StavBednyChoice.choices, max_length=2, default=StavBednyChoice.PRIJATO, verbose_name='Stav bedny')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Bedna'
        verbose_name_plural = 'Bedny'
        ordering = ['id']

    def __str__(self):
        return f'{self.zakazka_id.kamion_id.zakaznik_id.zkratka} - {self.zakazka_id.kamion_id.datum} - {self.zakazka_id.artikl} - \
            {self.zakazka_id.delka}x{self.zakazka_id.prumer} - {self.cislo_bedny}'