from django.contrib import admin
from .models import Zakaznik, Kamion, Zakazka, Bedna, TypHlavyChoice, StavBednyChoice
from simple_history.admin import SimpleHistoryAdmin
from django.db import models
from django.forms import TextInput

# Register your models here.
@admin.register(Zakaznik)
class ZakaznikAdmin(admin.ModelAdmin):
    list_display = ('nazev', 'zkratka', 'adresa', 'mesto', 'stat', 'kontaktni_osoba', 'telefon', 'email')
    search_fields = ('nazev',)
    list_filter = ('nazev',)
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
    search_fields = ('zakaznik_id__nazev',)
    list_filter = ('datum',)
    ordering = ('id',)
    date_hierarchy = 'datum'
    inlines = [ZakazkaInline]
    list_per_page = 14

    history_list_display = ["id", "zakaznik_id", "datum"]
    history_search_fields = ["zakaznik_id__nazev", "datum"]
    history_list_filter = ["zakaznik_id", "datum"]
    history_list_per_page = 14

class BednaInline(admin.TabularInline):
    model = Bedna
    extra = 3
    exclude = ('tryskat', 'rovnat', 'stav_bedny',)
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '20'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '10'})},
    }


@admin.register(Zakazka)
class ZakazkaAdmin(admin.ModelAdmin):
    list_display = ('id', 'kamion_id', 'artikl', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'popis', 'priorita', 'komplet', 'expedovano')
    list_editable = ('artikl', 'prumer', 'delka','popis', 'priorita')
    search_fields = ('kamion_id__zakaznik_id__nazev',)
    list_filter = ('kamion_id__zakaznik_id','kamion_id__datum', 'typ_hlavy', 'priorita', 'expedovano')
    ordering = ('id',)
    exclude = ('komplet', 'expedovano',)
    inlines = [BednaInline]
    list_per_page = 14

    history_list_display = ["id", "kamion_id", "artikl", "prumer", "delka", "predpis", "typ_hlavy", "popis", "priorita", "komplet"]
    history_search_fields = ["kamion_id__zakaznik_id__nazev", "artikl", "prumer", "delka", "predpis", "typ_hlavy", "popis"]
    history_list_filter = ["kamion_id__zakaznik_id", "kamion_id__datum", "typ_hlavy"]
    history_list_per_page = 14

@admin.register(Bedna)
class BednaAdmin(admin.ModelAdmin):
    list_display = ('id', 'cislo_bedny', 'zakazka_id', 'stav_bedny', 'zakazka_id__typ_hlavy', 'tryskat', 'rovnat', 'poznamka')
    list_editable = ('stav_bedny', 'tryskat', 'rovnat', 'poznamka')
    search_fields = ('cislo_bedny',)
    list_filter = ('zakazka_id__kamion_id__zakaznik_id', 'zakazka_id__kamion_id__datum', 'stav_bedny', 'zakazka_id__typ_hlavy')
    ordering = ('id',)
    list_per_page = 14

    history_list_display = ["id", "zakazka_id", "cislo_bedny", "stav_bedny", "zakazka_id__typ_hlavy", "poznamka"]
    history_search_fields = ["zakazka_id__kamion_id__zakaznik_id__nazev", "cislo_bedny", "stav_bedny", "zakazka_id__typ_hlavy", "poznamka"]
    history_list_filter = ["zakazka_id__kamion_id__zakaznik_id", "zakazka_id__kamion_id__datum", "stav_bedny"]
    history_list_per_page = 14