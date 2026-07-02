from django import forms
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.forms import BaseFormSet, formset_factory
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.admin.widgets import AdminDateWidget
from django.core.exceptions import ValidationError

from decimal import Decimal, ROUND_HALF_UP

from .models import Sarze, SarzeKrok, Zakaznik, Kamion, Zakazka, Bedna, Predpis, Odberatel, Pozice, Zarizeni
from .choices import (
    StavBednyChoice,
    RovnaniChoice,
    TryskaniChoice,
    PrioritaChoice,
    KamionChoice,
    TypZarizeniChoice,
    ZinkovaniChoice,
    STAV_BEDNY_SKLADEM,
)

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


class ZakazkaMeasurementForm(forms.ModelForm):
    """Formulář pro zápis měření zakázky v rámci akce kamionu výdej."""

    class Meta:
        model = Zakazka
        fields = ("tvrdost_povrchu", "tvrdost_jadra", "ohyb", "krut", "hazeni")
        widgets = {
            "tvrdost_povrchu": forms.TextInput(attrs={"size": "20"}),
            "tvrdost_jadra": forms.TextInput(attrs={"size": "20"}),
            "ohyb": forms.TextInput(attrs={"size": "20"}),
            "krut": forms.TextInput(attrs={"size": "20"}),
            "hazeni": forms.TextInput(attrs={"size": "20"}),
        }

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
                    predpis_qs = inst.kamion_prijem.zakaznik.predpisy.filter(aktivni=True)
                    # Při editaci zachová ve výběru i aktuálně přiřazený (potenciálně neaktivní) předpis.
                    if inst.predpis_id:
                        predpis_qs = inst.kamion_prijem.zakaznik.predpisy.filter(
                            Q(aktivni=True) | Q(pk=inst.predpis_id)
                        )
                    self.fields['predpis'].queryset = predpis_qs
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
    sarze = forms.CharField(
        label="Šarže",
        required=False,
        widget=forms.TextInput(attrs={'size': '10', 'style': 'width: 60px;'})
    )
    odfosfatovat = forms.BooleanField(
        label="Odfos.",
        required=False,
        widget=forms.CheckboxInput()
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
            predpis_qs = inst.kamion_prijem.zakaznik.predpisy.filter(aktivni=True)
            # Při editaci zachová ve výběru i aktuálně přiřazený (potenciálně neaktivní) předpis.
            if inst.predpis_id:
                predpis_qs = inst.kamion_prijem.zakaznik.predpisy.filter(
                    Q(aktivni=True) | Q(pk=inst.predpis_id)
                )
            self.fields['predpis'].queryset = predpis_qs
        elif zakaznik:
            self.fields['predpis'].queryset = zakaznik.predpisy.filter(aktivni=True)
        else:
            self.fields['predpis'].queryset = Predpis.objects.filter(aktivni=True)


class BednaAdminForm(forms.ModelForm):
    """
    Formulář pro model Bedna v Django Adminu. Použití v detailu bedny i v inline bedny.

    Omezuje výběr stavu bedny polí stav_bedny, tryskani, rovnani a zinkovat podle pravidel
    v modelu Bedna v metodách `get_allowed_xxxxx_choices`):

    1. NOVÁ instance (bez PK):
       - Pro stav_bedny nabídne všechny stavy kromě EXPEDOVANO a nastaví `initial` na hodnotu `NEPRIJATO`.
       - Pro tryskat nabídne všechny hodnoty a nastaví `initial` na hodnotu `NEZADANO`.
       - Pro rovnat nabídne všechny hodnoty a nastaví `initial` na hodnotu `NEZADANO`.
       - Pro zinkovat nabídne všechny hodnoty a nastaví `initial` zatím na hodnotu NEZINKOVAT, po rozjezdu externího zinkování `NEZADANO`.

    2. EXISTUJÍCÍ instance:
       - Pro stav_bedny nabídne všechny možné stavy, které jsou povoleny pro danou bednu a nastaví `initial` na aktuální stav.
       - Pro tryskat, rovnat a zinkovat nabídne všechny možné stavy, které jsou povoleny pro danou bednu a nastaví `initial` na aktuální stav.

    Omezuje jak při tvorbě, tak při změně výběr zakázky na ty zakázky, které ještě nejsou expedované.
    """
    brutto = forms.DecimalField(
        label="Brutto kg",
        min_value=0.0,
        decimal_places=1,
        max_digits=5,
        required=False,
        help_text="Zadejte brutto pro výpočet táry pouze v případě, že není zadána.",
        widget=forms.TextInput(attrs={'size': '8', 'style': 'width: 60px;'})
    )

    class Meta:
        model = Bedna
        fields = "__all__"
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Pokud je stav_bedny EXPEDOVANO, zobrazí se v detailu kvůli has_change_permission v adminu bedny ne jako formulář,
        # ale pouze čistý text. Objekt pak nemá fields ve formuláři, takže není potřeba ho inicializovat.
        # Pozor: Nefunguje v případě, že existuje nemodelové pole (brutto), proto je potřeba ještě další validace
        # existence jednotlivých polí v self.fields.
        if not self.fields:
            return

        field_stav_bedny = self.fields.get("stav_bedny")
        field_tryskat = self.fields.get("tryskat")
        field_rovnat = self.fields.get("rovnat")
        field_zinkovat = self.fields.get("zinkovat")

        # nová bedna
        if not self.instance or not self.instance.pk:
            # Nastaví pro stav bedny všechny možné stavy kromě EXPEDOVANO
            allowed_stav_bedny = [choice for choice in StavBednyChoice.choices if choice[0] != StavBednyChoice.EXPEDOVANO]
            if field_stav_bedny:
                field_stav_bedny.choices = allowed_stav_bedny
                field_stav_bedny.initial = StavBednyChoice.NEPRIJATO
            if field_tryskat:
                field_tryskat.initial = TryskaniChoice.NEZADANO
            if field_rovnat:
                field_rovnat.initial = RovnaniChoice.NEZADANO
            if field_zinkovat:
                field_zinkovat.initial = ZinkovaniChoice.NEZINKOVAT  # zatím NEZINKOVAT, po rozjezdu externího zinkování NEZADANO
            

        # editace: vrátí dle logiky v modelu v případě, že existují příslušná pole
        else:
            if field_stav_bedny:
                field_stav_bedny.choices = self.instance.get_allowed_stav_bedny_choices()
                field_stav_bedny.initial = self.instance.stav_bedny

            if field_tryskat:
                field_tryskat.choices = self.instance.get_allowed_tryskat_choices()
                field_tryskat.initial = self.instance.tryskat

            if field_rovnat:
                field_rovnat.choices = self.instance.get_allowed_rovnat_choices()
                field_rovnat.initial = self.instance.rovnat

            if field_zinkovat:
                field_zinkovat.choices = self.instance.get_allowed_zinkovat_choices()
                field_zinkovat.initial = self.instance.zinkovat

        if 'zakazka' in self.fields:
            # Nastavení querysetu pro pole 'zakazka' na zakázky, které nejsou expedované
            self.fields['zakazka'].queryset = Zakazka.objects.filter(expedovano=False).order_by('-id')

    def clean(self):
        """
        Výpočet táry pro formulář BednaAdminForm.
        """
        cleaned = super().clean()

        # Pole 'brutto' se díky get_fieldsets zobrazuje pouze v případě, že zatím není v db uložena tára
        if 'brutto' in self.fields:
            # Načtení hodnot pro výpočet táry
            hmotnost = cleaned.get('hmotnost')
            tara = cleaned.get('tara')
            brutto = cleaned.get('brutto')

            # Pokud není zadáno brutto, není co počítat, vrátí se
            if brutto is None or brutto <= 0:
                return cleaned

            # Výpočet táry z brutto hmotnosti proběhne pouze v případě, že tára není zadána nebo není nula
            # Pokud je zadána tára > 0, je to chyba, protože nesmí být zadáno současně brutto i tára. 
            if tara is not None and tara > 0:
                self.add_error('brutto', "Pokud je zadána tára, nesmí být zadáno brutto.")
            
            # Pokud není zadána hmotnost, dá chybovou hlášku, protože bez hmotnosti nelze táru spočítat
            if hmotnost is None or hmotnost <= 0:
                self.add_error('hmotnost', "Pro výpočet táry z brutto musí být zadána platná hmotnost (>0).")

            # Pokud je brutto menší nebo rovno hmotnosti, je to chyba, protože tára by byla záporná nebo nula
            if hmotnost is not None and brutto <= hmotnost:
                self.add_error('brutto', "Brutto musí být větší než hmotnost pro výpočet kladné táry.")
            
            # Výpočet táry pokud nebyly nalezeny chyby
            if not self.errors:
                vypocet = brutto - hmotnost
                cleaned['tara'] = (vypocet).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)

        return cleaned


