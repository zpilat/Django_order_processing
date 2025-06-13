from django.contrib import admin, messages
from django.db import models
from django.forms import TextInput, RadioSelect
from django.forms.models import BaseInlineFormSet
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.contrib.admin.views.main import ChangeList
from django.urls import path, reverse
from django.shortcuts import redirect, render
from django.utils.html import format_html

from simple_history.admin import SimpleHistoryAdmin
from decimal import Decimal, ROUND_HALF_UP
import pandas as pd

from .models import Zakaznik, Kamion, Zakazka, Bedna
from .actions import expedice_zakazek_action, import_kamionu_action, tisk_karet_beden_action, tisk_karet_beden_zakazek_action, tisk_karet_beden_kamionu_action, \
    tisk_dodaciho_listu_kamionu_action, vratit_zakazky_z_expedice_action
from .filters import ExpedovanaZakazkaFilter, StavBednyFilter, KompletZakazkaFilter
from .forms import ZakazkaAdminForm, BednaAdminForm, ImportZakazekForm, ZakazkaInlineForm
from .choices import (
    TypHlavyChoice, StavBednyChoice, RovnaniChoice, TryskaniChoice,
    PrioritaChoice, ZinkovnaChoice, KamionChoice
)


class CustomPaginationChangeList(ChangeList):
    """
    Vlastní ChangeList pro administraci s nastavením počtu položek na stránku.
    Pokud má uživatel oprávnění ke změně daného modelu,
    kvůli větší výšce editovatelných řádků se nastaví menší počet položek na stránku.
    """
    def get_results(self, request):
        # Název modelu v lowercase, např. 'bedna', 'zakazka'
        model_name = self.model._meta.model_name
        perm_codename = f"orders.change_{model_name}"

        if request.user.has_perm(perm_codename):
            self.list_per_page = 13
        else:
            self.list_per_page = 23
        super().get_results(request)


# Register your models here.
@admin.register(Zakaznik)
class ZakaznikAdmin(SimpleHistoryAdmin):
    """
    Správa zákazníků v administraci.
    """
    list_display = ('nazev', 'zkraceny_nazev', 'adresa', 'mesto', 'stat', 'kontaktni_osoba', 'telefon', 'email', 'vse_tryskat', 'pouze_komplet', 'ciselna_rada',)
    ordering = ('nazev',)
    list_per_page = 20

    history_list_display = ["id", "nazev", "zkratka",]
    history_search_fields = ["nazev", "zkratka",]    
    history_list_filter = ["nazev", "zkratka",]
    history_list_per_page = 20


class ZakazkaAutomatizovanyPrijemInline(admin.TabularInline):
    """
    Inline pro příjem zakázek v rámci kamionu na sklad včetně automatizovaného vytvoření beden a rozpočtení hmotnosti.
    """
    model = Zakazka
    form = ZakazkaInlineForm
    fk_name = 'kamion_prijem'
    verbose_name = 'Zakázka - automatizovaný příjem'
    verbose_name_plural = 'Zakázky - automatizovaný příjem'
    extra = 5
    fields = ('artikl', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'celozavit', 'popis', 'priorita', 'pocet_beden', 'celkova_hmotnost', 'tara', 'material',)
    show_change_link = True
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
    }


class ZakazkaPrijemInline(admin.TabularInline):
    """
    Inline pro správu zakázek v rámci kamionu.
    """
    model = Zakazka
    fk_name = 'kamion_prijem'
    verbose_name = 'Zakázka - příjem'
    verbose_name_plural = 'Zakázky - příjem'
    extra = 0
    fields = ('artikl', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'celozavit', 'popis', 'prubeh', 'priorita', 'celkovy_pocet_beden', 'get_komplet',)
    readonly_fields = ('expedovano', 'get_komplet', 'celkovy_pocet_beden')
    show_change_link = True
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
    }

    @admin.display(description='Komplet')
    def get_komplet(self, obj):
        '''
        Pokud není objekt (zakázka) uložen nebo neobsahuje bedny, vrátí '➖'.
        Pokud jsou všechny bedny v zakázce k_expedici nebo expedovano, vrátí ✔️.
        Pokud je alespoň jedna bedna v zakázce k expedici, vrátí ⏳.
        Pokud není žádná bedna v zakázce k expedici, vrátí ❌.
        '''
        if not obj.pk or not obj.bedny.exists():
            return '➖'

        if all(bedna.stav_bedny in (StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO) for bedna in obj.bedny.all()):
            return "✔️"
        elif any(bedna.stav_bedny == StavBednyChoice.K_EXPEDICI for bedna in obj.bedny.all()):
            return "⏳"
        return "❌"
    
    @admin.display(description='Beden')
    def celkovy_pocet_beden(self, obj):
        """
        Vrací počet beden v zakázce a umožní třídění podle hlavičky pole.
        """
        if not obj.pk:
            return 0
        return obj.bedny.count() if obj.bedny.exists() else 0
    celkovy_pocet_beden.admin_order_field = 'bedny__count'

    def get_queryset(self, request):
        """
        Přizpůsobení querysetu pro inline zakázek příjmu.
        Zobrazí pouze zakázky, které nejsou expedované.
        """
        qs = super().get_queryset(request)
        return qs.filter(expedovano=False)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """
        Přizpůsobení widgetů pro pole v administraci.
        """
        if db_field.name == 'prubeh':
            kwargs['widget'] = TextInput(attrs={'size': '12'})  # Změna velikosti pole pro průběh
        return super().formfield_for_dbfield(db_field, request, **kwargs)    


