from django import forms
from .models import Zakazka, Bedna
from .choices import (
    TypHlavyChoice, StavBednyChoice, RovnaniChoice, TryskaniChoice,
    PrioritaChoice, ZinkovnaChoice, KamionChoice
)

class ZakazkaForm(forms.ModelForm):
    celkova_hmotnost = forms.DecimalField(required=False, min_value=1.0, label="Celková hmotnost zakázky")
    pocet_beden = forms.IntegerField(required=False, min_value=1, label="Celkový počet beden v zakázce")   
    tara = forms.DecimalField(required=False, min_value=20.0, initial=65.0, label="Tára")
    material = forms.CharField(required=False, label="Materiál")
    sarze = forms.CharField(required=False, label="Šarže materiálu")
    dodavatel_materialu = forms.CharField(required=False, label="Lief.")
    vyrobni_zakazka = forms.CharField(required=False, label="Fertigungs-auftrags Nr.")
    poznamka = forms.CharField(required=False, label="Poznámka")
    zmena_stavu = forms.ChoiceField(choices=StavBednyChoice.choices[:-1], required=False, label="Změna stavu")

    class Meta:
        model = Zakazka
        fields = '__all__'


class BednaChangeListForm(forms.ModelForm):
    """
    Formulář pro changelist bedny, který neumožní výběr možnosti EXPEDOVANO pro stav_bedny.
    """
    class Meta:
        model = Bedna
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Zrušena volba pro stav_bedny = EXPEDOVANO
        self.fields['stav_bedny'].choices = StavBednyChoice.choices[:-1]

