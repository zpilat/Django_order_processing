from django.contrib import admin, messages
from django.contrib.auth.models import Permission
from django.db import models, transaction
from django.db.models import Case, When, Value, IntegerField, Prefetch
from django.forms import TextInput, RadioSelect, modelformset_factory
from django.forms.models import BaseInlineFormSet
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.contrib.admin.views.main import ChangeList
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from django.urls import path, reverse
from django.shortcuts import redirect, render
from django.utils.html import format_html, format_html_join
from django.db.models import Count, Max
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime

from simple_history.admin import SimpleHistoryAdmin
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
from django.core.files.storage import default_storage
import uuid
import pandas as pd
import re
from django import forms
from django.contrib.admin.helpers import ActionForm
from django.contrib.admin.actions import delete_selected as admin_delete_selected
from django_user_agents.utils import get_user_agent

from .import_strategies import BaseImportStrategy, EURImportStrategy, SPXImportStrategy

from .models import (
    Zakaznik, Kamion, Zakazka, Bedna, Predpis, Odberatel, TypHlavy, Cena, Pozice, Pletivo, PoziceZakazkaOrder, Rozpracovanost
)
from .actions import (
    expedice_zakazek_action, import_kamionu_action, tisk_karet_beden_action, tisk_karet_beden_zakazek_action,
    tisk_karet_beden_kamionu_action, tisk_dodaciho_listu_kamionu_action, vratit_zakazky_z_expedice_action, expedice_zakazek_kamion_action,
    tisk_karet_kontroly_kvality_action, tisk_karet_kontroly_kvality_zakazek_action, tisk_karet_kontroly_kvality_kamionu_action,
    tisk_karet_bedny_a_kontroly_action, tisk_protokolu_kamionu_vydej_action, tisk_proforma_faktury_kamionu_action,
    oznacit_k_navezeni_action, vratit_bedny_ze_stavu_k_navezeni_do_stavu_prijato_action, oznacit_navezeno_action,
    oznacit_prijato_navezeno_action, vratit_bedny_z_rozpracovanosti_do_stavu_prijato_action, vratit_bedny_ze_stavu_navezeno_do_stavu_prijato_action,
    oznacit_do_zpracovani_action, oznacit_zakaleno_action, oznacit_zkontrolovano_action, oznacit_k_expedici_action, oznacit_rovna_action,
    oznacit_kriva_action, oznacit_rovna_se_action, oznacit_vyrovnana_action, oznacit_cista_action, oznacit_spinava_action,
    oznacit_otryskana_action, prijmout_kamion_action, prijmout_zakazku_action, prijmout_bedny_action,
    export_bedny_to_csv_action, export_bedny_to_csv_customer_action, export_bedny_eurotec_dl_action, tisk_rozpracovanost_action, tisk_prehledu_zakazek_kamionu_action, expedice_beden_action,
    expedice_beden_kamion_action,
)
from .filters import (
    SklademZakazkaFilter, StavBednyFilter, KompletZakazkaFilter, AktivniPredpisFilter, SkupinaFilter, ZakaznikBednyFilter,
    ZakaznikZakazkyFilter, ZakaznikKamionuFilter, PrijemVydejFilter, TryskaniFilter, RovnaniFilter, PrioritaBednyFilter, PrioritaZakazkyFilter,
    OberflacheFilter, TypHlavyBednyFilter, TypHlavyZakazkyFilter, CelozavitBednyFilter, CelozavitZakazkyFilter, DelkaFilter, PozastavenoFilter,
    OdberatelFilter, ZakaznikPredpisFilter
)
from .forms import (
    BednaAdminForm,
    BednaChangeListForm,
    ImportZakazekForm,
    ZakazkaInlineForm,
    ZakazkaAdminForm,
    ZakazkaMeasurementForm,
)
from .choices import (
    StavBednyChoice, RovnaniChoice, TryskaniChoice, PrioritaChoice, KamionChoice, PrijemVydejChoice, SklademZakazkyChoice,
    BARVA_SKUPINY_TZ, STAV_BEDNY_ROZPRACOVANOST, STAV_BEDNY_SKLADEM, STAV_BEDNY_PRO_NAVEZENI,
)
from .utils import utilita_validate_excel_upload, build_postup_vyroby_cases

import logging
logger = logging.getLogger('orders')

@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    """
    Správa oprávnění v administraci.
    """
    list_display = ('name', 'codename', 'content_type')
    search_fields = ('name', 'codename')
    list_filter = ('content_type',)


@admin.register(Zakaznik)
class ZakaznikAdmin(SimpleHistoryAdmin):
    """
    Správa zákazníků v administraci.
    """
    # Parametry pro zobrazení detailu v administraci
    fieldsets = [
        ('Název a adresa', {
            'fields': ('nazev', 'adresa', 'mesto', 'psc', 'stat', 'zkratka_statu',)
        }),
        ('Kontaktní údaje', {
            'fields': ('kontaktni_osoba', 'telefon', 'email',)
        }),
        ('Podmínky a nastavení', {
            'fields': ('proforma_po_bednach', 'vse_tryskat', 'pouze_komplet', 'fakturovat_rovnani', 'fakturovat_tryskani',)
        }),
        ('Doplňující parametry', {
            'fields': ('zkraceny_nazev', 'zkratka', 'ciselna_rada',)
        })
    ]
    readonly_fields = ('zkratka',)
    
    # Parametry pro zobrazení seznamu v administraci
    list_display = ('nazev', 'zkraceny_nazev', 'zkratka', 'adresa', 'mesto', 'psc', 'stat', 'kontaktni_osoba', 'telefon',
                    'email', 'get_proforma_po_bednach', 'vse_tryskat', 'pouze_komplet', 'get_fakturovat_rovnani', 'get_fakturovat_tryskani', 'ciselna_rada',)
    ordering = ('nazev',)
    list_per_page = 20

    # Parametry pro zobrazení historie v administraci
    history_list_display = ["id", "nazev", "zkratka", "adresa", "mesto", "psc", "stat", "zkratka_statu", "kontaktni_osoba", "telefon", "email"]
    history_search_fields = ["nazev"]
    history_list_per_page = 20

    @admin.display(boolean=True, description='Fakt. rovn.')
    def get_fakturovat_rovnani(self, obj):
        """
        Vrací hodnotu fakturovat_rovnani pro zákazníka.
        """
        return obj.fakturovat_rovnani

    @admin.display(boolean=True, description='Fakt. trysk.')
    def get_fakturovat_tryskani(self, obj):
        """
        Vrací hodnotu fakturovat_tryskani pro zákazníka.
        """
        return obj.fakturovat_tryskani

    @admin.display(boolean=True, description='Po bednách')
    def get_proforma_po_bednach(self, obj):
        """
        Vrací hodnotu proforma_po_bednach pro zákazníka.
        """
        return obj.proforma_po_bednach

    def get_readonly_fields(self, request, obj = None):
        """
        Přizpůsobení readonly_fields pro detail zákazníka.
        V případě, že se vytváří nový zákazník (obj je None), pole 'zkratka' není readonly.
        """
        currently_readonly = list(super().get_readonly_fields(request, obj)) or []
        if obj is None:
            if 'zkratka' in currently_readonly:
                currently_readonly.remove('zkratka')
        return currently_readonly

    def delete_selected_one(self, request, queryset):
        """
        Obálka pro akci smazání, která umožňuje smazat pouze jeden vybraný záznam.
        Pokud je vybráno více nebo méně záznamů, zobrazí chybovou zprávu.
        """
        count = queryset.count()
        if count != 1:
            self.message_user(request, f"Pro smazání vyberte právě jednu položku (vybráno: {count}).", messages.ERROR)
            return
        return admin_delete_selected(self, request, queryset)
    delete_selected_one.allowed_permissions = ('delete',)

    def get_actions(self, request):
        """
        Přizpůsobení dostupných akcí v administraci.
        Nahrazení výchozí akce delete_selected vlastní obálkou s kontrolou počtu vybraných záznamů.
        """
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            actions['delete_selected'] = (
                self.__class__.delete_selected_one,
                'delete_selected',
                getattr(admin_delete_selected, 'short_description', 'Smazat vybrané'),
            )
        return actions

    def has_delete_permission(self, request, obj=None):
        """
        Skryje možnost mazání pro konkrétního zákazníka, pokud obsahuje kamiony.
        Hromadnou akci neblokuje (řeší se v modelu pomocí on_delete.PROTECT).
        """
        if obj is not None:
            if obj.kamiony.exists():
                return False
        return super().has_delete_permission(request, obj)    


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
              'priorita', 'pocet_beden', 'celkova_hmotnost', 'celkove_mnozstvi', 'tara', 'material', 'odfosfatovat',)
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
                can_view_related=False,
            )
            return formfield

        return super().formfield_for_dbfield(db_field, request, **kwargs)