class ZakazkaVydejInline(admin.TabularInline):
    """
    Inline pro správu zakázek v rámci kamionu pro výdej.
    """
    model = Zakazka
    fk_name = 'kamion_vydej'
    verbose_name = "Zakázka - výdej"
    verbose_name_plural = "Zakázky - výdej"
    extra = 0
    fields = ('artikl', 'kamion_prijem', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'celozavit', 'popis', 'prubeh', 'priorita', 'celkovy_pocet_beden',)
    readonly_fields = ('artikl', 'kamion_prijem', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'celozavit', 'popis', 'prubeh', 'priorita', 'celkovy_pocet_beden',)
    show_change_link = True
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
    }

    @admin.display(description='Beden')
    def celkovy_pocet_beden(self, obj):
        """
        Vrací počet beden v zakázce a umožní třídění podle hlavičky pole.
        """
        if not obj.pk:
            return 0
        return obj.bedny.count() if obj.bedny.exists() else 0
    celkovy_pocet_beden.admin_order_field = 'bedny__count'    


@admin.register(Kamion)
class KamionAdmin(SimpleHistoryAdmin):
    """
    Správa kamionů v administraci.
    """
    actions = [import_kamionu_action, tisk_karet_beden_kamionu_action, tisk_dodaciho_listu_kamionu_action]

    fields = ('zakaznik', 'datum', 'cislo_dl', 'prijem_vydej', 'misto_expedice',) 
    readonly_fields = ('prijem_vydej',)
    list_display = ('get_kamion_str', 'zakaznik__nazev', 'datum', 'cislo_dl', 'prijem_vydej', 'misto_expedice',)
    list_filter = ('zakaznik__nazev', 'prijem_vydej',)
    list_display_links = ('get_kamion_str',)
    ordering = ('-id',)
    date_hierarchy = 'datum'
    list_per_page = 20

    history_list_display = ["id", "zakaznik", "datum"]
    history_search_fields = ["zakaznik__nazev", "datum"]
    history_list_filter = ["zakaznik", "datum"]
    history_list_per_page = 20

    def get_inlines(self, request, obj):
        """
        Vrací inliny pro správu zakázek kamionu v závislosti na tom, zda se jedná o kamion pro příjem nebo výdej a jestli jde o přidání nebo editaci.
        """
        if not obj:  # Pokud se jedná o přidání nového kamionu
            return [ZakazkaAutomatizovanyPrijemInline]
        if obj and obj.prijem_vydej == 'P':
            return [ZakazkaPrijemInline]
        if obj and obj.prijem_vydej == 'V':
            return [ZakazkaVydejInline]
        return []
    
    @admin.display(description='Kamion')
    def get_kamion_str(self, obj):
        '''
        Zobrazí stringový popis kamionu a umožní třídění podle hlavičky pole.     
        '''
        return obj.__str__()
    get_kamion_str.admin_order_field = 'id'

    def get_fields(self, request, obj=None):
        """
        Vrací seznam polí, která se mají zobrazit ve formuláře Kamion při přidání nového a při editaci.

        - Pokud není obj (tj. add_view), zruší se zobrazení pole `prijem_vydej`.
        - Pokud je obj a kamion je pro příjem, zruší se zobrazení pole `misto_expedice`.

        """
        fields = list(super().get_fields(request, obj))

        if not obj:  # Pokud se jedná o přidání nového kamionu
            fields.remove('prijem_vydej')
            fields.remove('misto_expedice')
        if obj and obj.prijem_vydej == 'P':
            fields.remove('misto_expedice')

        return fields

    def get_readonly_fields(self, request, obj=None):
        """
        Vrací seznam readonly polí pro inline Kamion, pokud se jedná o editaci existujícího kamionu,
        přidá do stávajících readonly_fields pole 'zakaznik'.
        """
        rof = list(super().get_readonly_fields(request, obj)) or []
        if obj:
            rof.append('zakaznik')
        return rof
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('import-zakazek/', self.admin_site.admin_view(self.import_view), name='import_zakazek_beden'),
        ]
        return custom_urls + urls

    def import_view(self, request):
        kamion_id = request.GET.get("kamion")
        kamion = Kamion.objects.get(pk=kamion_id) if kamion_id else None
        errors = []
        preview = []

        if request.method == 'POST':
            form = ImportZakazekForm(request.POST, request.FILES)
            if form.is_valid():
                file = form.cleaned_data['file']
                try:
                    # Načte prvních 200 řádků (jinak načítá celý soubor - přes 100000 řádků)
                    df = pd.read_excel(file, nrows=200, engine="openpyxl")

                    # Najde první úplně prázdný řádek
                    first_empty_index = df[df.isnull().all(axis=1)].index.min()
                    if pd.notna(first_empty_index):
                        df = df.loc[:first_empty_index - 1]

                    # Zkontroluje, jsou všechny datumy ve sloupci 'Abhol- datum' stejné.
                    if not df['Abhol- datum'].isnull().all():
                        unique_dates = df['Abhol- datum'].dropna().unique()
                        if len(unique_dates) > 1:
                            errors.append("Chyba: Všechny datumy v 'Abhol- datum' musí být stejné.")
                            return render(request, 'admin/import_zakazky.html', {
                                'form': form,
                                'kamion': kamion,
                                'preview': preview,
                                'errors': errors,
                                'title': f"Import zakázek pro kamion {kamion}",
                            })

                    # Odstraní prázdné sloupce
                    df.dropna(axis=1, how='all', inplace=True)

                    # Přehledné přejmenování sloupců
                    df.rename(columns={
                        'Unnamed: 6': 'Kopf',
                        'Unnamed: 7': 'Abmessung',
                        'Menge       ': 'Menge',
                        'n. Zg. / \nas drg': 'n. Zg. / as drg',
                    }, inplace=True)

                    # Přidání prumer a delka
                    def rozdel_rozmer(row):
                        try:
                            prumer_str, delka_str = row['Abmessung'].replace(',', '.').split('x')
                            return Decimal(prumer_str.strip()), Decimal(delka_str.strip())
                        except Exception:
                            return None, None

                    df[['prumer', 'delka']] = df.apply(
                        lambda row: pd.Series(rozdel_rozmer(row)), axis=1
                    )

                    # Vytvoří se nový sloupec 'priorita', pokud je ve sloupci 'Sonder / Zusatzinfo' obsaženo 'eilig', vyplní se hodnota 'P1' jako priorita
                    def priorita(row):
                        if pd.notna(row['Sonder / Zusatzinfo']) and 'eilig' in row['Sonder / Zusatzinfo'].lower():
                            return 'P1'
                        return '-'
                    df['priorita'] = df.apply(priorita, axis=1)

                    # Vytvoří se nový sloupec 'celozavit', pokud je ve sloupci 'Bezeichnung' obsaženo 'konstrux', vyplní se hodnota True, jinak False
                    def celozavit(row):
                        if pd.notna(row['Bezeichnung']) and 'konstrux' in row['Bezeichnung'].lower():
                            return True
                        return False
                    df['celozavit'] = df.apply(celozavit, axis=1)            

                    # Odstraní ze sloupce Bezeichnung první číslo za mezerou (včetně mezery) a vše za ním
                    df["Bezeichnung"] = df["Bezeichnung"].str.replace(r"\s+\d+.*", "", regex=True)                            

                    # Odstranění nepotřebných sloupců
                    df.drop(columns=[
                        'Unnamed: 0', 'Abmessung', 'Gew + Tara', 'VPE', 'Box', 'Anzahl Boxen pro Behälter',
                        'Gew.', 'Härterei', 'Prod. Datum', 'Menge', 'von Härterei \nnach Galvanik', 'Galvanik',
                        'vom Galvanik nach Eurotec',
                    ], inplace=True, errors='ignore')

                    # Mapování názvů sloupců
                    column_mapping = {
                        'Abhol- datum': 'datum',
                        'Material- charge': 'sarze',
                        'Artikel- nummer': 'artikl',
                        'Kopf': 'typ_hlavy',
                        'Be-schich-tung': 'vrstva',
                        'Bezeichnung': 'popis',
                        'n. Zg. / as drg': 'predpis',
                        'Material': 'material',
                        'Ober- fläche': 'povrch',
                        'Gewicht in kg': 'hmotnost',
                        'Tara kg': 'tara',
                        'Behälter-Nr.:': 'behalter_nr',
                        'Sonder / Zusatzinfo': 'dodatecne_info',
                        'Lief.': 'dodavatel_materialu',
                        'Fertigungs- auftrags Nr.': 'vyrobni_zakazka',
                        'Vorgang+': 'prubeh',
                    }                  
                    df.rename(columns=column_mapping, inplace=True)

                    # Uložení záznamů
                    zakazky_cache = {}
                    for _, row in df.iterrows():
                        if pd.isna(row.get('artikl')):
                            break

                        artikl = row['artikl']

                        if artikl not in zakazky_cache:
                            zakazka = Zakazka.objects.create(
                                kamion_prijem=kamion,
                                artikl=artikl,
                                prumer=row.get('prumer'),
                                delka=row.get('delka'),
                                predpis=int(row.get('predpis')),
                                typ_hlavy=row.get('typ_hlavy'),
                                celozavit=row.get('celozavit', False),
                                priorita=row.get('priorita', PrioritaChoice.NIZKA),
                                popis=row.get('popis'),
                                vrstva=row.get('vrstva'),
                                povrch=row.get('povrch'),
                                prubeh=row.get('prubeh').zfill(6) if row.get('prubeh') else None,
                            )
                            zakazky_cache[artikl] = zakazka

                        Bedna.objects.create(
                            zakazka=zakazky_cache[artikl],
                            hmotnost=row.get('hmotnost'),
                            tara=row.get('tara'),
                            material=row.get('material'),
                            sarze=row.get('sarze'),
                            behalter_nr=row.get('behalter_nr'),
                            dodatecne_info=row.get('dodatecne_info'),
                            dodavatel_materialu=row.get('dodavatel_materialu'),
                            vyrobni_zakazka=row.get('vyrobni_zakazka')
                        )

                    self.message_user(request, "Import proběhl úspěšně.", messages.SUCCESS)
                    return redirect("..")

                except Exception as e:
                    self.message_user(request, f"Chyba při importu: {e}", messages.ERROR)
                    return redirect("..")

        else:
            form = ImportZakazekForm()

        return render(request, 'admin/import_zakazky.html', {
            'form': form,
            'kamion': kamion,
            'preview': preview,
            'errors': errors,
            'title': f"Import zakázek pro kamion {kamion}",
        })
    
    def save_formset(self, request, form, formset: BaseInlineFormSet, change):
        """
        Uloží inline formuláře pro zakázky kamionu a vytvoří bedny na základě zadaných dat.
        """
        # Uloží se inline formuláře bez okamžitého zápisu do DB
        zakazky = formset.save(commit=False)

        for inline_form, zakazka in zip(formset.forms, zakazky):
            zakazka.kamion_prijem = form.instance  # připojení k právě vytvořenému kamionu
            zakazka.save()

            # Získání dodatečných hodnot z vlastního formuláře
            celkova_hmotnost = inline_form.cleaned_data.get("celkova_hmotnost")
            pocet_beden = inline_form.cleaned_data.get("pocet_beden")
            tara = inline_form.cleaned_data.get("tara")
            material = inline_form.cleaned_data.get("material")

            # Rozpočítání hmotnosti, pro poslední bednu se použije zbytek hmotnosti po rozpočítání a zaokrouhlení
            if celkova_hmotnost and pocet_beden:
                hmotnost_bedny = Decimal(celkova_hmotnost) / pocet_beden
                hmotnost_bedny = hmotnost_bedny.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)

                hodnoty = [hmotnost_bedny] * (pocet_beden - 1)
                posledni = celkova_hmotnost - sum(hodnoty)
                posledni = posledni.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                hodnoty.append(posledni)

                for i in range(pocet_beden):
                    Bedna.objects.create(
                        zakazka=zakazka,
                        hmotnost=hodnoty[i],
                        tara=tara,
                        material=material,
                        # cislo_bedny se dopočítá v metodě save() modelu Bedna
                    )

        formset.save()    


