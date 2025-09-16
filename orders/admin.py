from django.contrib import admin, messages
from django.contrib.auth.models import Permission
from django.db import models, transaction
from django.forms import TextInput, RadioSelect
from django.forms.models import BaseInlineFormSet
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.contrib.admin.views.main import ChangeList
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from django.urls import path, reverse
from django.shortcuts import redirect, render
from django.utils.html import format_html
from django.db.models import Count
from django.core.exceptions import ValidationError 

from simple_history.admin import SimpleHistoryAdmin
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
from django.core.files.storage import default_storage
import uuid
import pandas as pd
import re
from django import forms
from django.contrib.admin.helpers import ActionForm

from .models import Zakaznik, Kamion, Zakazka, Bedna, Predpis, Odberatel, TypHlavy, Cena, Pozice
from .actions import (
    expedice_zakazek_action, import_kamionu_action, tisk_karet_beden_action, tisk_karet_beden_zakazek_action,
    tisk_karet_beden_kamionu_action, tisk_dodaciho_listu_kamionu_action, vratit_zakazky_z_expedice_action, expedice_zakazek_kamion_action,
    tisk_karet_kontroly_kvality_action, tisk_karet_kontroly_kvality_zakazek_action, tisk_karet_kontroly_kvality_kamionu_action,
    tisk_proforma_faktury_kamionu_action, oznacit_k_navezeni_action, vratit_bedny_do_stavu_prijato_action, oznacit_navezeno_action,
    oznacit_do_zpracovani_action, oznacit_zakaleno_action, oznacit_zkontrolovano_action, oznacit_k_expedici_action, oznacit_rovna_action,
    oznacit_kriva_action, oznacit_rovna_se_action, oznacit_vyrovnana_action, oznacit_cista_action, oznacit_spinava_action, oznacit_otryskana_action,
   )
from .filters import (
    ExpedovanaZakazkaFilter, StavBednyFilter, KompletZakazkaFilter, AktivniPredpisFilter, SkupinaFilter, ZakaznikBednyFilter,
    ZakaznikZakazkyFilter, ZakaznikKamionuFilter, PrijemVydejFilter, TryskaniFilter, RovnaniFilter, PrioritaBednyFilter, PrioritaZakazkyFilter,
    OberflacheFilter, TypHlavyBednyFilter, TypHlavyZakazkyFilter, CelozavitBednyFilter, CelozavitZakazkyFilter, DelkaFilter, UvolnenoFilter,
    OdberatelFilter, ZakaznikPredpisFilter
)
from .forms import ZakazkaAdminForm, BednaAdminForm, ImportZakazekForm, ZakazkaInlineForm
from .choices import StavBednyChoice, RovnaniChoice, TryskaniChoice, PrioritaChoice, KamionChoice, stav_bedny_rozpracovanost, stav_bedny_skladem
from .utils import utilita_validate_excel_upload

import logging
logger = logging.getLogger('orders')

@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'codename', 'content_type')
    search_fields = ('name', 'codename')
    list_filter = ('content_type',)


@admin.register(Zakaznik)
class ZakaznikAdmin(SimpleHistoryAdmin):
    """
    Správa zákazníků v administraci.
    """
    list_display = ('nazev', 'zkraceny_nazev', 'zkratka', 'adresa', 'mesto', 'psc', 'stat', 'zkratka_statu', 'kontaktni_osoba', 'telefon',
                    'email', 'vse_tryskat', 'pouze_komplet', 'ciselna_rada',)
    ordering = ('nazev',)
    list_per_page = 20

    history_list_display = ["id", "nazev", "zkratka", "adresa", "mesto", "psc", "stat", "zkratka_statu", "kontaktni_osoba", "telefon", "email"]
    history_search_fields = ["nazev"]
    history_list_per_page = 20


class ZakazkaAutomatizovanyPrijemInline(admin.TabularInline):
    """
    Inline pro příjem zakázek v rámci kamionu na sklad včetně automatizovaného vytvoření beden a rozpočtení hmotnosti a množství.
    """
    model = Zakazka
    form = ZakazkaInlineForm
    fk_name = 'kamion_prijem'
    verbose_name = 'Zakázka - automatizovaný příjem'
    verbose_name_plural = 'Zakázky - automatizovaný příjem'
    extra = 5
    fields = ('artikl', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'celozavit', 'popis',
              'priorita', 'pocet_beden', 'celkova_hmotnost', 'celkove_mnozstvi', 'tara', 'material',)
    select_related = ('predpis',)
    show_change_link = True
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {
            'widget': TextInput(attrs={ 'size': '8'}),
            'localize': True
        }
    }

    def get_formset(self, request, obj=None, **kwargs):
        """
        Přizpůsobení formsetu pro inline.
        Pokud je objekt (kamion) pro příjem, předá se zakazník do formuláře.
        """
        zakaznik = None
        if obj and obj.prijem_vydej == 'P':
            zakaznik = obj.zakaznik  # obj je instance Kamion

        Form = self.form

        class CustomForm(Form):
            def __init__(self, *args, **kw):
                kw['zakaznik'] = zakaznik
                super().__init__(*args, **kw)

        kwargs['form'] = CustomForm
        return super().get_formset(request, obj, **kwargs)
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """
        Přizpůsobení widgetů pro pole v administraci.
        """
        if isinstance(db_field, models.ForeignKey):
            # Zruší zobrazení ikon pro ForeignKey pole v administraci, nepřidá RelatedFieldWidgetWrapper.
            formfield = self.formfield_for_foreignkey(db_field, request, **kwargs)
            # DŮLEŽITÉ: znovu obalit widget
            rel = db_field.remote_field
            formfield.widget = RelatedFieldWidgetWrapper(
                formfield.widget,
                rel,
                self.admin_site,
                can_add_related=False,
                can_change_related=False,
                can_delete_related=False,
                can_view_related=True,
            )
            return formfield

        return super().formfield_for_dbfield(db_field, request, **kwargs)


class ZakazkaKamionPrijemInline(admin.TabularInline):
    """
    Inline pro správu zakázek v rámci kamionu.
    """
    model = Zakazka
    form = ZakazkaAdminForm
    fk_name = 'kamion_prijem'
    verbose_name = 'Zakázka - příjem'
    verbose_name_plural = 'Zakázky - příjem'
    extra = 0
    fields = ('artikl', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'celozavit',
              'popis', 'prubeh', 'priorita', 'celkovy_pocet_beden', 'get_komplet',)
    readonly_fields = ('expedovano', 'get_komplet', 'celkovy_pocet_beden',)
    select_related = ('predpis',)
    show_change_link = True
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {
            'widget': TextInput(attrs={'size': '8'}),
            'localize': True
        },
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
            kwargs['widget'] = TextInput(attrs={'size': '12'})
            return super().formfield_for_dbfield(db_field, request, **kwargs)

        if isinstance(db_field, models.ForeignKey):
            # Zruší zobrazení ikon pro ForeignKey pole v administraci, nepřidá RelatedFieldWidgetWrapper.
            formfield = self.formfield_for_foreignkey(db_field, request, **kwargs)
            # DŮLEŽITÉ: znovu obalit widget
            rel = db_field.remote_field
            formfield.widget = RelatedFieldWidgetWrapper(
                formfield.widget,
                rel,
                self.admin_site,
                can_add_related=False,
                can_change_related=False,
                can_delete_related=False,
                can_view_related=True,
            )
            return formfield

        return super().formfield_for_dbfield(db_field, request, **kwargs)


