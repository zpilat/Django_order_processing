from django.contrib import admin, messages
from django.db import models
from django.forms import TextInput
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.contrib.admin.views.main import ChangeList

from simple_history.admin import SimpleHistoryAdmin
from decimal import Decimal, ROUND_HALF_UP

from .models import Zakaznik, Kamion, Zakazka, Bedna
from .actions import expedice_zakazek
from .filters import ExpedovanaZakazkaFilter, StavBednyFilter
from .forms import ZakazkaAdminForm, BednaAdminForm
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
class ZakaznikAdmin(admin.ModelAdmin):
    """
    Správa zákazníků v administraci.
    """
    list_display = ('nazev', 'zkratka', 'adresa', 'mesto', 'stat', 'kontaktni_osoba', 'telefon', 'email', 'vse_tryskat', 'cisla_beden_auto',)
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
    fk_name = 'kamion_prijem_id'
    verbose_name = 'Zakázka - příjem'
    verbose_name_plural = 'Zakázky - příjem'
    extra = 0
    fields = ('artikl', 'kamion_vydej_id', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'popis', 'priorita', 'komplet','expedovano',)
    readonly_fields = ('komplet', 'expedovano',)
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
    }


class ZakazkaVydejInline(admin.TabularInline):
    """
    Inline pro správu zakázek v rámci kamionu pro výdej.
    """
    model = Zakazka
    fk_name = 'kamion_vydej_id'
    verbose_name = "Zakázka - výdej"
    verbose_name_plural = "Zakázky - výdej"
    extra = 0
    fields = ('artikl', 'kamion_prijem_id', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'popis', 'priorita',)
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
    }
 
    # def has_change_permission(self, request, obj=None):
    #     """
    #     Kontrola oprávnění pro změnu expedované zakázky.
    #     """
    #     base_permission = super().has_change_permission(request, obj)
    #     if not base_permission:
    #         return False
    #     if not request.user.has_perm('orders.change_expedovana_zakazka'):
    #         return False
    #     return True


@admin.register(Kamion)
class KamionAdmin(admin.ModelAdmin):
    """
    Správa kamionů v administraci.
    """
    list_display = ('get_kamion_str', 'zakaznik_id__nazev', 'datum', 'cislo_dl', 'prijem_vydej', 'misto_expedice',)
    list_filter = ('zakaznik_id__nazev', 'prijem_vydej',)
    list_display_links = ('get_kamion_str',)
    ordering = ('-id',)
    date_hierarchy = 'datum'
    list_per_page = 20

    history_list_display = ["id", "zakaznik_id", "datum"]
    history_search_fields = ["zakaznik_id__nazev", "datum"]
    history_list_filter = ["zakaznik_id", "datum"]
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

class BednaInline(admin.TabularInline):
    """
    Inline pro správu beden v rámci zakázky.
    """
    model = Bedna
    form = BednaAdminForm
    extra = 0
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={'size': '18'})},  # default
        models.DecimalField: {'widget': TextInput(attrs={'size': '6'})},
    }

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """
        Přizpůsobení widgetů pro pole v administraci.
        """
        if db_field.name == 'poznamka':
            kwargs['widget'] = TextInput(attrs={'size': '30'})  # Změna velikosti pole pro poznámku
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_exclude(self, request, obj=None):
        """
        Vrací seznam polí, která se mají vyloučit z formuláře Bedna při editaci.

        - Pokud není obj (tj. add_view), použije se základní exclude z super().  
        - Pokud obj existuje a zákazník zakázky není 'EUR' (Eurotec),
          přidají se do vyloučených polí dodavatel_materialu, vyrobni_zakazka a operator.
        """
        excluded = list(super().get_exclude(request, obj) or [])

        if obj and obj.kamion_prijem_id.zakaznik_id.zkratka != 'EUR':
            excluded += ['dodavatel_materialu', 'vyrobni_zakazka', 'operator']

        return excluded
    
    

