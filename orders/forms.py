from django import forms
from django.db.models import Exists, OuterRef
from django.utils import timezone
from .models import Zakaznik, Kamion, Zakazka, Bedna, Predpis, Odberatel
from .choices import StavBednyChoice, RovnaniChoice, TryskaniChoice, PrioritaChoice, KamionChoice

import logging
logger = logging.getLogger('orders')

class ImportZakazekForm(forms.Form):
    file = forms.FileField(label="Soubor (XLSX nebo CSV)")

class ZakazkaPredpisValidatorMixin:
    """
    Mixin pro validaci předpisu v rámci zakázky.
    Zajišťuje, že předpis patří ke stejnému zákazníkovi jako kamion,
    ke kterému je zakázka přiřazena.
    """
    def clean(self):
        cleaned_data = super().clean()
        predpis = cleaned_data.get("predpis")
        kamion = cleaned_data.get("kamion_prijem")

        if predpis and kamion and predpis.zakaznik != kamion.zakaznik:
            logger.error(f"Pokud o přiřazení předpisu „{predpis}“, který nepatří zákazníkovi „{kamion.zakaznik}“ zakázky.")
            raise forms.ValidationError(f"Předpis „{predpis}“ nepatří zákazníkovi „{kamion.zakaznik}“.")
        return cleaned_data