class ZakazkaKamionVydejInline(admin.TabularInline):
    """
    Inline pro správu zakázek v rámci kamionu pro výdej.
    """
    model = Zakazka
    fk_name = 'kamion_vydej'
    verbose_name = "Zakázka - výdej"
    verbose_name_plural = "Zakázky - výdej"
    extra = 0
    fields = ('artikl', 'kamion_prijem', 'prumer', 'delka', 'predpis', 'typ_hlavy', 'celozavit',
              'popis', 'prubeh', 'priorita', 'celkovy_pocet_beden', 'odberatel',)
    readonly_fields = ('artikl', 'kamion_prijem', 'prumer', 'delka', 'predpis', 'typ_hlavy',
                       'celozavit', 'popis', 'prubeh', 'priorita', 'celkovy_pocet_beden', 'odberatel',)
    select_related = ('kamion_prijem', 'predpis',)
    show_change_link = True
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={'size': '30'})},
        models.DecimalField: {
            'widget': TextInput(attrs={'size': '8'}),
            'localize': True
        },
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
    # Použité akce
    actions = [import_kamionu_action, tisk_karet_beden_kamionu_action, tisk_karet_kontroly_kvality_kamionu_action, tisk_dodaciho_listu_kamionu_action,
               tisk_proforma_faktury_kamionu_action]
    # Parametry pro zobrazení detailu v administraci
    fields = ('zakaznik', 'datum', 'poradove_cislo', 'cislo_dl', 'prijem_vydej', 'odberatel',) # další úpravy v get_fields
    readonly_fields = ('prijem_vydej', 'poradove_cislo',) # další úpravy v get_readonly_fields
    # Parametry pro zobrazení seznamu v administraci
    list_display = ('get_kamion_str', 'get_zakaznik_zkraceny_nazev', 'get_datum', 'poradove_cislo', 'cislo_dl', 'prijem_vydej',
                    'odberatel', 'get_pocet_beden_skladem', 'get_celkova_hmotnost_netto', 'get_celkova_hmotnost_brutto',)
    list_select_related = ('zakaznik',)
    list_filter = (ZakaznikKamionuFilter, PrijemVydejFilter)
    list_display_links = ('get_kamion_str',)
    date_hierarchy = 'datum'
    list_per_page = 20
    # Parametry pro zobrazení historie v administraci
    history_list_display = ["id", "zakaznik", "datum"]
    history_search_fields = ["zakaznik__zkraceny_nazev", "datum"]
    history_list_filter = ["zakaznik", "datum"]
    history_list_per_page = 20

    class Media:
        js = ('orders/admin_actions_target_blank.js',)

    def get_inlines(self, request, obj):
        """
        Vrací inliny pro správu zakázek kamionu v závislosti na tom,
        zda se jedná o kamion pro příjem nebo výdej a jestli jde o přidání nebo editaci.
        """
        # Pokud se jedná o editaci kamionu výdej.
        if obj and obj.prijem_vydej == 'V':
            return [ZakazkaKamionVydejInline]
        # Pokud se jedná o editaci kamionu příjem.
        if obj and obj.prijem_vydej == 'P':        
            # Pokud se jedná o přidání zakázek a beden do prázdného kamionu příjem.
            if obj and not obj.zakazky_prijem.exists():
                return [ZakazkaAutomatizovanyPrijemInline]
            return [ZakazkaKamionPrijemInline]
        return []
    
    @admin.display(description='Zákazník', ordering='zakaznik__zkraceny_nazev', empty_value='-')
    def get_zakaznik_zkraceny_nazev(self, obj):
        """
        Zobrazí zkrácený název zákazníka a umožní třídění podle hlavičky pole.
        """
        return obj.zakaznik.zkraceny_nazev
    
    @admin.display(description='Datum', ordering='datum', empty_value='-')
    def get_datum(self, obj):
        """
        Zobrazí datum kamionu ve formátu DD.MM.RRRR a umožní třídění podle hlavičky pole.
        """
        return obj.datum.strftime('%d.%m.%Y')

    @admin.display(description='Kamion', ordering='id', empty_value='-')
    def get_kamion_str(self, obj):
        """
        Zobrazí stringový popis kamionu a umožní třídění podle hlavičky pole.
        """
        return f'{obj.poradove_cislo}. kamión {obj.get_prijem_vydej_display().lower()} {obj.datum.strftime("%Y")} {obj.zakaznik.zkratka}'

    @admin.display(description='Netto kg')
    def get_celkova_hmotnost_netto(self, obj):
        """
        Vrací celkovou hmotnost netto kamionu, pokud existují zakázky.
        Pokud neexistují žádné zakázky, vrátí 0.
        """
        if not obj.zakazky_prijem.exists() and not obj.zakazky_vydej.exists():
            return 0
        return Decimal(obj.celkova_hmotnost_netto).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    
    @admin.display(description='Brutto kg')
    def get_celkova_hmotnost_brutto(self, obj):
        """
        Vrací celkovou hmotnost brutto kamionu, pokud existují zakázky.
        Pokud neexistují žádné zakázky, vrátí 0.
        """
        if not obj.zakazky_prijem.exists() and not obj.zakazky_vydej.exists():
            return 0
        return Decimal(obj.celkova_hmotnost_brutto).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    
    @admin.display(description='Beden skladem')
    def get_pocet_beden_skladem(self, obj):
        """
        Vrací počet beden skladem v kamionu příjem.
        """
        return obj.pocet_beden_skladem


    def get_fields(self, request, obj=None):
        """
        Vrací seznam polí, která se mají zobrazit ve formuláře Kamion při přidání nového a při editaci.

        - Pokud není obj (tj. add_view), zruší se zobrazení pole `prijem_vydej` a `odberatel`.
        - Pokud je obj a kamion je pro příjem, zruší se zobrazení pole `odberatel`.
        """
        fields = list(super().get_fields(request, obj))

        if not obj:  # Pokud se jedná o přidání nového kamionu
            fields = [f for f in fields if f not in ('prijem_vydej', 'odberatel')]
        if obj and obj.prijem_vydej == KamionChoice.PRIJEM:
            fields = [f for f in fields if f != 'odberatel']

        return fields

    def get_readonly_fields(self, request, obj=None):
        """
        Vrací seznam readonly polí pro inline Kamion, pokud se jedná o editaci existujícího kamionu,
        přidá do stávajících readonly_fields pole 'zakaznik'. Pokud je kamion pro výdej, přidá se pole 'cislo_dl'.
        """
        rof = list(super().get_readonly_fields(request, obj)) or []
        if obj:
            rof.append('zakaznik')
        if obj and obj.prijem_vydej == KamionChoice.VYDEJ:
            rof.append('cislo_dl')
        return rof
    
    def get_actions(self, request):
        """
        Přizpůsobí dostupné akce v administraci podle filtru typu kamionu
        (příjem - vyexpedovaný, příjem - skladem, výdej).
        Odstraní akce, které nejsou relevantní pro daný typ kamionu.
        """
        actions = super().get_actions(request)

        if (request.GET.get('prijem_vydej') == 'V'):
            actions_to_remove = [
                'import_kamionu_action',
                'tisk_karet_beden_kamionu_action',
                'tisk_karet_kontroly_kvality_kamionu_action'
            ]
        elif (request.GET.get('prijem_vydej') == 'PS'):
            actions_to_remove = [
                'import_kamionu_action',                
                'tisk_dodaciho_listu_kamionu_action',
                'tisk_proforma_faktury_kamionu_action'
            ]
        elif (request.GET.get('prijem_vydej') == 'PV'):
            actions_to_remove = [
                'import_kamionu_action',
                'tisk_karet_beden_kamionu_action',
                'tisk_karet_kontroly_kvality_kamionu_action',
                'tisk_dodaciho_listu_kamionu_action',
                'tisk_proforma_faktury_kamionu_action'
            ]
        elif (request.GET.get('prijem_vydej') == 'PB'):
            actions_to_remove = [
                'tisk_karet_beden_kamionu_action',
                'tisk_karet_kontroly_kvality_kamionu_action',
                'tisk_dodaciho_listu_kamionu_action',
                'tisk_proforma_faktury_kamionu_action'
            ]
        else:
            actions_to_remove = []

        for action in actions_to_remove:
            if action in actions:
                del actions[action]
        
        return actions

    def get_action_choices(self, request, default_choices=models.BLANK_CHOICE_DASH):
        """Seskupení akcí kamionu do optgroup + formátování placeholderů.

        Skupiny:
        - Import / Příjem
        - Tisk karet
        - Doklady
        Ostatní (delete_selected) spadne do 'Ostatní'.
        """
        actions = self.get_actions(request)
        if not actions:
            return default_choices

        group_map = {
            'import_kamionu_action': 'Import / Příjem',
            'tisk_karet_beden_kamionu_action': 'Tisk karet',
            'tisk_karet_kontroly_kvality_kamionu_action': 'Tisk karet',
            'tisk_dodaciho_listu_kamionu_action': 'Tisk dokladů',
            'tisk_proforma_faktury_kamionu_action': 'Tisk dokladů',
        }
        order = ['Import / Příjem', 'Tisk karet', 'Tisk dokladů']
        grouped = {g: [] for g in order}

        for name, (_func, _action_name, desc) in actions.items():
            group = group_map.get(name, 'Ostatní')
            text = str(desc) if desc is not None else ''
            if '%(verbose_name' in text:
                try:
                    text = text % {
                        'verbose_name': self.model._meta.verbose_name,
                        'verbose_name_plural': self.model._meta.verbose_name_plural,
                    }
                except Exception:
                    pass
            grouped.setdefault(group, []).append((name, text))

        choices = [default_choices[0]]
        for g in order + [g for g in grouped.keys() if g not in order]:
            opts = grouped.get(g)
            if opts:
                choices.append((g, sorted(opts, key=lambda x: x[1].lower())))
        return choices

    def get_urls(self):
        """
        Přidá vlastní URL pro import zakázek do kamionu.
        """
        urls = super().get_urls()
        custom_urls = [
            path('import-zakazek/', self.admin_site.admin_view(self.import_view), name='import_zakazek_beden'),
        ]
        return custom_urls + urls
    
    def _render_import(self, request, form, kamion, preview, errors, warnings, tmp_token,
                       tmp_filename, title=None, status=200):
        context = {
            'form': form,
            'kamion': kamion,
            'preview': preview,
            'errors': errors,
            'warnings': warnings,
            'tmp_token': tmp_token,
            'tmp_filename': tmp_filename,
            'title': title or (f"Import zakázek pro kamion {kamion} z {kamion.datum.strftime('%d.%m.%Y')}" if kamion else "Import zakázek"),
        }
        return render(request, 'admin/import_zakazky.html', context, status=status)

    def import_view(self, request):
        """
        Zobrazí formulář pro import zakázek do kamionu a zpracuje nahraný soubor.
        Umožňuje importovat zakázky z Excel souboru a automaticky vytvoří bedny na základě dat v souboru.
        Zatím funguje pouze pro kamiony Eurotecu.
        """
        kamion_id = request.GET.get("kamion")
        kamion = Kamion.objects.get(pk=kamion_id) if kamion_id else None
        errors: list[str] = []
        warnings: list[str] = []
        preview: list[dict] = []

        if request.method == 'POST':
            logger.info(f"Uživatel {request.user} zahájil import zakázek pro kamion {kamion.poradove_cislo}.")
            form = ImportZakazekForm(request.POST, request.FILES)
            if form.is_valid():
                file = form.cleaned_data.get('file')
                tmp_token = request.POST.get('tmp_token')
                tmp_filename = None
                is_htmx = False
                # Validace pouze nového uploadu
                if file:
                    errors = utilita_validate_excel_upload(file)
                    if errors:
                        return self._render_import(
                            request, form, kamion, preview, errors, warnings, tmp_token, tmp_filename
                        )
                # Zpracování souboru    
                try:
                    # Vyber zdroj souboru – nový upload nebo dočasný soubor z náhledu
                    try:
                        tmp_map = request.session.get('import_tmp_files', {})
                    except Exception:
                        tmp_map = {}
                    saved_path = None
                    excel_stream = None

                    if request.POST.get('preview'):
                        if not file:
                            errors.append("Pro náhled musíte vybrat soubor.")
                            return self._render_import(
                                request, form, kamion, preview, errors, warnings, tmp_token, tmp_filename
                            )
                        token = str(uuid.uuid4())
                        saved_path = default_storage.save(f"tmp/imports/{token}.xlsx", file)
                        tmp_map[token] = {'path': saved_path, 'name': file.name}
                        try:
                            request.session['import_tmp_files'] = tmp_map
                            request.session.modified = True
                        except Exception:
                            pass
                        tmp_token = token
                        tmp_filename = file.name
                        excel_stream = default_storage.open(saved_path, 'rb')
                    else:
                        if file:
                            excel_stream = file
                            tmp_filename = getattr(file, 'name', None)
                        elif tmp_token and tmp_token in tmp_map:
                            saved_path = tmp_map[tmp_token]['path']
                            tmp_filename = tmp_map[tmp_token]['name']
                            excel_stream = default_storage.open(saved_path, 'rb')
                        else:
                            errors.append("Nebyl poskytnut žádný soubor k importu.")
                            return self._render_import(
                                request, form, kamion, preview, errors, warnings, tmp_token, tmp_filename
                            )

                    # Načte prvních 200 řádků (jinak zbytečně načítá celý soubor - přes 100000 prázdných řádků)
                    df = pd.read_excel(
                        excel_stream,
                        nrows=200,
                        engine="openpyxl",
                        dtype={
                            'Artikel- nummer': str,
                            'Vorgang+': str,
                        },
                    )
                    try:
                        # zavřít handle, pokud je z uloženého souboru
                        if saved_path and excel_stream:
                            excel_stream.close()
                    except Exception:
                        pass

                    # Najde první úplně prázdný řádek
                    first_empty_index = df[df.isnull().all(axis=1)].index.min()
                    if pd.notna(first_empty_index):
                        df = df.loc[:first_empty_index - 1]

                    # Odstraní prázdné sloupce
                    df.dropna(axis=1, how='all', inplace=True)

                    # Pro debug vytisknout názvy sloupců a první řádek dat
                    logger.debug(f"Import - názvy sloupců: {df.columns.tolist()}")
                    logger.debug(f"Import - první řádek dat: {df.iloc[0].tolist()}")

                    # Jednorázové mapování zdrojových názvů na interní názvy
                    column_mapping = {
                        'Unnamed: 6': 'typ_hlavy',
                        'Unnamed: 7': 'rozmer',                        
                        'Abhol- datum': 'datum',
                        'Material- charge': 'sarze',
                        'Artikel- nummer': 'artikl',
                        'Be-schich-tung': 'vrstva',
                        'Bezeichnung': 'popis',
                        'n. Zg. / \nas drg': 'predpis',
                        'Material': 'material',
                        'Ober- fläche': 'povrch',
                        'Gewicht in kg': 'hmotnost',
                        'Tara kg': 'tara',
                        'Behälter-Nr.:': 'behalter_nr',
                        'Sonder / Zusatzinfo': 'dodatecne_info',
                        'Lief.': 'dodavatel_materialu',
                        'Fertigungs- auftrags Nr.': 'vyrobni_zakazka',
                        'Vorgang+': 'prubeh',
                        'Menge       ': 'mnozstvi',       
                        'Gew.': 'hmotnost_ks',              
                    }
                    df.rename(columns=column_mapping, inplace=True)              

                    # Povinné zdrojové sloupce dle specifikace
                    required_src = ['sarze', 'popis', 'rozmer', 'artikl', 'predpis', 'typ_hlavy', 'material', 'behalter_nr',
                                    'hmotnost', 'tara', 'hmotnost_ks', 'datum', 'dodatecne_info'
                    ]
                    missing = [c for c in required_src if c not in df.columns]
                    if missing:
                        errors.append(f"Chyba: V Excelu chybí povinné sloupce: {', '.join(missing)}")
                        preview = []
                        return self._render_import(
                            request, form, kamion, preview, errors, warnings, tmp_token, tmp_filename
                        )

                    # Zkontroluje datumy ve sloupci 'datum' – při různosti pouze varování
                    if 'datum' in df.columns and not df['datum'].isnull().all():
                        unique_dates = df['datum'].dropna().unique()
                        if len(unique_dates) > 1:
                            warnings.append("Upozornění: Sloupec 'datum' obsahuje různé hodnoty. Import pokračuje.")
                        if len(unique_dates) == 1 and pd.notna(unique_dates[0]):
                            excel_date = pd.to_datetime(unique_dates[0]).date()
                            if excel_date != kamion.datum:
                                warnings.append(
                                    f"Upozornění: Datum v souboru ({excel_date.strftime('%d.%m.%Y')}) "
                                    f"neodpovídá datumu kamionu ({kamion.datum.strftime('%d.%m.%Y')}). Import pokračuje."
                                )      

                    # Přidání prumer a delka
                    def rozdel_rozmer(row):
                        try:
                            text = str(row.get('rozmer', '') or '')
                            text = text.replace('×', 'x').replace('X', 'x')
                            prumer_str, delka_str = text.replace(',', '.').split('x')
                            return Decimal(prumer_str.strip()), Decimal(delka_str.strip())
                        except Exception:
                            messages.info(request, "Chyba: Sloupec 'Abmessung' musí obsahovat hodnoty ve formátu 'prumer x delka'.")
                            errors.append("Chyba: Sloupec 'Abmessung' musí obsahovat hodnoty ve formátu 'prumer x delka'.")
                            return None, None

                    df[['prumer', 'delka']] = df.apply(
                        lambda row: pd.Series(rozdel_rozmer(row)), axis=1
                    )

                    # Vytvoří se nový sloupec 'priorita', pokud je ve sloupci dodatecne_info obsaženo 'eilig', vyplní se hodnota 'P1' jako priorita
                    def priorita(row):
                        if pd.notna(row['dodatecne_info']) and 'eilig' in row['dodatecne_info'].lower():
                            return PrioritaChoice.VYSOKA
                        return PrioritaChoice.NIZKA
                    df['priorita'] = df.apply(priorita, axis=1)

                    # Vytvoří se nový sloupec 'celozavit', pokud je ve sloupci 'popis' obsaženo 'konstrux', vyplní se hodnota True, jinak False
                    def celozavit(row):
                        if pd.notna(row['popis']) and 'konstrux' in row['popis'].lower():
                            return True
                        return False
                    df['celozavit'] = df.apply(celozavit, axis=1)        

                    # Vytvoří se nový sloupec 'odfosfatovat', pokud je ve sloupci 'popis' obsaženo 'muss entphosphatiert werden',
                    # vyplní se hodnota True, jinak False
                    def odfosfatovat(row):
                        if pd.notna(row['dodatecne_info']) and 'muss entphosphatiert werden' in row['dodatecne_info'].lower():
                            return True
                        return False
                    df['odfosfatovat'] = df.apply(odfosfatovat, axis=1)

                    # Vypočítá množství v bedně dle zadané celkové hmotnosti a hmotnosti na ks (hmotnost / hmotnost_ks)
                    def vypocet_mnozstvi_v_bedně(row):
                        try:
                            hmotnost = row.get('hmotnost')
                            hmotnost_ks = row.get('hmotnost_ks')
                            if pd.isna(hmotnost) or pd.isna(hmotnost_ks) or hmotnost_ks == 0:
                                return 1
                            mnozstvi = int(hmotnost / hmotnost_ks)
                            return max(mnozstvi, 1)
                        except Exception:
                            return 1                        
                    df['mnozstvi'] = df.apply(vypocet_mnozstvi_v_bedně, axis=1)

                    # Odstranění nepotřebných sloupců
                    df.drop(columns=[
                        'Unnamed: 0', 'rozmer', 'Gew + Tara', 'VPE', 'Box', 'Anzahl Boxen pro Behälter',
                        'Härterei', 'Prod. Datum', 'hmotnost_ks', 'von Härterei \nnach Galvanik', 'Galvanik',
                        'vom Galvanik nach Eurotec',
                    ], inplace=True, errors='ignore')

                    # Setřídění podle sloupce prumer, delka, predpis, artikl, sarze, behalter_nr
                    df.sort_values(by=['prumer', 'delka', 'predpis', 'artikl', 'sarze', 'behalter_nr'], inplace=True)
                    logger.info(f"Uživatel {request.user} úspěšně načetl data z Excel souboru pro import zakázek.")

                    # Připravit náhled (prvních 50 řádků)
                    preview = [
                        {
                            'artikl': r.get('artikl'),
                            'prumer': r.get('prumer'),
                            'delka': r.get('delka'),
                            'predpis': int(r.get('predpis')),
                            'typ_hlavy': r.get('typ_hlavy'),
                            'popis': r.get('popis'),
                            'hmotnost': r.get('hmotnost'),
                            'mnozstvi': r.get('mnozstvi'),
                            'tara': r.get('tara'),
                        }
                        for _, r in df.head(50).iterrows()
                    ]

                    # Pokud jsou chyby po parsování, zobrazit náhled a chyby (bez uložení)
                    if errors:
                        if is_htmx and request.POST.get('preview'):
                            return render(request, 'admin/_import_zakazky_preview.html', {
                                'preview': preview,
                                'errors': errors,
                                'warnings': warnings,
                                'tmp_token': tmp_token,
                                'tmp_filename': tmp_filename,
                            })
                        return self._render_import(
                            request, form, kamion, preview, errors, warnings, tmp_token, tmp_filename
                        )

                    # Režim náhledu – bez uložení
                    if request.POST.get('preview'):
                        try:
                            messages.info(request, "Zobrazen náhled importu. Data nebyla uložena.")
                        except Exception:
                            pass
                        return self._render_import(
                            request, form, kamion, preview, errors, warnings, tmp_token, tmp_filename
                        )

                    # Uložení záznamů
                    with transaction.atomic():
                        zakazky_cache = {}
                        for _, row in df.iterrows():

                            # Kontrola zda všechna povinná pole jsou vyplněna
                            required_fields = ['sarze', 'popis', 'prumer', 'delka', 'artikl', 'predpis', 'typ_hlavy', 'material',
                                               'behalter_nr', 'hmotnost', 'tara', 'mnozstvi', 'datum',
                            ]
                            for field in required_fields:
                                if pd.isna(row[field]):
                                    logger.error(f"Chyba: Povinné pole '{field}' nesmí být prázdné.")
                                    raise ValueError(f"Chyba: Povinné pole '{field}' nesmí být prázdné.")

                            artikl = row['artikl']

                            if artikl not in zakazky_cache:
                                # Získání a formátování průměru pro sestavení názvu předpisu
                                prumer = row.get('prumer')
                                # Formátování průměru: '10.0' → '10', '7.5' → '7,5'
                                if prumer == prumer.to_integral():
                                    retezec_prumer = str(int(prumer))
                                else:
                                    retezec_prumer = str(prumer).replace('.', ',')

                                try:
                                    cislo_predpisu = int(row['predpis'])
                                    nazev_predpis=f"{cislo_predpisu:05d}_Ø{retezec_prumer}"
                                except (ValueError, TypeError):
                                    nazev_predpis = f"{row['predpis']}_Ø{retezec_prumer}"

                                # Získání předpisu, pokud existuje
                                predpis = Predpis.objects.filter(nazev=nazev_predpis, aktivni=True).first()
                                # Fallback: použít/nebo vytvořit 'Neznámý předpis' pro zákazníka Eurotec                                
                                if not predpis:
                                    eurotec = Zakaznik.objects.filter(zkratka='EUR').only('id').first()
                                    predpis, created = Predpis.objects.get_or_create(
                                        nazev='Neznámý předpis',
                                        zakaznik=eurotec,
                                        defaults={'aktivni': True},
                                    )
                                    if not created and not predpis.aktivni:
                                        predpis.aktivni = True
                                        predpis.save()
                                    warnings.append(f"Varování: Předpis „{nazev_predpis}“ neexistuje. Použit předpis 'Neznámý předpis'.")
                                    logger.warning(f"Varování při importu: Předpis „{nazev_predpis}“ neexistuje. Použit předpis 'Neznámý předpis'.")
                                
                                # Získání typu hlavy, pokud existuje
                                typ_hlavy_excel = row.get('typ_hlavy', None)
                                if pd.isna(typ_hlavy_excel) or not str(typ_hlavy_excel).strip():
                                    logger.error("Chyba: Sloupec s typem hlavy nesmí být prázdný.")
                                    raise ValueError("Chyba: Sloupec s typem hlavy nesmí být prázdný.")
                                typ_hlavy_excel = str(typ_hlavy_excel).strip()
                                typ_hlavy_qs = TypHlavy.objects.filter(nazev=typ_hlavy_excel)
                                typ_hlavy = typ_hlavy_qs.first() if typ_hlavy_qs.exists() else None
                                if not typ_hlavy:
                                    logger.error(f"Typ hlavy „{typ_hlavy_excel}“ neexistuje.")
                                    raise ValueError(f"Typ hlavy „{typ_hlavy_excel}“ neexistuje.")                            

                                zakazka = Zakazka.objects.create(
                                    kamion_prijem=kamion,
                                    artikl=artikl,
                                    prumer=prumer,
                                    delka=row.get('delka'),
                                    predpis=predpis,
                                    typ_hlavy=typ_hlavy,
                                    celozavit=row.get('celozavit', False),
                                    priorita=row.get('priorita', PrioritaChoice.NIZKA),
                                    popis=row.get('popis'),
                                    vrstva=row.get('vrstva'),
                                    povrch=row.get('povrch'),
                                    prubeh=row.get('prubeh'),
                                )
                                zakazky_cache[artikl] = zakazka

                            Bedna.objects.create(
                                zakazka=zakazky_cache[artikl],
                                hmotnost=row.get('hmotnost'),
                                tara=row.get('tara'),
                                mnozstvi=row.get('mnozstvi', 1),
                                material=row.get('material'),
                                sarze=row.get('sarze'),
                                behalter_nr=row.get('behalter_nr'),
                                dodatecne_info=row.get('dodatecne_info'),
                                dodavatel_materialu=row.get('dodavatel_materialu'),
                                vyrobni_zakazka=row.get('vyrobni_zakazka'),
                                odfosfatovat=row.get('odfosfatovat'),
                            )

                    logger.info(f"Uživatel {request.user} úspěšně uložil zakázky a bedny pro kamion {kamion.poradove_cislo}.")
                    # pokud se importovalo z dočasného souboru, uklidit
                    if not request.POST.get('preview') and 'tmp_token' in locals() and tmp_token:
                        try:
                            tmp_map = request.session.get('import_tmp_files', {})
                        except Exception:
                            tmp_map = {}
                        info = tmp_map.pop(tmp_token, None)
                        if info and info.get('path'):
                            try:
                                default_storage.delete(info['path'])
                            except Exception:
                                pass
                        try:
                            request.session['import_tmp_files'] = tmp_map
                            request.session.modified = True
                        except Exception:
                            pass
                    for w in warnings:
                        try:
                            messages.warning(request, w)
                        except Exception:
                            pass
                    try:
                        self.message_user(request, "Import proběhl úspěšně.", messages.SUCCESS)
                    except Exception:
                        pass
                    return redirect("..")

                except Exception as e:
                    logger.error(f"Chyba při importu zakázek pro kamion {kamion.poradove_cislo}: {e}")
                    try:
                        self.message_user(request, f"Chyba při importu: {e}", messages.ERROR)
                    except Exception:
                        pass
                    return redirect("..")
        else:
            logger.info(f"Uživatel {request.user} otevřel formulář pro import zakázek do kamionu {kamion}.")
            form = ImportZakazekForm()
        return self._render_import(
            request, form, kamion, preview, errors, warnings, None, None
        )
    
    def save_formset(self, request, form, formset: BaseInlineFormSet, change):
        """
        Uloží inline formuláře pro zakázky kamionu a vytvoří bedny na základě zadaných dat.
        """
        # Při úpravách stávajícího kamionu, který už obsahuje zakázky, se pouze uloží všechny změny do databáze bez vytvoření beden.
        if change and formset.instance.zakazky_prijem.exists():
            formset.save()
        # Při vytvoření nového kamionu nebo při přidání zakázek do prázdného kamionu se zpracují inline formuláře pro zakázky a vytvoří se případně automaticky bedny        
        else:
            # Uloží se inline formuláře bez okamžitého zápisu do DB
            zakazky = formset.save(commit=False)

            for inline_form, zakazka in zip(formset.forms, zakazky):
                # Uloží se zakázka a připojí se k právě vytvořenému kamionu                
                zakazka.kamion_prijem = form.instance
                zakazka.save()

                # Získání dodatečných hodnot z vlastního formuláře zakázky
                celkova_hmotnost = inline_form.cleaned_data.get("celkova_hmotnost")
                celkove_mnozstvi = inline_form.cleaned_data.get("celkove_mnozstvi")
                pocet_beden = inline_form.cleaned_data.get("pocet_beden")
                tara = inline_form.cleaned_data.get("tara", 65.0)  # výchozí hodnota 65 kg
                material = inline_form.cleaned_data.get("material", '')

                # Rozpočítání hmotnosti a množství a vytvoření beden zakázky, pokud je zadán počet beden a celková hmotnost
                if pocet_beden:
                    # Pokud není zadána celková hmotnost, dá se error, protože hmotnost bedny je povinná
                    if not celkova_hmotnost:
                        formset._non_form_errors = formset.error_class(
                            ["Pokud je zadán počet beden, musí být zadána i celková hmotnost."]
                        )
                        raise ValidationError(
                            "Pokud je zadán počet beden, musí být zadána i celková hmotnost."
                        )
                    if celkova_hmotnost <= 0:
                        formset._non_form_errors = formset.error_class(
                            ["Celková hmotnost musí být větší než 0."]
                        )
                        raise ValidationError("Celková hmotnost musí být větší než 0.")
                    # Pokud není zadáno správné množství, dá se warning a mnozstvi bedny se nastaví se na 1
                    if not celkove_mnozstvi or celkove_mnozstvi <= 0:
                        try:
                            messages.warning(
                                request,
                                f"U zakázky {zakazka} nebylo zadáno množství nebo bylo menší než 1. Nastavuje se množství v bedně na 1ks.",
                            )
                            logger.warning(
                                f"U zakázky {zakazka} nebylo zadáno množství nebo bylo menší než 1. Nastavuje se množství v bedně na 1ks."
                            )
                        except Exception:
                            pass
                        mnozstvi_bedny = 1
                    # Pokud je zadáno správné celkové množství, rozdělí se do jednotlivých beden, jedná se o orientační hodnotu
                    else:
                        mnozstvi_bedny = max(int(celkove_mnozstvi) // int(pocet_beden), 1)

                    # Rozpočítání hmotnosti, pro poslední bednu se použije zbytek hmotnosti po rozpočítání a zaokrouhlení
                    hmotnost_bedny = Decimal(celkova_hmotnost) / int(pocet_beden)
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
                            mnozstvi=mnozstvi_bedny,
                            # cislo_bedny se dopočítá v metodě save() modelu Bedna
                        )


