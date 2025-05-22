from django.contrib import admin, messages
from django.db import models
from django.forms import TextInput
from django.utils.safestring import mark_safe

from simple_history.admin import SimpleHistoryAdmin
from decimal import Decimal, ROUND_HALF_UP

from .models import Zakaznik, Kamion, Zakazka, Bedna, TypHlavyChoice, StavBednyChoice
from .forms import ZakazkaForm

@admin.action(description="Zobrazit celkovou hmotnost beden")
def zobrazit_celkovou_hmotnost_zakazek(modeladmin, request, queryset):
    celkem = 0
    for zakazka in queryset:
        celkem += sum(bedna.hmotnost or 0 for bedna in zakazka.bedny.all())
    messages.info(request, f"Celková hmotnost beden ve vybraných zakázkách: {celkem} kg")


class StavBednyFilter(admin.SimpleListFilter):
    title = "Stav bedny"
    parameter_name = "stav_bedny_vlastni"

    def lookups(self, request, model_admin):
        # všechny hodnoty z choices (+ Nezpracováno)
        #result = [('NEZPRACOVANO', "Nezpracováno")]
        result = []
        for value, label in StavBednyChoice.choices:
            result.append((value, label))
        return result

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset.exclude(stav_bedny=StavBednyChoice.EXPEDOVANO)
        # elif value == 'NEZPRACOVANO':
        #     return queryset.filter(stav_bedny__in=[StavBednyChoice.PRIJATO, StavBednyChoice.NAVEZENO, StavBednyChoice.DO_ZPRACOVANI])
        else:
            return queryset.filter(stav_bedny=value)


# Register your models here.
@admin.register(Zakaznik)
class ZakaznikAdmin(admin.ModelAdmin):
    list_display = ('nazev', 'zkratka', 'adresa', 'mesto', 'stat', 'kontaktni_osoba', 'telefon', 'email')
    ordering = ('nazev',)
    list_per_page = 14

    history_list_display = ["id", "nazev", "zkratka",]
    history_search_fields = ["nazev", "zkratka",]    
    history_list_filter = ["nazev", "zkratka",]
    history_list_per_page = 14


@admin.register(Kamion)
class KamionAdmin(admin.ModelAdmin):
    list_display = ('id', 'zakaznik_id__nazev', 'datum', 'cislo_dl')
    list_filter = ('zakaznik_id__nazev',)
    ordering = ('-id',)
    date_hierarchy = 'datum'
    list_per_page = 14

    history_list_display = ["id", "zakaznik_id", "datum"]
    history_search_fields = ["zakaznik_id__nazev", "datum"]
    history_list_filter = ["zakaznik_id", "datum"]
    history_list_per_page = 14


class BednaInline(admin.TabularInline):
    """
    Inline pro správu beden v rámci zakázky.
    """
    model = Bedna
    extra = 0
    exclude = ('tryskat', 'rovnat', 'stav_bedny', 'datum_expedice',)
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '25'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
    }