class BednaChangeListForm(forms.ModelForm):
    """
    Formulář pro model Bedna v Changelistu Django Adminu.

    Omezuje výběr stavu bedny polí stav_bedny, tryskani a rovnani podle pravidel
    v modelu Bedna v metodách `get_allowed_xxxxx_choices`):

       - Pro stav_bedny nabídne všechny možné stavy, které jsou povoleny pro danou bednu a nastaví `initial` na aktuální stav.
       - Pro tryskat, rovnat a zinkovat nabídne všechny možné stavy, které jsou povoleny pro danou bednu a nastaví `initial` na aktuální stav.
    """
    class Meta:
        model = Bedna
        fields = "__all__"

    CONCURRENT_CHANGE_MESSAGE = _(
        'Hodnota už není platná (záznam se mezitím změnil v jiné záložce nebo jiným uživatelem). '
        'Vyberte z aktuálně dostupných možností.'
    )
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Pokud je stav_bedny EXPEDOVANO, zobrazí se v detailu kvůli has_change_permission v adminu bedny ne jako formulář, ale pouze čistý text.
        # Objekt pak nemá fields ve formuláři, takže není potřeba ho inicializovat.
        if not self.fields:
            return

        field_stav_bedny = self.fields.get("stav_bedny")
        field_tryskat = self.fields.get("tryskat")
        field_rovnat = self.fields.get("rovnat")
        field_zinkovat = self.fields.get("zinkovat")

        for field in (field_stav_bedny, field_tryskat, field_rovnat, field_zinkovat):
            if field:
                field.error_messages['invalid_choice'] = self.CONCURRENT_CHANGE_MESSAGE

        # V changelistu vždy pouze editace: vrátí dle logiky v modelu v případě, že existují příslušná pole
        if field_stav_bedny:
            field_stav_bedny.choices = self.instance.get_allowed_stav_bedny_choices()
            field_stav_bedny.initial = self.instance.stav_bedny

        if field_tryskat:
            field_tryskat.choices = self.instance.get_allowed_tryskat_choices()
            field_tryskat.initial = self.instance.tryskat

        if field_rovnat:
            field_rovnat.choices = self.instance.get_allowed_rovnat_choices()
            field_rovnat.initial = self.instance.rovnat

        if field_zinkovat:
            field_zinkovat.choices = self.instance.get_allowed_zinkovat_choices()
            field_zinkovat.initial = self.instance.zinkovat


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