class ZakazkaKamionPrijemInline(admin.TabularInline):
    """
    Inline pro správu zakázek v rámci kamionu příjem.
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
    fields = ('artikl', 'kamion_prijem', 'prumer', 'delka', 'popis', 'celkovy_pocet_beden',
              'tvrdost_povrchu', 'tvrdost_jadra', 'ohyb', 'krut', 'hazeni',)
    readonly_fields = ('artikl', 'kamion_prijem', 'prumer', 'delka', 'popis', 'celkovy_pocet_beden',)
    select_related = ('kamion_prijem', 'predpis',)
    show_change_link = True
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={'size': '20'})},
        models.DecimalField: {
            'widget': TextInput(attrs={'size': '8'}),
            'localize': True
        },
    }

    @admin.display(description='Beden', ordering='bedny__count')
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
    Kamiony mohou být typu příjem nebo výdej.
    Inline pro správu zakázek kamionu se mění dle typu kamionu (příjem/výdej) a dle toho, zda se jedná o přidání nebo editaci.
    Akce dostupné v administraci umožňují import kamionu, tisk karet beden, tisk dodacího listu, tisk proforma faktury a přijetí kamionu.
    """
    # Použité akce
    actions = [
        import_kamionu_action,
        tisk_karet_beden_kamionu_action,
        tisk_karet_kontroly_kvality_kamionu_action,
        tisk_dodaciho_listu_kamionu_action,
        tisk_proforma_faktury_kamionu_action,
        tisk_protokolu_kamionu_vydej_action,        
        'zadat_mereni_action',
        prijmout_kamion_action,
        tisk_prehledu_zakazek_kamionu_action,
    ]
    # Parametry pro zobrazení detailu v administraci
    fields = ('zakaznik', 'datum', 'poradove_cislo', 'cislo_dl', 'prijem_vydej', 'odberatel',
              'poznamka', 'text_upozorneni', 'prepsani_hmotnosti_brutto', 'get_struktura_kamionu',) # další úpravy v get_fields
    readonly_fields = ('prijem_vydej', 'poradove_cislo', 'get_struktura_kamionu',) # další úpravy v get_readonly_fields
    # Parametry pro zobrazení seznamu v administraci
    list_display = ('get_kamion_str', 'get_zakaznik_zkraceny_nazev', 'get_datum', 'cislo_dl', 'get_typ_kamionu',
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
        js = ('orders/js/admin_actions_target_blank.js',)

    def zadat_mereni_action(self, request, queryset):
        """Přesměruje na formulář pro zadání měření po kontrole oprávnění."""
        if not request.user.has_perm('orders.change_mereni_zakazky'):
            self.message_user(request, _("Nemáte oprávnění upravovat měření zakázky."), messages.ERROR)
            return

        count = queryset.count()
        if count != 1:
            self.message_user(
                request,
                _(f"Vyberte právě jeden kamión (vybráno: {count})."),
                messages.ERROR,
            )
            return

        kamion = queryset.first()
        if kamion.prijem_vydej != KamionChoice.VYDEJ:
            self.message_user(request, _("Akce je dostupná pouze pro kamión výdej."), messages.ERROR)
            return

        return redirect(reverse('admin:orders_kamion_zadani_mereni', args=[kamion.pk]))

    zadat_mereni_action.short_description = _("Zadat / upravit měření vybraného kamionu výdej")
    zadat_mereni_action.allowed_permissions = ('change_mereni_zakazky',)

    def has_change_mereni_zakazky_permission(self, request):
        return request.user.has_perm('orders.change_mereni_zakazky')

    def get_inlines(self, request, obj):
        """
        Vrací inliny pro správu zakázek kamionu v závislosti na tom,
        zda se jedná o kamion pro příjem nebo výdej a jestli jde o přidání nebo editaci.
        """
        # Pokud se jedná o editaci kamionu výdej.
        if obj and obj.prijem_vydej == KamionChoice.VYDEJ:
            return [ZakazkaKamionVydejInline]
        # Pokud se jedná o editaci kamionu příjem.
        if obj and obj.prijem_vydej == KamionChoice.PRIJEM:        
            # Pokud se jedná o přidání zakázek a beden do prázdného kamionu příjem.
            if obj and not obj.zakazky_prijem.exists():
                return [ZakazkaAutomatizovanyPrijemInline]
            return [ZakazkaKamionPrijemInline]
        return []
    
    @admin.display(description='Typ kamiónu', empty_value='-')
    def get_typ_kamionu(self, obj):
        """
        Získá typ kamionu dle stavů zakázek a beden v kamionu.
        Stavy jsou podle PrijemVydejChoice a dle níže uvedených pravidel z filtru PrijemVydejFilter.

        1. Bez zakázek - kamion, který je typu příjem a nemá žádné zakázky
        2. Nepřijatý - kamion příjem, který obsahuje bedny, ale aspoň jedna bedna je ve stavu StavBednyChoices.NEPRIJATO
        3. Komplet přijatý - kamion příjem, který neobsahuje ani jednu bednu ve stavu StavBednyChoices.NEPRIJATO
            a alespoň jedna bedna je ve stavu uvedeném ve STAV_BEDNY_SKLADEM.
        4. Vyexpedovaný - kamion příjem, který má všechny bedny ve stavu StavBednyChoices.EXPEDOVANO
        5. Výdej - kamion, který je typu výdej
        """
        if not obj or obj.prijem_vydej not in (KamionChoice.PRIJEM, KamionChoice.VYDEJ):
            return '-'
        if obj.prijem_vydej == KamionChoice.PRIJEM:
            if not obj.zakazky_prijem.exists():
                return 'Bez zakázek'
            elif obj.zakazky_prijem.filter(bedny__stav_bedny=StavBednyChoice.NEPRIJATO).exists():
                return 'Nepřijatý'
            elif (not obj.zakazky_prijem.filter(bedny__stav_bedny=StavBednyChoice.NEPRIJATO).exists() and
                  obj.zakazky_prijem.filter(bedny__stav_bedny__in=STAV_BEDNY_SKLADEM).exists()):
                return 'Komplet přijatý'
            elif not obj.zakazky_prijem.filter(expedovano=False).exists():
                return 'Vyexpedovaný'
            else:
                return '-'
        elif obj.prijem_vydej == KamionChoice.VYDEJ:
            return 'Výdej'
    
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

    # --- UX blokace mazání kamionu ---
    def _delete_blockers(self, obj):
        """
        Vrátí seznam důvodů, proč nelze kamion smazat (pro hlášky).
        Pro kamion výdej: pokud je přiřazen k zakázkám.
        Pro kamion příjem: pokud obsahuje bedny, které nejsou ve stavu NEPRIJATO.
        """
        reasons = []
        if not obj:
            return reasons
        
        if obj.prijem_vydej == KamionChoice.PRIJEM:
            # Blokovat jen pokud existuje aspoň jedna bedna v jiném stavu než NEPRIJATO
            total = Bedna.objects.filter(zakazka__kamion_prijem=obj).count()
            non_neprijato = Bedna.objects.filter(zakazka__kamion_prijem=obj).exclude(stav_bedny=StavBednyChoice.NEPRIJATO).count()
            if non_neprijato:
                reasons.append(
                    f"Kamión příjem nelze smazat: obsahuje {non_neprijato} beden mimo stav NEPRIJATO (z celkem {total})."
                )

        elif obj.prijem_vydej == KamionChoice.VYDEJ:
            z_count = obj.zakazky_vydej.count()
            if z_count:
                b_count = Bedna.objects.filter(zakazka__kamion_vydej=obj).count()
                reasons.append(
                    f"Kamión výdej nelze smazat: je přiřazen k {z_count} zakázkám (a {b_count} bednám)."
                )
        return reasons

    def has_delete_permission(self, request, obj=None):
        """
        Skryje možnost mazání pro konkrétní kamion, pokud má návaznosti.
        Hromadnou akci neblokuje (řeší se v delete_queryset s hláškou).
        """
        if obj is not None:
            if self._delete_blockers(obj):
                return False
        return super().has_delete_permission(request, obj)

    def delete_model(self, request, obj):
        """Při mazání z detailu zablokuje s jasnou hláškou, pokud jsou návaznosti."""
        reasons = self._delete_blockers(obj)
        if reasons:
            for r in reasons:
                try:
                    messages.error(request, r)
                except Exception:
                    pass
            return  # Nic nemaž – ponech uživatele na stránce
        return super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        """
        Při hromadném mazání smaže jen kamiony bez návazností a pro ostatní vypíše důvod.
        """
        allowed_ids = []
        blocked_info = []

        for obj in queryset:
            reasons = self._delete_blockers(obj)
            if reasons:
                blocked_info.append((obj, reasons))
            else:
                allowed_ids.append(obj.pk)

        if blocked_info:
            for obj, reasons in blocked_info:
                for r in reasons:
                    try:
                        messages.error(request, f"{obj}: {r}")
                    except Exception:
                        pass

        if allowed_ids:
            super().delete_queryset(request, queryset.filter(pk__in=allowed_ids))
        # Pokud nic nepovoleno, jen vrátí – akce skončí s vypsanými hláškami

    def get_list_display(self, request):
        """
        Přizpůsobení zobrazení sloupců v seznamu zakázek podle aktivního filtru.
        Pokud je vybraný filtr PrijemVydejFilter a má hodnoty PRIJEM_NEPRIJATY nebo PRIJEM_KOMPLET_PRIJATY, 
        odebere se sloupec get_pocet_beden_skladem.
        Pokud je vybraný filtr PrijemVydejFilter a má hodnotu VYDEJ, odebere se sloupec odberatel.
        """
        ld = list(super().get_list_display(request))
        if request.GET.get('prijem_vydej') not in (None, PrijemVydejChoice.PRIJEM_NEPRIJATY, PrijemVydejChoice.PRIJEM_KOMPLET_PRIJATY):
            if 'get_pocet_beden_skladem' in ld:
                ld.remove('get_pocet_beden_skladem')
        if request.GET.get('prijem_vydej') not in (None, PrijemVydejChoice.VYDEJ):
            if 'odberatel' in ld:
                ld.remove('odberatel')
        return ld

    def get_fields(self, request, obj=None):
        """
        Vrací seznam polí, která se mají zobrazit ve formuláře Kamion při přidání nového a při editaci.

        - Pokud není obj (tj. add_view), zruší se zobrazení pole `prijem_vydej`, `odberatel`, `poznamka`, `text_upozorneni`,
          `prepsani_hmotnosti_brutto` a `get_struktura_kamionu`.
        - Pokud je obj a kamion je pro příjem, zruší se zobrazení pole `odberatel`, `poznamka`, `text_upozorneni` a `prepsani_hmotnosti_brutto`.
        """
        fields = list(super().get_fields(request, obj))

        if not obj:  # Pokud se jedná o přidání nového kamionu
            fields = [f for f in fields if f not in ('prijem_vydej', 'odberatel', 'poznamka', 'text_upozorneni', 'prepsani_hmotnosti_brutto', 'get_struktura_kamionu')]
        if obj and obj.prijem_vydej == KamionChoice.PRIJEM:
            fields = [f for f in fields if f not in ('odberatel', 'poznamka', 'text_upozorneni', 'prepsani_hmotnosti_brutto')]
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

    @admin.display(description='Struktura kamionu')
    def get_struktura_kamionu(self, obj):
        """Vrátí HTML strukturu kamionu s podřízenými zakázkami a bednami."""
        if not obj:
            return _('Struktura bude dostupná po uložení kamionu.')

        relation_name = 'zakazky_prijem' if obj.prijem_vydej == KamionChoice.PRIJEM else 'zakazky_vydej'
        zakazky_qs = (
            getattr(obj, relation_name)
            .all()
            .select_related('predpis')
            .order_by('id')
            .prefetch_related(
                Prefetch('bedny', queryset=Bedna.objects.select_related('pozice').order_by('cislo_bedny'))
            )
        )
        zakazky = list(zakazky_qs)
        if not zakazky:
            return _('Kamion neobsahuje žádné zakázky.')

        def fmt_decimal(value):
            if value is None:
                return '–'
            formatted = format(value, 'f').rstrip('0').rstrip('.')
            return formatted or '0'

        order_blocks = []
        total_bedny = 0
        for zakazka in zakazky:
            bedny = list(zakazka.bedny.all())
            total_bedny += len(bedny)
            if bedny:
                bedny_list = format_html_join(
                    '',
                    '<li><a href="{0}">#{1}{2}</a> · hmotnost: {3} kg · tára: {4} kg{5} · stav: {6}{7}</li>',
                    (
                        (
                            bedna.get_admin_url(),
                            bedna.cislo_bedny,
                            f' (#{bedna.behalter_nr})' if bedna.behalter_nr else '',
                            fmt_decimal(bedna.hmotnost),
                            fmt_decimal(bedna.tara),
                            f' · FA / Bestell-Nr.: {bedna.vyrobni_zakazka}' if bedna.vyrobni_zakazka else '',
                            bedna.get_stav_bedny_display(),
                            f' · pozice: {bedna.pozice.kod}' if bedna.pozice else ''
                        )
                        for bedna in bedny
                    )
                )
            else:
                bedny_list = format_html('<li><em>Žádné bedny</em></li>')

            order_blocks.append(
                format_html(
                    '<li>'
                    '<div class="kamion-structure__order-header">'
                    '<strong><a href="{0}">{1}</a></strong>'
                    '<span class="kamion-structure__order-meta"> · Ø {2} × {3} · předpis: {4} · bedny: {5}</span>'
                    '</div>'
                    '<ul class="kamion-structure__boxes">{6}</ul>'
                    '</li>',
                    zakazka.get_admin_url(),
                    zakazka.artikl,
                    fmt_decimal(zakazka.prumer),
                    fmt_decimal(zakazka.delka),
                    zakazka.predpis.nazev if zakazka.predpis else '–',
                    len(bedny),
                    bedny_list,
                )
            )

        orders_html = format_html(
            '<ul class="kamion-structure__orders">{}</ul>',
            format_html_join('', '{}', ((block,) for block in order_blocks))
        )
        summary = _('Zobrazit strukturu kamionu ({orders} zakázek / {boxes} beden / {netto} kg netto / {brutto} kg brutto)').format(
            orders=len(zakazky),
            boxes=total_bedny,
            netto=fmt_decimal(obj.celkova_hmotnost_netto),
            brutto=fmt_decimal(obj.celkova_hmotnost_brutto),
        )

        return format_html(
            '<details class="kamion-structure">'
            '<summary>{0}</summary>'
            '<div class="kamion-structure__content">'
            '<style>'
            '.kamion-structure__content ul{{margin:0;padding-left:1.2em;}}'
            '.kamion-structure__order-header{{margin:0.25em 0;}}'
            '.kamion-structure__orders>li{{margin-bottom:0.75em;}}'
            '.kamion-structure__boxes{{margin-top:0.3em;}}'
            '.kamion-structure__boxes li{{margin-bottom:0.2em;}}'
            '</style>'
            '{1}'
            '</div>'
            '</details>',
            summary,
            orders_html,
        )
    
    def get_actions(self, request):
        """
        Přizpůsobí dostupné akce v administraci podle filtru typu kamionu
        (příjem - bez zakázek, příjem - nepřijatý, příjem - komplet přijatý, příjem - vyexpedovaný, výdej).
        Odstraní akce, které nejsou relevantní pro daný typ kamionu.
        """
        actions = super().get_actions(request)

        if (request.GET.get('prijem_vydej') == PrijemVydejChoice.PRIJEM_BEZ_ZAKAZEK):
            actions_to_remove = [
                'tisk_karet_beden_kamionu_action',
                'tisk_karet_kontroly_kvality_kamionu_action',
                'tisk_dodaciho_listu_kamionu_action',
                'tisk_proforma_faktury_kamionu_action',
                'tisk_prehledu_zakazek_kamionu_action',
                'zadat_mereni_action',
                'tisk_protokolu_kamionu_vydej_action',                
                'prijmout_kamion_action'
            ]
        elif (request.GET.get('prijem_vydej') == PrijemVydejChoice.PRIJEM_NEPRIJATY):
            actions_to_remove = [
                'import_kamionu_action',
                'tisk_karet_beden_kamionu_action',
                'tisk_karet_kontroly_kvality_kamionu_action',
                'tisk_dodaciho_listu_kamionu_action',
                'tisk_proforma_faktury_kamionu_action',
                'zadat_mereni_action',
                'tisk_prehledu_zakazek_kamionu_action',
                'tisk_protokolu_kamionu_vydej_action',                
            ]
        elif (request.GET.get('prijem_vydej') == PrijemVydejChoice.PRIJEM_KOMPLET_PRIJATY):
            actions_to_remove = [
                'import_kamionu_action',                
                'tisk_dodaciho_listu_kamionu_action',
                'tisk_proforma_faktury_kamionu_action',
                'zadat_mereni_action',
                'tisk_protokolu_kamionu_vydej_action',                
                'prijmout_kamion_action',
                'delete_selected'
            ]
        elif (request.GET.get('prijem_vydej') == PrijemVydejChoice.PRIJEM_VYEXPEDOVANY):
            actions_to_remove = [
                'import_kamionu_action',
                'tisk_karet_beden_kamionu_action',
                'tisk_karet_kontroly_kvality_kamionu_action',
                'tisk_dodaciho_listu_kamionu_action',
                'tisk_proforma_faktury_kamionu_action',
                'zadat_mereni_action',
                'tisk_protokolu_kamionu_vydej_action',                
                'prijmout_kamion_action',
                'delete_selected'
            ]
        elif (request.GET.get('prijem_vydej') == PrijemVydejChoice.VYDEJ):
            actions_to_remove = [
                'import_kamionu_action',
                'tisk_karet_beden_kamionu_action',
                'tisk_karet_kontroly_kvality_kamionu_action',
                'prijmout_kamion_action',
                'tisk_prehledu_zakazek_kamionu_action',
                'delete_selected'
            ]            
        else:
            actions_to_remove = []

        # Vždy nahradí "delete_selected" obálkou s kontrolou 1 položky
        if 'delete_selected' in actions:
            actions['delete_selected'] = (
                self.__class__.delete_selected_one,
                'delete_selected',
                getattr(admin_delete_selected, 'short_description', 'Smazat vybrané'),
            )

        for action in actions_to_remove:
            if action in actions:
                del actions[action]

        return actions

    def delete_selected_one(self, request, queryset):
        """
        Obálka pro akci smazání, která umožňuje smazat pouze jeden vybraný záznam.
        Pokud je vybráno více nebo méně záznamů, zobrazí chybovou zprávu.
        """
        count = queryset.count()
        if count != 1:
            self.message_user(request, f"Pro smazání vyberte právě jednu položku (vybráno: {count}).", messages.ERROR)
            return
        return admin_delete_selected(self, request, queryset)

    def get_action_choices(self, request, default_choices=models.BLANK_CHOICE_DASH):
        """Seskupení akcí kamionu do optgroup + formátování placeholderů.

        Skupiny:
        - Import / Příjem
        - Tisk karet
        - Tisk dokladů
        - Měření
        Ostatní (delete_selected) spadne do 'Ostatní'.
        """
        actions = self.get_actions(request)
        if not actions:
            return default_choices

        group_map = {
            'import_kamionu_action': 'Import / Příjem',
            'prijmout_kamion_action': 'Import / Příjem',
            'tisk_karet_beden_kamionu_action': 'Tisk karet',
            'tisk_karet_kontroly_kvality_kamionu_action': 'Tisk karet',
            'tisk_dodaciho_listu_kamionu_action': 'Tisk dokladů',
            'tisk_proforma_faktury_kamionu_action': 'Tisk dokladů',
            'tisk_protokolu_kamionu_vydej_action': 'Tisk dokladů',
            'tisk_prehledu_zakazek_kamionu_action': 'Měření',        
            'zadat_mereni_action': 'Měření',          
        }
        order = ['Import / Příjem', 'Tisk karet', 'Tisk dokladů', 'Měření']
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
                # Přidat skupinu akcí bez řazení akcí uvnitř skupiny
                choices.append((g, opts))
                # # Seřadit akce podle názvu                
                # choices.append((g, sorted(opts, key=lambda x: x[1].lower())))
        return choices

    def get_urls(self):
        """
        Přidá vlastní URL pro import zakázek do kamionu.
        """
        urls = super().get_urls()
        custom_urls = [
            path('<path:object_id>/zadani-mereni/', self.admin_site.admin_view(self.zadani_mereni_view), name='orders_kamion_zadani_mereni'),
            path('import-zakazek/', self.admin_site.admin_view(self.import_view), name='import_zakazek_beden'),
        ]
        return custom_urls + urls

    def zadani_mereni_view(self, request, object_id):
        """Zobrazí a zpracuje formulář pro zadání měření zakázek kamionu výdej."""
        kamion = self.get_object(request, object_id)
        changelist_url = reverse('admin:orders_kamion_changelist')

        if kamion is None:
            self.message_user(request, _("Kamión nebyl nalezen."), messages.ERROR)
            return redirect(changelist_url)

        if kamion.prijem_vydej != KamionChoice.VYDEJ:
            self.message_user(request, _("Akce je dostupná pouze pro kamión výdej."), messages.ERROR)
            return redirect(kamion.get_admin_url())

        if not request.user.has_perm('orders.change_mereni_zakazky'):
            self.message_user(request, _("Nemáte oprávnění upravovat měření zakázky."), messages.ERROR)
            return redirect(kamion.get_admin_url())

        queryset = kamion.zakazky_vydej.all().select_related('kamion_prijem').order_by('id')
        MeasurementFormSet = modelformset_factory(Zakazka, form=ZakazkaMeasurementForm, extra=0)

        if request.method == 'POST':
            formset = MeasurementFormSet(request.POST, queryset=queryset)
            if formset.is_valid():
                formset.save()
                self.message_user(request, _("Měření zakázek bylo uloženo."), messages.SUCCESS)
                return redirect(kamion.get_admin_url())
            self.message_user(request, _("Zadaná data obsahují chyby. Opravte je prosím."), messages.ERROR)
        else:
            formset = MeasurementFormSet(queryset=queryset)

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'original': kamion,
            'camion': kamion,
            'formset': formset,
            'media': self.media + formset.media,
            'title': _("Zadat / upravit měření kamionu výdej"),
            'back_url': kamion.get_admin_url(),
            'changelist_url': changelist_url,
        }
        return render(request, 'admin/orders/kamion/zadani_mereni.html', context)
    
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

    def _get_import_strategy(self, kamion) -> BaseImportStrategy:
        """
        Vrátí strategii importu podle zákazníka (zatím pouze EUR a SPX).
        Pro ostatní zákazníky vrací výchozí strategii, která nemá definovanou logiku.
        """
        try:
            zkratka = getattr(getattr(kamion, 'zakaznik', None), 'zkratka', None)
        except Exception:
            zkratka = None
        match zkratka:
            case 'EUR':
                return EURImportStrategy()
            case 'SPX':
                return SPXImportStrategy()
            case _:
                return BaseImportStrategy()

    def import_view(self, request):
        """
        Zobrazí formulář pro import zakázek do kamionu a zpracuje nahraný soubor.
        Umožňuje importovat zakázky z Excel souboru a automaticky vytvoří bedny na základě dat v souboru.
        Zakázky jsou odděleny podle artiklu a šarže, přičemž každá unikátní kombinace tvoří jednu zakázku.
        Zatím funguje pouze pro kamiony EUR a SPX, ale je navrženo tak, aby bylo možné přidat další zákazníky
        s vlastními strategiemi importu.
        Strategie importu je určena na základě zkratky zákazníka kamionu a je implementována pomocí návrhového vzoru Strategy.
        1. Načte nahraný Excel soubor a zvaliduje jeho strukturu.
        2. Zobrazí náhled dat před samotným importem.
        3. Uloží zakázky a bedny do databáze, pokud uživatel potvrdí import bez chyb.
        4. Zobrazí chyby a varování během procesu importu.
        5. Umožní opakovaný import s novým souborem nebo zobrazení náhledu bez uložení.
        6. Používá dočasné soubory pro zpracování nahraných dat a správu relací uživatelů.
        7. Loguje klíčové události pro audit a sledování akcí uživatelů.
        8. Zajišťuje transakční integritu při ukládání dat do databáze.
        9. Validuje povinná pole před uložením zakázek.
        10. Poskytuje uživatelsky přívětivé rozhraní pro správu importu zakázek v administraci Django.
        11. Podporuje HTMX pro dynamické aktualizace části stránky bez nutnosti plného reloadu.
        12. Umožňuje přizpůsobení importní logiky pro různé zákazníky pomocí strategií.
        """
        kamion_id = request.GET.get("kamion")
        kamion = Kamion.objects.get(pk=kamion_id) if kamion_id else None
        errors: list[str] = []
        warnings: list[str] = []
        preview: list[dict] = []
        required_fields: list[str] = []

        strategy = self._get_import_strategy(kamion)

        if request.method == 'POST':
            logger.info(f"Uživatel {request.user} zahájil import zakázek pro kamion {kamion}.")
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
                        
                    try:
                        df, preview, parse_errors, parse_warnings, required_fields = strategy.parse_excel(
                            excel_stream, request, kamion
                        )
                        errors.extend(parse_errors)
                        warnings.extend(parse_warnings)
                    except NotImplementedError:
                        msg = "Strategie importu pro tohoto zákazníka není implementována."
                        logger.error(msg)
                        errors.append(msg)
                    finally:
                        # zavřít handle, pokud je z uloženého souboru
                        try:
                            if saved_path and excel_stream:
                                excel_stream.close()
                        except Exception:
                            pass

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
                            if not required_fields:
                                required_fields = strategy.get_required_fields()
                            for field in required_fields:
                                if pd.isna(row[field]):
                                    logger.error(f"Chyba: Povinné pole '{field}' nesmí být prázdné.")
                                    raise ValueError(f"Chyba: Povinné pole '{field}' nesmí být prázdné.")

                            cache_key = strategy.get_cache_key(row)

                            if cache_key not in zakazky_cache:
                                zakazka_kwargs = strategy.map_row_to_zakazka_kwargs(row, kamion, warnings)
                                zakazky_cache[cache_key] = Zakazka.objects.create(**zakazka_kwargs)

                            bedna_kwargs = strategy.map_row_to_bedna_kwargs(row)
                            Bedna.objects.create(
                                zakazka=zakazky_cache[cache_key],
                                **bedna_kwargs,
                            )

                    logger.info(f"Uživatel {request.user} úspěšně uložil zakázky a bedny pro kamion {kamion}.")
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
                    logger.error(f"Chyba při importu zakázek pro kamion {kamion}: {e}")
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
        Při úpravách stávajícího kamionu, který už obsahuje zakázky, se pouze uloží všechny změny do databáze bez vytvoření beden.
        """
        # Zajistit existenci atributů používaných admin utilitou construct_change_message
        for _attr in ("new_objects", "changed_objects", "deleted_objects"):
            if not hasattr(formset, _attr):
                setattr(formset, _attr, [])

        try:
            fk_name = getattr(getattr(formset, "fk", None), "name", None)

            # Pokud inline nepracuje s kamionem příjem, ukládá se standardně bez automatického vytváření beden.
            if fk_name is not None and fk_name != 'kamion_prijem':
                formset.save()
                return

            # Úprava stávajícího kamionu s již existujícími zakázkami - pouze uloží změny
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

                    # Ulož M2M vazby pro tento formulář (pokud nějaké jsou)
                    if hasattr(inline_form, 'save_m2m'):
                        try:
                            inline_form.save_m2m()
                        except Exception:
                            pass

                    # Získání dodatečných hodnot z vlastního formuláře zakázky (bezpečné převody z None)
                    celkova_hmotnost = inline_form.cleaned_data.get("celkova_hmotnost")
                    celkove_mnozstvi = inline_form.cleaned_data.get("celkove_mnozstvi")
                    pocet_beden = inline_form.cleaned_data.get("pocet_beden")
                    tara = inline_form.cleaned_data.get("tara")
                    material = inline_form.cleaned_data.get("material")
                    # BooleanField nepřenáší False, když není zaškrtnuto -> může být None
                    odfosfatovat = bool(inline_form.cleaned_data.get("odfosfatovat") or False)

                    # Vytvoření beden zakázky, pokud je zadán počet beden 
                    if pocet_beden and pocet_beden > 0:
                        # Shromažďování varování pro jednu souhrnnou hlášku
                        warnings_for_order = []
                        # Pokud je zadána celková hmotnost, rozpočítá se na jednotlivé bedny, pro poslední bednu se použije
                        # zbytek hmotnosti po rozpočítání a zaokrouhlení
                        if celkova_hmotnost and celkova_hmotnost > 0:
                            # Zajistit Decimal (testy posílají int/float)
                            if not isinstance(celkova_hmotnost, Decimal):
                                try:
                                    celkova_dec = Decimal(str(celkova_hmotnost))
                                except Exception:
                                    celkova_dec = Decimal(celkova_hmotnost)
                            else:
                                celkova_dec = celkova_hmotnost
                            jednotkova = (celkova_dec / pocet_beden).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
                            hodnoty = [jednotkova] * (pocet_beden - 1)
                            posledni = (celkova_dec - sum(hodnoty)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
                            hodnoty.append(posledni)
                        else:
                            hodnoty = [None] * pocet_beden
                            warnings_for_order.append("není zadána celková hmotnost - hmotnosti beden nebudou nastaveny")
                        # Pokud je zadáno celkové množství, rozpočítá se jednoduše na jednotlivé bedny, je to orientační hodnota
                        if celkove_mnozstvi and celkove_mnozstvi > 0:
                            mnozstvi_bedny = celkove_mnozstvi // pocet_beden
                        else:
                            mnozstvi_bedny = None
                            warnings_for_order.append("není zadáno celkové množství - množství v bednách nebude nastaveno")

                        if not (tara and tara > 0):
                            tara = None                        
                            warnings_for_order.append("není zadána hodnota v poli tára - tára nebude nastavena")

                        # Pokud vznikly varování, pošle se jedna souhrnnou hlášku
                        if warnings_for_order:
                            try:
                                messages.info(
                                    request,
                                    _(f"U zakázky {zakazka} {', '.join(warnings_for_order)}.")
                                )
                            except Exception:
                                pass

                        for i in range(pocet_beden):
                            Bedna.objects.create(
                                zakazka=zakazka,
                                hmotnost=hodnoty[i],
                                tara=tara,
                                material=material,
                                mnozstvi=mnozstvi_bedny,
                                odfosfatovat=odfosfatovat,
                                # cislo_bedny se dopočítá v metodě save() modelu Bedna
                            )

                    # Pokud není zadán počet beden, nevytváří se automaticky žádné bedny a dá se info
                    else:
                        messages.info(
                            request,
                            _(f"U zakázky {zakazka} je zadán počet beden nula, nebudou vytvořeny žádné bedny.")
                        )
                        logger.info(
                            _(f"U zakázky {zakazka} je zadán počet beden nula, nebudou vytvořeny žádné bedny.")
                        )

                    # Zaznamená nově vytvořenou zakázku pro change log
                    if zakazka not in formset.new_objects:
                        formset.new_objects.append(zakazka)

        except ProtectedError:
            # Uživatelsky přívětivá zpráva místo tracebacku
            try:
                messages.error(request, _("Zakázku nelze smazat: obsahuje bedny, které nejsou ve stavu NEPRIJATO."))
            except Exception:
                pass
            logger.warning("Mazání zakázky zablokováno (ProtectedError).")
            return


class BednaInline(admin.TabularInline):
    """
    Inline pro správu beden v rámci zakázky.
    Zobrazuje a umožňuje upravovat bedny patřící k zakázce.
    """
    model = Bedna
    form = BednaAdminForm
    extra = 0
    # další úprava zobrazovaných polí podle různých podmínek je v get_fields
    fields = ('cislo_bedny', 'behalter_nr', 'hmotnost', 'tara', 'brutto', 'mnozstvi', 'material', 'sarze', 'dodatecne_info',
              'dodavatel_materialu', 'vyrobni_zakazka', 'odfosfatovat', 'stav_bedny', 'tryskat', 'rovnat', 'poznamka',)
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
        - Pokud je obj (tj. edit_view) a zákazník kamionu příjmu je SPX, vyloučí se pole `dodatecne_info` a
            `dodavatel_materialu`. 
        - Pokud je obj (tj. edit_view) a zákazník kamionu příjmu je 'SSH', 'SWG', 'HPM', 'FIS',
            vyloučí se pole `behalter_nr`, `dodatecne_info`, `dodavatel_materialu` a `vyrobni_zakazka`.
        - Pokud je obj (tj. edit_view) a všechny bedny zakázky mají vyplněné pole `tara` větší než nula, vyloučí se pole `brutto`.
        """
        fields = list(super().get_fields(request, obj))
        exclude_fields = []
        if obj:  # očekává se Zakazka (parent objekt inlinu)
            zakazka_inst = obj
            kamion_prijem = getattr(obj, 'kamion_prijem', None)
            zkratka = getattr(getattr(kamion_prijem, 'zakaznik', None), 'zkratka', None)
            if zkratka == 'ROT':
                exclude_fields.extend(['dodatecne_info', 'dodavatel_materialu', 'vyrobni_zakazka'])
            elif zkratka == 'SPX':
                exclude_fields.extend(['dodatecne_info', 'dodavatel_materialu'])
            elif zkratka in ('SSH', 'SWG', 'HPM', 'FIS'):
                exclude_fields.extend(['behalter_nr', 'dodatecne_info', 'dodavatel_materialu', 'vyrobni_zakazka'])

            # Pokud všechny bedny zakázky mají vyplněnou taru větší než nula, vyloučit brutto
            if zakazka_inst and hasattr(zakazka_inst, 'bedny') and zakazka_inst.bedny.exists():
                if not zakazka_inst.bedny.exclude(tara__gt=0).exists():
                    exclude_fields.append('brutto')
        else:  # add view
            exclude_fields.append('cislo_bedny')
        return [f for f in fields if f not in exclude_fields]

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
        - Pokud je bedna pozastavena a uživatel má příslušná oprávnění, dojde pouze k vizuálnímu zvýraznění polí.
        - Pokud je bedna pozastavena a uživatel nemá oprávnění, zakáže se možnost změny polí.
        """
        Formset = super().get_formset(request, obj, **kwargs)

        class CustomFormset(Formset):
            def __init__(self_inner, *args, **kwargs):
                super().__init__(*args, **kwargs)
                for form in self_inner.forms:
                    bedna = form.instance
                    if bedna.pozastaveno:
                        for field_name, field in form.fields.items():
                            # Vizuální zvýraznění pozastavených polí
                            try:
                                existing = field.widget.attrs.get('class', '')
                                field.widget.attrs['class'] = (existing + ' paused-row').strip()
                            except Exception:
                                pass
                            if not request.user.has_perm('orders.change_pozastavena_bedna'):
                                # Pole DELETE se dá disabled pouze pokud je bedna v stavu NEPRIJATO,
                                # protože dále v kódu se disablují pole DELETE pro všechny bedny mimo stav NEPRIJATO
                                if field_name == 'DELETE' and bedna.pk and bedna.stav_bedny != StavBednyChoice.NEPRIJATO:
                                    continue
                                # Hidden pole se přeskočí, jinak by zmizela hodnota ID bedny a nastala chyba při uložení
                                if field.widget.is_hidden:
                                    continue
                                field.required = False
                                field.disabled = True

                    delete_field = form.fields.get('DELETE')
                    if delete_field and bedna.pk and bedna.stav_bedny != StavBednyChoice.NEPRIJATO:
                        delete_field.disabled = True
                        delete_field.initial = False
                        delete_field.help_text = _('Mazání je povoleno pouze pro bedny ve stavu NEPRIJATO.')

        return CustomFormset
    

@admin.register(Zakazka)
class ZakazkaAdmin(SimpleHistoryAdmin):
    """
    Správa zakázek v administraci.
    Umožňuje správu zakázek, jejich inline beden, tisk karet beden a kontroly kvality,
    expedici zakázek a další akce.
    """
    # Použité inline, formuláře a akce
    inlines = [BednaInline]
    form = ZakazkaAdminForm
    actions = [tisk_karet_beden_zakazek_action, tisk_karet_kontroly_kvality_zakazek_action, expedice_zakazek_action,
               vratit_zakazky_z_expedice_action, expedice_zakazek_kamion_action, prijmout_zakazku_action]

    # Parametry pro zobrazení detailu v administraci
    exclude = ('tvrdost_povrchu', 'tvrdost_jadra', 'ohyb', 'krut', 'hazeni')    
    readonly_fields = ('expedovano', 'get_komplet',)
    
    # Parametry pro zobrazení seznamu v administraci
    list_display = ('artikl', 'get_datum', 'kamion_prijem_link', 'kamion_vydej_link', 'get_prumer', 'get_delka_int', 'predpis_link',
                    'typ_hlavy_link', 'get_skupina_TZ', 'get_celozavit', 'get_zkraceny_popis', 'priorita', 'get_odberatel',
                    'hmotnost_zakazky_k_expedici_brutto', 'pocet_beden_k_expedici', 'celkovy_pocet_beden', 'get_komplet',)
    list_display_links = ('artikl',)
    # list_editable = nastavováno dynamicky v get_list_editable
    list_select_related = ("kamion_prijem", "kamion_vydej")
    search_fields = ('artikl',)
    search_help_text = "Dle artiklu"
    list_filter = (ZakaznikZakazkyFilter, SklademZakazkaFilter, OdberatelFilter, KompletZakazkaFilter, PrioritaZakazkyFilter,
                   CelozavitZakazkyFilter, TypHlavyZakazkyFilter,)
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
            'orders/js/zakazky_hmotnost_sum.js',
            'orders/js/admin_actions_target_blank.js',
            'orders/js/changelist_dirty_guard.js',
            )
        css = {
            'all': ('orders/css/admin_paused_rows.css',)
        }

    # --- UX blokace mazání zakázky ---
    def _delete_blockers(self, obj):
        """Vrátí seznam důvodů, proč nelze zakázku smazat (pokud obsahuje bedny mimo NEPRIJATO)."""
        reasons = []
        if not obj:
            return reasons
        non_neprijato = obj.bedny.exclude(stav_bedny=StavBednyChoice.NEPRIJATO).count() if obj.pk else 0
        total = obj.bedny.count() if obj.pk else 0
        if non_neprijato:
            reasons.append(
                f"Zakázku nelze smazat: obsahuje {non_neprijato} beden mimo stav NEPRIJATO (z celkem {total})."
            )
        return reasons

    def has_delete_permission(self, request, obj=None):
        """Skryje mazání na detailu u zakázky s bednami mimo NEPRIJATO."""
        if obj is not None and self._delete_blockers(obj):
            return False
        return super().has_delete_permission(request, obj)

    def delete_model(self, request, obj):
        """Blokuje smazání z detailu a vypíše důvody."""
        reasons = self._delete_blockers(obj)
        if reasons:
            for r in reasons:
                try:
                    messages.error(request, r)
                except Exception:
                    pass
            return
        return super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        """Při hromadném mazání smaže jen povolené a ostatní vypíše s důvodem."""
        allowed_ids = []
        blocked_info = []

        for obj in queryset:
            reasons = self._delete_blockers(obj)
            if reasons:
                blocked_info.append((obj, reasons))
            else:
                allowed_ids.append(obj.pk)

        if blocked_info:
            for obj, reasons in blocked_info:
                for r in reasons:
                    try:
                        messages.error(request, f"{obj}: {r}")
                    except Exception:
                        pass

        if allowed_ids:
            super().delete_queryset(request, queryset.filter(pk__in=allowed_ids))
        # Pokud nic povoleno, jen končí s vypsanými hláškami

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
        Předá hodnotu jako html s typem textu bold.
        Pokud není délka připojena, vrátí prázdný řetězec.
        """
        if obj.delka is not None:
            return mark_safe(f'<strong>{int(obj.delka.to_integral_value(rounding=ROUND_DOWN))}</strong>')
        return '-'
    
    @admin.display(description='Ø', ordering='prumer', empty_value='-')
    def get_prumer(self, obj):
        """
        Zobrazí průměr zakázky a umožní třídění podle hlavičky pole.
        Předá hodnotu jako html s typem textu bold.
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
    def get_skupina_TZ(self, obj):
        """
        Zobrazí skupinu tepelného zpracování zakázky a umožní třídění podle hlavičky pole.
        Vrátí html číslo s barvou podle skupiny - BARVA_SKUPINY_TZ.
        """
        barva = BARVA_SKUPINY_TZ[obj.predpis.skupina] if obj.predpis and obj.predpis.skupina in BARVA_SKUPINY_TZ else ''
        if obj.predpis and obj.predpis.skupina:
            return mark_safe(
                f'<span style="color: {barva["text"]}; background-color: {barva["pozadi"]}; padding: 0.1rem 0.35rem; border-radius: 0.25rem; display: inline-block;">'
                f"{obj.predpis.skupina}"
                "</span>"
            )            
        return '-'

    @admin.display(boolean=True, description='VG', ordering='celozavit')
    def get_celozavit(self, obj):
        """
        Zobrazí boolean, jestli je vrut celozávitový a umožní třídění podle hlavičky pole.
        """
        return obj.celozavit
    
    @admin.display(description='Povrch', ordering='povrch', empty_value='-')
    def get_povrch(self, obj):
        """
        Zobrazí povrch zakázky a umožní třídění podle hlavičky pole.
        """
        if obj.povrch:
            return obj.povrch
        return '-'

    @admin.display(description='Odběratel', ordering='odberatel__zkraceny_nazev', empty_value='-')
    def get_odberatel(self, obj):
        """
        Zobrazí určeného odběratele zakázky a umožní třídění podle hlavičky pole.
        """
        if obj.odberatel and obj.odberatel.zkraceny_nazev:
            return obj.odberatel.zkraceny_nazev
        elif obj.odberatel:
            return obj.odberatel.nazev
        return '-'
    
    @admin.display(description='Hlava', ordering='typ_hlavy', empty_value='-')
    def typ_hlavy_link(self, obj):
        """
        Zobrazí typ hlavy a umožní třídění podle hlavičky pole.
        """
        if obj.typ_hlavy:
            return mark_safe(f'<a href="{obj.typ_hlavy.get_admin_url()}">{obj.typ_hlavy.nazev}</a>')

    @admin.display(description="Popis zkr.", ordering='popis')
    def get_zkraceny_popis(self, obj):
        """
        Zobrazí zkrácený popis zakázky (první část před čísly) s tooltipem celého popisu
        a umožní třídění podle hlavičky pole.
        """        
        return format_html('<span title="{}">{}</span>', obj.popis, obj.zkraceny_popis)        

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
                        'fields': ['kamion_prijem', 'kamion_vydej', 'artikl', 'puvodni_zakazka', 'typ_hlavy', 'celozavit', 'prumer', 'delka', 'predpis',
                                   'priorita', 'popis', 'odberatel', 'get_komplet', 'expedovano'],
                        'description': 'Zakázka je expedovaná a nelze ji měnit.',
                    }),
                ]
            else:  # Pokud zakázka není expedovaná, zobrazí se základní pole pro editaci
                my_fieldsets = [
                    ('Zakázka skladem:', {
                        'fields': ['kamion_prijem', 'artikl', 'puvodni_zakazka', 'typ_hlavy', 'celozavit', 'prumer', 'delka', 'predpis',
                                   'priorita', 'popis', 'odberatel', 'get_komplet', 'expedovano'],
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
        
    def get_readonly_fields(self, request, obj = None):
        """
        Přizpůsobí readonly_fields podle toho, zda je zakázka expedovaná.
        Pokud je zakázka expedovaná a uživatel má oprávnění 'orders.change_expedovana_zakazka',
        přidají se další pole jako readonly, kvůli případným vzniklým nekonzistencím po změně těchto polí.
        """
        current_readonly_fields = list(super().get_readonly_fields(request, obj))
        added_readonly_fields = []
        if obj and obj.expedovano:
            added_readonly_fields = ['kamion_prijem', 'kamion_vydej',]
        return current_readonly_fields + added_readonly_fields        
   
    def get_actions(self, request):
        """
        Přizpůsobí dostupné akce v administraci podle filtru stavu bedny.
        Standardně jsou dostupné všechny akce:
        actions = [tisk_karet_beden_zakazek_action, tisk_karet_kontroly_kvality_zakazek_action, expedice_zakazek_action,
        vratit_zakazky_z_expedice_action, expedice_zakazek_kamion_action]        
        Pokud je filtr skladem == expedovano, zruší se akce expedice_zakazek_action a expedice_zakazek_kamion_action
        Pokud není filtr skladem aktivovan, zruší se akce vratit_zakazky_z_expedice_action.
        Pokud je filtr skladem != neprijato, zruší se akce prijmout_zakazku_action.
        """
        actions = super().get_actions(request)
        actions_to_remove = []

        if request.method == "GET":
            skladem = request.GET.get('skladem', None)
            if not skladem:
                actions_to_remove = [
                    'vratit_zakazky_z_expedice_action', 'delete_selected'
                ]
            else:
                if skladem == SklademZakazkyChoice.NEPRIJATO:
                    actions_to_remove = [
                        'tisk_karet_beden_zakazek_action', 'tisk_karet_kontroly_kvality_zakazek_action',
                        'vratit_zakazky_z_expedice_action', 'expedice_zakazek_kamion_action',
                        'expedice_zakazek_action'
                    ]
                elif skladem == SklademZakazkyChoice.BEZ_BEDEN:
                    actions_to_remove = [
                        'tisk_karet_beden_zakazek_action', 'tisk_karet_kontroly_kvality_zakazek_action',
                        'vratit_zakazky_z_expedice_action', 'expedice_zakazek_kamion_action',
                        'expedice_zakazek_action', 'prijmout_zakazku_action'
                    ]
                elif skladem == SklademZakazkyChoice.EXPEDOVANO:
                    actions_to_remove = [
                        'expedice_zakazek_action', 'expedice_zakazek_kamion_action', 'prijmout_zakazku_action',
                        'delete_selected'
                    ]
                elif skladem == SklademZakazkyChoice.PO_EXSPIRACI:
                    actions_to_remove = [
                        'vratit_zakazky_z_expedice_action', 'prijmout_zakazku_action', 'delete_selected'
                    ]
                else:
                    actions_to_remove = ['tisk_karet_beden_zakazek_action', 'tisk_karet_kontroly_kvality_zakazek_action',
                        'vratit_zakazky_z_expedice_action', 'expedice_zakazek_kamion_action',
                        'expedice_zakazek_action', 'prijmout_zakazku_action', 'delete_selected'
                        ]

        for action in actions_to_remove:
            if action in actions:
                del actions[action]

        return actions

    def get_action_choices(self, request, default_choices=models.BLANK_CHOICE_DASH):
        """
        Seskupení akcí zakázek do optgroup a formátování placeholderů.
        Skupiny:
        - Příjem
        - Tisk / Export
        - Expedice
        Ostatní akce (např. delete_selected) spadnou do 'Ostatní'.
        """
        actions = self.get_actions(request)
        if not actions:
            return default_choices

        group_map = {
            'prijmout_zakazku_action': 'Příjem',
            'tisk_karet_beden_zakazek_action': 'Tisk',
            'tisk_karet_kontroly_kvality_zakazek_action': 'Tisk',
            'expedice_zakazek_action': 'Expedice',
            'expedice_zakazek_kamion_action': 'Expedice',
            'vratit_zakazky_z_expedice_action': 'Expedice',
        }
        order = ['Příjem','Tisk', 'Expedice']
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
        Pokud není aktivní filtr "skladem=SklademZakazkyChoice.EXPEDOVANO", odebere se sloupec kamion_vydej.
        """
        ld = list(super().get_list_display(request))
        if request.GET.get('skladem') != SklademZakazkyChoice.EXPEDOVANO:
            if 'kamion_vydej_link' in ld:
                ld.remove('kamion_vydej_link')
        return ld

    def get_list_editable(self, request):
        """
        Přizpůsobení zobrazení sloupců pro editaci v seznamu zakázek podle aktivního filtru.
        Pokud není aktivní filtr "skladem=SklademZakazkyChoice.EXPEDOVANO", přidá se do list_editable pole priorita.
        """
        if request.GET.get('skladem') != SklademZakazkyChoice.EXPEDOVANO:
            return ['priorita']
        return []

    def changelist_view(self, request, extra_context=None):
        """
        Přizpůsobení zobrazení seznamu zakázek podle aktivního filtru.
        """
        self.list_editable = self.get_list_editable(request)
        return super().changelist_view(request, extra_context)


