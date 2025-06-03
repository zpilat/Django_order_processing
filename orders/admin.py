from django.contrib import admin, messages
from django.db import models
from django.forms import TextInput
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.contrib.admin.views.main import ChangeList
from django.urls import path
from django.shortcuts import redirect, render

from simple_history.admin import SimpleHistoryAdmin
from import_export.admin import ImportExportModelAdmin
from import_export.formats.base_formats import XLSX, CSV
from tablib import Dataset
from decimal import Decimal, ROUND_HALF_UP
import pandas as pd

from .models import Zakaznik, Kamion, Zakazka, Bedna
from .actions import expedice_zakazek, import_zakazek_beden_action
from .filters import ExpedovanaZakazkaFilter, StavBednyFilter
from .forms import ZakazkaAdminForm, BednaAdminForm, ImportZakazekForm
from .resources import BednaResourceEurotec
from .choices import (
    TypHlavyChoice, StavBednyChoice, RovnaniChoice, TryskaniChoice,
    PrioritaChoice, ZinkovnaChoice, KamionChoice
)


class ImportExportHistoryModelAdmin(ImportExportModelAdmin, SimpleHistoryAdmin):
    """
    Kombinovaná třída adminu pro podporu jak import/exportu,
    tak verzování pomocí django-simple-history.
    """
    pass


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
    list_display = ('nazev', 'zkratka', 'adresa', 'mesto', 'stat', 'kontaktni_osoba', 'telefon', 'email', 'vse_tryskat', 'ciselna_rada',)
    ordering = ('nazev',)
    list_per_page = 20

    history_list_display = ["id", "nazev", "zkratka",]
    history_search_fields = ["nazev", "zkratka",]    
    history_list_filter = ["nazev", "zkratka",]
    history_list_per_page = 20


class ZakazkaPrijemInline(admin.TabularInline):
    """
    Inline pro správu zakázek v rámci kamionu.
    """
    model = Zakazka
    fk_name = 'kamion_prijem'
    verbose_name = 'Zakázka - příjem'
    verbose_name_plural = 'Zakázky - příjem'
    extra = 0
    fields = ('artikl', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'popis', 'priorita', 'komplet','expedovano',)
    readonly_fields = ('komplet', 'expedovano',)
    show_change_link = True
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
    }

    def get_queryset(self, request):
        """
        Přizpůsobení querysetu pro inline zakázek příjmu.
        Zobrazí pouze zakázky, které nejsou expedované.
        """
        qs = super().get_queryset(request)
        return qs.filter(expedovano=False)


class ZakazkaVydejInline(admin.TabularInline):
    """
    Inline pro správu zakázek v rámci kamionu pro výdej.
    """
    model = Zakazka
    fk_name = 'kamion_vydej'
    verbose_name = "Zakázka - výdej"
    verbose_name_plural = "Zakázky - výdej"
    extra = 0
    fields = ('artikl', 'kamion_prijem', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'popis', 'priorita', 'komplet', 'expedovano',)
    readonly_fields = ('artikl', 'kamion_prijem', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'popis', 'priorita', 'komplet', 'expedovano',)
    show_change_link = True
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
    }


