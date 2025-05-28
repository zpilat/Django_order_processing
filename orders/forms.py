from django import forms
from .models import Zakazka, Bedna
from .choices import (
    TypHlavyChoice, StavBednyChoice, RovnaniChoice, TryskaniChoice,
    PrioritaChoice, ZinkovnaChoice, KamionChoice
)

def add_empty_choice(choices, label="---------"):
    '''
    Přidá prázdnou volbu do choices jako defaultní ve formuláři.
    '''
    return [('', label)] + list(choices)

class ZakazkaAdminForm(forms.ModelForm):
    celkova_hmotnost = forms.DecimalField(required=False, min_value=1.0, label="Celková hmotnost zakázky")
    pocet_beden = forms.IntegerField(required=False, min_value=1, label="Celkový počet beden v zakázce")   
    tara = forms.DecimalField(required=False, min_value=20.0, initial=65.0, label="Tára")
    material = forms.CharField(required=False, label="Materiál")
    sarze = forms.CharField(required=False, label="Šarže materiálu")
    dodavatel_materialu = forms.CharField(required=False, label="Lief.")
    vyrobni_zakazka = forms.CharField(required=False, label="Fertigungs-auftrags Nr.")
    poznamka = forms.CharField(required=False, label="Poznámka")
    tryskat = forms.ChoiceField(choices=add_empty_choice(TryskaniChoice.choices), required=False, label="Tryskání")
    rovnat = forms.ChoiceField(choices=add_empty_choice(RovnaniChoice.choices), required=False, label="Rovnání")
    zmena_stavu = forms.ChoiceField(choices=add_empty_choice(StavBednyChoice.choices[:-1]), required=False, label="Změna stavu")

    class Meta:
        model = Zakazka
        fields = "__all__"


class BednaAdminForm(forms.ModelForm):
    """
    Formulář pro model Bedna v Django Adminu.

    Omezuje výběr stavu bedny v poli `stav_bedny` podle následujících pravidel:

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
        choices = list(StavBednyChoice.choices)
        field = self.fields["stav_bedny"]
        inst = getattr(self, "instance", None)

        # 1) NOVÁ instance → pouze PRIJATO
        if not inst or not inst.pk:
            first = choices[0]
            field.choices = [first]
            field.initial = first[0]
            return

        # 2) EXISTUJÍCÍ instance
        curr = inst.stav_bedny
        try:
            idx = next(i for i, (val, _) in enumerate(choices) if val == curr)
        except StopIteration:
            return  # neplatná hodnota

        # sestavíme základní allowed podle stavu
        if curr == StavBednyChoice.EXPEDOVANO:
            allowed = [choices[idx]]

        elif curr == StavBednyChoice.K_EXPEDICI:
            allowed = [choices[idx - 1], choices[idx]]

        elif curr == StavBednyChoice.ZKONTROLOVANO:
            allowed = [choices[idx - 1], choices[idx]]
            # přidat další, jen pokud try sk a rov mají správné hodnoty
            if inst.tryskat in (TryskaniChoice.CISTA, TryskaniChoice.OTRYSKANA) and \
               inst.rovnat in (RovnaniChoice.ROVNA, RovnaniChoice.VYROVNANA):
                allowed.append(choices[idx + 1])

        elif curr == StavBednyChoice.PRIJATO:
            allowed = [choices[idx], choices[idx + 1]]

        else:
            before = [choices[idx - 1]] if idx > 0 else []
            after  = [choices[idx + 1]] if idx < len(choices) - 1 else []
            allowed = before + [choices[idx]] + after

        field.choices = allowed
        field.initial = curr