@admin.register(Bedna)
class BednaAdmin(SimpleHistoryAdmin):
    """
    Admin pro model Bedna:
    
    - Detail/inline: BednaAdminForm (omezuje stavové volby dle instance).
    - Seznam (change_list): list_editable je nastavován dynamicky v get_list_editable podle aktivního filtru.
    - Pro každý řádek dropdown omezí na povolené volby podle stejné logiky.
    - Číslo bedny se generuje automaticky a je readonly
    - Akce se vybírají dynamicky v get_actions.
    - Priorita se zobrazuje barevně podle hodnoty (VYSOKA - červená, STREDNI - oranžová, NIZKA - zelená).
    """
    change_list_template = 'admin/orders/bedna/change_list.html'
    poll_interval_ms = 30000
    actions = [
        export_bedny_to_csv_action, tisk_karet_beden_action, tisk_karet_kontroly_kvality_action, tisk_karet_bedny_a_kontroly_action,
        export_bedny_to_csv_customer_action, export_bedny_eurotec_dl_action,
        oznacit_k_navezeni_action, oznacit_navezeno_action, oznacit_prijato_navezeno_action, vratit_bedny_ze_stavu_k_navezeni_do_stavu_prijato_action,
        vratit_bedny_ze_stavu_navezeno_do_stavu_prijato_action, vratit_bedny_z_rozpracovanosti_do_stavu_prijato_action,
        oznacit_do_zpracovani_action, oznacit_zakaleno_action, oznacit_zkontrolovano_action, oznacit_k_expedici_action,
        oznacit_rovna_action, oznacit_kriva_action, oznacit_rovna_se_action, oznacit_vyrovnana_action,
        oznacit_cista_action, oznacit_spinava_action, oznacit_otryskana_action, prijmout_bedny_action, expedice_beden_action,
        expedice_beden_kamion_action,
    ]
    form = BednaAdminForm

    # Parametry pro zobrazení detailu v administraci (použijeme get_fieldsets)
    readonly_fields = ('cislo_bedny', 'cena_za_kg', 'cena_za_bednu', 'cena_rovnani_za_kg', 'cena_rovnani_za_bednu',
                       'cena_tryskani_za_kg', 'cena_tryskani_za_bednu')
    autocomplete_fields = ('zakazka',)

    # Parametry pro zobrazení seznamu v administraci
    list_display = (
        'get_cislo_bedny', 'get_behalter_nr', 'get_poradi_bedny_v_zakazce', 'zakazka_link', 'get_zakaznik_zkratka', 'kamion_prijem_link',
        'kamion_vydej_link', 'stav_bedny', 'rovnat', 'tryskat', 'get_prumer', 'get_delka_int','get_skupina_TZ',
        'get_typ_hlavy', 'get_celozavit', 'get_zkraceny_popis', 'hmotnost', 'tara', 'get_hmotnost_brutto',
        'mnozstvi', 'pozice', 'get_priorita', 'get_datum_prijem', 'get_datum_vydej', 'get_postup', 'cena_za_kg', 'poznamka',
        )
    # list_editable nastavován dynamicky v get_list_editable
    list_display_links = ('get_cislo_bedny', )
    list_select_related = ("zakazka", "zakazka__kamion_prijem", "zakazka__kamion_vydej")
    list_per_page = 50
    search_fields = ('cislo_bedny', 'behalter_nr', 'zakazka__artikl',)
    search_help_text = "Dle čísla bedny, č.b. zákazníka nebo zakázky"
    list_filter = (ZakaznikBednyFilter, StavBednyFilter, TryskaniFilter, RovnaniFilter, SkupinaFilter, DelkaFilter,
                   CelozavitBednyFilter, TypHlavyBednyFilter, PrioritaBednyFilter, PozastavenoFilter,)
    ordering = ('id',)
    # Výchozí date_hierarchy pro povolení lookupů; skutečně se přepíná dynamicky v get_date_hierarchy
    date_hierarchy = 'zakazka__kamion_prijem__datum'
    save_on_top = True
    formfield_overrides = {
        # models.CharField: {'widget': TextInput(attrs={ 'size': '20', 'style': 'font-size: 10px;'})},
        models.DecimalField: {
            'widget': TextInput(attrs={ 'size': '3'}),
            'localize': True
        },
        models.IntegerField: {
            'widget': TextInput(attrs={ 'size': '3'}),
        },
        models.BooleanField: {'widget': RadioSelect(choices=[(True, 'Ano'), (False, 'Ne')])}
    }

    # Parametry pro historii změn
    history_list_display = ["cislo_bedny", "behalter_nr", "zakazka_link", "stav_bedny", "rovnat", "tryskat",
                            "get_prumer", "get_delka_int", "get_skupina_TZ", "poznamka"]
    history_search_fields = ["zakazka__kamion_prijem__zakaznik__nazev", "cislo_bedny",]
    history_list_filter = ["zakazka__kamion_prijem__zakaznik__nazev", "zakazka__kamion_prijem__datum", "stav_bedny"]
    history_list_per_page = 20

    class Media:
        js = (
            'orders/js/admin_actions_target_blank.js',
            'orders/js/changelist_dirty_guard.js',
            'orders/js/admin_bedna_group_separator.js',
            'orders/js/admin_bedna_change_poll.js',
            'orders/js/bedny_hmotnost_sum.js',
        )
        css = {
            'all': ('orders/css/admin_paused_rows.css',)
        }

    def get_date_hierarchy(self, request):
        """Dynamicky přepne hierarchii dat podle filtru stavu bedny."""
        if request is None:
            return 'zakazka__kamion_prijem__datum'

        stav = request.GET.get('stav_bedny')
        if stav == StavBednyChoice.EXPEDOVANO:
            return 'zakazka__kamion_vydej__datum'
        return 'zakazka__kamion_prijem__datum'

    def lookup_allowed(self, key, value):
        """Povolí drilldown lookupy pro obě datové hierarchie (příjem/výdej)."""
        if key.startswith('zakazka__kamion_prijem__datum__') or key.startswith('zakazka__kamion_vydej__datum__'):
            return True
        return super().lookup_allowed(key, value)

    def get_changelist_instance(self, request):
        """Použije dynamickou date_hierarchy (z get_date_hierarchy)."""
        list_display = self.get_list_display(request)
        list_display_links = self.get_list_display_links(request, list_display)
        if self.get_actions(request):
            list_display = ['action_checkbox', *list_display]
        sortable_by = self.get_sortable_by(request)
        ChangeList = self.get_changelist(request)
        return ChangeList(
            request,
            self.model,
            list_display,
            list_display_links,
            self.get_list_filter(request),
            self.get_date_hierarchy(request),
            self.get_search_fields(request),
            self.get_list_select_related(request),
            self.list_per_page,
            self.list_max_show_all,
            self.list_editable,
            self,
            sortable_by,
            self.search_help_text,
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'changes/poll/',
                self.admin_site.admin_view(self.poll_changes_view),
                name='orders_bedna_poll',
            ),
        ]
        return custom_urls + urls

    def _get_latest_change_timestamp(self):
        latest = Bedna.history.aggregate(last=Max('history_date'))['last']
        return latest

    def poll_changes_view(self, request):
        last_change = self._get_latest_change_timestamp()
        since_raw = request.GET.get('since')
        since_value = None

        if since_raw:
            try:
                normalized = since_raw.replace(' ', '+')
                since_value = datetime.fromisoformat(normalized)
                if timezone.is_naive(since_value):
                    since_value = timezone.make_aware(since_value, timezone.get_current_timezone())
            except ValueError:
                since_value = None

        changed = False
        if last_change and since_value:
            if last_change > since_value:
                changed = True
            elif last_change == since_value:
                history_model = Bedna.history.model
                duplicates = history_model.objects.filter(history_date=last_change).count()
                changed = duplicates > 1

        payload = {
            'changed': changed,
            'timestamp': last_change.isoformat() if last_change else None,
        }
        return JsonResponse(payload)

    @admin.display(description='Č. bedny', ordering='cislo_bedny')
    def get_cislo_bedny(self, obj):
        """
        Zobrazí číslo bedny a umožní třídění podle hlavičky pole.
        Číslo bedny se generuje automaticky a je readonly.
        """
        return obj.cislo_bedny

    @admin.display(description='Pořadí', empty_value='-')
    def get_poradi_bedny_v_zakazce(self, obj):
        """
        Zobrazí pořadí bedny v zakázce (1/7, 2/7, 3/7, ...).
        Pokud bedna není přiřazena k zakázce, vrátí '-'.
        """
        if obj.zakazka:
            poradi = f"{obj.poradi_bedny}/{obj.zakazka.pocet_beden}"
            return poradi
        return '-'

    @admin.display(description='Zák.', ordering='zakazka__kamion_prijem__zakaznik__zkratka', empty_value='-')
    def get_zakaznik_zkratka(self, obj):
        """
        Zobrazí zkratku zákazníka, ke kterému bedna patří, a umožní třídění podle hlavičky pole.
        Pokud bedna není přiřazena k zakázce nebo zakázka nemá zákazníka, vrátí '-'.
        """
        if obj.zakazka and obj.zakazka.kamion_prijem and obj.zakazka.kamion_prijem.zakaznik:
            return obj.zakazka.kamion_prijem.zakaznik.zkratka
        return '-'

    @admin.display(description='Brutto', empty_value='-')        
    def get_hmotnost_brutto(self, obj):
        """
        Zobrazí brutto hmotnost bedny (hmotnost + tara), použije property hmotnost_brutto v modelu Bedna.
        """
        return obj.hmotnost_brutto.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP) if obj.hmotnost_brutto else '-'

    @admin.display(description='Dat. příjem', ordering='zakazka__kamion_prijem__datum', empty_value='-')
    def get_datum_prijem(self, obj):
        """Zobrazí datum kamionu příjmu, ke kterému bedna patří."""
        if obj.zakazka and obj.zakazka.kamion_prijem:
            return obj.zakazka.kamion_prijem.datum.strftime('%y-%m-%d')
        return '-'
    
    @admin.display(description='Dat. výdej', ordering='zakazka__kamion_vydej__datum', empty_value='-')
    def get_datum_vydej(self, obj):
        """Zobrazí datum kamionu výdeje, ke kterému bedna patří."""
        if obj.zakazka and obj.zakazka.kamion_vydej:
            return obj.zakazka.kamion_vydej.datum.strftime('%y-%m-%d')
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
    def get_zkraceny_popis(self, obj):
        """
        Vrátí zkrácený popis zakázky (první část před čísly) s tooltipem celého popisu
        a umožní třídění podle hlavičky pole.
        """
        return format_html('<span title="{}">{}</span>', obj.zakazka.popis, obj.zakazka.zkraceny_popis)        

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
        Pro prioritu VYSOKA vrátí červenou barvu, STREDNI oranžovou a NIZKA zelenou.
        """
        priorita = obj.zakazka.get_priorita_display() if obj.zakazka else "-"
        barva_map = {
            PrioritaChoice.VYSOKA: 'red',
            PrioritaChoice.STREDNI: 'orange',
            PrioritaChoice.NIZKA: 'green',
        }
        barva = barva_map.get(obj.zakazka.priorita, 'black') if obj.zakazka else 'black'
        return format_html('<span style="color: {};">{}</span>', barva, priorita)

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
        Předá jako html s text bold.
        """
        if obj.zakazka and obj.zakazka.delka is not None:
            return mark_safe(f'<strong>{int(obj.zakazka.delka.to_integral_value(rounding=ROUND_DOWN))}</strong>')
        return '-'
    
    @admin.display(description='Stav bedny', ordering='stav_bedny', empty_value='-')
    def get_stav_bedny_mobile(self, obj):
        """Zkrácený popis stavu bedny pro zúžené layouty (např. mobilní)."""
        if not obj or obj.stav_bedny is None:
            return '-'

        label = obj.get_stav_bedny_display()
        max_len = 10
        if len(label) > max_len:
            return f"{label[:max_len - 1]}…"
        return label

    @admin.display(description='TZ', ordering='zakazka__predpis__skupina', empty_value='-')
    def get_skupina_TZ(self, obj):
        """
        Zobrazí skupinu tepelného zpracování bedny a umožní třídění podle hlavičky pole.
        Vrátí html číslo s barvou podle skupiny - BARVA_SKUPINY_TZ.
        """
        barva = BARVA_SKUPINY_TZ[obj.zakazka.predpis.skupina] if obj.zakazka and obj.zakazka.predpis and obj.zakazka.predpis.skupina in BARVA_SKUPINY_TZ else ''
        if obj.zakazka and obj.zakazka.predpis and obj.zakazka.predpis.skupina:
            return mark_safe(
                f'<span style="color: {barva["text"]}; background-color: {barva["pozadi"]}; padding: 0.1rem 0.35rem; border-radius: 0.25rem; display: inline-block;">'
                f"{obj.zakazka.predpis.skupina}"
                "</span>"
            )
        return '-'        

    @admin.display(description='Postup', ordering='postup_vyroby_value', empty_value='-')
    def get_postup(self, obj):
        """
        Zobrazí postup bedny pomocí progress barupodle stavu bedny a umožní třídění podle hlavičky pole.
        """
        # jednoduchý progress bar
        postup = obj.postup_vyroby
        barva = obj.barva_postupu_vyroby
        bar = f"""
        <div style="width:60px;border:1px solid #ddd;height:12px;border-radius:6px;overflow:hidden;">
            <div style="width:{postup}%;height:100%;background:{barva};"></div>
        </div>
        """
        return format_html(bar)

    def get_queryset(self, request):
        """Rozšíří queryset o anotaci postup_vyroby_value (SQL ekvivalent property postup_vyroby)."""
        qs = super().get_queryset(request)

        # Replikace logiky property postup_vyroby do SQL CASE
        return qs.annotate(
            postup_vyroby_value=Case(*build_postup_vyroby_cases(), default=Value(0), output_field=IntegerField())
        )

    def get_fieldsets(self, request, obj=None):
        """
        Sestaví fieldsety podle požadavku a zachová logiku vylučování polí dle zákazníka a toho, zda se jedná o editaci.
        Pokud se jedná o přidání nové bedny (obj je None), vyloučí se pole cislo_bedny, které se generuje automaticky.
        Pokud se jedná o editaci (obj není None), vyloučí se pole dle zákazníka a dalších podmínek:
        - ROT: dodatecne_info, dodavatel_materialu, vyrobni_zakazka
        - SSH, SWG, HPM, FIS: behalter_nr, dodatecne_info, dodavatel_materialu, vyrobni_zakazka
        - SPX: dodatecne_info, dodavatel_materialu
        - Pokud je vyplněna tara a je větší než 0, skryje se pole brutto
        - Pokud není stav bedny ve STAV_BEDNY_SKLADEM, skryje se pole cena_za_kg, cena_za_bednu, cena_rovnani_za_kg,
          cena_rovnani_za_bednu, cena_tryskani_za_kg a cena_tryskani_za_bednu
        - Pokud není stav bedny ve STAV_BEDNY_PRO_NAVEZENI, skryje se pole pozice a poznamka_k_navezeni
        """
        groups = [
            ("Základní údaje", (
                'zakazka', 'cislo_bedny', 'behalter_nr', 'material', 'sarze', 'poznamka', 'odfosfatovat'
            )),
            ("Hmotnost a množství", (
                'hmotnost', 'tara', 'brutto', 'mnozstvi'
            )),
            ("Stavy bedny", (
                'stav_bedny', 'tryskat', 'rovnat', 'pozastaveno', 'fakturovat'
            )),
            ("K navezení", (
                'pozice', 'poznamka_k_navezeni'
            )),
            ("Speciální informace", (
                'dodatecne_info', 'dodavatel_materialu', 'vyrobni_zakazka'
            )),
            ('Prodejní cena', (
                'cena_za_kg', 'cena_za_bednu', 'cena_rovnani_za_kg', 'cena_rovnani_za_bednu',
                'cena_tryskani_za_kg', 'cena_tryskani_za_bednu'
            )),
        ]

        # Logika vyloučení polí z původního get_fields
        exclude_fields = []
        if obj:
            zakaznik = getattr(getattr(getattr(obj, 'zakazka', None), 'kamion_prijem', None), 'zakaznik', None)
            zkratka = getattr(zakaznik, 'zkratka', None)
            if zkratka == 'ROT':
                exclude_fields = ['dodatecne_info', 'dodavatel_materialu', 'vyrobni_zakazka']
            elif zkratka in ('SSH', 'SWG', 'HPM', 'FIS'):
                exclude_fields = ['behalter_nr', 'dodatecne_info', 'dodavatel_materialu', 'vyrobni_zakazka']
            elif zkratka == 'SPX':
                exclude_fields = ['dodatecne_info', 'dodavatel_materialu']
            # Pokud je vyplněna tara a je větší než 0, skryje se pole brutto
            if obj.tara is not None and obj.tara > 0:
                exclude_fields.append('brutto')
            # Pokud není stav bedny ve STAV_BEDNY_SKLADEM, skryje se pole cena_za_kg, cena_za_bednu, cena_rovnani_za_kg a cena_tryskani_za_kg
            if obj.stav_bedny and obj.stav_bedny not in STAV_BEDNY_SKLADEM:
                exclude_fields.extend(['cena_za_kg', 'cena_za_bednu', 'cena_rovnani_za_kg', 'cena_rovnani_za_bednu',
                                       'cena_tryskani_za_kg', 'cena_tryskani_za_bednu'])
            # Pokud není stav bedny ve STAV_BEDNY_PRO_NAVEZENI, skryje se pole pozice a poznamka_k_navezeni
            if obj.stav_bedny and obj.stav_bedny not in STAV_BEDNY_PRO_NAVEZENI:
                exclude_fields.extend(['pozice', 'poznamka_k_navezeni'])
        else:
            # add_view: cislo_bedny se generuje automaticky
            exclude_fields = ['cislo_bedny']

        fieldsets = []
        for title, fields in groups:
            kept = [f for f in fields if f not in exclude_fields]
            if kept:
                fieldsets.append((title, {'fields': tuple(kept)}))

        return fieldsets

    def get_readonly_fields(self, request, obj = None):
        """
        Přizpůsobí readonly_fields podle toho, zda je bedna expedovaná.
        Pokud je bedna expedovaná a uživatel má oprávnění 'orders.change_expedovana_bedna',
        přidají se další pole jako readonly, kvůli případným vzniklým nekonzistencím po změně těchto polí.
        """
        current_readonly_fields = list(super().get_readonly_fields(request, obj))
        added_readonly_fields = []
        if obj and obj.stav_bedny == StavBednyChoice.NEPRIJATO:
            # Uživatel bez change_neprijata_bedna může upravit pouze poznámku, pokud má speciální oprávnění.
            if (not request.user.has_perm('orders.change_neprijata_bedna')
                    and request.user.has_perm('orders.change_poznamka_neprijata_bedna')):
                editable_fields = {'poznamka'}
                all_fields = {f.name for f in self.model._meta.fields}
                readonly_set = (set(current_readonly_fields) | all_fields) - editable_fields
                return list(readonly_set)
        if obj and obj.stav_bedny == StavBednyChoice.EXPEDOVANO:
            # Expedovanou bednu kvůli has_permission v modelu BednaAdmin normálně nelze měnit,
            # ale pokud uživatel má speciální oprávnění, povolíme zobrazení některých polí jako readonly.
            added_readonly_fields = [
                'zakazka', 'cislo_bedny', 'tryskat', 'rovnat', 'stav_bedny', 'pozastaveno',
                'pozice', 'poznamka_k_navezeni',
            ]
        return current_readonly_fields + added_readonly_fields

    def get_list_editable(self, request):
        """
        Dynamicky určí, která pole jsou inline-editovatelná v changelistu.
        Podmínky (podle původní logiky/testů):
        - Pokud je zařízení mobil => žádná inline editace.
        - Pokud je filtr stav_bedny = StavBednyChoice.EXPEDOVANO nebo pozastaveno=True => žádná inline editace.
        - Pokud je filtr stav_bedny = StavBednyChoice.NEPRIJATO a uživatel nemá oprávnění change_neprijata_bedna ani change_poznamka_neprijata_bedna => žádná inline editace.
        - Jinak standardně: stav_bedny, tryskat, rovnat, hmotnost, poznamka.
        - Pokud je stav_bedny == StavBednyChoice.NEPRIJATO a uživatel má oprávnění change_neprijata_bedna, přidá se i mnozstvi.
        - Pokud je stav_bedny == StavBednyChoice.NEPRIJATO a uživatel má jen change_poznamka_neprijata_bedna, zůstane editovatelná pouze poznamka.
        - Pokud je stav_bedny v STAV_BEDNY_PRO_NAVEZENI, přidá se i pozice.
        """
        if get_user_agent(request).is_mobile:
            return []

        stav_filter = request.GET.get('stav_bedny')

        if stav_filter == StavBednyChoice.EXPEDOVANO or request.GET.get('pozastaveno') == 'True':
            return []
        
        if stav_filter == StavBednyChoice.NEPRIJATO:
            if request.user.has_perm('orders.change_neprijata_bedna'):
                editable = ['stav_bedny', 'tryskat', 'rovnat', 'hmotnost', 'tara', 'poznamka', 'mnozstvi']
            elif request.user.has_perm('orders.change_poznamka_neprijata_bedna'):
                return ['poznamka']
            else:
                return []
        else:
            editable = ['stav_bedny', 'tryskat', 'rovnat', 'hmotnost', 'tara', 'poznamka']

        if stav_filter in STAV_BEDNY_PRO_NAVEZENI:
            editable.append('pozice')

        if stav_filter == StavBednyChoice.K_EXPEDICI:
            if 'hmotnost' in editable:
                editable.remove('hmotnost') 

        return editable

    def has_change_permission(self, request, obj=None):
        """
        Omezení změn:
        - Expedovaná bedna vyžaduje oprávnění change_expedovana_bedna
        - Pozastavená bedna vyžaduje oprávnění change_pozastavena_bedna
        - Neprijatá bedna vyžaduje oprávnění change_neprijata_bedna nebo pouze change_poznamka_neprijata_bedna (jen pro úpravu poznámky)
        Jinak platí standardní change_bedna.
        """
        if obj is not None:
            # Pozastavení má prioritu: pokud je bedna pozastavená, vyžaduj speciální oprávnění
            # a neblokuj kvůli jiným stavům (např. NEPRIJATO), pokud ho uživatel má.
            if getattr(obj, 'pozastaveno', False):
                return request.user.has_perm('orders.change_pozastavena_bedna')

            # Expedovaná vyžaduje speciální oprávnění
            if getattr(obj, 'stav_bedny', None) == StavBednyChoice.EXPEDOVANO:
                return request.user.has_perm('orders.change_expedovana_bedna')

            # Neprijatá vyžaduje speciální oprávnění
            if getattr(obj, 'stav_bedny', None) == StavBednyChoice.NEPRIJATO:
                if request.user.has_perm('orders.change_neprijata_bedna'):
                    return True
                return request.user.has_perm('orders.change_poznamka_neprijata_bedna')
            
        return super().has_change_permission(request, obj)

    def has_mark_bedna_navezeno_permission(self, request):
        return request.user.has_perm('orders.mark_bedna_navezeno')
    
    def get_changelist_form(self, request, **kwargs):
        """
        Vytvoří vlastní form pro ChangeList, který omezuje volby stav_bedny, tryskat a rovnat podle instance.
        """
        return BednaChangeListForm

    def changelist_view(self, request, extra_context=None):
        """
        Přizpůsobení zobrazení seznamu beden podle aktivního filtru.
        Dynamicky nastaví list_editable podle get_list_editable, ověří, zda jsou tyto pole v list_display nebo v list_display_links.
        Pokud není některé pole z list_editable v list_display nebo je v list_display_links, odstraní ho z list_editable.
        """
        editable = self.get_list_editable(request)
        links = self.get_list_display_links(request, self.get_list_display(request))
        display = self.get_list_display(request)
        self.list_editable = [f for f in editable if f in display and f not in links]
        extra_context = extra_context or {}
        last_change = self._get_latest_change_timestamp()
        extra_context.update({
            'bedna_poll_url': reverse('admin:orders_bedna_poll'),
            'bedna_last_change': last_change.isoformat() if last_change else '',
            'bedna_poll_interval': self.poll_interval_ms,
        })
        response = super().changelist_view(request, extra_context)
        return response

    def get_changelist_formset(self, request, **kwargs):
        """
        Vytvoří vlastní formset pro ChangeList, který zakáže editaci polí v závislosti na stavu bedny a oprávněních uživatele.
        Pokud je bedna pozastavena a uživatel má příslušná oprávnění, dojde pouze k vizuálnímu zvýraznění polí.
        Pokud je bedna pozastavena a uživatel nemá příslušná oprávnění, zakáže se editace polí.
        """
        formset = super().get_changelist_formset(request, **kwargs)

        class CustomFormset(formset):
            def __init__(self_inner, *args, **kwargs):
                super().__init__(*args, **kwargs)
                for form in self_inner.forms:
                    obj = form.instance
                    if obj.pozastaveno:
                        for _, field in form.fields.items():
                            # Vizuální zvýraznění pozastavených polí v changelistu
                            try:
                                existing = field.widget.attrs.get('class', '')
                                field.widget.attrs['class'] = (existing + ' paused-row').strip()
                            except Exception:
                                pass
                            if not request.user.has_perm('orders.change_pozastavena_bedna'):
                                # Hidden pole se přeskočí, jinak by zmizela hodnota ID bedny a nastala chyba při uložení
                                if field.widget.is_hidden:
                                    continue
                                field.required = False
                                field.disabled = True

        return CustomFormset
    
    def get_list_display(self, request):
        """
        Přizpůsobení zobrazení sloupců v seznamu Bedna.
        Pokud je zařízení mobil, zůstanou pouze sloupce 'get_cislo_bedny', 'get_stav_bedny_mobile',
        'get_prumer', 'get_delka_int' a 'get_skupina_TZ'.
        Pokud je aktivní filtr stav bedny a zároveň stav bedny != Po exspiraci, vyloučí se zobrazení sloupce get_postup.        
        Pokud není filtr stav bedny == Expedováno, vyloučí se zobrazení sloupce kamion_vydej_link a get_datum_vydej,
        jinak get_datum_prijem.
        Pokud není filtr stav bedny v STAV_BEDNY_PRO_NAVEZENI, vyloučí se zobrazení sloupce pozice.
        Pokud není filtr stav bedny == Neprijato, vyloučí se zobrazení sloupce mnozstvi a tara.
        Pokud není filtr stav bedny == K_expedici, vyloučí se zobrazení sloupce cena_za_kg a hmotnost_brutto.
        Pokud není filtr stav bedny == Prijato nebo K_expedici, vyloučí se sloupce get_zakaznik_zkratka a get_poradi_bedny_v_zakazce,
        jinak kamion_prijem_link.
        """
        list_display = list(super().get_list_display(request))
        stav_bedny = request.GET.get('stav_bedny', None)

        # Podmínky pro odstranění sloupců z list_display
        if get_user_agent(request).is_mobile:
            return ['get_cislo_bedny', 'get_stav_bedny_mobile', 'get_prumer', 'get_delka_int', 'get_skupina_TZ']
        if stav_bedny and stav_bedny not in ['PE', 'RO']:
            if 'get_postup' in list_display:
                list_display.remove('get_postup')
        if stav_bedny != StavBednyChoice.EXPEDOVANO:
            if 'kamion_vydej_link' in list_display:
                list_display.remove('kamion_vydej_link')
            if 'get_datum_vydej' in list_display:
                list_display.remove('get_datum_vydej')
        else:
            if 'get_datum_prijem' in list_display:
                list_display.remove('get_datum_prijem')
        if stav_bedny not in STAV_BEDNY_PRO_NAVEZENI:
            if 'pozice' in list_display:
                list_display.remove('pozice')
        if stav_bedny != StavBednyChoice.NEPRIJATO:
            if 'mnozstvi' in list_display:
                list_display.remove('mnozstvi')
            if 'tara' in list_display:
                list_display.remove('tara')
        if stav_bedny != StavBednyChoice.K_EXPEDICI:
            if 'cena_za_kg' in list_display:
                list_display.remove('cena_za_kg')
            if 'get_hmotnost_brutto' in list_display:
                list_display.remove('get_hmotnost_brutto')
        if stav_bedny not in [StavBednyChoice.PRIJATO, StavBednyChoice.K_EXPEDICI]:
            if 'get_poradi_bedny_v_zakazce' in list_display:
                list_display.remove('get_poradi_bedny_v_zakazce')
            if 'get_zakaznik_zkratka' in list_display:
                list_display.remove('get_zakaznik_zkratka')                
        else:
            if 'kamion_prijem_link' in list_display:
                list_display.remove('kamion_prijem_link')
        
        return list_display
    
    def get_list_filter(self, request):
        """
        Přizpůsobení dostupných filtrů v administraci podle filtru stavu bedny.
        Pokud není vůbec aktivní filtr stav bedny, zruší se filtr DelkaFilter, TypHlavyBednyFilter a CelozavitBednyFilter,
        pokud není aktivní filtr stav bedny PRIJATO, zruší se filtr DelkaFilter,
        SkupinaFilter, TypHlavyBednyFilter a CelozavitBednyFilter,
        jinak se zruší filtry TryskaniFilter, RovnaniFilter a PozastavenoFilter.
        """
        actual_filters = super().get_list_filter(request)
        filters_to_remove = []
        if request.GET.get('stav_bedny', None) is None:
            filters_to_remove.extend([DelkaFilter, TypHlavyBednyFilter, CelozavitBednyFilter])
        elif request.GET.get('stav_bedny', None) != StavBednyChoice.PRIJATO:
            filters_to_remove.extend([DelkaFilter, SkupinaFilter, TypHlavyBednyFilter, CelozavitBednyFilter])
        else:
            filters_to_remove.extend([TryskaniFilter, RovnaniFilter, PozastavenoFilter])
        return [f for f in actual_filters if f not in filters_to_remove]

    def get_actions(self, request):
        """
        Přizpůsobí dostupné akce v administraci podle filtru stavu bedny, rovnat a tryskat.
        Pokud není aktivní filtr stav bedny NEPRIJATO, zruší se akce pro přijetí bedny,
            jinak se zruší akce pro tisk karet beden, kontroly kvality a tisk karet beden a kontroly.
        Pokud není vůbec aktivní filtr stav bedny, zruší se akce export_beden_to_csv_action.            
        Pokud není vůbec aktivní filtr stav bedny nebo není aktivní filtr stav bedny PRIJATO,
        zruší se akce pro změnu stavu bedny na K_NAVEZENI.
        Pokud není aktivní filtr stav bedny K_NAVEZENI, zruší se akce pro vrácení bedny ze stavu K_NAVEZENI do stavu PRIJATO
            a akce pro označení bedny jako NAVEZENO.
        Pokud není aktivní filtr stav bedny NAVEZENO nebo RO, zruší se akce pro označení bedny do stavu DO_ZPRACOVANI
            a akce pro vrácení bedny ze stavu NAVEZENO do stavu PRIJATO.
        Pokud není aktivní filtr stav bedny NAVEZENO, DO_ZPRACOVANI nebo RO, zruší se akce pro označení bedny jako ZAKALENO.
        Pokud není aktivní filtr stav bedny NAVEZENO, DO_ZPRACOVANI, ZAKALENO nebo RO, zruší se akce pro označení bedny jako ZKONTROLOVANO.
        Pokud není aktivní filtr stav bedny NAVEZENO, DO_ZPRACOVANI, ZAKALENO, ZKONTROLOVANO nebo RO,
        zruší se akce pro označení bedny jako K_EXPEDICI.
        Pokud není aktivní filtr stav bedny EXPEDOVANO, zruší se akce pro export_beden_eurotec_dl_action.
        Pokud není aktivní filtr stav bedny RO, zruší se akce pro vrácení bedny z rozpracovanosti do stavu PRIJATO.
        Pokud není aktivní filtr stav bedny K_EXPEDICI, zruší se akce expedice_beden a expedice_beden_kamion.
        Pokud není aktivní filtr stav bedny K_EXPEDICI nebo EXPEDOVANO nebo filtr rovnani "k_vyrovnani" (KRIVA nebo ROVNA_SE),
        zruší se akce export_bedny_to_csv_customer_action.
        Pokud není aktivní filtr rovnani NEZADANO, zruší se akce pro označení bedny jako ROVNA a KŘIVÁ.
        Pokud není aktivní filtr rovnani KŘIVÁ, zruší se akce pro označení bedny jako ROVNÁ SE.
        Pokud není aktivní filtr rovnani KŘIVÁ nebo ROVNÁ SE, zruší se akce pro označení bedny jako VYROVNANÁ.
        Pokud není aktivní filtr tryskani NEZADANO, zruší se akce pro označení bedny jako ČISTÁ a ŠPINAVÁ.
        Pokud není aktivní filtr tryskani ŠPINAVÁ nebo NEZADANO, zruší se akce pro označení bedny jako OTRYSKANÁ.
        Pokud není vůbec aktivní filtr stavu bedny nebo není aktivní filtr stavu bedny PRIJATO nebo K_NAVEZENI,
            nebo nemá uživatel jedno z oprávnění orders.can_change_bedna, orders.mark_bedna_navezeno,
            zruší se akce oznacit_prijato_navezeno_action.
        """
        actions = super().get_actions(request)

        actions_to_remove = []

        if request.method == "GET":
            stav_filter = request.GET.get('stav_bedny', None)
            rovnani_filter = request.GET.get('rovnani', None)
            tryskani_filter = request.GET.get('tryskani', None)

            if stav_filter != StavBednyChoice.NEPRIJATO:
                actions_to_remove += [
                    'prijmout_bedny_action',
                ]
            else:
                actions_to_remove += [
                    'tisk_karet_beden_action', 'tisk_karet_kontroly_kvality_action', 'tisk_karet_bedny_a_kontroly_action',
                ]
            if stav_filter:
                actions_to_remove += [
                    'export_bedny_to_csv_action',
                ]
            if stav_filter and stav_filter != StavBednyChoice.PRIJATO:
                actions_to_remove += [
                    'oznacit_k_navezeni_action',
                ]
            if stav_filter != StavBednyChoice.K_NAVEZENI:
                actions_to_remove += [
                    'vratit_bedny_ze_stavu_k_navezeni_do_stavu_prijato_action', 'oznacit_navezeno_action',
                ]
            if stav_filter not in [StavBednyChoice.NAVEZENO, 'RO']:
                actions_to_remove += [
                    'oznacit_do_zpracovani_action', 'vratit_bedny_ze_stavu_navezeno_do_stavu_prijato_action',
                ]
            if stav_filter not in [StavBednyChoice.NAVEZENO, StavBednyChoice.DO_ZPRACOVANI, 'RO']:
                actions_to_remove += [
                    'oznacit_zakaleno_action',
                ]
            if stav_filter not in [StavBednyChoice.NAVEZENO, StavBednyChoice.DO_ZPRACOVANI, StavBednyChoice.ZAKALENO, 'RO']:
                actions_to_remove += [
                    'oznacit_zkontrolovano_action',
                ]
            if stav_filter not in [
                StavBednyChoice.NAVEZENO, StavBednyChoice.DO_ZPRACOVANI, StavBednyChoice.ZAKALENO,
                StavBednyChoice.ZKONTROLOVANO, 'RO'
                ]:
                actions_to_remove += [
                    'oznacit_k_expedici_action',
                ]
            if stav_filter != 'RO':
                actions_to_remove += [
                    'vratit_bedny_z_rozpracovanosti_do_stavu_prijato_action',
                ]
            if stav_filter != StavBednyChoice.K_EXPEDICI:
                actions_to_remove += [
                    'expedice_beden_action', 'expedice_beden_kamion_action',
                ]
            # Povolit export zákaznického CSV i tehdy, když je aktivní pouze rovnání k_vyrovnani
            if (stav_filter not in [StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO]) and rovnani_filter != 'k_vyrovnani':
                actions_to_remove += [
                    'export_bedny_to_csv_customer_action',
                ]
            if stav_filter != StavBednyChoice.EXPEDOVANO:
                actions_to_remove += [
                    'export_bedny_eurotec_dl_action',
                ]
            if rovnani_filter != RovnaniChoice.NEZADANO:
                actions_to_remove += [
                    'oznacit_rovna_action', 'oznacit_kriva_action',
                ]
            if rovnani_filter != RovnaniChoice.KRIVA:
                actions_to_remove += [
                    'oznacit_rovna_se_action',
                ]
            if rovnani_filter not in [RovnaniChoice.KRIVA, RovnaniChoice.ROVNA_SE]:
                actions_to_remove += [
                    'oznacit_vyrovnana_action',
                ]
            if tryskani_filter != TryskaniChoice.NEZADANO:
                actions_to_remove += [
                    'oznacit_cista_action', 'oznacit_spinava_action',
                ]
            if tryskani_filter not in [TryskaniChoice.SPINAVA, TryskaniChoice.NEZADANO]:
                actions_to_remove += [
                    'oznacit_otryskana_action',
                ]
            permissions_not_ok = not(request.user.has_perm('orders.change_bedna') or request.user.has_perm('orders.mark_bedna_navezeno'))
            if (stav_filter and stav_filter not in [StavBednyChoice.PRIJATO, StavBednyChoice.K_NAVEZENI]) or permissions_not_ok:
                actions_to_remove += [
                    'oznacit_prijato_navezeno_action',
                ]

        for action in actions_to_remove:
            if action in actions:
                del actions[action]

        return actions

    def get_action_choices(self, request, default_choices=models.BLANK_CHOICE_DASH):
        """
        Seskupení akcí beden do optgroup a formátování placeholderů.
        Skupiny:
        - Stav bedny
        - Tisk
        - Export        
        - Rovnání
        - Tryskání
        - Expedice
    
        Ostatní akce (např. delete_selected) spadnou do 'Ostatní'.
        """
        actions = self.get_actions(request)
        if not actions:
            return default_choices

        group_map = {
            'export_bedny_to_csv_action': 'Export',
            'export_bedny_to_csv_customer_action': 'Export',
            'export_bedny_eurotec_dl_action': 'Export',
            'tisk_karet_beden_action': 'Tisk',
            'tisk_karet_kontroly_kvality_action': 'Tisk',
            'tisk_karet_bedny_a_kontroly_action': 'Tisk',
            'prijmout_bedny_action': 'Stav bedny',
            'oznacit_k_navezeni_action': 'Stav bedny',
            'oznacit_prijato_navezeno_action': 'Stav bedny',            
            'oznacit_navezeno_action': 'Stav bedny',
            'vratit_bedny_ze_stavu_k_navezeni_do_stavu_prijato_action': 'Stav bedny',
            'oznacit_do_zpracovani_action': 'Stav bedny',
            'vratit_bedny_ze_stavu_navezeno_do_stavu_prijato_action': 'Stav bedny',
            'oznacit_zakaleno_action': 'Stav bedny',
            'oznacit_zkontrolovano_action': 'Stav bedny',
            'oznacit_k_expedici_action': 'Stav bedny',
            'vratit_bedny_z_rozpracovanosti_do_stavu_prijato_action': 'Stav bedny',
            'oznacit_rovna_action': 'Rovnání',
            'oznacit_kriva_action': 'Rovnání',
            'oznacit_rovna_se_action': 'Rovnání',
            'oznacit_vyrovnana_action': 'Rovnání',
            'oznacit_cista_action': 'Tryskání',
            'oznacit_spinava_action': 'Tryskání',
            'oznacit_otryskana_action': 'Tryskání',
            'expedice_beden_action': 'Expedice',
            'expedice_beden_kamion_action': 'Expedice',
        }
        order = ['Stav bedny', 'Tisk', 'Export', 'Rovnání', 'Tryskání', 'Expedice']
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
                # Přidat skupinu akcí bez řazení akcí uvnitř skupiny
                choices.append((g, opts))
                # # Seřadit akce podle názvu
                # choices.append((g, sorted(opts, key=lambda x: x[1].lower())))
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
        - Pro ForeignKey pole zruší zobrazení ikon pro přidání, změnu, smazání a zobrazení souvisejících objektů.
        - Pro pole 'poznamka' použije TextInput s menším fontem a velikostí.
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
        elif isinstance(db_field, models.CharField):
            if db_field.name in ['poznamka']:
                kwargs['widget'] = TextInput(attrs={'size': '20', 'style': 'font-size: 10px;'})
            return db_field.formfield(**kwargs)

        return super().formfield_for_dbfield(db_field, request, **kwargs)

    # --- UX blokace mazání bedny ---
    def _delete_blockers(self, obj):
        """
        Vrátí seznam důvodů, proč nelze bednu smazat (pro hlášky).
        Povoleno pouze, pokud je bedna ve stavu NEPRIJATO.
        """
        reasons = []
        if not obj:
            return reasons
        if obj.stav_bedny != StavBednyChoice.NEPRIJATO:
            reasons.append(
                f"Bednu lze smazat pouze ve stavu NEPRIJATO (aktuálně: {obj.get_stav_bedny_display()})."
            )
        return reasons

    def has_delete_permission(self, request, obj=None):
        """
        Skryje možnost mazání na detailu bedny, pokud není ve stavu NEPRIJATO.
        Hromadnou akci neblokuje (řeší se v delete_queryset s hláškou).
        """
        if obj is not None:
            if self._delete_blockers(obj):
                return False
        return super().has_delete_permission(request, obj)

    def delete_model(self, request, obj):
        """Při mazání z detailu zablokuje a vypíše důvod, pokud bedna není ve stavu NEPRIJATO."""
        reasons = self._delete_blockers(obj)
        if reasons:
            for r in reasons:
                try:
                    messages.error(request, r)
                except Exception:
                    pass
            return  # nic nemaž
        return super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        """
        Při hromadném mazání smaže jen bedny ve stavu NEPRIJATO a pro ostatní vypíše důvod.
        """
        allowed_ids = []
        blocked_info = []

        for obj in queryset:
            reasons = self._delete_blockers(obj)
            if reasons:
                blocked_info.append((obj, reasons))
            else:
                allowed_ids.append(obj.pk)

        if blocked_info:
            for obj, reasons in blocked_info:
                for r in reasons:
                    try:
                        messages.error(request, f"{obj}: {r}")
                    except Exception:
                        pass

        if allowed_ids:
            super().delete_queryset(request, queryset.filter(pk__in=allowed_ids))
        # Pokud nic nepovoleno, jen vrátí – akce skončí s vypsanými hláškami


