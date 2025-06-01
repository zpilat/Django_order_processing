from django import forms
from .models import Zakazka, Bedna
from .choices import (
    TypHlavyChoice, StavBednyChoice, RovnaniChoice, TryskaniChoice,
    PrioritaChoice, ZinkovnaChoice, KamionChoice
)

class ZakazkaAdminForm(forms.ModelForm):
    celkova_hmotnost = forms.DecimalField(required=False, min_value=1.0, label="Celková hmotnost zakázky")
    pocet_beden = forms.IntegerField(required=False, min_value=1, label="Celkový počet beden v zakázce")   
    tara = forms.DecimalField(required=False, min_value=20.0, initial=65.0, label="Tára")
    material = forms.CharField(required=False, label="Materiál")
    sarze = forms.CharField(required=False, label="Šarže materiálu")
    dodatecne_info = forms.CharField(required=False, label="Sonder / Zusatzinfo")
    dodavatel_materialu = forms.CharField(required=False, label="Lief.")
    vyrobni_zakazka = forms.CharField(required=False, label="Fertigungs-auftrags Nr.")
    poznamka = forms.CharField(required=False, label="Poznámka HPM")
    tryskat = forms.ChoiceField(choices=TryskaniChoice.choices, required=False, label="Změna stavu tryskání")
    rovnat = forms.ChoiceField(choices=RovnaniChoice.choices, required=False, label="Změna stavu rovnání")
    stav_bedny = forms.ChoiceField(choices=StavBednyChoice.choices[:-1], required=False, label="Změna stavu bedny")

    class Meta:
        model = Zakazka
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        """
        Inicializace formuláře ZakazkaAdminForm.
        Pole stav_bedny, tryskat a rovnat se u tvorby nové zakázky nezobrazují,
        při editaci se zobrazí pouze v případě, že všechny bedny v zakázce mají stejný stav a/nebo
        hodnotu tryskat a/nebo rovnat. Zobrazení je zajištěno podmínkou v fieldsetu v modeladminu.
        V tomto případě se zobrazí s nabídkou stávající hodnoty jako initial, tryskat a rovnat všechny hodnoty,
        stav_bedny s možností změny na přechozí nebo následující stav bedny pro všechny bedny v zakázce.
        Stav bedny se nastaví podle první bedny v zakázce, pokud existuje 
        a to ve třídě Patchedform v metodě get_form v modelu Bedna.
        """
        super().__init__(*args, **kwargs)
        inst = getattr(self, "instance", None)

        if inst and inst.pk:
            # Existující instance
            tryskat = inst.bedny.first().tryskat if inst.bedny.exists() else TryskaniChoice.NEZADANO
            rovnat = inst.bedny.first().rovnat if inst.bedny.exists() else RovnaniChoice.NEZADANO

            # Nastavíme initial hodnoty pro pole stav_bedny, tryskat a rovnat
            self.fields['tryskat'].initial = tryskat
            self.fields['rovnat'].initial = rovnat


class BednaAdminForm(forms.ModelForm):
    """
    Formulář pro model Bedna v Django Adminu.

    Omezuje výběr stavu bedny v poli `stav_bedny` podle následujících pravidel
    (nově definováno v modelu Bedna v metodě `get_allowed_stav_bedny_choices`):

    1. NOVÁ instance (bez PK):
       - Nabídne pouze první stav `PRIJATO` jako jedinou volbu.
       - Nastaví `initial` na hodnotu `PRIJATO`.

    2. EXISTUJÍCÍ instance:
       - Získá seznam všech voleb z `StavBednyChoice.choices` a určí index aktuálního stavu.
       - Pokud je stav `EXPEDOVANO`, nabídne pouze tento stav.
       - Pokud je stav `K_EXPEDICI`, nabídne předchozí stav a aktuální stav.
       - Pokud je stav `ZKONTROLOVANO`, nabídne předchozí stav a aktuální stav, 
         a pokud zároveň `tryskat` ∈ {CISTA, OTRYSKANA} a 
         `rovnat` ∈ {ROVNA, VYROVNANA}, doplní i následující stav.
       - Pokud je stav `PRIJATO`, nabídne tento stav a následující stav.
       - Ve všech ostatních stavech nabídne předchozí, aktuální a následující stav.
       - Nastaví `initial` na aktuální stav.
    """
    class Meta:
        model = Bedna
        fields = "__all__"
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Pokud je stav_bedny EXPEDOVANO, zobrazí se v detailu kvůli has_change_permission v adminu bedny ne jako formulář, ale pouze čistý text
        # Objekt pak nemá fields, takže není potřeba ho inicializovat
        if not self.fields:
            return

        field = self.fields["stav_bedny"]

        # nová bedna → jen PRIJATO
        if not self.instance or not self.instance.pk:
            first = list(StavBednyChoice.choices)[0]
            field.choices = [first]
            field.initial = first[0]
            return

        # jinak vrať logiku z modelu
        allowed = self.instance.get_allowed_stav_bedny_choices()
        field.choices = allowed
        field.initial = self.instance.stav_bedny