class BednaInline(admin.TabularInline):
    """
    Inline pro správu beden v rámci zakázky.
    """
    model = Bedna
    form = BednaAdminForm
    extra = 0
    # další úprava zobrazovaných polí podle různých podmínek je v get_fields
    fields = ('cislo_bedny', 'behalter_nr', 'hmotnost', 'tara', 'mnozstvi', 'material', 'sarze', 'dodatecne_info', 'dodavatel_materialu',
              'vyrobni_zakazka', 'odfosfatovat', 'tryskat', 'rovnat', 'stav_bedny', 'pozice', 'poznamka_k_navezeni', 'poznamka',)
    readonly_fields = ('cislo_bedny',)
    show_change_link = True
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={'size': '12'})},  # default
        models.DecimalField: {
            'widget': TextInput(attrs={'size': '5'}),
            'localize': True
        },
        models.IntegerField: {'widget': TextInput(attrs={'size': '5'})},
    }

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """
        Přizpůsobení widgetů pro pole v administraci.
        """
        if db_field.name == 'dodatecne_info':
            kwargs['widget'] = TextInput(attrs={
                'size': '30',
                'style': 'font-size: 10px;',
                })  # Změna velikosti pole a velikosti písma pro dodatečné info
        elif db_field.name == 'poznamka':
            kwargs['widget'] = TextInput(attrs={
                'size': '20',
                'style': 'font-size: 10px;'
                }) # Změna velikosti pole pro poznámku HPM
        elif db_field.name == 'dodavatel_materialu':
            kwargs['widget'] = TextInput(attrs={'size': '4'})  # Změna velikosti pole pro dodavatele materiálu

        if isinstance(db_field, models.ForeignKey):
            # Zruší zobrazení ikon pro ForeignKey pole v administraci, nepřidá RelatedFieldWidgetWrapper.
            formfield = self.formfield_for_foreignkey(db_field, request, **kwargs)
            # DŮLEŽITÉ: znovu obalit widget
            rel = db_field.remote_field
            formfield.widget = RelatedFieldWidgetWrapper(
                formfield.widget,
                rel,
                self.admin_site,
                can_add_related=False,
                can_change_related=False,
                can_delete_related=False,
                can_view_related=True,
            )
            return formfield
                    
        return super().formfield_for_dbfield(db_field, request, **kwargs)
    
    def get_fields(self, request, obj=None):
        """
        Vrací seznam polí, která se mají zobrazit ve formuláři Bednainline.

        - Pokud není obj (tj. add_view), vyloučí se pole `cislo_bedny`, protože se generuje automaticky.
        - Pokud je obj (tj. edit_view) a zákazník kamionu příjmu je 'ROT', vyloučí se pole `dodatecne_info`,
            `dodavatel_materialu` a `vyrobni_zakazka`.
        - Pokud je obj (tj. edit_view) a zákazník kamionu příjmu je 'SSH', 'SWG', 'HPM', 'FIS',
            vyloučí se pole `behalter_nr`, `dodatecne_info`, `dodavatel_materialu` a `vyrobni_zakazka`.
        """
        fields = list(super().get_fields(request, obj))
        exclude_fields = []
        # Pokud se jedná o editaci existující bedny
        if obj:
            # Vyloučení polí dle zákazníka
            if obj.kamion_prijem.zakaznik.zkratka == 'ROT':
                exclude_fields = ['dodatecne_info', 'dodavatel_materialu', 'vyrobni_zakazka']
            elif obj.kamion_prijem.zakaznik.zkratka in ('SSH', 'SWG', 'HPM', 'FIS'):
                exclude_fields = ['behalter_nr', 'dodatecne_info', 'dodavatel_materialu', 'vyrobni_zakazka']
        # Při přidání nové bedny se vyloučí pole `cislo_bedny`, protože se generuje automaticky.
        else:
            exclude_fields = ['cislo_bedny']

        fields = [f for f in fields if f not in exclude_fields]
        return fields

    def has_change_permission(self, request, obj=None):
        """
        Přizpůsobení oprávnění pro změnu inline Bedna.
        - Pokud je zakázka expedována a uživatel nemá oprávnění, zakáže se možnost změny.
        """
        if obj and obj.expedovano and not request.user.has_perm('orders.change_expedovana_bedna'):
            return False
        return super().has_change_permission(request, obj)
    
    def get_formset(self, request, obj=None, **kwargs):
        """
        Přizpůsobení formsetu pro inline Bedna.
        - Pokud je bedna pozastavena a uživatel nemá oprávnění, zakáže se možnost změny polí.
        """
        Formset = super().get_formset(request, obj, **kwargs)

        class CustomFormset(Formset):
            def __init__(self_inner, *args, **kwargs):
                super().__init__(*args, **kwargs)
                for form in self_inner.forms:
                    bedna = form.instance
                    if bedna.pozastaveno and not request.user.has_perm('orders.change_pozastavena_bedna'):
                        for field in form.fields:
                            form.fields[field].disabled = True

        return CustomFormset
    