@admin.register(Predpis)
class PredpisAdmin(SimpleHistoryAdmin):
    """
    Správa předpisů v administraci.
    """
    save_as = True
    list_display = ('nazev', 'skupina', 'get_zakaznik_zkraceny_nazev', 'ohyb', 'krut', 'povrch', 'jadro', 'vrstva', 'popousteni',
                    'sarzovani', 'pletivo', 'poznamka', 'aktivni')
    list_display_links = ('nazev',)
    search_fields = ('nazev',)
    search_help_text = "Dle názvu předpisu"
    list_filter = (ZakaznikPredpisFilter, AktivniPredpisFilter)
    ordering = ['-zakaznik__zkratka', 'nazev']
    list_per_page = 25

    history_list_display = ('nazev', 'skupina', 'zakaznik__zkraceny_nazev', 'ohyb', 'krut', 'povrch', 'jadro', 'vrstva', 'popousteni',
                            'sarzovani', 'pletivo', 'poznamka', 'aktivni')
    history_search_fields = ['nazev']
    history_list_filter = ['zakaznik__zkraceny_nazev']
    history_list_per_page = 20

    @admin.display(description='Zákazník', ordering='zakaznik__zkraceny_nazev', empty_value='-')
    def get_zakaznik_zkraceny_nazev(self, obj):
        return obj.zakaznik.zkraceny_nazev if obj.zakaznik else '-'