@admin.register(Zakazka)
class ZakazkaAdmin(admin.ModelAdmin):
    """
    Správa zakázek v administraci.
    """
    inlines = [BednaInline]
    form = ZakazkaForm
    actions = [zobrazit_celkovou_hmotnost_zakazek,]
    list_display = ('id', 'kamion_id', 'artikl', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'popis', 'priorita', 'hmotnost_zakazky', 'komplet',)
    list_editable = ('artikl', 'prumer', 'delka','popis', 'priorita')
    search_fields = ('artikl',)
    search_help_text = "Hledat podle artiklu"
    list_filter = ('kamion_id__zakaznik_id', 'typ_hlavy', 'priorita', 'komplet', 'expedovano')
    ordering = ('id',)
    exclude = ('komplet', 'expedovano',)
    date_hierarchy = 'kamion_id__datum'
    list_per_page = 14
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
    }

    history_list_display = ["id", "kamion_id", "artikl", "prumer", "delka", "predpis", "typ_hlavy", "popis", "priorita", "komplet"]
    history_search_fields = ["kamion_id__zakaznik_id__nazev", "artikl", "prumer", "delka", "predpis", "typ_hlavy", "popis"]
    history_list_filter = ["kamion_id__zakaznik_id", "kamion_id__datum", "typ_hlavy"]
    history_list_per_page = 14

    @admin.display(description='Hm. zakázky')
    def hmotnost_zakazky(self, obj):
        """
        Vypočítá celkovou hmotnost beden v zakázce.
        """
        return sum(bedna.hmotnost or 0 for bedna in obj.bedny.all())
    
    def save_formset(self, request, form, formset, change):
        """
        Uložení formsetu pro bedny. Pokud je vyplněn počet beden, vytvoří se nové instance. 
        Pokud je vyplněna celková hmotnost, rozpočítá se na jednotlivé bedny.
        """
        if not change:
            instances = formset.save(commit=False)
            zakazka = form.instance
            celkova_hmotnost = form.cleaned_data.get('celkova_hmotnost')
            pocet_beden = form.cleaned_data.get('pocet_beden')
            data_ze_zakazky = {
                'tara': form.cleaned_data.get('tara'),
                'material': form.cleaned_data.get('material'),
                'sarze': form.cleaned_data.get('sarze'),
                'dodavatel_materialu': form.cleaned_data.get('dodavatel_materialu'),
                'vyrobni_zakazka': form.cleaned_data.get('vyrobni_zakazka'),
                'poznamka': form.cleaned_data.get('poznamka'),
            }

            # Pokud nejsou žádné bedny ručně zadané a je vyplněn počet beden, tak se vytvoří nové bedny 
            # a naplní se z daty ze zakázky a celkovou hmotností
            if len(instances) == 0 and pocet_beden:
                nove_bedny = []
                for i in range(pocet_beden):
                    bedna = Bedna(zakazka=zakazka)
                    nove_bedny.append(bedna)
                instances = nove_bedny

            # Tady dál pokračuje stejná logika bez ohledu na způsob vzniku beden:

            # Rozpočítání hmotnosti
            if celkova_hmotnost and len(instances) > 0:
                hmotnost_bedny = Decimal(celkova_hmotnost) / len(instances)
                hmotnost_bedny = hmotnost_bedny.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
                for instance in instances:
                    instance.hmotnost = hmotnost_bedny

            # Doplň prázdná pole ze zakázky (když už nebyla nastavena výše)
            for field, hodnota in data_ze_zakazky.items():
                if hodnota:
                    for instance in instances:
                        value = getattr(instance, field)
                        if value in (None, ''):
                            setattr(instance, field, hodnota)

            # Další logika (tryskání, čísla beden atd.)
            zakaznik = zakazka.kamion_id.zakaznik_id
            if zakaznik.vse_tryskat:
                for instance in instances:
                    instance.tryskat = True

            if zakaznik.cisla_beden_auto:
                posledni_bedna = Bedna.objects.filter(zakazka_id__kamion_id__zakaznik_id=zakaznik).order_by('-cislo_bedny').first()
                nove_cislo_bedny = (posledni_bedna.cislo_bedny + 1) if posledni_bedna else 1000001
                for index, instance in enumerate(instances):
                    instance.cislo_bedny = nove_cislo_bedny + index

            # Ulož všechny instance
            for instance in instances:
                instance.save()
            formset.save_m2m()
            formset.delete_existing()
        else: # editace existujících beden
            formset.save()

    def get_fieldsets(self, request, obj=None):
        """
        Vytváří pole pro zobrazení v administraci na základě toho, zda se jedná o editaci nebo přidání.
        """
        if obj:  # editace stávajícího záznamu
            my_fieldsets = [(None, {'fields': ['kamion_id', 'artikl', 'typ_hlavy', 'prumer', 'delka', 'predpis', 'priorita', 'popis', 'zinkovna',]}),]
            # Pokud je zákazník Eurotec, přidej speciální pole pro zobrazení
            if obj.kamion_id.zakaznik_id.zkratka == 'EUR':
                my_fieldsets.append(                  
                    ('Pouze pro Eurotec:', {
                        'fields': ['prubeh', 'vrstva', 'povrch'],
                        'description': 'Pro Eurotec musí být vyplněno: Průběh zakázky, tloušťka vrstvy a povrchová úprava.',
                    }),  
                )
            return my_fieldsets
        
        else:  # přidání nového záznamu
            return [
                ('Příjem zakázek na sklad:', {
                    'fields': ['kamion_id', 'artikl', 'typ_hlavy', 'prumer', 'delka', 'predpis', 'priorita', 'popis', 'zinkovna',],
                    'description': 'Přijímání zakázek z kamiónu na sklad, pokud ještě není kamión v systému, vytvořte ho pomocí ikony "+" u položky Kamión.',
                }), 
                ('Pouze pro Eurotec:', {
                    'fields': ['prubeh', 'vrstva', 'povrch'],
                    'classes': ['collapse'],
                    'description': 'Pro Eurotec musí být vyplněno: Průběh zakázky, tloušťka vrstvy a povrchová úprava.',
                }),  
                ('Celková hmotnost zakázky a počet beden pro rozpočtení hmotnosti na jednotlivé bedny:', {
                    'fields': ['celkova_hmotnost', 'pocet_beden',],
                    'classes': ['collapse'],
                    'description': 'Celková hmotnost zakázky z DL bude rozpočítána na jednotlivé bedny, případné zadané hmotnosti u beden budou přespány. \
                        Počet beden zadejte pouze v případě, že jednotlivé bedny nebudete níže zadávat ručně.',
                }),                      
                ('Zadejte v případě, že jsou hodnoty těchto polí pro celou zakázku stejné: Tára, Materiál, Šarže materiálu, Lief., Fertigungs-auftrags Nr. nebo Poznámka:', {
                    'fields': ['tara', 'material', 'sarze', 'dodavatel_materialu', 'vyrobni_zakazka', 'poznamka'],
                    'classes': ['collapse'],
                    'description': 'Pokud jsou hodnoty polí pro celou zakázku stejné, zadejte je sem. Jinak je nechte prázdné a vyplňte je u jednotlivých beden. Případné zadané hodnoty u beden zůstanou zachovány.',}),
            ]         