@admin.register(Zakazka)
class ZakazkaAdmin(SimpleHistoryAdmin):
    """
    Správa zakázek v administraci.
    """
    # Použité inline, formuláře a akce
    inlines = [BednaInline]
    form = ZakazkaAdminForm
    actions = [tisk_karet_beden_zakazek_action, tisk_karet_kontroly_kvality_zakazek_action, expedice_zakazek_action,
               vratit_zakazky_z_expedice_action, expedice_zakazek_kamion_action]

    # Parametry pro zobrazení detailu v administraci
    readonly_fields = ('expedovano', 'get_komplet')
    
    # Parametry pro zobrazení seznamu v administraci
    list_display = ('artikl', 'get_datum', 'kamion_prijem_link', 'kamion_vydej_link', 'get_prumer', 'get_delka_int', 'predpis_link',
                    'typ_hlavy_link', 'get_skupina', 'get_celozavit', 'zkraceny_popis', 'priorita', 'hmotnost_zakazky_k_expedici_brutto',
                    'pocet_beden_k_expedici', 'celkovy_pocet_beden', 'get_komplet',)
    list_display_links = ('artikl',)
    # list_editable = nastavováno dynamicky v get_list_editable
    list_select_related = ("kamion_prijem", "kamion_vydej")
    search_fields = ('artikl',)
    search_help_text = "Dle artiklu"
    list_filter = (ZakaznikZakazkyFilter, OdberatelFilter, KompletZakazkaFilter, PrioritaZakazkyFilter, CelozavitZakazkyFilter, TypHlavyZakazkyFilter,
                   OberflacheFilter, ExpedovanaZakazkaFilter,)
    ordering = ('id',)
    date_hierarchy = 'kamion_prijem__datum'
    list_per_page = 25
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '30'})},
        models.DecimalField: {
            'widget': TextInput(attrs={ 'size': '8'}),
            'localize': True
        },
        models.BooleanField: {'widget': RadioSelect(choices=[(True, 'Ano'), (False, 'Ne')])}
    }

    # Parametry pro zobrazení historie v administraci
    history_list_display = ["id", "kamion_prijem", "kamion_vydej", "artikl", "prumer", "delka", "predpis", "typ_hlavy", "popis", "priorita",]
    history_search_fields = ["kamion_prijem__zakaznik__nazev", "artikl", "prumer", "delka", "predpis", "typ_hlavy", "popis"]
    history_list_filter = ["kamion_prijem__zakaznik", "kamion_prijem__datum", "typ_hlavy"]
    history_list_per_page = 20

    class Media:
        js = (
            'orders/zakazky_hmotnost_sum.js',
            'orders/admin_actions_target_blank.js',
            )

    @admin.display(description='Předpis', ordering='predpis__id', empty_value='-')
    def predpis_link(self, obj):
        """
        Zobrazí odkaz na předpis zakázky a umožní třídění podle hlavičky pole.
        Pokud není předpis připojen, vrátí prázdný řetězec.
        """
        if obj.predpis:
            return mark_safe(f'<a href="{obj.predpis.get_admin_url()}">{obj.predpis.nazev}</a>')
        
    @admin.display(description='Délka', ordering='delka', empty_value='-')
    def get_delka_int(self, obj):
        """
        Zobrazí délku zakázky jako celé číslo (oříznuté číslice za čárkou) a umožní třídění podle hlavičky pole.
        Pokud není délka připojena, vrátí prázdný řetězec.
        """
        if obj.delka is not None:
            return int(obj.delka.to_integral_value(rounding=ROUND_DOWN))
        return '-'
    
    @admin.display(description='Ø', ordering='prumer', empty_value='-')
    def get_prumer(self, obj):
        """
        Zobrazí průměr zakázky a umožní třídění podle hlavičky pole.
        Pokud není průměr připojen, vrátí prázdný řetězec.
        """
        if obj.prumer is not None:
            return obj.prumer
        return '-'
        
    @admin.display(description='Datum', ordering='kamion_prijem__datum', empty_value='-')
    def get_datum(self, obj):
        """
        Zobrazí datum kamionu příjmu, ke kterému zakázka patří, a umožní třídění podle hlavičky pole.
        Pokud není kamion příjmu připojen, vrátí prázdný řetězec.
        """
        if obj.kamion_prijem:
            return obj.kamion_prijem.datum.strftime('%y-%m-%d')
        return '-'

    @admin.display(description='TZ', ordering='predpis__skupina', empty_value='-')
    def get_skupina(self, obj):
        """
        Zobrazí skupinu tepelného zpracování zakázky a umožní třídění podle hlavičky pole.
        """
        if obj.predpis:
            return obj.predpis.skupina
        return '-'

    @admin.display(boolean=True, description='VG', ordering='celozavit')
    def get_celozavit(self, obj):
        """
        Zobrazí boolean, jestli je vrut celozávitový a umožní třídění podle hlavičky pole.
        """
        return obj.celozavit
    
    @admin.display(description='Hlava', ordering='typ_hlavy', empty_value='-')
    def typ_hlavy_link(self, obj):
        """
        Zobrazí typ hlavy a umožní třídění podle hlavičky pole.
        """
        if obj.typ_hlavy:
            return mark_safe(f'<a href="{obj.typ_hlavy.get_admin_url()}">{obj.typ_hlavy.nazev}</a>')

    @admin.display(description="Popis zkr.", ordering='popis')
    def zkraceny_popis(self, obj):
        # Vrátí vše do prvního výskytu čísla (včetně předchozí mezery)
        match = re.match(r"^(.*?)(\s+\d+.*)?$", obj.popis)    
        if not match:
            return obj.popis
        return format_html('<span title="{}">{}</span>', obj.popis, match.group(1))        

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

    @admin.display(description='Kam. příjem', ordering='kamion_prijem__id', empty_value='-')
    def kamion_prijem_link(self, obj):
        """
        Vytvoří odkaz na detail kamionu příjmu, ke kterému zakázka patří a umožní třídění podle hlavičky pole.
        """
        if obj.kamion_prijem:
            return mark_safe(f'<a href="{obj.kamion_prijem.get_admin_url()}">{obj.kamion_prijem}</a>')

    @admin.display(description='Kam. výdej', ordering='kamion_vydej__id', empty_value='-')
    def kamion_vydej_link(self, obj):
        """
        Vytvoří odkaz na detail kamionu výdeje, ke kterému zakázka patří a umožní třídění podle hlavičky pole.
        """
        if obj.kamion_vydej:
            return mark_safe(f'<a href="{obj.kamion_vydej.get_admin_url()}">{obj.kamion_vydej}</a>')

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

    def has_change_permission(self, request, obj=None):
        """
        Kontrola oprávnění pro změnu zakázky, v případě expedované zakázky nelze měnit, pokud nemá uživatel oprávnění.
        """
        if obj and obj.expedovano and not request.user.has_perm('orders.change_expedovana_zakazka'):
            return False
        return super().has_change_permission(request, obj)      

    def get_fieldsets(self, request, obj=None):
        """
        Vytváří pole pro zobrazení v administraci na základě toho, zda se jedná o editaci nebo přidání, případně zda je zakázka expedovaná.
        """
        if obj:  # editace stávajícího záznamu
            if obj.expedovano:
                # Pokud je zakázka expedovaná, kvůli has_permission v modelu ZakazkaAdmin nelze měnit, zobrazí i kamion výdej
                my_fieldsets = [
                    ('Expedovaná zakázka:', {
                        'fields': ['kamion_prijem', 'kamion_vydej', 'artikl', 'typ_hlavy', 'celozavit', 'prumer', 'delka', 'predpis', 'priorita', 'popis', 'odberatel', 'get_komplet',],
                        'description': 'Zakázka je expedovaná a nelze ji měnit.',
                    }),
                ]
            else:  # Pokud zakázka není expedovaná, zobrazí se základní pole pro editaci
                my_fieldsets = [
                    ('Zakázka skladem:', {
                        'fields': ['kamion_prijem', 'artikl', 'typ_hlavy', 'celozavit', 'prumer', 'delka', 'predpis', 'priorita', 'popis', 'odberatel', 'get_komplet',],
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

            return my_fieldsets

        else:  # přidání nového záznamu
            return [
                ('Příjem zakázky na sklad:', {
                    'fields': ['kamion_prijem', 'artikl', 'typ_hlavy', 'celozavit','prumer', 'delka', 'predpis', 'priorita', 'popis', 'odberatel', 'get_komplet',],
                    'description': 'Přijímání zakázky z kamiónu na sklad, pokud ještě není kamión v systému, vytvořte ho pomocí ikony ➕ u položky Kamión.',
                }), 
                ('Pouze pro Eurotec:', {
                    'fields': ['vrstva', 'povrch', 'prubeh'],
                    'classes': ['collapse'],
                    'description': 'Pro Eurotec musí být vyplněno: Tloušťka vrstvy, Povrchová úprava a Průběh.',
                }),                 
            ]                    
   
    def get_actions(self, request):
        """
        Přizpůsobí dostupné akce v administraci podle filtru stavu bedny.
        Standardně jsou dostupné všechny akce:
        actions = [tisk_karet_beden_zakazek_action, tisk_karet_kontroly_kvality_zakazek_action, expedice_zakazek_action,
        vratit_zakazky_z_expedice_action, expedice_zakazek_kamion_action]        
        Pokud je filtr skladem == expedovano, zruší se akce expedice_zakazek_action a expedice_zakazek_kamion_action
        Pokud není filtr skladem aktivovan, zruší se akce vratit_zakazky_z_expedice_action.
        """
        actions = super().get_actions(request)

        actions_to_remove = []

        if request.method == "GET":
            if request.GET.get('skladem', None) == 'expedovano':
                actions_to_remove = [
                    'expedice_zakazek_action', 'expedice_zakazek_kamion_action'
                ]
            else:
                actions_to_remove = [
                    'vratit_zakazky_z_expedice_action',
                ]

        for action in actions_to_remove:
            if action in actions:
                del actions[action]

        return actions

    def get_action_choices(self, request, default_choices=models.BLANK_CHOICE_DASH):
        """Seskupení akcí zakázek do optgroup a formátování placeholderů.

        Skupiny:
        - Tisk / Export
        - Expedice
        Ostatní akce (např. delete_selected) spadnou do 'Ostatní'.
        """
        actions = self.get_actions(request)
        if not actions:
            return default_choices

        group_map = {
            'tisk_karet_beden_zakazek_action': 'Tisk / Export',
            'tisk_karet_kontroly_kvality_zakazek_action': 'Tisk / Export',
            'expedice_zakazek_action': 'Expedice',
            'expedice_zakazek_kamion_action': 'Expedice',
            'vratit_zakazky_z_expedice_action': 'Expedice',
        }
        order = ['Tisk / Export', 'Expedice']
        grouped = {g: [] for g in order}

        for name, (_func, _action_name, desc) in actions.items():
            group = group_map.get(name, 'Ostatní')
            text = str(desc) if desc is not None else ''
            if '%(verbose_name' in text:
                try:
                    text = text % {
                        'verbose_name': self.model._meta.verbose_name,
                        'verbose_name_plural': self.model._meta.verbose_name_plural,
                    }
                except Exception:
                    pass
            grouped.setdefault(group, []).append((name, text))

        choices = [default_choices[0]]
        for g in order + [g for g in grouped.keys() if g not in order]:
            opts = grouped.get(g)
            if opts:
                choices.append((g, sorted(opts, key=lambda x: x[1].lower())))
        return choices

    def get_list_display(self, request):
        """
        Přizpůsobení zobrazení sloupců v seznamu zakázek podle aktivního filtru.
        Pokud není aktivní filtr "skladem=Expedováno", odebere se sloupec kamion_vydej.
        """
        ld = list(super().get_list_display(request))
        if not request.GET.get('skladem'):
            if 'kamion_vydej_link' in ld:
                ld.remove('kamion_vydej_link')
        return ld

    def get_list_editable(self, request):
        """
        Přizpůsobení zobrazení sloupců pro editaci v seznamu zakázek podle aktivního filtru.
        Pokud není aktivní filtr "skladem=Expedováno", přidá se do list_editable pole priorita.
        """
        if request.GET.get('skladem') != 'expedovano':
            return ['priorita']
        return []

    def changelist_view(self, request, extra_context=None):
        """
        Přizpůsobení zobrazení seznamu zakázek podle aktivního filtru.
        """
        self.list_editable = self.get_list_editable(request)
        return super().changelist_view(request, extra_context)

    def get_form(self, request, obj=None, **kwargs):
        """
        Vrací ModelForm pro Zakázku, ale upraví 'choices' 
        u polí hromadné změny podle stavu první bedny.
        """
        FormClass = super().get_form(request, obj, **kwargs)
        
        class CustomForm(FormClass):
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

        return CustomForm


@admin.register(Bedna)
class BednaAdmin(SimpleHistoryAdmin):
    """
    Admin pro model Bedna:
    
    - Detail/inline: BednaAdminForm (omezuje stavové volby dle instance).
    - Seznam (change_list): list_editable pro stav_bedny, tryskat, rovnat a poznamka.
    - Pro každý řádek dropdown omezí na povolené volby podle stejné logiky.
    - Číslo bedny se generuje automaticky a je readonly
    """
    actions = [
        tisk_karet_beden_action, tisk_karet_kontroly_kvality_action, oznacit_k_navezeni_action, oznacit_navezeno_action,
        vratit_bedny_do_stavu_prijato_action, oznacit_do_zpracovani_action, oznacit_zakaleno_action, oznacit_zkontrolovano_action,
        oznacit_k_expedici_action, oznacit_rovna_action, oznacit_kriva_action, oznacit_rovna_se_action, oznacit_vyrovnana_action,
        oznacit_cista_action, oznacit_spinava_action, oznacit_otryskana_action,
    ]
    form = BednaAdminForm

    # Parametry pro zobrazení detailu v administraci
    fields = ('zakazka', 'pozice', 'cislo_bedny', 'hmotnost', 'tara', 'mnozstvi', 'material', 'sarze', 'behalter_nr', 'dodatecne_info',
              'dodavatel_materialu', 'vyrobni_zakazka', 'tryskat', 'rovnat', 'stav_bedny', 'poznamka', 'odfosfatovat', 'pozastaveno', 'poznamka_k_navezeni')
    readonly_fields = ('cislo_bedny',)
    autocomplete_fields = ('zakazka',)

    # Parametry pro zobrazení seznamu v administraci
    list_display = ('get_cislo_bedny', 'get_behalter_nr', 'zakazka_link', 'kamion_prijem_link', 'kamion_vydej_link',
                    'rovnat', 'tryskat', 'stav_bedny', 'get_prumer', 'get_delka_int','get_skupina_TZ', 'get_typ_hlavy',
                    'get_celozavit', 'zkraceny_popis', 'hmotnost', 'pozice', 'get_priorita', 'get_datum', 'poznamka',)
    # list_editable nastavován dynamicky v get_list_editable
    list_display_links = ('get_cislo_bedny', )
    list_select_related = ("zakazka", "zakazka__kamion_prijem", "zakazka__kamion_vydej")
    list_per_page = 25
    search_fields = ('cislo_bedny', 'behalter_nr', 'zakazka__artikl',)
    search_help_text = "Dle čísla bedny, č.b. zákazníka nebo zakázky"
    list_filter = (ZakaznikBednyFilter, StavBednyFilter, TryskaniFilter, RovnaniFilter, CelozavitBednyFilter,
                   TypHlavyBednyFilter, PrioritaBednyFilter, UvolnenoFilter, SkupinaFilter, DelkaFilter)
    ordering = ('id',)
    date_hierarchy = 'zakazka__kamion_prijem__datum'
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={ 'size': '20', 'style': 'font-size: 10px;'})},
        models.DecimalField: {
            'widget': TextInput(attrs={ 'size': '3'}),
            'localize': True
        },
        models.BooleanField: {'widget': RadioSelect(choices=[(True, 'Ano'), (False, 'Ne')])}
    }

    # Parametry pro historii změn
    history_list_display = ["id", "zakazka", "cislo_bedny", "stav_bedny", "typ_hlavy", "poznamka"]
    history_search_fields = ["zakazka__kamion_prijem__zakaznik__nazev", "cislo_bedny", "stav_bedny", "zakazka__typ_hlavy", "poznamka"]
    history_list_filter = ["zakazka__kamion_prijem__zakaznik__nazev", "zakazka__kamion_prijem__datum", "stav_bedny"]
    history_list_per_page = 20

    class Media:
        js = ('orders/admin_actions_target_blank.js',)    

    @admin.display(description='Č. bedny', ordering='cislo_bedny')
    def get_cislo_bedny(self, obj):
        """
        Zobrazí číslo bedny a umožní třídění podle hlavičky pole.
        Číslo bedny se generuje automaticky a je readonly.
        """
        return obj.cislo_bedny
    
    @admin.display(description='Datum', ordering='zakazka__kamion_prijem__datum', empty_value='-')
    def get_datum(self, obj):
        """
        Zobrazí datum kamionu příjmu, ke kterému bedna patří, a umožní třídění podle hlavičky pole.
        Pokud není kamion příjmu připojen, vrátí prázdný řetězec.
        """
        if obj.zakazka and obj.zakazka.kamion_prijem:
            return obj.zakazka.kamion_prijem.datum.strftime('%y-%m-%d')
        return '-'
    
    @admin.display(description='Č.b.z.', ordering='behalter_nr', empty_value='-')
    def get_behalter_nr(self, obj):
        """
        Zobrazí číslo bedny zákazníka a umožní třídění podle hlavičky pole.
        Pokud není vyplněno, zobrazí se '-'.
        """
        return obj.behalter_nr
    
    @admin.display(description='Poz.', ordering='pozice', empty_value='-')
    def get_pozice(self, obj):
        """
        Zobrazí kod pozice bedny a umožní třídění podle hlavičky pole.
        Pokud není pozice vyplněna, zobrazí se '-'.
        """
        return obj.pozice.kod if obj.pozice else '-'

    @admin.display(description='Zakázka', ordering='zakazka__id', empty_value='-')
    def zakazka_link(self, obj):
        """
        Vytvoří odkaz na detail zakázky, ke které bedna patří a umožní třídění podle hlavičky pole.
        """
        if obj.zakazka:
            return mark_safe(f'<a href="{obj.zakazka.get_admin_url()}">{obj.zakazka.artikl}</a>')

    @admin.display(boolean=True, description='VG', ordering='zakazka__celozavit')
    def get_celozavit(self, obj):
        """
        Zobrazí boolean, jestli je vrut celozávitový a umožní třídění podle hlavičky pole.
        """
        return obj.zakazka.celozavit
    
    @admin.display(description="Zkrácený popis", ordering='zakazka__popis')
    def zkraceny_popis(self, obj):
        """
        Vrátí vše do prvního výskytu čísla (včetně předchozí mezery)
        """
        match = re.match(r"^(.*?)(\s+\d+.*)?$", obj.zakazka.popis)    
        if not match:
            return obj.zakazka.popis
        return format_html('<span title="{}">{}</span>', obj.zakazka.popis, match.group(1))        

    @admin.display(description='Kam. příjem', ordering='zakazka__kamion_prijem__id', empty_value='-')
    def kamion_prijem_link(self, obj):
        """
        Vytvoří odkaz na detail kamionu příjmu, ke kterému bedna patří a umožní třídění podle hlavičky pole.
        """
        if obj.zakazka and obj.zakazka.kamion_prijem:
            return mark_safe(f'<a href="{obj.zakazka.kamion_prijem.get_admin_url()}">{obj.zakazka.kamion_prijem}</a>')

    @admin.display(description='Kam. výdej', ordering='zakazka__kamion_vydej__id', empty_value='-')
    def kamion_vydej_link(self, obj):
        """
        Vytvoří odkaz na detail kamionu výdeje, ke kterému bedna patří a umožní třídění podle hlavičky pole.
        """
        if obj.zakazka and obj.zakazka.kamion_vydej:
            return mark_safe(f'<a href="{obj.zakazka.kamion_vydej.get_admin_url()}">{obj.zakazka.kamion_vydej}</a>')

    @admin.display(description='Hlava', ordering='zakazka__typ_hlavy')
    def get_typ_hlavy(self, obj):
        """
        Zobrazí typ hlavy zakázky a umožní třídění podle hlavičky pole.
        """
        return obj.zakazka.typ_hlavy

    @admin.display(description='Prior.', ordering='zakazka__priorita')
    def get_priorita(self, obj):
        """
        Zobrazí prioritu zakázky a umožní třídění podle hlavičky pole.
        """
        return obj.zakazka.get_priorita_display() if obj.zakazka else "-"

    @admin.display(description='Ø', ordering='zakazka__prumer')
    def get_prumer(self, obj):
        """
        Zobrazí průměr zakázky a umožní třídění podle hlavičky pole.
        """
        return obj.zakazka.prumer

    @admin.display(description='Délka', ordering='zakazka__delka', empty_value='-')
    def get_delka_int(self, obj):
        """
        Zobrazí délku zakázky jako integer a umožní třídění podle hlavičky pole.
        """
        if obj.zakazka and obj.zakazka.delka is not None:
            return int(obj.zakazka.delka.to_integral_value(rounding=ROUND_DOWN))
        return '-'
    
    @admin.display(description='TZ', ordering='zakazka__predpis__skupina', empty_value='-')
    def get_skupina_TZ(self, obj):
        """
        Zobrazí skupinu tepelného zpracování zakázky a umožní třídění podle hlavičky pole.
        """
        if obj.zakazka and obj.zakazka.predpis and obj.zakazka.predpis.skupina:
            return obj.zakazka.predpis.skupina
        return '-'

    def get_fields(self, request, obj=None):
        """
        Vrací seznam polí, která se mají zobrazit z formuláře Bedna při editaci.

        - Pokud není obj (tj. add_view), odebere se pole `cislo_bedny`, protože se generuje automaticky.  
        - Pokud obj existuje a zákazník zakázky je ROT, odebere se ze zobrazených polí dodatecne_info, dodavatel_materialu a vyrobni_zakazka.
        - Pokud obj existuje a zákazník zakázky je SSH, SWG, HPM nebo FIS, odebere se navíc k ROT ze zobrazených polí behalter_nr.
        """   
        fields = list(super().get_fields(request, obj))
        exclude_fields = []
        # Pokud se jedná o editaci existující bedny
        if obj:
            # Vyloučení polí dle zákazníka
            if obj.zakazka.kamion_prijem.zakaznik.zkratka == 'ROT':
                exclude_fields = ['dodatecne_info', 'dodavatel_materialu', 'vyrobni_zakazka']
            elif obj.zakazka.kamion_prijem.zakaznik.zkratka in ('SSH', 'SWG', 'HPM', 'FIS'):
                exclude_fields = ['behalter_nr', 'dodatecne_info', 'dodavatel_materialu', 'vyrobni_zakazka']
        # Při přidání nové bedny se vyloučí pole `cislo_bedny`, protože se generuje automaticky.
        else:
            exclude_fields = ['cislo_bedny']

        fields = [f for f in fields if f not in exclude_fields]
        return fields
    
    def get_changelist_form(self, request, **kwargs):
        """
        Vytvoří vlastní formulář pro ChangeList s omezenými volbami pro `stav_bedny`.
        """
        return BednaAdminForm

    def has_change_permission(self, request, obj=None):
        """
        Kontrola oprávnění pro změnu bedny, v případě expedované nebo pozastavené bedny nelze bez práv měnit.
        """
        if obj and obj.stav_bedny == StavBednyChoice.EXPEDOVANO and not request.user.has_perm('orders.change_expedovana_bedna'):
            return False
        if obj and obj.pozastaveno and not request.user.has_perm('orders.change_pozastavena_bedna'):
            return False
        return super().has_change_permission(request, obj)  
    
    def get_list_editable(self, request):
        """
        Přizpůsobení zobrazení sloupců pro editaci v seznamu beden podle aktivního filtru.
        Pokud je aktivní filtr Stav bedny = Expedováno nebo Uvolněno = Pozastaveno, odebere se inline-editace.
        Pokud není aktivní filtr stav bedny = Prijato, K_navezeni, Navezeno, vyloučí se možnost editace sloupce pozice.
        """
        if request.GET.get('stav_bedny', None) == 'EX' or request.GET.get('uvolneno', None) == 'pozastaveno':
            return []
        if request.GET.get('stav_bedny', None) not in ('PR', 'KN', 'NA'):
            return ['stav_bedny', 'tryskat', 'rovnat', 'hmotnost', 'poznamka']
        return ['stav_bedny', 'tryskat', 'rovnat', 'hmotnost', 'poznamka', 'pozice']

    def changelist_view(self, request, extra_context=None):
        """
        Přizpůsobení zobrazení seznamu beden podle aktivního filtru.
        """
        self.list_editable = self.get_list_editable(request)
        return super().changelist_view(request, extra_context)

    def get_changelist_formset(self, request, **kwargs):
        """
        Vytvoří vlastní formset pro ChangeList, který zakáže editaci polí v závislosti na stavu bedny a oprávněních uživatele.
        Pokud je bedna pozastavena a uživatel nemá příslušná oprávnění, zakáže se editace polí.
        """
        formset = super().get_changelist_formset(request, **kwargs)

        class CustomFormset(formset):
            def __init__(self_inner, *args, **kwargs):
                super().__init__(*args, **kwargs)
                for form in self_inner.forms:
                    obj = form.instance
                    if obj.pozastaveno and not request.user.has_perm('orders.change_pozastavena_bedna'):
                        for field in form.fields:
                            form.fields[field].disabled = True

        return CustomFormset
    
    def get_list_display(self, request):
        """
        Přizpůsobení zobrazení sloupců v seznamu Bedna.
        Pokud není aktivní filtr stav bedny Expedováno, vyloučí se zobrazení sloupce kamion_vydej_link.
        Pokud není aktivní filtr stav bedny Prijato, K_navezeni, Navezeno, vyloučí se zobrazení sloupce pozice.
        """
        list_display = list(super().get_list_display(request))
        if request.GET.get('stav_bedny', None) != 'EX':
            if 'kamion_vydej_link' in list_display:
                list_display.remove('kamion_vydej_link')
        if request.GET.get('stav_bedny', None) not in ('PR', 'KN', 'NA'):
            if 'pozice' in list_display:
                list_display.remove('pozice')
        return list_display

    def get_actions(self, request):
        """
        Přizpůsobí dostupné akce v administraci podle filtru stavu bedny, rovnat a tryskat.
        Pokud není aktivní filtr stav bedny PRIJATO, zruší se akce pro změnu stavu bedny na K_NAVEZENI.
        Pokud není aktivní filtr stav bedny K_NAVEZENI, zruší akci pro změnu stavu bedny na NAVEZENO a pro vrácení stavu bedny na PRIJATO.
        Pokud není aktivní filtr stav bedny NAVEZENO, zruší akci pro změnu stavu bedny na DO_ZPRACOVANI.
        Pokud není aktivní filtr stav bedny DO_ZPRACOVANI, zruší akci pro změnu stavu bedny na ZAKALENO.
        Pokud není aktivní filtr stav bedny ZAKALENO, zruší akci pro změnu stavu bedny na ZKONTROLOVANO.
        Pokud není aktivní filtr stav bedny ZKONTROLOVANO, zruší akci pro změnu stavu bedny na K_EXPEDICI.
        Pokud není aktivní filtr stav bedny K_EXPEDICI, zruší akci pro změnu stavu bedny na ZPRACOVANO.
        Pokud není aktivní filtr rovnani NEZADANO, zruší akce pro změnu stavu rovnání na ROVNA a KRIVA.
        Pokud není aktivní filtr rovnani KRIVA, zruší akci pro změnu stavu rovnání na ROVNA_SE.
        Pokud není aktivní filtr rovnani ROVNA_SE, zruší akci pro změnu stavu rovnání na VYROVNANA.
        Pokud není aktivní filtr tryskani NEZADANO, zruší akce pro změnu stavu tryskání na CISTA a SPINAVA.
        Pokud není aktivní filtr tryskani SPINAVA nebo NEZADANO, zruší akci pro změnu stavu tryskání na OTRYSKANA.
        """
        actions = super().get_actions(request)

        actions_to_remove = []

        if request.method == "GET":
            if request.GET.get('stav_bedny', None) != StavBednyChoice.PRIJATO:
                actions_to_remove = [
                    'oznacit_k_navezeni_action',
                ]
            if request.GET.get('stav_bedny', None) != StavBednyChoice.K_NAVEZENI:
                actions_to_remove += [
                    'vratit_bedny_do_stavu_prijato_action', 'oznacit_navezeno_action',
                ]
            if request.GET.get('stav_bedny', None) != StavBednyChoice.NAVEZENO:
                actions_to_remove += [
                    'oznacit_do_zpracovani_action',
                ]
            if request.GET.get('stav_bedny', None) != StavBednyChoice.DO_ZPRACOVANI:
                actions_to_remove += [
                    'oznacit_zakaleno_action',
                ]
            if request.GET.get('stav_bedny', None) != StavBednyChoice.ZAKALENO:
                actions_to_remove += [
                    'oznacit_zkontrolovano_action',
                ]
            if request.GET.get('stav_bedny', None) not in [StavBednyChoice.ZKONTROLOVANO, 'RO']:
                actions_to_remove += [
                    'oznacit_k_expedici_action',
                ]
            if request.GET.get('rovnani', None) != RovnaniChoice.NEZADANO:
                actions_to_remove += [
                    'oznacit_rovna_action', 'oznacit_kriva_action',
                ]
            if request.GET.get('rovnani', None) != RovnaniChoice.KRIVA:
                actions_to_remove += [
                    'oznacit_rovna_se_action',
                ]
            if request.GET.get('rovnani', None) != RovnaniChoice.ROVNA_SE:
                actions_to_remove += [
                    'oznacit_vyrovnana_action',
                ]
            if request.GET.get('tryskani', None) != TryskaniChoice.NEZADANO:
                actions_to_remove += [
                    'oznacit_cista_action', 'oznacit_spinava_action',
                ]
            if request.GET.get('tryskani', None) not in [TryskaniChoice.SPINAVA, TryskaniChoice.NEZADANO]:
                actions_to_remove += [
                    'oznacit_otryskana_action',
                ]

        for action in actions_to_remove:
            if action in actions:
                del actions[action]

        return actions

    def get_action_choices(self, request, default_choices=models.BLANK_CHOICE_DASH):
        """
        Seskupení akcí beden do optgroup a formátování placeholderů.
        Skupiny:
        - Tisk / Export
        - Stav bedny
        - Rovnání
        - Tryskání
        Ostatní akce (např. delete_selected) spadnou do 'Ostatní'.
        """
        actions = self.get_actions(request)
        if not actions:
            return default_choices

        group_map = {
            'tisk_karet_beden_action': 'Tisk / Export',
            'tisk_karet_kontroly_kvality_action': 'Tisk / Export',
            'oznacit_k_navezeni_action': 'Stav bedny',
            'oznacit_navezeno_action': 'Stav bedny',
            'vratit_bedny_do_stavu_prijato_action': 'Stav bedny',
            'oznacit_do_zpracovani_action': 'Stav bedny',
            'oznacit_zakaleno_action': 'Stav bedny',
            'oznacit_zkontrolovano_action': 'Stav bedny',
            'oznacit_k_expedici_action': 'Stav bedny',
            'oznacit_rovna_action': 'Rovnání',
            'oznacit_kriva_action': 'Rovnání',
            'oznacit_rovna_se_action': 'Rovnání',
            'oznacit_vyrovnana_action': 'Rovnání',
            'oznacit_cista_action': 'Tryskání',
            'oznacit_spinava_action': 'Tryskání',
            'oznacit_otryskana_action': 'Tryskání',
        }
        order = ['Tisk / Export', 'Stav bedny', 'Rovnání', 'Tryskání']
        grouped = {g: [] for g in order}

        for name, (_func, _action_name, desc) in actions.items():
            g = group_map.get(name, 'Ostatní')
            # Přetypovat i případný lazy překlad na str
            text = str(desc) if desc is not None else ''
            # Formátovat jen pokud obsahuje placeholdery delete_selected (bez toho by % vyhodilo chybu)
            if '%(verbose_name' in text:
                try:
                    text = text % {
                        'verbose_name': self.model._meta.verbose_name,
                        'verbose_name_plural': self.model._meta.verbose_name_plural,
                    }
                except Exception:
                    # Při chybě ponechat původní text
                    pass
            grouped.setdefault(g, []).append((name, text))

        choices = [default_choices[0]]
        for g in order + [g for g in grouped.keys() if g not in order]:
            opts = grouped.get(g)
            if opts:
                choices.append((g, sorted(opts, key=lambda x: x[1].lower())))
        return choices
    
    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        """
        Přizpůsobí zobrazení pole pro cizí klíč v administraci.
        """
        if db_field.name == "pozice":
            kwargs['empty_label'] = "-"        
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """
        Přizpůsobení widgetů pro pole v administraci.
        """
        if isinstance(db_field, models.ForeignKey):
            # Zruší zobrazení ikon pro ForeignKey pole v administraci, nepřidá RelatedFieldWidgetWrapper.
            formfield = self.formfield_for_foreignkey(db_field, request, **kwargs)
            # pokud už je wrapnutý? -> jen se vypnou ikonky
            if isinstance(formfield.widget, RelatedFieldWidgetWrapper):
                for attr in ("can_add_related", "can_change_related", "can_delete_related", "can_view_related"):
                    if hasattr(formfield.widget, attr):
                        setattr(formfield.widget, attr, False)
                return formfield

            # není wrapnutý? -> zabalí se a vypnou se ikonky
            rel = db_field.remote_field
            formfield.widget = RelatedFieldWidgetWrapper(
                formfield.widget, rel, self.admin_site,
                can_add_related=False,
                can_change_related=False,
                can_delete_related=False,
                can_view_related=False,
            )
            return formfield

        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(Predpis)