class BednaInline(admin.TabularInline):
    """
    Inline pro správu beden v rámci zakázky.
    """
    model = Bedna
    form = BednaAdminForm
    extra = 0
    # další úprava zobrazovaných polí podle různých podmínek je v get_fields
    fields = ('cislo_bedny', 'hmotnost', 'tara', 'mnozstvi', 'material', 'sarze', 'behalter_nr', 'dodatecne_info', 'dodavatel_materialu', 'vyrobni_zakazka', 'tryskat', 'rovnat', 'stav_bedny', 'poznamka')
    readonly_fields = ('cislo_bedny',)
    show_change_link = True
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={'size': '12'})},  # default
        models.DecimalField: {'widget': TextInput(attrs={'size': '6'})},
    }

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """
        Přizpůsobení widgetů pro pole v administraci.
        """
        if db_field.name == 'dodatecne_info':
            kwargs['widget'] = TextInput(attrs={'size': '28'})  # Změna velikosti pole pro dodatečné info
        elif db_field.name == 'poznamka':
            kwargs['widget'] = TextInput(attrs={'size': '22'}) # Změna velikosti pole pro poznámku HPM
        elif db_field.name == 'dodavatel_materialu':
            kwargs['widget'] = TextInput(attrs={'size': '8'})  # Změna velikosti pole pro dodavatele materiálu
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_fields(self, request, obj=None):
        """
        Vrací seznam polí, která se mají zobrazit ve formuláři Bedna při editaci.

        - Pokud není obj (tj. add_view), použije se základní fields z super().  
        - Pokud obj existuje a zákazník zakázky není 'EUR' (Eurotec),
          vyloučí se pole dodatecne_info, dodavatel_materialu a vyrobni_zakazka.
        """
        fields = list(super().get_fields(request, obj))

        if obj:
            if obj.kamion_prijem.zakaznik.zkratka != 'EUR':
                # Pokud je zakázka přiřazena k zákazníkovi, který není Eurotec, vyloučíme některá pole
                exclude_fields = ['behalter_nr', 'dodatecne_info', 'dodavatel_materialu', 'vyrobni_zakazka']
                for field in exclude_fields:
                    if field in fields:
                        fields.remove(field)
        else:
            # Při přidáno nové bedny se vyloučí pole `cislo_bedny`, protože se generuje automaticky.
            fields.remove('cislo_bedny')

        return fields
    

