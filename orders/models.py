from django.db import models
from simple_history.models import HistoricalRecords
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.core.exceptions import ValidationError

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
    ciselna_rada = models.PositiveIntegerField(verbose_name='Číselná řada', default=100000, unique=True,
                                               help_text='Číselná řada pro automatické číslování beden - např. 100000, 200000, 300000 atd.')
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
    prijem_vydej = models.CharField(choices=KamionChoice.choices, max_length=1, verbose_name='Přijem/Výdej', default=KamionChoice.PRIJEM)
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
    predpis = models.CharField(max_length=30, verbose_name='Předpis / Výkres')
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
    cislo_bedny = models.PositiveIntegerField(blank=True, verbose_name='Číslo bedny', unique=True,)
    hmotnost = models.DecimalField(max_digits=5, decimal_places=1, blank=True, verbose_name='Hm. netto')
    tara = models.DecimalField(max_digits=5, blank=True, decimal_places=1, verbose_name='Tára')
    material = models.CharField(max_length=20, null=True, blank=True, verbose_name='Materiál')
    sarze = models.CharField(max_length=20, null=True, blank=True, verbose_name='Šarže mat. / Charge')
    behalter_nr = models.CharField(max_length=20, null=True, blank=True, verbose_name='Behälter-Nr.')
    dodatecne_info = models.CharField(max_length=100, null=True, blank=True, verbose_name='Sonder / Zusatzinfo')
    dodavatel_materialu = models.CharField(max_length=10, null=True, blank=True, verbose_name='Lief.')
    vyrobni_zakazka = models.CharField(max_length=20, null=True, blank=True, verbose_name='Fertigungs-auftrags Nr.')
    operator = models.CharField(max_length=20, null=True, blank=True, verbose_name='Bediener')
    tryskat = models.CharField(choices=TryskaniChoice.choices, max_length=5, default=TryskaniChoice.NEZADANO, verbose_name='Tryskání')
    rovnat = models.CharField(choices=RovnaniChoice.choices, max_length=5, default=RovnaniChoice.NEZADANO, verbose_name='Rovnání')
    stav_bedny = models.CharField(choices=StavBednyChoice.choices, max_length=2, default=StavBednyChoice.PRIJATO, verbose_name='Stav bedny')    
    poznamka = models.CharField(max_length=100, null=True, blank=True, verbose_name='Poznámka HPM')
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Bedna'
        verbose_name_plural = 'bedny'
        ordering = ['id']

    def __str__(self):
        return f'{self.zakazka_id.kamion_prijem_id.zakaznik_id.zkratka} {self.zakazka_id.kamion_prijem_id.datum} - {self.zakazka_id.artikl} - {self.zakazka_id.prumer}x{self.zakazka_id.delka} - {self.cislo_bedny}'
    
    def get_admin_url(self):
        """
        Vrací URL pro zobrazení detailu bedny v administraci.
        """
        return reverse("admin:orders_bedna_change", args=[self.pk])
    
    # def clean(self):
    #     """
    #     Validace před uložením Bedny:
    #     - Pokud je související zákazník Eurotec (zkratka 'EUR'), musí být před uložením vyplněna všechna pole:
    #         material, sarze, behalter_nr, dodavatel_materialu, vyrobni_zakazka, operator.
    #     """
    #     super().clean()
    #     zak = self.zakazka_id
    #     if not zak or not zak.kamion_prijem_id:
    #         return  # není úplná vazba na zakázku, neověřujeme

    #     zakaznik = zak.kamion_prijem_id.zakaznik_id
    #     if zakaznik.zkratka == 'EUR':
    #         mandatory_fields = {
    #             'material':             self.material,
    #             'sarze':                self.sarze,
    #             'behalter_nr':          self.behalter_nr,
    #             'dodavatel_materialu':  self.dodavatel_materialu,
    #             'vyrobni_zakazka':      self.vyrobni_zakazka,
    #             'operator':             self.operator,
    #         }
    #         errors = []
    #         for field_name, value in mandatory_fields.items():
    #             if value in (None, ''):
    #                 errors.append(
    #                     ValidationError(
    #                         f"Pole '{self._meta.get_field(field_name).verbose_name}' je povinné pro zákazníka Eurotec.",
    #                         code='required'
    #                     )
    #                 )
    #         if errors:
    #             # vyhodí jednu ValidationError obsahující všechny chybové zprávy
    #             raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """
        Uloží instanci Bedna a po aktualizaci přepočítá příznak `komplet` 
        na související Zakázce.
        - Před uložením provede full_clean(), aby se spustila validace v clean().
        - Pokud se jedná o novou instanci (bez PK), pouze uloží model.
        - Při změně existující Bedny:
            * Pokud je stav `K_EXPEDICI`, ověří, zda všechny ostatní bedny
            ve stejné zakázce jsou ve stavu `K_EXPEDICI`,
            a podle toho nastaví `zakazka.komplet` na True/False.
            * V ostatních případech (ne `K_EXPEDICI`) vždy nastaví
            `zakazka.komplet` na False.
        """
        is_update = bool(self.pk)
        self.full_clean()  # spustí clean() a případně vyhodí ValidationError        
        super().save(*args, **kwargs)

        if is_update:            
            zak = self.zakazka_id
            siblings = Bedna.objects.filter(zakazka_id=zak).exclude(pk=self.pk)
            if self.stav_bedny == StavBednyChoice.K_EXPEDICI:
                zak.komplet = all(b.stav_bedny == StavBednyChoice.K_EXPEDICI for b in siblings)
            else:
                zak.komplet = False
            zak.save()

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
        Vrátí seznam tuple (value,label) pro pole `tryskat`
        podle aktuálního stavu.
        Pravidla pro výběr:
        - Pokud je stav_bedny K_EXPEDICI, nabídne pouze aktuální stav, stav tryskání už nejde měnit.
        - Pokud je tryskání nezadáno ('-------'), nabídne možnosti špinavá a čistá.
        - Pokud je tryskání špinavá, nabídne nezadáno, špinavá a otryskaná.
        - Pokud je tryskání čistá, nabídne nezadáno a čistá.
        - Pokud je tryskání otryskaná, nabídne špinavá a otryskaná.
        """
        curr = self.tryskat
        curr_choice = (curr, dict(TryskaniChoice.choices).get(curr,     'Neznámý stav'))

        # stav bedny K_EXPEDICI
        if self.stav_bedny == StavBednyChoice.K_EXPEDICI:
            return [curr_choice]

        # NEZADANO
        if curr == TryskaniChoice.NEZADANO:
            return [choice for choice in TryskaniChoice.choices if choice[0] != TryskaniChoice.OTRYSKANA]
        
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