class NavezenoForm(forms.Form):
    """
    Formulář pro výběr pozice pro bednu při změně stavu na NAVEZENO.
    """
    bedna_id = forms.IntegerField(widget=forms.HiddenInput())
    pozice = forms.ModelChoiceField(
        queryset=Pozice.objects.all(),
        label="Pozice",
        required=False
    )

class SarzeKrokActionInitForm(forms.Form):
    datum = forms.DateField(
        required=True,
        label='Datum',
        input_formats=['%d.%m.%Y', '%Y-%m-%d'],
        widget=AdminDateWidget(),
    )
    zarizeni = forms.ModelChoiceField(
        queryset=Zarizeni.objects.order_by('kod_zarizeni', 'nazev_zarizeni'),
        required=True,
        label='Pracoviště',
    )
    zacatek = forms.TimeField(required=True, label='Začátek', input_formats=['%H:%M', '%H.%M'])
    konec = forms.TimeField(required=False, label='Konec', input_formats=['%H:%M', '%H.%M'])
    operator = forms.CharField(max_length=30, required=True, label='Operátor')
    program = forms.CharField(max_length=20, required=False, label='Program')
    alarm = forms.CharField(max_length=50, required=False, label='Alarm')
    poznamka = forms.CharField(max_length=100, required=False, label='Poznámka')

    def __init__(self, *args, **kwargs):
        self.sarze = kwargs.pop('sarze', None)
        super().__init__(*args, **kwargs)
        # Nastavení upozornění pro zarizeni, které už mají v této sarži krok.
        if 'zarizeni' in self.fields and self.sarze:
            # Získání všech zařízení, které už mají v této šarži krok
            existing_zarizeni_ids = set(self.sarze.kroky.values_list('zarizeni_id', flat=True))
            self.fields["zarizeni"].label_from_instance = (
                lambda obj: (
                        f"{obj.zkraceny_nazev_zarizeni} - Pro toto pracoviště již existuje krok v této šarži."
                ) if obj.id in existing_zarizeni_ids else f"{obj.zkraceny_nazev_zarizeni}"
            )             

    def clean_operator(self):
        operator = (self.cleaned_data.get('operator') or '').strip()
        if not operator:
            raise ValidationError('Pole Operátor je povinné.')
        return operator    


