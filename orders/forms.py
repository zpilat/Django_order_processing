from django import forms
from django.db.models import Exists, OuterRef
from django.utils import timezone

from decimal import Decimal, ROUND_HALF_UP

from .models import Zakaznik, Kamion, Zakazka, Bedna, Predpis, Odberatel, Pozice
from .choices import StavBednyChoice, RovnaniChoice, TryskaniChoice, PrioritaChoice, KamionChoice

import logging
logger = logging.getLogger('orders')

class ImportZakazekForm(forms.Form):
    file = forms.FileField(
        label="Soubor (pouze XLSX)",
        required=False,
        widget=forms.ClearableFileInput(attrs={
            "accept": ".xlsx",
            "style": "padding:.4rem .6rem; border:1px solid var(--hairline-color); "
                     "border-radius:6px; height:1.35rem; width:350px; max-width:450px;"
        }),
    )

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
    material = forms.CharField(required=False, label="Materiál")
    sarze = forms.CharField(required=False, label="Šarže materiálu")
    dodatecne_info = forms.CharField(required=False, label="Sonder / Zusatzinfo")
    dodavatel_materialu = forms.CharField(required=False, label="Lief.")
    vyrobni_zakazka = forms.CharField(required=False, label="Fertigungs-auftrags Nr.")
    poznamka = forms.CharField(required=False, label="Poznámka HPM")

    class Meta:
        model = Zakazka
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        """
        Inicializace formuláře ZakazkaAdminForm.
        Jsou vyfiltrovány pouze aktivní předpisy zákazníka, pokud je zakázka přiřazena ke kamionu s zákazníkem.
        Jinak jsou zobrazeny všechny aktivní předpisy.
        Jsou vyfiltrovány pouze kamiony, které mají stav 'P' (příjem) a obsahují aspoň jednu zakázku, která
        nemá stav expedováno.
        """
        super().__init__(*args, **kwargs)
        inst = getattr(self, "instance", None)

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
        label="Celk. hmotn.",
        min_value=0.0,
        required=False,
        widget=forms.TextInput(attrs={'size': '8', 'style': 'width: 60px;'})
    )
    celkove_mnozstvi = forms.IntegerField(
        label="Celk. množ.",
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={'size': '5', 'style': 'width: 60px;'})
    )
    pocet_beden = forms.IntegerField(
        label="Počet beden",
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={'size': '5', 'style': 'width: 40px;'})
    )
    tara = forms.DecimalField(
        label="Tára",
        min_value=0.0,
        required=False,
        widget=forms.TextInput(attrs={'size': '8', 'style': 'width: 40px;'})
    )
    material = forms.CharField(
        label="Materiál",
        required=False,
        widget=forms.TextInput(attrs={'size': '10', 'style': 'width: 60px;'})
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
       - Pro stav_bedny nabídne všechny stavy kromě EXPEDOVANO a nastaví `initial` na hodnotu `NEPRIJATO`.
       - Pro tryskat nabídne všechny hodnoty a nastaví `initial` na hodnotu `NEZADANO`.
       - Pro rovnat nabídne všechny hodnoty a nastaví `initial` na hodnotu `NEZADANO`.

    2. EXISTUJÍCÍ instance:
       - Pro stav_bedny nabídne všechny možné stavy, které jsou povoleny pro danou bednu a nastaví `initial` na aktuální stav.
       - Pro tryskat a rovnat nabídne všechny možné stavy, které jsou povoleny pro danou bednu a nastaví `initial` na aktuální stav.

    Omezuje jak při tvorbě, tak při změně výběr zakázky na ty zakázky, které ještě nejsou expedované.
    """
    brutto = forms.DecimalField(
        label="Brutto kg",
        min_value=0.0,
        required=False,
        help_text="Zadejte brutto pouze pro výpočet táry v případě, že není zadána.",
        widget=forms.TextInput(attrs={'size': '8', 'style': 'width: 60px;'})
    )

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
            # Nastaví pro stav bedny všechny možné stavy kromě EXPEDOVANO
            allowed_stav_bedny = [choice for choice in StavBednyChoice.choices if choice[0] != StavBednyChoice.EXPEDOVANO]
            field_stav_bedny.choices = allowed_stav_bedny
            field_stav_bedny.initial = StavBednyChoice.NEPRIJATO
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

    def clean(self):
        """
        Validace a výpočet pro formulář BednaAdminForm.
        Validace:
        1) Hmotnost musí být zadána a větší než 0.
        2) Musí být zadána buď tára (větší než 0) nebo brutto (větší než 0) - stačí jedno z nich.
        3) Musí být zadáno množství větší než 0.
        4) Pokud není zadána tára, ověří se, že brutto > hmotnost, jinak přidá chybu.
        5) Pokud je zadána tára, nesmí už být zadána hodnota brutto.
        Výpočet:
        Vypočítá táru z ne-modelového pole 'brutto' pokud je zadáno brutto a není zadána tára.
        """
        cleaned = super().clean()

        brutto = cleaned.get('brutto')
        hmotnost = cleaned.get('hmotnost')
        tara = cleaned.get('tara')
        mnozstvi = cleaned.get('mnozstvi')

        # VALIDACE - zobrazí se chyby a nedojde k uložení

        # 1) Hmotnost musí být zadána a větší než 0
        if hmotnost is None or hmotnost <= 0:
            self.add_error('hmotnost', "Musí být zadána hmotnost.")

        # 2) Musí být zadána buď tára (větší než 0) nebo brutto (větší než 0) - stačí jedno z nich
        if (tara is None or tara <= 0) and (brutto is None or brutto <= 0):
            self.add_error('tara', "Zadejte buď táru nebo brutto.")
        
        # 3) Musí být zadáno množství větší než 0
        if mnozstvi is None or mnozstvi <= 0:
            self.add_error('mnozstvi', "Množství musí být větší než 0.")

        # 4) Pokud není zadána tára, ověří se, že brutto > hmotnost, jinak přidá chybu
        if (tara is None or tara <= 0) and (brutto is not None and brutto > 0) and (hmotnost is not None and hmotnost > 0):
            if brutto <= hmotnost:
                self.add_error('brutto', "Brutto musí být větší než hmotnost nebo zadejte táru.")

        # 5) Pokud je zadána tára, nesmí už být zadána hodnota brutto
        if tara is not None and tara > 0 and brutto is not None and brutto > 0:
            self.add_error('brutto', "Pokud je zadána tára, nesmí být zadáno brutto.")

        # VÝPOČET - pokud nejsou chyby, nastaví se tára
        if not self.errors:
            try:
                if brutto is not None and brutto > 0:
                    vypocet = brutto - hmotnost
                    cleaned['tara'] = vypocet.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
            except Exception:
                # v případě nečekaného typu/konverze nech beze změny
                return cleaned

        return cleaned


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


class KNavezeniForm(forms.Form):
    """
    Formulář pro výběr pozice pro bednu při změně stavu na k navezení.
    """
    bedna_id = forms.IntegerField(widget=forms.HiddenInput())
    poznamka_k_navezeni = forms.CharField(label="Poznámka k navezení", required=False)
    pozice = forms.ModelChoiceField(
        queryset=Pozice.objects.all(),
        label="Pozice",
        required=False
    )