@admin.register(Zakazka)
class ZakazkaAdmin(admin.ModelAdmin):
    """
    Správa zakázek v administraci.
    """
    inlines = [BednaInline]
    form = ZakazkaAdminForm
    actions = [expedice_zakazek,]
    readonly_fields = ('komplet', 'expedovano')
    list_display = ('artikl', 'kamion_prijem_link', 'kamion_vydej_link', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'popis', 'priorita', 'hmotnost_zakazky', 'komplet',)
    list_editable = ('priorita',)
    list_display_links = ('artikl',)
    search_fields = ('artikl',)
    search_help_text = "Hledat podle artiklu"
    list_filter = ('kamion_prijem_id__zakaznik_id', 'typ_hlavy', 'priorita', 'komplet', ExpedovanaZakazkaFilter,)
    ordering = ('-id',)
    date_hierarchy = 'kamion_prijem_id__datum'
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
    }

    history_list_display = ["id", "kamion_prijem_id", "kamion_vydej_id", "artikl", "prumer", "delka", "predpis", "typ_hlavy", "popis", "priorita", "komplet"]
    history_search_fields = ["kamion_prijem_id__zakaznik_id__nazev", "artikl", "prumer", "delka", "predpis", "typ_hlavy", "popis"]
    history_list_filter = ["kamion_prijem_id__zakaznik_id", "kamion_prijem_id__datum", "typ_hlavy"]
    history_list_per_page = 20

    class Media:
        js = ('admin/js/zakazky_hmotnost_sum.js',)

    @admin.display(description='Brutto hm.')
    def hmotnost_zakazky(self, obj):
        """
        Vypočítá celkovou brutto hmotnost beden v zakázce a umožní třídění podle hlavičky pole.
        """
        bedny = list(obj.bedny.all())
        netto = sum(bedna.hmotnost or 0 for bedna in bedny)
        brutto = netto + sum(bedna.tara or 0 for bedna in bedny)
        if brutto:
            return brutto.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
        return Decimal('0.0')

    @admin.display(description='Kamion příjem')
    def kamion_prijem_link(self, obj):
        """
        Vytvoří odkaz na detail kamionu příjmu, ke kterému zakázka patří a umožní třídění podle hlavičky pole.
        """
        if obj.kamion_prijem_id:
            return mark_safe(f'<a href="{obj.kamion_prijem_id.get_admin_url()}">{obj.kamion_prijem_id}</a>')
        return '-'
    kamion_prijem_link.admin_order_field = 'kamion_prijem_id__id'

    @admin.display(description='Kamion výdej')
    def kamion_vydej_link(self, obj):
        """
        Vytvoří odkaz na detail kamionu výdeje, ke kterému zakázka patří a umožní třídění podle hlavičky pole.
        """
        if obj.kamion_vydej_id:
            return mark_safe(f'<a href="{obj.kamion_vydej_id.get_admin_url()}">{obj.kamion_vydej_id}</a>')
        return '-'
    kamion_vydej_link.admin_order_field = 'kamion_vydej_id__id'

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

            # Další logika (tryskání, čísla beden atd.)
            zakaznik = zakazka.kamion_prijem_id.zakaznik_id
            if zakaznik.vse_tryskat:
                for instance in instances:
                    instance.tryskat = TryskaniChoice.SPINAVA

            if zakaznik.cisla_beden_auto:
                posledni_bedna = Bedna.objects.filter(zakazka_id__kamion_prijem_id__zakaznik_id=zakaznik).order_by('-cislo_bedny').first()
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
            my_fieldsets = [
                (None, {
                    'fields': ['kamion_prijem_id', 'kamion_vydej_id', 'artikl', 'typ_hlavy', 'prumer', 'delka', 'predpis', 'priorita', 'popis', 'zinkovna', 'komplet', 'expedovano'],
                    }),
                    ('Změna stavu všech beden v zakázce:', {
                        'fields': ['tryskat', 'rovnat', 'zmena_stavu'],
                        'description': 'Zde můžete změnit stav všech beden v zakázce najednou, ale bedny musí mít pro měněnou položku všechny stejnou hodnotu.',
                    }),                    
                ]
            # Pokud je zákazník Eurotec, přidej speciální pole pro zobrazení
            if obj.kamion_prijem_id.zakaznik_id.zkratka == 'EUR':
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
                    'fields': ['kamion_prijem_id', 'artikl', 'typ_hlavy', 'prumer', 'delka', 'predpis', 'priorita', 'popis', 'zinkovna',],
                    'description': 'Přijímání zakázek z kamiónu na sklad, pokud ještě není kamión v systému, vytvořte ho pomocí ikony ➕ u položky Kamión.',
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
           
    def get_changelist(self, request, **kwargs):
        return CustomPaginationChangeList    


