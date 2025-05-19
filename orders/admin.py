from django.contrib import admin, messages
from .models import Zakaznik, Kamion, Zakazka, Bedna, TypHlavyChoice, StavBednyChoice
from simple_history.admin import SimpleHistoryAdmin
from django.db import models
from django.forms import TextInput

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

class ZakazkaInline(admin.TabularInline):
    model = Zakazka
    extra = 1
    exclude = ('komplet', 'expedovano',)
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '20'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '10'})},
    }

@admin.register(Kamion)
class KamionAdmin(admin.ModelAdmin):
    list_display = ('id', 'zakaznik_id__nazev', 'datum', 'cislo_dl')
    list_filter = ('zakaznik_id__nazev',)
    ordering = ('-id',)
    date_hierarchy = 'datum'
    inlines = [ZakazkaInline]
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
    extra = 3
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
    actions = [zobrazit_celkovou_hmotnost_zakazek,]
    list_display = ('id', 'kamion_id', 'artikl', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'popis', 'priorita', 'hmotnost_celkem', 'komplet',)
    list_editable = ('artikl', 'prumer', 'delka','popis', 'priorita')
    search_fields = ('artikl',)
    search_help_text = "Hledat podle artiklu"
    list_filter = ('kamion_id__zakaznik_id', 'typ_hlavy', 'priorita', 'komplet', 'expedovano')
    ordering = ('id',)
    exclude = ('komplet', 'expedovano',)
    date_hierarchy = 'kamion_id__datum'
    fieldsets = (
        (None, {'fields': ['kamion_id', 'artikl', 'typ_hlavy', 'prumer', 'delka', 'predpis', 'priorita', 'popis']}), 
        ('Pouze pro Eurotec:', {
            'fields': ['prubeh', 'vrstva', 'povrch'],
            'classes': ['collapse'],
            }),                        
    )
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
    }
            
    inlines = [BednaInline]
    list_per_page = 14

    history_list_display = ["id", "kamion_id", "artikl", "prumer", "delka", "predpis", "typ_hlavy", "popis", "priorita", "komplet"]
    history_search_fields = ["kamion_id__zakaznik_id__nazev", "artikl", "prumer", "delka", "predpis", "typ_hlavy", "popis"]
    history_list_filter = ["kamion_id__zakaznik_id", "kamion_id__datum", "typ_hlavy"]
    history_list_per_page = 14

    def hmotnost_celkem(self, obj):
        """
        Vypočítá celkovou hmotnost beden v zakázce.
        """
        return sum(bedna.hmotnost for bedna in obj.bedny.all())

@admin.register(Bedna)
class BednaAdmin(admin.ModelAdmin):
    list_display = ('id', 'cislo_bedny', 'zakazka_id', 'stav_bedny', 'zakazka_id__typ_hlavy', 'tryskat', 'rovnat', 'poznamka')
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