@admin.register(Odberatel)
class OdberatelAdmin(SimpleHistoryAdmin):
    """
    Správa odběratelů v administraci.
    """
    # Parametry pro zobrazení detailu v administraci
    fieldsets = [
        ('Název a adresa', {
            'fields': ('nazev', 'adresa', 'mesto', 'psc', 'stat', 'zkratka_statu',)
        }),
        ('Kontaktní údaje', {
            'fields': ('kontaktni_osoba', 'telefon', 'email',)
        }),
        ('Doplňující parametry', {
            'fields': ('zkraceny_nazev', 'zkratka',)
        })
    ]
    readonly_fields = ('zkratka',)

    list_display = ('nazev', 'zkraceny_nazev', 'zkratka', 'adresa', 'mesto', 'psc', 'stat', 'zkratka_statu', 'kontaktni_osoba', 'telefon', 'email',)
    list_display_links = ('nazev',)
    ordering = ['nazev']
    list_per_page = 25

    history_list_display = ['nazev', 'zkraceny_nazev', 'zkratka', 'adresa', 'mesto', 'psc', 'stat', 'zkratka_statu', 'kontaktni_osoba', 'telefon', 'email']
    history_search_fields = ['nazev']
    history_list_per_page = 20    

    def get_readonly_fields(self, request, obj = None):
        """
        Přizpůsobení readonly_fields pro detail zákazníka.
        V případě, že se vytváří nový zákazník (obj je None), pole 'zkratka' není readonly.
        """
        currently_readonly = list(super().get_readonly_fields(request, obj)) or []
        if obj is None:
            if 'zkratka' in currently_readonly:
                currently_readonly.remove('zkratka')
        return currently_readonly    


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
    list_display = ('get_zakaznik', 'popis_s_delkou', 'delka_min', 'delka_max', 'cena_za_kg', 'cena_rovnani_za_kg',
                    'cena_tryskani_za_kg', 'get_predpisy')
    list_editable = ('delka_min', 'delka_max', 'cena_za_kg', 'cena_rovnani_za_kg', 'cena_tryskani_za_kg',)
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

    class Media:
        js = ('orders/js/changelist_dirty_guard.js',)


    @admin.display(description='Předpisy', ordering='predpis__nazev', empty_value='-')
    def get_predpisy(self, obj):
        """
        Zobrazí názvy předpisů spojených s cenou a umožní třídění podle hlavičky pole.
        Pokud není žádný předpis spojen, vrátí prázdný řetězec.
        """
        if obj.predpis.exists():
            predpisy_text = []
            for predpis in obj.predpis.all():
                aktivni_text = "A" if predpis.aktivni else "N"
                predpis_text = f"{predpis.nazev}-{aktivni_text}"
                predpisy_text.append(predpis_text)
            predpisy_text = ", ".join(predpisy_text)
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
        Zobrazí popis ceny s přidanou délkou v jednom řádku, aby se nelámal.
        """
        text = f"{obj.popis}x{int(obj.delka_min)}-{int(obj.delka_max)}" if obj.delka_min and obj.delka_max else obj.popis
        return format_html('<div style="white-space: nowrap;">{}</div>', text)
    

class BednaPoziceInline(admin.TabularInline):
    """
    Inline pro správu beden v rámci pozice.
    """
    model = Bedna
    extra = 0
    fields = ('cislo_bedny', 'behalter_nr', 'hmotnost', 'tara', 'mnozstvi', 'material', 'sarze', 'dodatecne_info',
              'dodavatel_materialu', 'vyrobni_zakazka', 'odfosfatovat', 'tryskat', 'rovnat', 'stav_bedny', 'poznamka',)
    readonly_fields = ('cislo_bedny', 'behalter_nr', 'hmotnost', 'tara', 'mnozstvi', 'material', 'sarze', 'dodatecne_info',
                       'dodavatel_materialu', 'vyrobni_zakazka', 'odfosfatovat', 'tryskat', 'rovnat', 'stav_bedny', 'poznamka',)
    show_change_link = True


@admin.register(Pozice)
class PoziceAdmin(admin.ModelAdmin):
    """
    Správa pozic v administraci.
    """
    fields = ('kod', 'kapacita',)
    readonly_fields = ('kod',)
    list_display = ("kod", "get_pocet_beden", "get_vyuziti", "seznam_beden")
    list_per_page = 20
    search_fields = ("kod",)
    ordering = ("kod",)
    inlines = [BednaPoziceInline]

    @admin.display(description="Obsazenost")
    def get_pocet_beden(self, obj: Pozice):
        return f"{obj.pocet_beden} / {obj.kapacita}"

    @admin.display(description="Využití")
    def get_vyuziti(self, obj: Pozice):
        """
        Zobrazí procentuální využití pozice jako barevný progress bar.
        """
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


@admin.register(Pletivo)
class PletivoAdmin(SimpleHistoryAdmin):
    """
    Správa pletiv v administraci.
    """
    list_display = ('nazev', 'rozmer_oka', 'tloustka_dratu')
    list_display_links = ('nazev',)
    ordering = ['nazev']
    list_per_page = 25

    history_list_display = ['nazev', 'rozmer_oka', 'tloustka_dratu']
    history_search_fields = ['nazev']
    history_list_per_page = 20

@admin.register(PoziceZakazkaOrder)
class PoziceZakazkaOrderAdmin(admin.ModelAdmin):
    """
    Správa pozic zakázek v administraci.
    """
    list_display = ('zakazka', 'pozice', 'poradi')
    list_display_links = ('zakazka',)
    ordering = ['pozice', 'poradi']
    list_per_page = 25

    search_fields = ['zakazka__nazev', 'pozice__kod']
    list_filter = ['pozice']


class RozpracovanostBednaInline(admin.TabularInline):
    model = Rozpracovanost.bedny.through
    fk_name = 'rozpracovanost'
    extra = 0
    can_delete = True
    verbose_name = "Bedna"
    verbose_name_plural = "Bedny v rozpracovanosti"
    fields = ('bedna_link', 'cislo_bedny', 'zakazka', 'stav', 'hmotnost', 'tara', 'mnozstvi')
    readonly_fields = fields
    ordering = ('bedna__cislo_bedny',)

    @admin.display(description='Bedna')
    def bedna_link(self, obj):
        bedna = obj.bedna
        if not bedna:
            return '-'
        return format_html('<a href="{}">{}</a>', bedna.get_admin_url(), bedna)

    @admin.display(description='Číslo bedny')
    def cislo_bedny(self, obj):
        return getattr(obj.bedna, 'cislo_bedny', '-')

    @admin.display(description='Zakázka')
    def zakazka(self, obj):
        bedna = obj.bedna
        if not bedna or not bedna.zakazka:
            return '-'
        return format_html('<a href="{}">{}</a>', bedna.zakazka.get_admin_url(), bedna.zakazka)

    @admin.display(description='Stav')
    def stav(self, obj):
        bedna = obj.bedna
        return bedna.get_stav_bedny_display() if bedna else '-'

    @admin.display(description='Netto kg')
    def hmotnost(self, obj):
        bedna = obj.bedna
        return bedna.hmotnost if bedna and bedna.hmotnost is not None else '-'

    @admin.display(description='Tára kg')
    def tara(self, obj):
        bedna = obj.bedna
        return bedna.tara if bedna and bedna.tara is not None else '-'

    @admin.display(description='Množství ks')
    def mnozstvi(self, obj):
        bedna = obj.bedna
        return bedna.mnozstvi if bedna and bedna.mnozstvi is not None else '-'


@admin.register(Rozpracovanost)
class RozpracovanostAdmin(admin.ModelAdmin):
    """
    Správa měsíční rozpracovanosti v administraci.
    """
    list_display = ('cas_zaznamu', 'pocet_beden',)
    list_display_links = ('cas_zaznamu',)
    ordering = ['-cas_zaznamu']
    list_per_page = 25
    date_hierarchy = 'cas_zaznamu'
    actions = (tisk_rozpracovanost_action,)
    inlines = [RozpracovanostBednaInline]

    class Media:
        js = (
            'orders/js/admin_actions_target_blank.js',
        )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        bedny_qs = Bedna.objects.only('pk', 'cislo_bedny', 'zakazka').order_by('cislo_bedny')
        return qs.annotate(_bedny_count=Count('bedny', distinct=True)).prefetch_related(
            Prefetch('bedny', queryset=bedny_qs)
        )

    def get_action_choices(self, request, default_choices=models.BLANK_CHOICE_DASH):
        """Seskupení akcí rozpracovanosti do optgroup + formátování placeholderů.
        Skupiny:
        - Tisk dokladů
        - Ostatní - (delete_selected) spadne do 'Ostatní'.
        """
        actions = self.get_actions(request)
        if not actions:
            return default_choices

        group_map = {
            'tisk_rozpracovanost_action': 'Tisk dokladů',
        }
        order = ['Tisk dokladů']
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
                # Přidat skupinu akcí bez řazení akcí uvnitř skupiny
                choices.append((g, opts))
        return choices

    def pocet_beden(self, obj):
        return getattr(obj, '_bedny_count', obj.pocet_beden)

    pocet_beden.short_description = 'Počet beden'


# Nastavení atributů AdminSite
admin.site.index_title = "Správa zakázek"