@admin.register(Zakazka)
class ZakazkaAdmin(SimpleHistoryAdmin):
    """
    Správa zakázek v administraci.
    """
    inlines = [BednaInline]
    form = ZakazkaAdminForm
    actions = [expedice_zakazek_action, tisk_karet_beden_zakazek_action, vratit_zakazky_z_expedice_action]

    # Parametry pro zobrazení detailu v administraci
    readonly_fields = ('expedovano', 'get_komplet')
    
    # Parametry pro zobrazení seznamu v administraci
    list_display = ('artikl', 'zakaznik', 'kamion_prijem_link', 'kamion_vydej_link', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'celozavit', 'popis', 'prubeh', 'priorita',
                    'hmotnost_zakazky_k_expedici_brutto', 'pocet_beden_k_expedici', 'celkovy_pocet_beden', 'get_komplet',)
    list_display_links = ('artikl',)
    search_fields = ('artikl',)
    search_help_text = "Hledat podle artiklu"
    list_filter = ('kamion_prijem__zakaznik', 'typ_hlavy', 'celozavit', 'priorita', 'povrch', KompletZakazkaFilter, ExpedovanaZakazkaFilter,)
    ordering = ('-id',)
    date_hierarchy = 'kamion_prijem__datum'
    list_per_page = 25
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
        models.BooleanField: {'widget': RadioSelect(choices=[(True, 'Ano'), (False, 'Ne')])}
    }

    # Parametry pro zobrazení historie v administraci
    history_list_display = ["id", "kamion_prijem", "kamion_vydej", "artikl", "prumer", "delka", "predpis", "typ_hlavy", "popis", "priorita",]
    history_search_fields = ["kamion_prijem__zakaznik__nazev", "artikl", "prumer", "delka", "predpis", "typ_hlavy", "popis"]
    history_list_filter = ["kamion_prijem__zakaznik", "kamion_prijem__datum", "typ_hlavy"]
    history_list_per_page = 20

    class Media:
        js = ('admin/js/zakazky_hmotnost_sum.js',)

    @admin.display(description='Brutto k exp.')
    def hmotnost_zakazky_k_expedici_brutto(self, obj):
        """
        Vrátí součet brutto hmotnosti (hmotnost + tara) všech beden se stavem 'K expedici' v dané zakázce.
        Výsledek je zaokrouhlen na 0.1 a umožňuje třídění v Django adminu.
        """
        bedny = obj.bedny.filter(stav_bedny=StavBednyChoice.K_EXPEDICI)
        brutto = sum((bedna.hmotnost or 0) + (bedna.tara or 0) for bedna in bedny)

        return brutto.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP) if brutto else Decimal('0.0')

    @admin.display(description='Beden')
    def celkovy_pocet_beden(self, obj):
        """
        Vrací počet beden v zakázce a umožní třídění podle hlavičky pole.
        """
        return obj.bedny.count() if obj.bedny.exists() else 0
    
    @admin.display(description='K exp.')
    def pocet_beden_k_expedici(self, obj):
        """
        Vrátí počet beden se stavem 'K expedici' v dané zakázce a umožní třídění podle hlavičky pole.
        """
        return obj.bedny.filter(stav_bedny=StavBednyChoice.K_EXPEDICI).count() if obj.bedny.exists() else 0

    @admin.display(description='Kamion příjem')
    def kamion_prijem_link(self, obj):
        """
        Vytvoří odkaz na detail kamionu příjmu, ke kterému zakázka patří a umožní třídění podle hlavičky pole.
        """
        if obj.kamion_prijem:
            return mark_safe(f'<a href="{obj.kamion_prijem.get_admin_url()}">{obj.kamion_prijem}</a>')
        return '-'
    kamion_prijem_link.admin_order_field = 'kamion_prijem__id'

    @admin.display(description='Kamion výdej')
    def kamion_vydej_link(self, obj):
        """
        Vytvoří odkaz na detail kamionu výdeje, ke kterému zakázka patří a umožní třídění podle hlavičky pole.
        """
        if obj.kamion_vydej:
            return mark_safe(f'<a href="{obj.kamion_vydej.get_admin_url()}">{obj.kamion_vydej}</a>')
        return '-'
    kamion_vydej_link.admin_order_field = 'kamion_vydej__id'

    @admin.display(description='Zák.')
    def zakaznik(self, obj):
        """
        Vrací zkratku zákazníka, ke kterému kamion příjmu patří a umožní třídění podle hlavičky pole.
        Umožňuje třídění podle hlavičky pole.
        """
        if obj.kamion_prijem and obj.kamion_prijem.zakaznik:
            return obj.kamion_prijem.zakaznik.zkratka
        return '-'
    zakaznik.admin_order_field = 'kamion_prijem__zakaznik__zkratka'

    def get_komplet(self, obj):
        '''
        Pokud není objekt (zakázka) uložen nebo neobsahuje bedny, vrátí '➖'.
        Pokud jsou všechny bedny v zakázce k_expedici nebo expedovano, vrátí ✔️.
        Pokud je alespoň jedna bedna v zakázce k expedici, vrátí ⏳.
        Pokud není žádná bedna v zakázce k expedici, vrátí ❌.
        '''
        if not obj.pk or not obj.bedny.exists():
            return '➖'

        if all(bedna.stav_bedny in (StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO) for bedna in obj.bedny.all()):
            return "✔️"
        elif any(bedna.stav_bedny == StavBednyChoice.K_EXPEDICI for bedna in obj.bedny.all()):
            return "⏳"
        return "❌"
    get_komplet.short_description = "Komplet"

    def has_change_permission(self, request, obj=None):
        """
        Kontrola oprávnění pro změnu zakázky, v případě expedované zakázky nelze měnit.
        """
        if obj and obj.expedovano:
            return False
        return super().has_change_permission(request, obj)  
       
    def save_formset(self, request, form, formset, change):
        """
        Uložení formsetu pro bedny. 
        Při vytváření nové zakázky - příjem zboží na sklad:
        - Pokud je vyplněn počet beden, vytvoří se nové instance. 
        - Pokud je vyplněna celková hmotnost, rozpočítá se na jednotlivé bedny.
        Při editaci zakázky:
        - Pokud je zakázka expedovaná, nelze upravovat.
        - Pokud se mění stav bedny, tryskat nebo rovnat, provede se logika pro změnu stavu všech beden v zakázce.
        """
        if change:
            # Pokud se jedná o editaci, zkontroluje, zda se mění pole stav bedny, tryskat nebo rovnat ve formuláři zakázek.
            # Pokud ano, tak se provede logika pro změnu stavu všech beden v zakázce pro změněné pole.
            if any(f in form.changed_data for f in ('stav_bedny','tryskat','rovnat')):
                zakazka = form.instance
                instances = list(formset.queryset)
                
                # Získání hodnot z formuláře
                new_stav_bedny = form.cleaned_data['stav_bedny'] if 'stav_bedny' in form.changed_data else None
                new_tryskat = form.cleaned_data['tryskat'] if 'tryskat' in form.changed_data else None
                new_rovnat = form.cleaned_data['rovnat'] if 'rovnat' in form.changed_data else None

                for bedna in instances:
                    # Pokud se mění stav bedny, tryskat nebo rovnat, nastaví se nové hodnoty
                    for field, new_value in [('stav_bedny', new_stav_bedny), ('tryskat', new_tryskat), ('rovnat', new_rovnat)]:
                        if new_value:
                            setattr(bedna, field, new_value)
                    bedna.save()

        else: # Přidání nové zakázky s bednami
            instances = formset.save(commit=False)
            zakazka = form.instance
            celkova_hmotnost = form.cleaned_data.get('celkova_hmotnost')
            pocet_beden = form.cleaned_data.get('pocet_beden')
            data_ze_zakazky = {
                'tara': form.cleaned_data.get('tara'),
                'material': form.cleaned_data.get('material'),
                'sarze': form.cleaned_data.get('sarze'),
                'dodatecne_info': form.cleaned_data.get('dodatecne_info'),
                'dodavatel_materialu': form.cleaned_data.get('dodavatel_materialu'),
                'vyrobni_zakazka': form.cleaned_data.get('vyrobni_zakazka'),
                'poznamka': form.cleaned_data.get('poznamka'),
            }

            # Pokud jsou zároveň ručně zadané bedny a zadaná celková hmotnost a počet beden, tak se zkontroluje,
            # jestli je počet beden roven počtu ručně zadaných beden, pokud ne, tak se vyhodí chyba.
            if pocet_beden and len(instances) != pocet_beden:
                messages.error(request, f"Počet ručně zadaných beden ({len(instances)}) se neshoduje s údajem v poli Celkový počet beden v zakázce: ({pocet_beden}).")
                return

            # Pokud nejsou žádné bedny ručně zadané a je vyplněn počet beden, tak se vytvoří automaticky nové bedny
            nove_bedny = []
            if len(instances) == 0 and pocet_beden:
                for i in range(pocet_beden):
                    bedna = Bedna(zakazka=zakazka)
                    nove_bedny.append(bedna)
                instances = nove_bedny

            # Společná logika bez ohledu na způsob vzniku beden:

            # Pokude je vyplněna celková hmotnost a počet beden, tak se rozpočítá hmotnost na jednotlivé bedny,
            # pro poslední bednu se použije zbytek hmotnosti po rozpočítání a zaokrouhlení
            # Případné ručně zadané hodnoty hmotnosti u beden se přepíší vypočtenými hodnotami.           
            if celkova_hmotnost and len(instances) > 0:
                hmotnost_bedny = Decimal(celkova_hmotnost) / len(instances)
                hmotnost_bedny = hmotnost_bedny.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
                hodnoty = [hmotnost_bedny] * (pocet_beden - 1)
                posledni = celkova_hmotnost - sum(hodnoty)
                posledni = posledni.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                hodnoty.append(posledni)
                for instance, hodnota in zip(instances, hodnoty):
                    instance.hmotnost = hodnota

            # Doplň prázdná pole ze zakázky (pokud už nebyla nastavena výše)
            for field, hodnota in data_ze_zakazky.items():
                if hodnota:
                    for instance in instances:
                        if getattr(instance, field) in (None, ''):
                            setattr(instance, field, hodnota)

            # Ulož všechny instance, pokud jsou to nove_bedny automaticky přidané
            if nove_bedny:
                for instance in instances:
                    instance.save()

        formset.save()

    def get_fieldsets(self, request, obj=None):
        """
        Vytváří pole pro zobrazení v administraci na základě toho, zda se jedná o editaci nebo přidání, případně zda je zakázka expedovaná.
        """
        if obj:  # editace stávajícího záznamu
            if obj.expedovano:
                # Pokud je zakázka expedovaná, kvůli has_permission v modelu ZakazkaAdmin nelze měnit, zobrazí i kamion výdej
                my_fieldsets = [
                    ('Expedovaná zakázka:', {
                        'fields': ['kamion_prijem', 'kamion_vydej', 'artikl', 'typ_hlavy', 'celozavit', 'prumer', 'delka', 'predpis', 'priorita', 'popis', 'zinkovna', 'get_komplet',],
                        'description': 'Zakázka je expedovaná a nelze ji měnit.',
                    }),
                ]
            else:  # Pokud zakázka není expedovaná, zobrazí se základní pole pro editaci
                my_fieldsets = [
                    ('Zakázka skladem:', {
                        'fields': ['kamion_prijem', 'artikl', 'typ_hlavy', 'celozavit', 'prumer', 'delka', 'predpis', 'priorita', 'popis', 'zinkovna', 'get_komplet',],
                    }),
                ]
               
            # Pokud je zákazník Eurotec, přidá speciální pole pro zobrazení
            if obj.kamion_prijem.zakaznik.zkratka == 'EUR':
                my_fieldsets.append(                  
                    ('Pouze pro Eurotec:', {
                        'fields': ['vrstva', 'povrch', 'prubeh'],
                        'description': 'Pro Eurotec musí být vyplněno: Tloušťka vrstvy, povrchová úprava a průběh.',
                    }),
                )

            # Pokud jsou pro stav_bedny, tryskat a rovnat stejné hodnoty pro všechny bedny v zakázce, přidá pole pro změnu stavu těchto položek pro všechny bedny
            if obj.bedny.exists() and obj.expedovano is False:
                stav_bedny = obj.bedny.first().stav_bedny
                tryskat = obj.bedny.first().tryskat
                rovnat = obj.bedny.first().rovnat
                fields = []
                # Pokud není pro žádnou bednu stav_bedny k_expedici:
                if not any(bedna.stav_bedny == StavBednyChoice.K_EXPEDICI for bedna in obj.bedny.all()):
                    # Pokud mají všechny bedny stejnou hodnotu pro tryskat, přidá pole pro změnu tryskat
                    if all(bedna.tryskat == tryskat for bedna in obj.bedny.all()):
                        fields += ['tryskat']
                    # Pokud mají všechny bedny stejnou hodnotu pro rovnat, přidá pole pro změnu rovnat
                    if all(bedna.rovnat == rovnat for bedna in obj.bedny.all()):
                        fields += ['rovnat']
                # Pokud mají všechny bedny stejnou hodnotu pro stav_bedny:
                if all(bedna.stav_bedny == stav_bedny for bedna in obj.bedny.all()):
                    # Pokud není stav_bedny zkontrolovano, přidá pole pro změnu stav_bedny
                    if stav_bedny != StavBednyChoice.ZKONTROLOVANO:
                        fields += ['stav_bedny']
                    # Pokud je stav bedny k_expedici a zároveň není pro žádnou bednu tryskat in (TryskaniChoice.SPINAVA, TryskaniChoice.NEZADANO)
                    # a zároveň není pro žádnou bednu rovnat in (RovnatChoice.NEZADANO, RovnatChoice.KRIVA), přidej pole pro změnu stavu beden
                    else:
                        if not any(bedna.tryskat in (TryskaniChoice.SPINAVA, TryskaniChoice.NEZADANO) for bedna in obj.bedny.all()) and \
                           not any(bedna.rovnat in (RovnaniChoice.KRIVA, RovnaniChoice.NEZADANO) for bedna in obj.bedny.all()):
                            fields += ['stav_bedny']
                if fields:
                    my_fieldsets.append(
                        ('Změna stavu všech beden v zakázce:', {
                            'fields': fields,
                            'description': 'Zde můžete změnit stav všech beden v zakázce najednou, ale bedny musí mít pro měněnou položku všechny stejnou hodnotu. \
                                Přepíše případné změněné hodnoty u jednotlivých beden.',
                        }),
                    )

            return my_fieldsets

        else:  # přidání nového záznamu
            return [
                ('Příjem zakázky na sklad:', {
                    'fields': ['kamion_prijem', 'artikl', 'typ_hlavy', 'celozavit','prumer', 'delka', 'predpis', 'priorita', 'popis', 'zinkovna', 'get_komplet',],
                    'description': 'Přijímání zakázky z kamiónu na sklad, pokud ještě není kamión v systému, vytvořte ho pomocí ikony ➕ u položky Kamión.',
                }), 
                ('Pouze pro Eurotec:', {
                    'fields': ['vrstva', 'povrch', 'prubeh'],
                    'classes': ['collapse'],
                    'description': 'Pro Eurotec musí být vyplněno: Tloušťka vrstvy, Povrchová úprava a Průběh.',
                }),  
                ('Celková hmotnost zakázky a počet beden pro rozpočtení na jednotlivé bedny:', {
                    'fields': ['celkova_hmotnost', 'pocet_beden',],
                    'classes': ['collapse'],
                    'description': 'Celková hmotnost v zakázce z DL bude rozpočítána na jednotlivé bedny, případné zadané hmotnosti u beden budou přepsány. \
                        Pokud budete jednotlivé bedny zadávat ručně a chcete rozpočítat celkovou hmotnost, musí se počet ručně zadaných beden shodovat s počtem beden v zakázce.',
                }),                      
                ('Zadejte v případě, že jsou hodnoty těchto polí pro celou zakázku stejné: Tára, Materiál, Šarže mat./Charge, Sonder/Zusatz info, Lief., Fertigungs-auftrags Nr. nebo Poznámka HPM:', {
                    'fields': ['tara', 'material', 'sarze', 'dodatecne_info', 'dodavatel_materialu', 'vyrobni_zakazka', 'poznamka'],
                    'classes': ['collapse'],
                    'description': 'Pokud jsou hodnoty polí pro celou zakázku stejné, zadejte je sem. Jinak je nechte prázdné a vyplňte je u jednotlivých beden. Případné zadané hodnoty u beden zůstanou zachovány.',}),
                ('Nastavení nestandardního stavu beden v zakázce:', {
                    'fields': ['tryskat', 'rovnat', 'stav_bedny'],
                    'classes': ['collapse'],
                    'description': 'Zde můžete ve speciálních případech nastavit při příjmu stav beden v zakázce. Např. reklamované bedny, bedny pouze k tryskání \
                        nebo rovnání, případně pouze k přeposlání do zinkovny ...',
                }),                    
            ]                    
   
    def get_list_display(self, request):
        """
        Přizpůsobení zobrazení sloupců v seznamu zakázek podle aktivního filtru.
        Pokud není aktivní filtr "skladem=Expedováno", odebere se sloupec kamion_vydej.
        """
        ld = list(super().get_list_display(request))
        if not request.GET.get('skladem'):
            ld.remove('kamion_vydej_link')
        return ld

    def get_form(self, request, obj=None, **kwargs):
        """
        Vrací ModelForm pro Zakázku, ale upraví 'choices' 
        u polí hromadné změny podle stavu první bedny.
        """
        FormClass = super().get_form(request, obj, **kwargs)
        
        class PatchedForm(FormClass):
            def __init__(self_inner, *args, **inner_kwargs):
                super().__init__(*args, **inner_kwargs)

                # Pokud upravujeme existující Zakázku a má bedny:
                if obj and obj.pk and obj.bedny.exists():
                    prvni_bedna = obj.bedny.first()
                    
                    # Omezení choices pro stav_bedny
                    if 'stav_bedny' in self_inner.fields:
                        allowed = prvni_bedna.get_allowed_stav_bedny_choices()
                        self_inner.fields['stav_bedny'].choices = allowed
                        self_inner.fields['stav_bedny'].initial = prvni_bedna.stav_bedny

                    # Omezení choices pro tryskat
                    if 'tryskat' in self_inner.fields:
                        allowed = prvni_bedna.get_allowed_tryskat_choices()
                        self_inner.fields['tryskat'].choices = allowed
                        self_inner.fields['tryskat'].initial = prvni_bedna.tryskat

                    # Omezení choices pro rovnat
                    if 'rovnat' in self_inner.fields:
                        allowed = prvni_bedna.get_allowed_rovnat_choices()
                        self_inner.fields['rovnat'].choices = allowed
                        self_inner.fields['rovnat'].initial = prvni_bedna.rovnat
        
        return PatchedForm
    