@admin.register(Bedna)
class BednaAdmin(admin.ModelAdmin):
    """
    Admin pro model Bedna:
    
    - Detail/inline: BednaAdminForm (omezuje stavové volby dle instance).
    - Seznam (change_list): list_editable pro `stav_bedny`.
    - Pro každý řádek dropdown omezí na povolené volby podle stejné logiky.
    """
    form = BednaAdminForm
    list_display = ('cislo_bedny', 'zakazka_link', 'get_prumer', 'get_delka', 'rovnat', 'tryskat', 'stav_bedny', 'get_typ_hlavy', 'get_priorita', 'poznamka')
    list_editable = ('stav_bedny', 'rovnat', 'tryskat', 'poznamka',)
    list_display_links = ('cislo_bedny', )
    search_fields = ('cislo_bedny', 'zakazka_id__artikl', 'zakazka_id__delka',)
    search_help_text = "Hledat podle čísla bedny, artiklu nebo délky vrutu"
    list_filter = ('zakazka_id__kamion_prijem_id__zakaznik_id__nazev', StavBednyFilter, 'zakazka_id__typ_hlavy', 'zakazka_id__priorita', )
    ordering = ('id',)
    date_hierarchy = 'zakazka_id__kamion_prijem_id__datum'
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {'widget': TextInput(attrs={ 'size': '8'})},
    }

    history_list_display = ["id", "zakazka_id", "cislo_bedny", "stav_bedny", "typ_hlavy", "poznamka"]
    history_search_fields = ["zakazka_id__kamion_prijem_id__zakaznik_id__nazev", "cislo_bedny", "stav_bedny", "zakazka_id__typ_hlavy", "poznamka"]
    history_list_filter = ["zakazka_id__kamion_prijem_id__zakaznik_id__nazev", "zakazka_id__kamion_prijem_id__datum", "stav_bedny"]
    history_list_per_page = 20

    @admin.display(description='Zakázka')
    def zakazka_link(self, obj):
        """
        Vytvoří odkaz na detail zakázky, ke které bedna patří a umožní třídění podle hlavičky pole.
        """
        if obj.zakazka_id:
            return mark_safe(f'<a href="{obj.zakazka_id.get_admin_url()}">{obj.zakazka_id}</a>')
        return '-'
    zakazka_link.admin_order_field = 'zakazka_id__id'

    @admin.display(description='Typ hlavy')
    def get_typ_hlavy(self, obj):
        """
        Zobrazí typ hlavy zakázky a umožní třídění podle hlavičky pole.
        """
        return obj.zakazka_id.typ_hlavy
    get_typ_hlavy.admin_order_field = 'zakazka_id__typ_hlavy'

    @admin.display(description='Priorita')
    def get_priorita(self, obj):
        """
        Zobrazí prioritu zakázky a umožní třídění podle hlavičky pole.
        """
        return obj.zakazka_id.priorita
    get_priorita.admin_order_field = 'zakazka_id__priorita'

    @admin.display(description='Průměr')
    def get_prumer(self, obj):
        """
        Zobrazí průměr zakázky a umožní třídění podle hlavičky pole.
        """
        return obj.zakazka_id.prumer
    get_prumer.admin_order_field = 'zakazka_id__prumer'

    @admin.display(description='Délka')
    def get_delka(self, obj):
        """
        Zobrazí délku zakázky a umožní třídění podle hlavičky pole.
        """
        return obj.zakazka_id.delka
    get_delka.admin_order_field = 'zakazka_id__delka'
    
    def get_exclude(self, request, obj=None):
        """
        Vrací seznam polí, která se mají vyloučit z formuláře Bedna při editaci.

        - Pokud není obj (tj. add_view), použije se základní exclude z super().  
        - Pokud obj existuje a zákazník zakázky není 'EUR' (Eurotec),
          přidají se do vyloučených polí dodavatel_materialu, vyrobni_zakazka a operator.
        """
        excluded = list(super().get_exclude(request, obj) or [])

        if obj and obj.zakazka_id.kamion_prijem_id.zakaznik_id.zkratka != 'EUR':
            excluded += ['dodavatel_materialu', 'vyrobni_zakazka', 'operator']

        return excluded

    def save_model(self, request, obj, form, change):
        """
        Uložení modelu Bedna.
        Pokud je ve formuláři zadán stav bedny Expedováno, neuloží se a vytvoří zprávu.
        Pokud je stav bedny "K expedici", zkontroluje se, zda jsou všechny bedny v zakázce k expedici nebo expedovány,
        pokud ano, nastaví se atribut zakázky komplet na True.
        Pokud není stav bedny "K expedici", zkontroluje se, zda je jeho zakázka označena jako kompletní, pokud ano, nastaví se atribut zakázky komplet na False.
        """
        if obj.stav_bedny == StavBednyChoice.EXPEDOVANO:
            messages.error(
                request,
                "Nejde změnit stav bedny na expedováno ručně, pouze pomocí akce expedice zakázky!"
            )            
            return
        
        if obj.stav_bedny == StavBednyChoice.K_EXPEDICI:
            bedny = list(Bedna.objects.filter(zakazka_id=obj.zakazka_id).exclude(id=obj.id))
            zakazka_komplet = all(
                bedna.stav_bedny in {StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO}
                for bedna in bedny
            )
            obj.zakazka_id.komplet = zakazka_komplet
            obj.zakazka_id.save()

        else:
            if obj.zakazka_id.komplet:
                obj.zakazka_id.komplet = False
                obj.zakazka_id.save()

        super().save_model(request, obj, form, change)
    
    def get_changelist(self, request, **kwargs):
        """
        Vytvoří vlastní ChangeList s nastavením počtu položek na stránku.
        Pokud má uživatel oprávnění ke změně modelu Bedna, nastaví se menší počet položek na stránku.
        """
        return CustomPaginationChangeList
    
    def get_changelist_formset(self, request, **kwargs):
        """
        Vrátí vlastní FormSet pro change_list, kde každý řádek dostane
        pro `stav_bedny` jen ty volby podle BednaAdminForm.__init__ logiky.
        """
        FormSet = super().get_changelist_formset(request, **kwargs)
        choices = list(StavBednyChoice.choices)

        class RestrictedStateFormSet(FormSet):
            def __init__(self, *args, **fs_kwargs):
                super().__init__(*args, **fs_kwargs)
                for form in self.forms:
                    inst = getattr(form, 'instance', None)
                    if not inst or not inst.pk:
                        continue

                    try:
                        idx = next(i for i, (val, _) in enumerate(choices)
                                   if val == inst.stav_bedny)
                    except StopIteration:
                        continue

                    curr = inst.stav_bedny
                    if curr == StavBednyChoice.EXPEDOVANO:
                        allowed = [choices[idx]]
                    elif curr == StavBednyChoice.K_EXPEDICI:
                        allowed = [choices[idx - 1], choices[idx]]
                    elif curr == StavBednyChoice.ZKONTROLOVANO:
                        allowed = [choices[idx - 1], choices[idx]]
                        if inst.tryskat in (TryskaniChoice.CISTA, TryskaniChoice.OTRYSKANA) and \
                           inst.rovnat in (RovnaniChoice.ROVNA, RovnaniChoice.VYROVNANA):
                            allowed.append(choices[idx + 1])
                    elif curr == StavBednyChoice.PRIJATO:
                        allowed = [choices[idx], choices[idx + 1]]
                    else:
                        before = [choices[idx - 1]] if idx > 0 else []
                        after  = [choices[idx + 1]] if idx < len(choices) - 1 else []
                        allowed = before + [choices[idx]] + after

                    form.fields['stav_bedny'].choices = allowed
                    form.fields['stav_bedny'].initial = curr

        return RestrictedStateFormSet