class ZakazkaAdminForm(ZakazkaPredpisValidatorMixin, forms.ModelForm):
    celkova_hmotnost = forms.DecimalField(required=False, min_value=1.0, label="Celková hmotnost kg zakázky")
    celkove_mnozstvi = forms.IntegerField(required=False, min_value=1, label="Celkové množství ks v zakázce")
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
        Jsou vyfiltrovány pouze aktivní předpisy zákazníka, pokud je zakázka přiřazena ke kamionu s zákazníkem.
        Jinak jsou zobrazeny všechny aktivní předpisy.
        Jsou vyfiltrovány pouze kamiony, které mají stav 'P' (příjem) a obsahují aspoň jednu zakázku, která
        nemá stav expedováno.
        """
        super().__init__(*args, **kwargs)
        inst = getattr(self, "instance", None)

        if inst and inst.pk:
            # Inicializace z první bedny (pokud existuje)
            bedna = inst.bedny.first()
            self.fields['tryskat'].initial = bedna.tryskat if bedna else TryskaniChoice.NEZADANO
            self.fields['rovnat'].initial = bedna.rovnat if bedna else RovnaniChoice.NEZADANO

        # Nastavení querysetu pro pole 'predpis' podle kontextu zakázky
        if 'predpis' in self.fields:
            if inst and inst.pk:
                if not inst.expedovano and inst.kamion_prijem and inst.kamion_prijem.zakaznik:
                    self.fields['predpis'].queryset = inst.kamion_prijem.zakaznik.predpisy.filter(aktivni=True)
            else:
                self.fields['predpis'].queryset = Predpis.objects.filter(aktivni=True)
         
        # Nastavení querysetu pro pole 'kamion_prijem'
        if 'kamion_prijem' in self.fields:
            zakazka_qs = Zakazka.objects.filter(kamion_prijem=OuterRef('pk'), expedovano=False)
            self.fields['kamion_prijem'].queryset = Kamion.objects.filter(
                prijem_vydej=KamionChoice.PRIJEM,
            ).annotate(
                ma_neexpedovanou=Exists(zakazka_qs)
            ).filter(
                ma_neexpedovanou=True
            )


class ZakazkaInlineForm(ZakazkaPredpisValidatorMixin, forms.ModelForm):
    """
    Inline formulář pro model Zakazka v Django Adminu, slouží pro automatické vytvoření beden pro jednotlivé zakázky.
    Umožní rozpočítat celkovou hmotnost zakázky na jednotlivé bedny. Přidá všem bedná v zakázce táru a typ materiálu.
    """
    celkova_hmotnost = forms.DecimalField(
        label="Celková hmotnost",
        min_value=1.0,
        widget=forms.TextInput(attrs={'size': '8', 'style': 'width: 80px;'})
    )
    pocet_beden = forms.IntegerField(
        label="Počet beden",
        min_value=1,
        widget=forms.NumberInput(attrs={'size': '5', 'style': 'width: 60px;'})
    )
    tara = forms.DecimalField(
        label="Tára",
        min_value=20.0,
        initial=65.0,
        widget=forms.TextInput(attrs={'size': '8', 'style': 'width: 80px;'})
    )
    material = forms.CharField(
        label="Materiál",
        required=False,
        widget=forms.TextInput(attrs={'size': '10', 'style': 'width: 80px;'})
    )

    class Meta:
        model = Zakazka
        fields = "__all__"            

    def __init__(self, *args, zakaznik=None, **kwargs):
        """
        Inicializace formuláře ZakazkaInlineForm.
        Pokud existuje instance zakázky nebo kamion, nastaví se queryset pro pole 'predpis'
        """
        super().__init__(*args, **kwargs)
        inst = getattr(self, "instance", None)

        if inst and inst.pk and inst.kamion_prijem and inst.kamion_prijem.zakaznik:
            self.fields['predpis'].queryset = inst.kamion_prijem.zakaznik.predpisy.filter(aktivni=True)
        elif zakaznik:
            self.fields['predpis'].queryset = zakaznik.predpisy.filter(aktivni=True)
        else:
            self.fields['predpis'].queryset = Predpis.objects.filter(aktivni=True)


class BednaAdminForm(forms.ModelForm):
    """
    Formulář pro model Bedna v Django Adminu.

    Omezuje výběr stavu bedny polí stav_bedny, tryskani a rovnani podle pravidel
    v modelu Bedna v metodách `get_allowed_xxxxx_choices`):

    1. NOVÁ instance (bez PK):
       - Pro stav_bedny nabídne všechny stavy a nastaví `initial` na hodnotu `PRIJATO`.
       - Pro tryskat nabídne všechny hodnoty a nastaví `initial` na hodnotu `NEZADANO`.
       - Pro rovnat nabídne všechny hodnoty a nastaví `initial` na hodnotu `NEZADANO`.

    2. EXISTUJÍCÍ instance:
       - Pro stav_bedny nabídne všechny možné stavy, které jsou povoleny pro danou bednu a nastaví `initial` na aktuální stav.
       - Pro tryskat a rovnat nabídne všechny možné stavy, které jsou povoleny pro danou bednu a nastaví `initial` na aktuální stav.

    Omezuje jak při tvorbě, tak při změně výběr zakázky na ty zakázky, které ještě nejsou expedované.
    """
    class Meta:
        model = Bedna
        fields = "__all__"
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Pokud je stav_bedny EXPEDOVANO, zobrazí se v detailu kvůli has_change_permission v adminu bedny ne jako formulář, ale pouze čistý text.
        # Objekt pak nemá fields ve formuláři, takže není potřeba ho inicializovat.
        if not self.fields:
            return

        field_stav_bedny = self.fields["stav_bedny"]
        field_tryskat = self.fields["tryskat"]
        field_rovnat = self.fields["rovnat"]

        # nová bedna
        if not self.instance or not self.instance.pk:
            field_stav_bedny.initial = StavBednyChoice.PRIJATO
            field_tryskat.initial = TryskaniChoice.NEZADANO
            field_rovnat.initial = RovnaniChoice.NEZADANO

        # editace: vrátí dle logiky v modelu
        else:
            allowed_stav_bedny = self.instance.get_allowed_stav_bedny_choices()
            field_stav_bedny.choices = allowed_stav_bedny
            field_stav_bedny.initial = self.instance.stav_bedny

            allowed_tryskat = self.instance.get_allowed_tryskat_choices()
            field_tryskat.choices = allowed_tryskat
            field_tryskat.initial = self.instance.tryskat

            allowed_rovnat = self.instance.get_allowed_rovnat_choices()
            field_rovnat.choices = allowed_rovnat
            field_rovnat.initial = self.instance.rovnat

        if 'zakazka' in self.fields:
            # Nastavení querysetu pro pole 'zakazka' na zakázky, které nejsou expedované
            self.fields['zakazka'].queryset = Zakazka.objects.filter(expedovano=False).order_by('-id')


class VyberKamionVydejForm(forms.Form):
    """
    Formulář pro výběr kamionu pro expedici zakázek.
    Umožňuje vybrat kamion, který má stav 'V' (výdej).
    Při inicializaci se nastaví queryset kamionů podle zadaného zákazníka.
    """
    kamion = forms.ModelChoiceField(
        queryset=Kamion.objects.none(),
        label="Vyberte kamion pro expedici",
        required=True
    )

    def __init__(self, *args, **kwargs):
        zakaznik = kwargs.pop('zakaznik', None)
        super().__init__(*args, **kwargs)
        if zakaznik:
            self.fields['kamion'].queryset = Kamion.objects.filter(
                prijem_vydej=KamionChoice.VYDEJ,
                zakaznik=zakaznik,
                datum__gte=timezone.now()-timezone.timedelta(days=10)
            ).order_by('-id')


class OdberatelForm(forms.Form):
    """
    Formulář pro výběr odběratele.
    Umožňuje vybrat odběratele při expedici zakázky.
    """
    odberatel = forms.ModelChoiceField(
        queryset=Odberatel.objects.all(),
        label="Vyberte odběratele",
    )