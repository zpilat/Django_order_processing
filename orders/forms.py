from django import forms
from .models import Zakazka

class ZakazkaForm(forms.ModelForm):
    celkova_hmotnost = forms.DecimalField(required=False, label="Celková hmotnost zakázky")
    tara = forms.DecimalField(required=False, label="Tára")
    material = forms.CharField(required=False, label="Materiál")
    sarze = forms.CharField(required=False, label="Šarže materiálu")
    dodavatel_materialu = forms.CharField(required=False, label="Lief.")
    vyrobni_zakazka = forms.CharField(required=False, label="Fertigungs-auftrags Nr.")
    poznamka = forms.CharField(required=False, label="Poznámka")

    class Meta:
        model = Zakazka
        fields = '__all__'