@admin.register(Kamion)
class KamionAdmin(SimpleHistoryAdmin):
    """
    Správa kamionů v administraci.
    """
    actions = [import_zakazek_beden_action]

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
        if obj and obj.prijem_vydej == 'P':
            return [ZakazkaPrijemInline]
        elif obj and obj.prijem_vydej == 'V':
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
                    # Načti prvních 200 řádků (rychlejší + kontrola rozsahu)
                    df = pd.read_excel(file, nrows=200, engine="openpyxl")

                    # Najdi první úplně prázdný řádek
                    first_empty_index = df[df.isnull().all(axis=1)].index.min()
                    if pd.notna(first_empty_index):
                        df = df.loc[:first_empty_index - 1]

                    # Odstraň prázdné sloupce
                    df.dropna(axis=1, how='all', inplace=True)

                    # Přehledné přejmenování sloupců
                    df.rename(columns={
                        "Unnamed: 6": "Kopf",
                        "Unnamed: 7": "Abmessung",
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

                    # Odstranit nepotřebné sloupce
                    df.drop(columns=[
                        'Unnamed: 0', 'Abmessung', 'Gew + Tara', 'VPE', 'Box',
                        'Anzahl Boxen pro Behälter', 'Gew.', 'Härterei',
                        'von Härterei \nnach Galvanik', 'Galvanik', 'vom Galvanik nach Eurotec'
                    ], inplace=True, errors='ignore')

                    # Mapování názvů sloupců
                    column_mapping = {
                        'Abhol- datum': 'datum',
                        'Prod. Datum': 'datum_vyroby',
                        'Material- charge': 'sarze',
                        'Vorgang+': 'prubeh',
                        'Artikel- nummer': 'artikl',
                        'Kopf': 'typ_hlavy',
                        'Be-schich-tung': 'vrstva',
                        'Bezeichnung': 'popis',
                        'n. Zg. / \nas drg': 'predpis',
                        'Material': 'material',
                        'Ober- fläche': 'povrch',
                        'Gewicht in kg': 'hmotnost',
                        'Tara kg': 'tara',
                        'Menge       ': 'mnozstvi',
                        'Behälter-Nr.:': 'behalter_nr',
                        'Sonder / Zusatzinfo': 'dodatecne_info',
                        'Lief.': 'dodavatel_materialu',
                        'Fertigungs- auftrags Nr.': 'vyrobni_zakazka'
                    }

                    df.rename(columns=column_mapping, inplace=True)

                    # Ukázka náhledu
                    preview = df.head(5).to_dict(orient='records')

                    # Uložení záznamů
                    zakazky_cache = {}
                    for _, row in df.iterrows():
                        if pd.isna(row.get('artikl')):
                            break

                        artikl = row['artikl']
                        prumer = row['prumer']
                        delka = row['delka']

                        if artikl not in zakazky_cache:
                            zakazka = Zakazka.objects.create(
                                kamion_prijem=kamion,
                                artikl=artikl,
                                prumer=prumer,
                                delka=delka,
                                predpis=row.get('predpis'),
                                typ_hlavy=row.get('typ_hlavy'),
                                popis=row.get('popis'),
                                prubeh=row.get('prubeh'),
                                vrstva=row.get('vrstva'),
                                povrch=row.get('povrch')
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


class BednaInline(admin.TabularInline):
    """
    Inline pro správu beden v rámci zakázky.
    """
    model = Bedna
    form = BednaAdminForm
    extra = 0
    # další úprava zobrazovaných polí podle různých podmínek je v get_fields
    fields = ('cislo_bedny', 'hmotnost', 'tara', 'material', 'sarze', 'behalter_nr', 'dodatecne_info', 'dodavatel_materialu', 'vyrobni_zakazka', 'tryskat', 'rovnat', 'stav_bedny', 'poznamka')
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
    actions = [expedice_zakazek,]
    readonly_fields = ('komplet', 'expedovano')
    list_display = ('artikl', 'kamion_prijem_link', 'kamion_vydej_link', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'popis', 'priorita', 'hmotnost_zakazky_netto', 'hmotnost_zakazky_brutto', 'pocet_beden', 'komplet', 'expedovano',)
    #list_editable = je nastaveno pro různé stavy filtru Skladem v metodě changelist_view
    list_display_links = ('artikl',)
    search_fields = ('artikl',)
    search_help_text = "Hledat podle artiklu"
    list_filter = ('kamion_prijem__zakaznik', 'typ_hlavy', 'priorita', 'komplet', ExpedovanaZakazkaFilter,)
    ordering = ('-id',)
    date_hierarchy = 'kamion_prijem__datum'
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
    }

    history_list_display = ["id", "kamion_prijem", "kamion_vydej", "artikl", "prumer", "delka", "predpis", "typ_hlavy", "popis", "priorita", "komplet"]
    history_search_fields = ["kamion_prijem__zakaznik__nazev", "artikl", "prumer", "delka", "predpis", "typ_hlavy", "popis"]
    history_list_filter = ["kamion_prijem__zakaznik", "kamion_prijem__datum", "typ_hlavy"]
    history_list_per_page = 20

    class Media:
        js = ('admin/js/zakazky_hmotnost_sum.js',)

    @admin.display(description='Brutto')
    def hmotnost_zakazky_brutto(self, obj):
        """
        Vypočítá celkovou brutto hmotnost beden v zakázce a umožní třídění podle hlavičky pole.
        """
        bedny = list(obj.bedny.all())
        netto = sum(bedna.hmotnost or 0 for bedna in bedny)
        brutto = netto + sum(bedna.tara or 0 for bedna in bedny)
        if brutto:
            return brutto.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
        return Decimal('0.0')
    

    @admin.display(description='Netto')
    def hmotnost_zakazky_netto(self, obj):
        """
        Vypočítá celkovou netto hmotnost beden v zakázce a umožní třídění podle hlavičky pole.
        """
        if obj.bedny.exists():
            return sum(bedna.hmotnost or 0 for bedna in obj.bedny.all()).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
        return Decimal('0.0')

    @admin.display(description='Počet beden')
    def pocet_beden(self, obj):
        """
        Vrací počet beden v zakázce a umožní třídění podle hlavičky pole.
        """
        return obj.bedny.count() if obj.bedny.exists() else 0

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
                if not instances:
                    messages.error(request, "Zakázka neobsahuje žádné bedny.")
                    return
                
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

            # Pokud nejsou žádné bedny ručně zadané a je vyplněn počet beden, tak se vytvoří nové bedny 
            # a naplní se z daty ze zakázky a celkovou hmotností
            nove_bedny = []
            if len(instances) == 0 and pocet_beden:
                for i in range(pocet_beden):
                    bedna = Bedna(zakazka=zakazka)
                    nove_bedny.append(bedna)
                instances = nove_bedny

            # Společná logika bez ohledu na způsob vzniku beden:

            # Rozpočítání hmotnosti
            if celkova_hmotnost and len(instances) > 0:
                hmotnost_bedny = Decimal(celkova_hmotnost) / len(instances)
                hmotnost_bedny = hmotnost_bedny.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
                for instance in instances:
                    instance.hmotnost = hmotnost_bedny

            # Doplň prázdná pole ze zakázky (pokud už nebyla nastavena výše)
            for field, hodnota in data_ze_zakazky.items():
                if hodnota:
                    for instance in instances:
                        value = getattr(instance, field)
                        if value in (None, ''):
                            setattr(instance, field, hodnota)

            # Další logika dle zákazníka (tryskání ...)
            zakaznik = zakazka.kamion_prijem.zakaznik
            if zakaznik.vse_tryskat:
                for instance in instances:
                    instance.tryskat = TryskaniChoice.SPINAVA

            # Přiřadíme cislo_bedny nově vzniklým instancím
            # Najdeme poslední bednu pro daného zákazníka:
            posledni_bedna = Bedna.objects.filter(
                zakazka__kamion_prijem__zakaznik=zakaznik
            ).order_by('-cislo_bedny').first()
            # Pokud neexistuje žádná bedna daného zákazníka, začneme s číslem dle číselné řady zákazníka
            nove_cislo_bedny = (posledni_bedna.cislo_bedny + 1) if posledni_bedna else zakaznik.ciselna_rada + 1
            for index, instance in enumerate(instances):
                instance.cislo_bedny = nove_cislo_bedny + index

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
            my_fieldsets = [
                (None, {
                    'fields': ['kamion_prijem', 'artikl', 'typ_hlavy', 'prumer', 'delka', 'predpis', 'priorita', 'popis', 'zinkovna', 'komplet', 'expedovano'],
                    }),
            ]
               
            # Pokud je zákazník Eurotec, přidej speciální pole pro zobrazení
            if obj.kamion_prijem.zakaznik.zkratka == 'EUR':
                my_fieldsets.append(                  
                    ('Pouze pro Eurotec:', {
                        'fields': ['prubeh', 'vrstva', 'povrch'],
                        'description': 'Pro Eurotec musí být vyplněno: Průběh zakázky, tloušťka vrstvy a povrchová úprava.',
                    }),  
                )

            # Pokud jsou pro stav_bedny, tryskat a rovnat stejné hodnoty pro všechny bedny v zakázce, přidej pole pro změnu stavu těchto položek pro všechny bedny
            if obj.bedny.exists() and obj.expedovano is False:
                stav_bedny = obj.bedny.first().stav_bedny
                tryskat = obj.bedny.first().tryskat
                rovnat = obj.bedny.first().rovnat
                fields = []
                if all(bedna.tryskat == tryskat for bedna in obj.bedny.all()):
                    fields += ['tryskat']
                if all(bedna.rovnat == rovnat for bedna in obj.bedny.all()):
                    fields += ['rovnat']
                if all(bedna.stav_bedny == stav_bedny for bedna in obj.bedny.all()):
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
                ('Příjem zakázek na sklad:', {
                    'fields': ['kamion_prijem', 'artikl', 'typ_hlavy', 'prumer', 'delka', 'predpis', 'priorita', 'popis', 'zinkovna',],
                    'description': 'Přijímání zakázek z kamiónu na sklad, pokud ještě není kamión v systému, vytvořte ho pomocí ikony ➕ u položky Kamión.',
                }), 
                ('Pouze pro Eurotec:', {
                    'fields': ['prubeh', 'vrstva', 'povrch'],
                    'classes': ['collapse'],
                    'description': 'Pro Eurotec musí být vyplněno: Průběh zakázky, Tloušťka vrstvy a Povrchová úprava.',
                }),  
                ('Celková hmotnost zakázky a počet beden pro rozpočtení hmotnosti na jednotlivé bedny:', {
                    'fields': ['celkova_hmotnost', 'pocet_beden',],
                    'classes': ['collapse'],
                    'description': 'Celková hmotnost zakázky z DL bude rozpočítána na jednotlivé bedny, případné zadané hmotnosti u beden budou přepsány. \
                        Počet beden zadejte pouze v případě, že jednotlivé bedny nebudete níže zadávat ručně.',
                }),                      
                ('Zadejte v případě, že jsou hodnoty těchto polí pro celou zakázku stejné: Tára, Materiál, Šarže mat./Charge, Sonder/Zusatz info, Lief., Fertigungs-auftrags Nr. nebo Poznámka HPM:', {
                    'fields': ['tara', 'material', 'sarze', 'dodatecne_info', 'dodavatel_materialu', 'vyrobni_zakazka', 'poznamka'],
                    'classes': ['collapse'],
                    'description': 'Pokud jsou hodnoty polí pro celou zakázku stejné, zadejte je sem. Jinak je nechte prázdné a vyplňte je u jednotlivých beden. Případné zadané hodnoty u beden zůstanou zachovány.',}),
            ]         
           
    def get_changelist(self, request, **kwargs):
        return CustomPaginationChangeList
    
    def changelist_view(self, request, extra_context=None):
        # když je aktivní filtr "skladem=Expedováno", zakáže se inline-editace
        if request.GET.get('skladem'):
            self.list_editable = ()      # žádné editovatelné sloupce
        else:
            self.list_editable = ('priorita',)
        return super().changelist_view(request, extra_context)    
    
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
class BednaAdmin(ImportExportHistoryModelAdmin):
    """
    Admin pro model Bedna:
    
    - Detail/inline: BednaAdminForm (omezuje stavové volby dle instance).
    - Seznam (change_list): list_editable pro stav_bedny, tryskat, rovnat a poznamka.
    - Pro každý řádek dropdown omezí na povolené volby podle stejné logiky.
    - Číslo bedny se generuje automaticky a je readonly
    """
    form = BednaAdminForm

    # Parametry pro zobrazení detailu v administraci
    fields = ('zakazka', 'cislo_bedny', 'hmotnost', 'tara', 'material', 'sarze', 'behalter_nr', 'dodatecne_info', 
              'dodavatel_materialu', 'vyrobni_zakazka', 'tryskat', 'rovnat', 'stav_bedny', 'poznamka')
    readonly_fields = ('cislo_bedny',)

    # Parametry pro zobrazení seznamu v administraci
    list_display = ('cislo_bedny', 'zakazka_link', 'kamion_prijem_link', 'kamion_vydej_link', 'get_prumer', 'get_delka',
                    'rovnat', 'tryskat', 'stav_bedny', 'get_typ_hlavy', 'hmotnost', 'tara', 'get_priorita', 'poznamka')
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
