from django.contrib import admin
from .models import Zakaznik, Kamion, Zakazka, Bedna, TypHlavyChoice, StavBednyChoice

# Register your models here.
@admin.register(Zakaznik)
class ZakaznikAdmin(admin.ModelAdmin):
    list_display = ('nazev',)
    search_fields = ('nazev',)
    list_filter = ('nazev',)
    ordering = ('nazev',)
    list_per_page = 20

@admin.register(Kamion)
class KamionAdmin(admin.ModelAdmin):
    list_display = ('zakaznik_id__nazev', 'datum')
    search_fields = ('zakaznik_id__nazev',)
    list_filter = ('datum',)
    ordering = ('-datum',)
    list_per_page = 20

@admin.register(Zakazka)
class ZakazkaAdmin(admin.ModelAdmin):
    list_display = ('kamion_id', 'artikl', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'nazev', 'komplet')
    list_editable = ('komplet',)
    search_fields = ('kamion_id__zakaznik_id__nazev',)
    list_filter = ('kamion_id__zakaznik_id','kamion_id__datum', 'typ_hlavy')
    ordering = ('-kamion_id__id',)
    list_per_page = 20

@admin.register(Bedna)
class BednaAdmin(admin.ModelAdmin):
    list_display = ('id', 'zakazka_id__kamion_id__zakaznik_id__zkratka', 'zakazka_id', 'cislo_bedny', 'stav_bedny', 'zakazka_id__typ_hlavy', 'poznamka')
    list_editable = ('stav_bedny', 'poznamka')
    search_fields = ('zakazka_id__kamion_id__zakaznik_id__nazev',)
    list_filter = ('zakazka_id__kamion_id__zakaznik_id', 'zakazka_id__kamion_id__datum', 'stav_bedny')
    ordering = ('-zakazka_id__id',)
    list_per_page = 20