@admin.register(Bedna)
class BednaAdmin(admin.ModelAdmin):
    list_display = ('id', 'cislo_bedny', 'zakazka_id', 'tryskat', 'rovnat', 'stav_bedny', 'zakazka_id__typ_hlavy', 'poznamka')
    list_editable = ('stav_bedny', 'tryskat', 'rovnat', 'poznamka')
    search_fields = ('cislo_bedny', 'zakazka_id__artikl',)
    search_help_text = "Hledat podle čísla bedny nebo artiklu"
    readonly_fields = ('datum_expedice',)
    list_filter = ('zakazka_id__kamion_id__zakaznik_id', StavBednyFilter, 'zakazka_id__typ_hlavy')
    ordering = ('id',)
    date_hierarchy = 'zakazka_id__kamion_id__datum'
    list_per_page = 14
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
    }

    history_list_display = ["id", "zakazka_id", "cislo_bedny", "stav_bedny", "zakazka_id__typ_hlavy", "poznamka"]
    history_search_fields = ["zakazka_id__kamion_id__zakaznik_id__nazev", "cislo_bedny", "stav_bedny", "zakazka_id__typ_hlavy", "poznamka"]
    history_list_filter = ["zakazka_id__kamion_id__zakaznik_id", "zakazka_id__kamion_id__datum", "stav_bedny"]
    history_list_per_page = 14