class PredpisAdmin(SimpleHistoryAdmin):
    """
    Správa předpisů v administraci.
    """
    save_as = True
    list_display = ('nazev', 'skupina', 'zakaznik__zkraceny_nazev', 'ohyb', 'krut', 'povrch', 'jadro', 'vrstva', 'popousteni',
                    'sarzovani', 'pletivo', 'poznamka', 'aktivni')
    list_display_links = ('nazev',)
    search_fields = ('nazev',)
    search_help_text = "Dle názvu předpisu"
    list_filter = (ZakaznikPredpisFilter, AktivniPredpisFilter)
    ordering = ['-zakaznik__zkratka', 'nazev']
    list_per_page = 25

    history_list_display = ['nazev', 'skupina', 'zakaznik']
    history_search_fields = ['nazev']
    history_list_filter = ['zakaznik__zkraceny_nazev']
    history_list_per_page = 20


@admin.register(Odberatel)
class OdberatelAdmin(SimpleHistoryAdmin):
    """
    Správa odběratelů v administraci.
    """
    list_display = ('nazev', 'zkraceny_nazev', 'zkratka', 'adresa', 'mesto', 'psc', 'stat', 'zkratka_statu', 'kontaktni_osoba', 'telefon', 'email',)
    list_display_links = ('nazev',)
    ordering = ['nazev']
    list_per_page = 25

    history_list_display = ['nazev', 'zkraceny_nazev', 'zkratka', 'adresa', 'mesto', 'psc', 'stat', 'zkratka_statu', 'kontaktni_osoba', 'telefon', 'email']
    history_search_fields = ['nazev']
    history_list_per_page = 20    


