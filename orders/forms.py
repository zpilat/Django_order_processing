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

class ZakazkaForm(forms.ModelForm):
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
        fields = '__all__'
