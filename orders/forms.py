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
    class Meta:
        model = Bedna
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        """
        Inicializuje BednaAdminForm a omezuje výběr stavů pro pole `stav_bedny`:

        - Pokud je instance nová (bez primárního klíče):
            * Nabídne pouze výchozí stav (PRIJATO) jako jedinou volbu.
            * Nastaví ho jako výchozí (`initial`).
        - Pokud je instance existující:
            * Najde aktuální index stavu v `StavBednyChoice.choices`.
            * Pokud existuje následující stav, zobrazí jen tu jedinou volbu.
            * Pokud je instance v posledním stavu, deaktivuje pole (`disabled`).
        """        
        super().__init__(*args, **kwargs)

        # úprava existující bedny
        if self.instance and self.instance.pk:
            choices = list(StavBednyChoice.choices)
            # index aktuálního stavu bedny
            current_index = next((i for i, (val, _) in enumerate(choices)
                                  if val == self.instance.stav_bedny), None)
            # povolená možnost - následující stav_bedny, kromě možnosti expedováno
            if current_index and current_index + 1 < len(choices) - 1:
                next_choice = choices[current_index + 1]
                self.fields['stav_bedny'].choices = [next_choice]
            else:
                self.fields['stav_bedny'].widget.attrs['disabled'] = True