class SarzeScanKrokChangeForm(forms.ModelForm):
    class Meta:
        model = SarzeKrok
        fields = ('datum', 'zarizeni', 'zacatek', 'konec', 'operator', 'program', 'alarm', 'poznamka')
        widgets = {
            'datum': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'},
                format='%Y-%m-%d',
            ),
            'zarizeni': forms.Select(attrs={'class': 'form-select'}),
            'zacatek': forms.TimeInput(
                attrs={'class': 'form-control', 'type': 'time'},
                format='%H:%M',
            ),
            'konec': forms.TimeInput(
                attrs={'class': 'form-control', 'type': 'time'},
                format='%H:%M',
            ),
            'operator': forms.TextInput(attrs={'class': 'form-control'}),
            'program': forms.TextInput(attrs={'class': 'form-control'}),
            'alarm': forms.TextInput(attrs={'class': 'form-control'}),
            'poznamka': forms.TextInput(attrs={'class': 'form-control'}),
        }


class RychleZalozeniSarzeForm(forms.Form):
    cislo_pripravku = forms.IntegerField(
        required=True,
        min_value=0,
        label='Číslo přípravku',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
    )
    poznamka_sarze = forms.CharField(
        required=False,
        max_length=100,
        label='Poznámka šarže',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    datum = forms.DateField(
        required=True,
        label='Datum kroku',
        input_formats=['%Y-%m-%d', '%d.%m.%Y'],
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
    )
    zacatek = forms.TimeField(
        required=True,
        label='Začátek',
        input_formats=['%H:%M', '%H.%M'],
        initial=timezone.localtime().strftime('%H:%M'),
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}, format='%H:%M'),
    )
    konec = forms.TimeField(
        required=False, # konec kroku není povinný, protože při rychlém založení šarže nemusí být hned zadán
        label='Konec',
        input_formats=['%H:%M', '%H.%M'],
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}, format='%H:%M'),
    )
    operator = forms.CharField(
        required=True,
        max_length=30,
        label='Operátor',
        widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'on'}),
    )
    poznamka_kroku = forms.CharField(
        required=False,
        max_length=100,
        label='Poznámka kroku nakládání',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    def __init__(self, *args, sarze=None, krok=None, **kwargs):
        if (sarze is None) != (krok is None):
            raise ValueError('Pro úpravu musí být předána šarže i krok.')
        if krok is not None and krok.sarze_id != sarze.pk:
            raise ValueError('Krok nepatří k předané šarži.')

        self.sarze = sarze
        self.krok = krok
        if sarze is not None:
            initial = kwargs.setdefault('initial', {})
            initial.setdefault('cislo_pripravku', sarze.cislo_pripravku)
            initial.setdefault('poznamka_sarze', sarze.poznamka)
            initial.setdefault('datum', krok.datum)
            initial.setdefault('zacatek', krok.zacatek)
            initial.setdefault('konec', krok.konec)
            initial.setdefault('operator', krok.operator)
            initial.setdefault('poznamka_kroku', krok.poznamka)

        super().__init__(*args, **kwargs)

    def clean_operator(self):
        operator = (self.cleaned_data.get('operator') or '').strip()
        if not operator:
            raise ValidationError('Pole Operátor je povinné.')
        return operator

    def clean_poznamka_kroku(self):
        return (self.cleaned_data.get('poznamka_kroku') or '').strip()
    
    def clean_poznamka_sarze(self):
        return (self.cleaned_data.get('poznamka_sarze') or '').strip()

    def clean(self):
        cleaned_data = super().clean()
        zarizeni = self._get_nakladani_zarizeni()
        if zarizeni is None:
            raise ValidationError(
                'Pracoviště Nakládání nebylo nalezeno jednoznačně. Zkontrolujte číselník pracovišť.'
            )
        cleaned_data['zarizeni'] = zarizeni
        return cleaned_data

    def save(self):
        if not self.is_valid():
            raise ValueError('Formulář musí být před uložením validní.')

        data = self.cleaned_data
        with transaction.atomic():
            if self.sarze is not None:
                sarze = Sarze.objects.select_for_update().get(pk=self.sarze.pk)
                krok = SarzeKrok.objects.select_for_update().get(
                    pk=self.krok.pk,
                    sarze=sarze,
                )
                sarze.cislo_pripravku = data['cislo_pripravku']
                sarze.poznamka = data['poznamka_sarze'] or None
                sarze.save(update_fields=['cislo_pripravku', 'poznamka'])

                krok.datum = data['datum']
                krok.zarizeni = data['zarizeni']
                krok.zacatek = data['zacatek']
                krok.konec = data['konec']
                krok.operator = data['operator']
                krok.poznamka = data['poznamka_kroku'] or None
                krok.save(
                    update_fields=[
                        'datum',
                        'zarizeni',
                        'zacatek',
                        'konec',
                        'operator',
                        'poznamka',
                    ]
                )
                return sarze, krok

            sarze = Sarze.objects.create(
                datum_zalozeni=timezone.localdate(),
                cislo_pripravku=data['cislo_pripravku'],
                aktivni=True,
                poznamka=data['poznamka_sarze'] or None,
            )
            krok = SarzeKrok.objects.create(
                sarze=sarze,
                poradi=1,
                datum=data['datum'],
                zarizeni=data['zarizeni'],
                zacatek=data['zacatek'],
                konec=data['konec'],
                operator=data['operator'],
                poznamka=data['poznamka_kroku'] or None,
            )
        return sarze, krok

    def _get_nakladani_zarizeni(self):
        qs = Zarizeni.objects.filter(typ_zarizeni=TypZarizeniChoice.NAKLADANI)
        if qs.count() == 1:
            return qs.first()
        return None


class SarzeKrokPatroPolozkaForm(forms.Form):
    bedna = forms.ModelChoiceField(
        queryset=Bedna.objects.none(),
        required=False,
        label='Bedna',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm js-bedna'}),
    )
    popis_mimo_db = forms.CharField(
        required=False,
        max_length=50,
        label='Popis mimo DB',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm js-iron-label'}),
    )
    zakaznik_mimo_db = forms.CharField(
        required=False,
        max_length=50,
        label='Zákazník mimo DB',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm js-iron-label'}),
    )
    zakazka_mimo_db = forms.CharField(
        required=False,
        max_length=30,
        label='Zakázka mimo DB',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm js-iron-label'}),
    )
    cislo_bedny_mimo_db = forms.CharField(
        required=False,
        max_length=30,
        label='Číslo bedny mimo DB',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm js-iron-label'}),
    )
    procent_z_patra = forms.IntegerField(
        required=False,
        min_value=5,
        max_value=100,
        widget=forms.HiddenInput(attrs={'class': 'js-percentage'}),
    )

    def __init__(self, *args, **kwargs):
        self.bedna_only = kwargs.pop('bedna_only', False)
        super().__init__(*args, **kwargs)
        allowed_states = [
            state.value if hasattr(state, 'value') else state
            for state in STAV_BEDNY_SKLADEM
        ]
        self.fields['bedna'].queryset = (
            Bedna.objects
            .filter(stav_bedny__in=allowed_states)
            .select_related('zakazka', 'zakazka__kamion_prijem', 'zakazka__kamion_prijem__zakaznik')
            .order_by('-cislo_bedny')
        )
        if self.bedna_only:
            for field_name in (
                'popis_mimo_db',
                'zakaznik_mimo_db',
                'zakazka_mimo_db',
                'cislo_bedny_mimo_db',
            ):
                self.fields.pop(field_name, None)

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('DELETE'):
            return cleaned_data

        bedna = cleaned_data.get('bedna')
        if self.bedna_only:
            return cleaned_data

        iron_fields = (
            'popis_mimo_db',
            'zakaznik_mimo_db',
            'zakazka_mimo_db',
            'cislo_bedny_mimo_db',
        )
        iron_field_mandatory = (
            'popis_mimo_db',
            'zakaznik_mimo_db',
            'zakazka_mimo_db',
        )
        iron_values = {
            field_name: (cleaned_data.get(field_name) or '').strip()
            for field_name in iron_fields
        }
        for field_name, value in iron_values.items():
            cleaned_data[field_name] = value

        has_iron_value = any(iron_values.values())
        if not bedna and not has_iron_value:
            return cleaned_data

        if bedna and has_iron_value:
            raise ValidationError('Vyplňte buď bednu, nebo údaje železa mimo DB, ne obojí.')

        iron_values_for_mandatory = {
            field_name: iron_values[field_name]
            for field_name in iron_field_mandatory
        }

        if has_iron_value:
            missing_labels = [
                self.fields[field_name].label
                for field_name, value in iron_values_for_mandatory.items()
                if not value
            ]
            if missing_labels:
                raise ValidationError(
                    f"Pro železo vyplňte povinná pole. Chybí: {', '.join(missing_labels)}."
                )

        return cleaned_data

    def has_item(self):
        if not hasattr(self, 'cleaned_data') or self.cleaned_data.get('DELETE'):
            return False
        if self.bedna_only:
            return bool(self.cleaned_data.get('bedna'))
        return bool(
            self.cleaned_data.get('bedna')
            or self.cleaned_data.get('popis_mimo_db')
            or self.cleaned_data.get('zakaznik_mimo_db')
            or self.cleaned_data.get('zakazka_mimo_db')
            or self.cleaned_data.get('cislo_bedny_mimo_db')
        )


class BaseSarzeKrokPatroFormSet(BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        active_forms = [form for form in self.forms if form.has_item()]
        if not active_forms:
            if all(getattr(form, 'bedna_only', False) for form in self.forms):
                raise ValidationError('Vyplňte alespoň jednu bednu.')
            raise ValidationError('Vyplňte alespoň jednu bednu nebo jeden řádek železa.')
        if len(active_forms) > 5:
            raise ValidationError('Jedno patro může obsahovat nejvýše 5 položek.')

        percentages = [
            form.cleaned_data.get('procent_z_patra')
            for form in active_forms
        ]
        if any(value is None for value in percentages):
            raise ValidationError('Nastavte rozdělení roštu pro všechny položky.')
        if sum(percentages) > 100:
            raise ValidationError('Součet procent všech položek v patře nesmí překročit 100 %.')

    def active_forms(self):
        return [form for form in self.forms if form.has_item()]


def get_sarze_krok_patro_formset(*, is_change):
    return formset_factory(
        SarzeKrokPatroPolozkaForm,
        formset=BaseSarzeKrokPatroFormSet,
        extra=1 if is_change else 3,
        can_delete=True,
        max_num=5,
        validate_max=True,
    )