@admin.register(TypHlavy)
class TypHlavyAdmin(SimpleHistoryAdmin):
    """
    Správa typů hlav v administraci.
    """
    list_display = ('nazev', 'popis')
    list_display_links = ('nazev',)
    ordering = ['nazev']
    list_per_page = 25

    history_list_display = ['nazev', 'popis']
    history_search_fields = ['nazev']
    history_list_per_page = 20
    

@admin.register(Cena)    
class CenaAdmin(SimpleHistoryAdmin):
    """
    Správa cen v administraci.
    """
    list_display = ('get_zakaznik', 'popis_s_delkou', 'delka_min', 'delka_max', 'cena_za_kg', 'get_predpisy')
    list_editable = ('delka_min', 'delka_max', 'cena_za_kg')
    list_display_links = ('popis_s_delkou',)
    list_filter = ('zakaznik',)
    search_fields = ('popis', 'predpis__nazev',)
    search_help_text = "Dle popisu ceny a názvu předpisu"
    autocomplete_fields = ('predpis',)
    save_as = True
    list_per_page = 25

    history_list_display = ['zakaznik', 'delka_min', 'delka_max', 'cena_za_kg']
    history_list_filter = ['zakaznik',]
    history_list_per_page = 20

    formfield_overrides = {
        models.DecimalField: {
            'widget': TextInput(attrs={'size': '6'}),
            'localize': True
            },
    }    

    @admin.display(description='Předpisy', ordering='predpis__nazev', empty_value='-')
    def get_predpisy(self, obj):
        """
        Zobrazí názvy předpisů spojených s cenou a umožní třídění podle hlavičky pole.
        Pokud není žádný předpis spojen, vrátí prázdný řetězec.
        """
        if obj.predpis.exists():
            predpisy_text = ", ".join(predpis.nazev for predpis in obj.predpis.all())
            return format_html(
                '<div style="max-width: 780px; white-space: normal;">{}</div>',
                predpisy_text
            )
        return "-"
    
    @admin.display(description='Zák.', ordering='zakaznik__nazev', empty_value='-')
    def get_zakaznik(self, obj):
        """
        Zobrazí zkratku zákazníka spojeného s cenou.
        """
        return obj.zakaznik.zkratka if obj.zakaznik else "-"
    
    @admin.display(description='Popis s délkou', ordering='popis', empty_value='-')
    def popis_s_delkou(self, obj):
        """
        Zobrazí popis ceny s délkou, pokud je delka_max a delka_min vyplněna.
        Pokud není delka_max nebo delka_min vyplněna, vrátí pouze popis.
        """
        if obj.delka_min and obj.delka_max:
            return f"{obj.popis}x{int(obj.delka_min)}-{int(obj.delka_max)}"
        return obj.popis
    