@admin.register(Bedna)
class BednaAdmin(SimpleHistoryAdmin):
    """
    Admin pro model Bedna:
    
    - Detail/inline: BednaAdminForm (omezuje stavové volby dle instance).
    - Seznam (change_list): list_editable pro stav_bedny, tryskat, rovnat a poznamka.
    - Pro každý řádek dropdown omezí na povolené volby podle stejné logiky.
    - Číslo bedny se generuje automaticky a je readonly
    """
    actions = [tisk_karet_beden_action]
    form = BednaAdminForm

    # Parametry pro zobrazení detailu v administraci
    fields = ('zakazka', 'cislo_bedny', 'hmotnost', 'tara', 'mnozstvi', 'material', 'sarze', 'behalter_nr', 'dodatecne_info',
              'dodavatel_materialu', 'vyrobni_zakazka', 'tryskat', 'rovnat', 'stav_bedny', 'poznamka',)
    readonly_fields = ('cislo_bedny',)

    # Parametry pro zobrazení seznamu v administraci
    list_display = ('cislo_bedny', 'behalter_nr', 'zakazka_link', 'kamion_prijem_link', 'kamion_vydej_link', 'get_prumer', 'get_delka',
                    'rovnat', 'tryskat', 'stav_bedny', 'get_typ_hlavy', 'hmotnost', 'tara', 'get_priorita', 'poznamka', 'karta_link',)
    # list_editable - je nastaveno pro různé stavy filtru Skladem v metodě changelist_view
    list_display_links = ('cislo_bedny', )
    search_fields = ('cislo_bedny', 'zakazka__artikl', 'zakazka__delka',)
    search_help_text = "Hledat podle čísla bedny, artiklu nebo délky vrutu"
    list_filter = ('zakazka__kamion_prijem__zakaznik__nazev', StavBednyFilter, 'rovnat', 'tryskat', 'zakazka__priorita', )
    ordering = ('id',)
    date_hierarchy = 'zakazka__kamion_prijem__datum'
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
    }

    # Parametry pro historii změn
    history_list_display = ["id", "zakazka", "cislo_bedny", "stav_bedny", "typ_hlavy", "poznamka"]
    history_search_fields = ["zakazka__kamion_prijem__zakaznik__nazev", "cislo_bedny", "stav_bedny", "zakazka__typ_hlavy", "poznamka"]
    history_list_filter = ["zakazka__kamion_prijem__zakaznik__nazev", "zakazka__kamion_prijem__datum", "stav_bedny"]
    history_list_per_page = 20

    @admin.display(description='Karta')
    def karta_link(self, obj):
        url = reverse("karta_bedny", args=[obj.pk])
        return format_html('<a href="{}" target="_blank">Zobrazit</a>', url)

    @admin.display(description='Zakázka')
    def zakazka_link(self, obj):
        """
        Vytvoří odkaz na detail zakázky, ke které bedna patří a umožní třídění podle hlavičky pole.
        """
        if obj.zakazka:
            return mark_safe(f'<a href="{obj.zakazka.get_admin_url()}">{obj.zakazka.artikl}</a>')
        return '-'
    zakazka_link.admin_order_field = 'zakazka__id'

    @admin.display(description='Kamion příjem')
    def kamion_prijem_link(self, obj):
        """
        Vytvoří odkaz na detail kamionu příjmu, ke kterému bedna patří a umožní třídění podle hlavičky pole.
        """
        if obj.zakazka and obj.zakazka.kamion_prijem:
            return mark_safe(f'<a href="{obj.zakazka.kamion_prijem.get_admin_url()}">{obj.zakazka.kamion_prijem}</a>')
        return '-'
    kamion_prijem_link.admin_order_field = 'zakazka__kamion_prijem__id'

    @admin.display(description='Kamion výdej')
    def kamion_vydej_link(self, obj):
        """
        Vytvoří odkaz na detail kamionu výdeje, ke kterému bedna patří a umožní třídění podle hlavičky pole.
        """
        if obj.zakazka and obj.zakazka.kamion_vydej:
            return mark_safe(f'<a href="{obj.zakazka.kamion_vydej.get_admin_url()}">{obj.zakazka.kamion_vydej}</a>')
        return '-'
    kamion_vydej_link.admin_order_field = 'zakazka__kamion_vydej__id'

    @admin.display(description='Typ hlavy')
    def get_typ_hlavy(self, obj):
        """
        Zobrazí typ hlavy zakázky a umožní třídění podle hlavičky pole.
        """
        return obj.zakazka.typ_hlavy
    get_typ_hlavy.admin_order_field = 'zakazka__typ_hlavy'

    @admin.display(description='Priorita')
    def get_priorita(self, obj):
        """
        Zobrazí prioritu zakázky a umožní třídění podle hlavičky pole.
        """
        return obj.zakazka.priorita
    get_priorita.admin_order_field = 'zakazka__priorita'

    @admin.display(description='Průměr')
    def get_prumer(self, obj):
        """
        Zobrazí průměr zakázky a umožní třídění podle hlavičky pole.
        """
        return obj.zakazka.prumer
    get_prumer.admin_order_field = 'zakazka__prumer'

    @admin.display(description='Délka')
    def get_delka(self, obj):
        """
        Zobrazí délku zakázky a umožní třídění podle hlavičky pole.
        """
        return obj.zakazka.delka
    get_delka.admin_order_field = 'zakazka__delka'

    def get_fields(self, request, obj=None):
        """
        Vrací seznam polí, která se mají zobrazit z formuláře Bedna při editaci.

        - Pokud není obj (tj. add_view), použije se základní fields ze super().  
        - Pokud obj existuje a zákazník zakázky není 'EUR' (Eurotec),
          odeberou se ze zobrazených polí behalter_nr, dodatecne_info, dodavatel_materialu a vyrobni_zakazka.
        """
        fields = list(super().get_fields(request, obj) or [])

        if obj and obj.zakazka.kamion_prijem.zakaznik.zkratka != 'EUR':
            fields_to_remove = ['behalter_nr', 'dodatecne_info', 'dodavatel_materialu', 'vyrobni_zakazka']
            for field in fields_to_remove:
                if field in fields:
                    fields.remove(field)

        return fields

    def get_changelist(self, request, **kwargs):
        """
        Vytvoří vlastní ChangeList s nastavením počtu položek na stránku.
        Pokud má uživatel oprávnění ke změně modelu Bedna, nastaví se menší počet položek na stránku.
        """
        return CustomPaginationChangeList
    
    def get_changelist_form(self, request, **kwargs):
        """
        Vytvoří vlastní formulář pro ChangeList s omezenými volbami pro `stav_bedny`.
        """
        return BednaAdminForm

    def has_change_permission(self, request, obj=None):
        """
        Kontrola oprávnění pro změnu bedny, v případě expedované bedny nelze měnit.
        """
        if obj and obj.stav_bedny == StavBednyChoice.EXPEDOVANO:
            return False
        return super().has_change_permission(request, obj)  
    
    def changelist_view(self, request, extra_context=None):
        # když je aktivní filtr Stav bedny vlastni = EX (expedováno), zakáže se inline-editace
        if request.GET.get('stav_bedny_vlastni') == 'EX':
            self.list_editable = ()      # žádné editovatelné sloupce
        else:
            self.list_editable = ('stav_bedny', 'rovnat', 'tryskat', 'poznamka',)
        return super().changelist_view(request, extra_context)        
    
    def get_list_display(self, request):
        """
        Přizpůsobení zobrazení sloupců v seznamu Bedna.
        Pokud není aktivní filtr Expedováno, vyloučí se zobrazení sloupce kamion_vydej_link.
        """
        list_display = list(super().get_list_display(request))
        if request.GET.get('stav_bedny_vlastni') != 'EX':
            list_display.remove('kamion_vydej_link')
        return list_display
