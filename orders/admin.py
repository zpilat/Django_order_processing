from django.contrib import admin, messages
from django.db import models
from django.forms import TextInput
from django.utils.safestring import mark_safe

from simple_history.admin import SimpleHistoryAdmin
from decimal import Decimal, ROUND_HALF_UP

from .models import Zakaznik, Kamion, Zakazka, Bedna, TypHlavyChoice, StavBednyChoice
from .forms import ZakazkaForm, BednaChangeListForm

@admin.action(description="Expedovat zakázky")
def expedice_zakazek(modeladmin, request, queryset):
    """
    Expeduje vybrané zakázky.
    """
    for zakazka in queryset:
        zakazka.expedovano = True
        zakazka.save()
    messages.success(request, "Zakázky byly expedovány.")
    return queryset

class StavBednyFilter(admin.SimpleListFilter):
    """
    Filtrovat bedny podle stavu.
    """
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
        return queryset.filter(stav_bedny=value)
        

class ExpedovanaZakazkaFilter(admin.SimpleListFilter):
    """
    Filtrovat zakázky podle stavu expedice.
    """
    title = "Expedováno"
    parameter_name = "expedovano"

    def lookups(self, request, model_admin):
        return (
            ('ANO', 'ANO'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset.filter(expedovano=False)
        elif value == 'ANO':
            return queryset.filter(expedovano=True)
        return queryset


# Register your models here.
@admin.register(Zakaznik)
class ZakaznikAdmin(admin.ModelAdmin):
    """
    Správa zákazníků v administraci.
    """
    list_display = ('nazev', 'zkratka', 'adresa', 'mesto', 'stat', 'kontaktni_osoba', 'telefon', 'email')
    ordering = ('nazev',)
    list_per_page = 14

    history_list_display = ["id", "nazev", "zkratka",]
    history_search_fields = ["nazev", "zkratka",]    
    history_list_filter = ["nazev", "zkratka",]
    history_list_per_page = 14


@admin.register(Kamion)
class KamionAdmin(admin.ModelAdmin):
    """
    Správa kamionů v administraci.
    """
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
    actions = [expedice_zakazek,]
    list_display = ('id', 'kamion_id', 'artikl', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'popis', 'priorita', 'hmotnost_zakazky', 'komplet',)
    list_editable = ('priorita',)
    search_fields = ('artikl',)
    search_help_text = "Hledat podle artiklu"
    list_filter = ('kamion_id__zakaznik_id', 'typ_hlavy', 'priorita', 'komplet', ExpedovanaZakazkaFilter)
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

    class Media:
        css = {
            'all': ('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css',)
        }
        js = ('admin/js/zakazky_hmotnost_sum.js',)


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
            nove_bedny = []
            if len(instances) == 0 and pocet_beden:
                for i in range(pocet_beden):
                    bedna = Bedna(zakazka_id=zakazka)
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

            # Ulož všechny instance, pokud jsou to nove_bedny automaticky přidané
            if nove_bedny:
                for instance in instances:
                    instance.save()

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
    """
    Správa beden v administraci.
    """
    list_display = ('id', 'cislo_bedny', 'zakazka_id', 'rovnat', 'tryskat', 'stav_bedny', 'typ_hlavy', 'priorita', 'poznamka')
    list_editable = ('stav_bedny', 'poznamka',)
    search_fields = ('cislo_bedny', 'zakazka_id__artikl',)
    search_help_text = "Hledat podle čísla bedny nebo artiklu"
    readonly_fields = ('datum_expedice',)
    list_filter = ('zakazka_id__kamion_id__zakaznik_id__nazev', StavBednyFilter, 'zakazka_id__typ_hlavy', 'zakazka_id__priorita',)
    ordering = ('id',)
    date_hierarchy = 'zakazka_id__kamion_id__datum'
    list_per_page = 13
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
    }

    history_list_display = ["id", "zakazka_id", "cislo_bedny", "stav_bedny", "typ_hlavy", "poznamka"]
    history_search_fields = ["zakazka_id__kamion_id__zakaznik_id__nazev", "cislo_bedny", "stav_bedny", "zakazka_id__typ_hlavy", "poznamka"]
    history_list_filter = ["zakazka_id__kamion_id__zakaznik_id__nazev", "zakazka_id__kamion_id__datum", "stav_bedny"]
    history_list_per_page = 14

    def typ_hlavy(self, obj):
        """
        Zobrazí typ hlavy zakázky.
        """
        return obj.zakazka_id.typ_hlavy
    typ_hlavy.short_description = 'Typ hlavy'

    def priorita(self, obj):
        """
        Zobrazí prioritu zakázky.
        """
        return obj.zakazka_id.priorita
    priorita.short_description = 'Priorita'

    def get_changelist_form(self, request, **kwargs):
        """
        Formulář pro zobrazení v administraci beze stavu bedny expedováno.
        """
        return BednaChangeListForm

    def save_model(self, request, obj, form, change):
        """
        Uložení modelu Bedna. 
        Pokud je stav bedny Křivá nebo Vyrovnaná, nastaví se atribut rovnat na True.
        Pokud je stav bedny Tryskat nebo Otryskána, nastaví se atribut tryskat na True.
        Pokud je stav bedny "K expedici", zkontroluje se, zda jsou všechny bedny v zakázce k expedici nebo expedovány,
        pokud ano, nastaví se atribut zakázky komplet na True.
        """
        if obj.stav_bedny in {StavBednyChoice.KRIVA, StavBednyChoice.VYROVNANA}:
            obj.rovnat = True

        if obj.stav_bedny in {StavBednyChoice.TRYSKAT, StavBednyChoice.OTRYSKANA}:
            obj.tryskat = True

        if obj.stav_bedny == StavBednyChoice.K_EXPEDICI:
            bedny = list(Bedna.objects.filter(zakazka_id=obj.zakazka_id).exclude(id=obj.id))
            zakazka_komplet = all(
                bedna.stav_bedny in {StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO}
                for bedna in bedny
            )
            obj.zakazka_id.komplet = zakazka_komplet
            obj.zakazka_id.save()

        super().save_model(request, obj, form, change)