@admin.register(Pozice)
class PoziceAdmin(admin.ModelAdmin):
    list_display = ("kod", "get_pocet_beden", "get_vyuziti", "seznam_beden")
    list_per_page = 20
    search_fields = ("kod",)

    @admin.display(description="Obsazenost")
    def get_pocet_beden(self, obj: Pozice):
        return f"{obj.pocet_beden} / {obj.kapacita}"

    @admin.display(description="Využití")
    def get_vyuziti(self, obj: Pozice):
        # jednoduchý progress bar
        vyuziti = obj.vyuziti_procent
        pozadi = "#22c55e" if vyuziti < 80 else ("#eab308" if vyuziti < 100 else "#ef4444")
        bar = f"""
        <div style="width:120px;border:1px solid #ddd;height:12px;border-radius:6px;overflow:hidden;">
            <div style="width:{vyuziti}%;height:100%;background:{pozadi};"></div>
        </div>
        """
        return format_html(bar + f" {vyuziti}%")

    @admin.display(description="Bedny na pozici")
    def seznam_beden(self, obj):
        bedny_na_pozici = obj.bedny.values_list("cislo_bedny", flat=True)
        return f"{', '.join(map(str, bedny_na_pozici))}" if bedny_na_pozici else "-"


# Nastavení atributů AdminSite
admin.site.index_title = "Správa zakázek"