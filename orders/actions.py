from django.contrib import admin, messages
from django.shortcuts import redirect
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.shortcuts import render
from django.db import transaction
from django import forms
from django.forms import formset_factory
from django.template.response import TemplateResponse
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

import datetime
from weasyprint import HTML

from .models import Zakazka, Bedna, Kamion, Zakaznik, Pozice
from .utils import utilita_tisk_dokumentace, utilita_expedice_zakazek, utilita_kontrola_zakazek, utilita_tisk_dl_a_proforma_faktury
from .forms import VyberKamionVydejForm, OdberatelForm, KNavezeniForm
from .choices import KamionChoice, StavBednyChoice, RovnaniChoice, TryskaniChoice, stav_bedny_skladem, stav_bedny_rozpracovanost

import logging
logger = logging.getLogger('orders')

# Akce pro bedny:

@admin.action(description="Vytisknout karty bedny")
def tisk_karet_beden_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartou bedny pro označené bedny. Bedny musí být od jednoho zákazníka.
    """
    if queryset.values('zakazka__kamion_prijem__zakaznik').distinct().count() != 1:
        logger.error(f"Uživatel {request.user} se pokusil tisknout karty beden, ale vybral bedny od více zákazníků.")
        modeladmin.message_user(request, "Pro tisk karet beden musí být vybrány bedny od jednoho zákazníka.", level=messages.ERROR)
        return None

    zakaznik_zkratka = queryset.first().zakazka.kamion_prijem.zakaznik.zkratka
    if zakaznik_zkratka:
        filename = f"karty_beden_{zakaznik_zkratka.lower()}.pdf"
        html_path = f"orders/karta_bedny_{zakaznik_zkratka.lower()}.html"
        response = utilita_tisk_dokumentace(modeladmin, request, queryset, html_path, filename)
        logger.info(f"Uživatel {request.user} tiskne karty beden pro {queryset.count()} vybraných beden.")
        return response
    else:
        logger.error(f"Bedna {queryset.first()} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.")
        modeladmin.message_user(request, "Bedna nemá přiřazeného zákazníka nebo zákazník nemá zkratku.", level=messages.ERROR)
        return None

@admin.action(description="Vytisknout KKK")
def tisk_karet_kontroly_kvality_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartou kontroly kvality pro označené bedny. Bedny musít být od jednoho zákazníka.
    """
    if queryset.values('zakazka__kamion_prijem__zakaznik').distinct().count() != 1:
        logger.error(f"Uživatel {request.user} se pokusil tisknout karty beden, ale vybral bedny od více zákazníků.")
        modeladmin.message_user(request, "Pro tisk karet beden musí být vybrány bedny od jednoho zákazníka.", level=messages.ERROR)
        return None

    zakaznik_zkratka = queryset.first().zakazka.kamion_prijem.zakaznik.zkratka
    if zakaznik_zkratka:
        filename = f"karty_kontroly_kvality_{zakaznik_zkratka.lower()}.pdf"
        html_path = f"orders/karta_kontroly_kvality_{zakaznik_zkratka.lower()}.html"
        response = utilita_tisk_dokumentace(modeladmin, request, queryset, html_path, filename)
        logger.info(f"Uživatel {request.user} tiskne karty kontroly kvality pro {queryset.count()} vybraných beden.")
        return response        
    else:
        logger.error(f"Bedna {queryset.first()} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.")
        modeladmin.message_user(request, "Bedna nemá přiřazeného zákazníka nebo zákazník nemá zkratku.", level=messages.ERROR)
        return None

def _render_oznacit_k_navezeni(modeladmin, request, queryset, formset):
    """
    Interní funkce vykreslení mezikroku akce (formset s volbou pozic).
    """
    action = request.POST.get("action") or request.GET.get("action") or "oznacit_k_navezeni_action"
    context = {
        **modeladmin.admin_site.each_context(request),
        "title": "Zvol pozice pro vybrané bedny",
        "queryset": queryset,
        "formset": formset,
        "opts": modeladmin.model._meta,
        "action_name": action,
        "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
    }
    return TemplateResponse(request, "admin/bedna/oznacit_k_navezeni.html", context)    

@admin.action(description="Změna stavu bedny na K_NAVEZENI")
def oznacit_k_navezeni_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden na K_NAVEZENI a přidá k bedně zvolenou pozici.
    1) GET: zobrazí formset s výběrem pozice pro každou vybranou bednu.
    2) POST (apply): validace kapacit + uložení (stav PRIJATO -> K_NAVEZENI a přiřazení pozice).
    """
    for bedna in queryset:
        if bedna.stav_bedny != StavBednyChoice.PRIJATO:
            logger.info(f"Uživatel {request.user} se pokusil změnit stav bedny {bedna}, ale ta není v stavu PRIJATO.")
            modeladmin.message_user(request, f"Bedna {bedna} není v stavu PRIJATO.", level=messages.ERROR)
            continue

    KNavezeniFormSet = formset_factory(KNavezeniForm, extra=0)

    if request.method == "POST" and "apply" in request.POST:
        select_ids = request.POST.getlist(admin.helpers.ACTION_CHECKBOX_NAME)
        qs = Bedna.objects.filter(pk__in=select_ids)            
        initial = [
            {
                "bedna_id": bedna.pk,
                "cislo": bedna.cislo_bedny,
                "prumer": bedna.zakazka.prumer,
                "delka": bedna.zakazka.delka,
                "hmotnost": bedna.hmotnost,
                "zakazka_id": bedna.zakazka.pk,
                "artikl": bedna.zakazka.artikl,
                "typ_hlavy": bedna.zakazka.typ_hlavy,
                "popis": bedna.zakazka.popis,
                "poznamka_k_navezeni": bedna.poznamka_k_navezeni,
                "pozice": bedna.pozice
            } for bedna in qs
        ]
        formset = KNavezeniFormSet(data=request.POST, initial=initial, prefix="ozn")

        # Pokud formset není validní, znovu se vykreslí s hodnotami
        if not formset.is_valid():           
            messages.error(request, "Formulář není validní.")
            return _render_oznacit_k_navezeni(modeladmin, request, qs, formset)
        
        # Pokud není uvedena pozice u první bedny, znovu se vykreslí s hodnotami a chybou
        aktualni_pozice = formset.forms[0].cleaned_data.get("pozice")
        if not aktualni_pozice:
            messages.error(request, "Je potřeba vybrat alespoň první pozici.")
            return _render_oznacit_k_navezeni(modeladmin, request, qs, formset)

        # Předpočítáme aktuální obsazenost/kapacity pro varování
        kapacita = {}
        obsazenost = {}
        for p in Pozice.objects.all():
            kapacita[p.pk] = p.kapacita
            obsazenost[p.pk] = p.bedny.count()

        uspesne = 0
        prekrocena_kapacita = 0

        with transaction.atomic():
            vybrane_ids = [f.cleaned_data["bedna_id"] for f in formset.forms]
            bedny_map = {
                b.pk: b for b in Bedna.objects.select_for_update().filter(pk__in=vybrane_ids)
            }

            for form in formset.forms:
                bedna_id = form.cleaned_data["bedna_id"]
                poznamka_k_navezeni = form.cleaned_data["poznamka_k_navezeni"]
                pozice = form.cleaned_data["pozice"] #co zadal uživatel na tomto řádku

                # pokud uživatel zadal na řádku pozici, stane se aktuální pozicí, jinak se použije poslední zadaná pozice
                if pozice:
                    aktualni_pozice = pozice
                else:
                    pozice = aktualni_pozice               

                bedna = bedny_map.get(bedna_id)
                if not bedna:
                    continue

                pid = pozice.pk
                # Pokud by přiřazení přesáhlo kapacitu, jen poznačíme pro warning
                if obsazenost[pid] + 1 > kapacita[pid]:
                    prekrocena_kapacita += 1

                # Přesun + změna stavu (bez ohledu na kapacitu)
                bedna.pozice = pozice
                bedna.poznamka_k_navezeni = poznamka_k_navezeni
                bedna.stav_bedny = StavBednyChoice.K_NAVEZENI
                bedna.save()

                obsazenost[pid] += 1
                uspesne += 1

        if uspesne:
            messages.success(request, f"Připraveno k navezení: {uspesne} beden.")
        if prekrocena_kapacita:
            messages.warning(
                request,
                f"U {prekrocena_kapacita} beden byla překročena kapacita cílové pozice, přesto byly přiřazeny."
            )

        # návrat na changelist
        return None

    # GET – předvyplň formset
    initial = [
        {
            "bedna_id": bedna.pk,
            "cislo": bedna.cislo_bedny,
            "prumer": bedna.zakazka.prumer,
            "delka": bedna.zakazka.delka,
            "hmotnost": bedna.hmotnost,
            "artikl": bedna.zakazka.artikl,
            "zakazka_id": bedna.zakazka.pk,
            "typ_hlavy": bedna.zakazka.typ_hlavy,
            "popis": bedna.zakazka.popis,
            "poznamka_k_navezeni": bedna.poznamka_k_navezeni,
            "pozice": bedna.pozice
        } for bedna in queryset
    ]
    formset = KNavezeniFormSet(initial=initial, prefix="ozn")
    return _render_oznacit_k_navezeni(modeladmin, request, queryset, formset)       

@admin.action(description="Změna stavu bedny na NAVEZENO")
def oznacit_navezeno_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden z K_NAVEZENI na NAVEZENO.
    """
    # kontrola, zda jsou všechny bedny v querysetu ve stavu K_NAVEZENI
    if queryset.exclude(stav_bedny=StavBednyChoice.K_NAVEZENI).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na NAVEZENO, ale některé bedny nejsou ve stavu K NAVEZENÍ.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu K NAVEZENÍ.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.stav_bedny == StavBednyChoice.K_NAVEZENI:
                bedna.stav_bedny = StavBednyChoice.NAVEZENO
                bedna.save()

    messages.success(request, f"Navezeno: {queryset.count()} beden.")
    logger.info(f"Uživatel {request.user} změnil stav na NAVEZENO u {queryset.count()} beden.")
    return None

@admin.action(description="Vrátit bedny do stavu PŘIJATO")
def vratit_bedny_do_stavu_prijato_action(modeladmin, request, queryset):
    """
    Vrátí vybrané bedny ze stavu K NAVEZENÍ do PŘIJATO.
    """
    # kontrola, zda jsou všechny zakázky v querysetu ve stavu K_NAVEZENI
    if queryset.exclude(stav_bedny=StavBednyChoice.K_NAVEZENI).exists():
        logger.info(f"Uživatel {request.user} se pokusil vrátit bedny do stavu PŘIJATO, ale některé nejsou ve stavu K NAVEZENÍ.")
        messages.error(request, "Některé vybrané bedny nejsou ve stavu K NAVEZENÍ.")
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.stav_bedny == StavBednyChoice.K_NAVEZENI:
                bedna.stav_bedny = StavBednyChoice.PRIJATO
                bedna.save()

    logger.info(f"Uživatel {request.user} vrátil do stavu PŘIJATO {queryset.count()} beden.")
    messages.success(request, f"Vráceno do stavu PŘIJATO: {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu bedny na DO ZPRACOVÁNÍ")
def oznacit_do_zpracovani_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden z NAVEZENO na DO_ZPRACOVANI.
    """
    # kontrola, zda jsou všechny bedny v querysetu ve stavu NAVEZENO
    if queryset.exclude(stav_bedny=StavBednyChoice.NAVEZENO).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na DO ZPRACOVÁNÍ, ale některé bedny nejsou ve stavu NAVEZENO.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu NAVEZENO.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.stav_bedny == StavBednyChoice.NAVEZENO:
                bedna.stav_bedny = StavBednyChoice.DO_ZPRACOVANI
                bedna.save()

    messages.success(request, f"Do zpracování: {queryset.count()} beden.")
    logger.info(f"Uživatel {request.user} změnil stav na DO ZPRACOVÁNÍ u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu bedny na ZAKALENO")
def oznacit_zakaleno_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden z DO ZPRACOVÁNÍ na ZAKALENO.
    """
    # kontrola, zda jsou všechny bedny v querysetu ve stavu DO_ZPRACOVANI
    if queryset.exclude(stav_bedny=StavBednyChoice.DO_ZPRACOVANI).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na ZAKALENO, ale některé bedny nejsou ve stavu DO ZPRACOVÁNÍ.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu DO ZPRACOVÁNÍ.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.stav_bedny == StavBednyChoice.DO_ZPRACOVANI:
                bedna.stav_bedny = StavBednyChoice.ZAKALENO
                bedna.save()

    messages.success(request, f"Zakaleno: {queryset.count()} beden.")
    logger.info(f"Uživatel {request.user} změnil stav na ZAKALENO u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu bedny na ZKONTROLOVÁNO")
def oznacit_zkontrolovano_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden ze ZAKALENO na ZKONTROLOVANO.
    """
    # kontrola, zda jsou všechny bedny v querysetu ve stavu NAVEZENO
    if queryset.exclude(stav_bedny=StavBednyChoice.ZAKALENO).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na ZKONTROLOVANO, ale některé bedny nejsou ve stavu ZAKALENO.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu ZAKALENO.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.stav_bedny == StavBednyChoice.ZAKALENO:
                bedna.stav_bedny = StavBednyChoice.ZKONTROLOVANO
                bedna.save()

    messages.success(request, f"Zkontrolováno: {queryset.count()} beden.")
    logger.info(f"Uživatel {request.user} změnil stav na ZKONTROLOVANO u {queryset.count()} beden.")
    return None


@admin.action(description="Změna stavu bedny na K_EXPEDICI")
def oznacit_k_expedici_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden z NAVEZENO, DO_ZPRACOVANI, ZAKALENO nebo ZKONTROLOVANO na K_EXPEDICI.
    """
    # kontrola, zda jsou všechny bedny v querysetu ve stavu NAVEZENO, DO_ZPRACOVANI, ZAKALENO nebo ZKONTROLOVANO
    if queryset.exclude(stav_bedny__in=stav_bedny_rozpracovanost).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na K_EXPEDICI, ale některé bedny nejsou ve stavu NAVEZENO, DO_ZPRACOVANI, ZAKALENO nebo ZKONTROLOVANO.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu NAVEZENO, DO_ZPRACOVANI, ZAKALENO nebo ZKONTROLOVANO.", level=messages.ERROR)
        return None
    
    # kontrola, zda všechny bedny splňují podmínky pro přechod do stavu K_EXPEDICI:

    # rovnání musí být buď Rovná nebo Vyrovnaná
    if queryset.exclude(rovnat__in=[RovnaniChoice.ROVNA, RovnaniChoice.VYROVNANA]).exists():
        logger.warning(f'Uživatel {request.user} se pokusil změnit stav na K_EXPEDICI s neplatným stavem rovnání.')
        modeladmin.message_user(request, _("Pro změnu stavu bedny na 'K expedici' musí být rovnání buď Rovná nebo Vyrovnaná " \
        "a tryskání buď Čistá nebo Otryskaná."), level=messages.ERROR)
        return None
        
    # tryskat musí být buď Čistá nebo Otryskaná
    if queryset.exclude(tryskat__in=[TryskaniChoice.CISTA, TryskaniChoice.OTRYSKANA]).exists():
        logger.warning(f'Uživatel {request.user} se pokusil změnit stav na K_EXPEDICI s neplatným stavem tryskání.')
        modeladmin.message_user(request, _("Pro změnu stavu bedny na 'K expedici' musí být rovnání buď Rovná nebo Vyrovnaná " \
        "a tryskání buď Čistá nebo Otryskaná."), level=messages.ERROR)
        return None

    # pokud nějaká bedna nesplňuje podmínky, akce se přeruší
    with transaction.atomic():
        for bedna in queryset:
            if bedna.stav_bedny in [StavBednyChoice.NAVEZENO, StavBednyChoice.DO_ZPRACOVANI, StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO]:
                bedna.stav_bedny = StavBednyChoice.K_EXPEDICI
                bedna.save()

    messages.success(request, f"Změněno na K EXPEDICI: {queryset.count()} beden.")
    logger.info(f"Uživatel {request.user} změnil stav na K_EXPEDICI u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu rovnání na ROVNÁ")
def oznacit_rovna_action(modeladmin, request, queryset):
    """
    Změní stav rovnání vybraných beden z NEZADANO na ROVNA.
    """
    # kontrola, zda jsou všechny bedny v querysetu ve stavu NEZADANO
    if queryset.exclude(rovnat=RovnaniChoice.NEZADANO).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na ROVNA, ale některé bedny nejsou ve stavu NEZADANO.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu NEZADANO.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.rovnat == RovnaniChoice.NEZADANO:
                bedna.rovnat = RovnaniChoice.ROVNA
                bedna.save()

    messages.success(request, f"Změněno: {queryset.count()} beden.")
    logger.info(f"Uživatel {request.user} změnil stav rovnání na ROVNA u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu rovnání na KŘIVÁ")
def oznacit_kriva_action(modeladmin, request, queryset):
    """
    Změní stav rovnání vybraných beden z NEZADANO na KRIVA.
    """
    # kontrola, zda jsou všechny bedny v querysetu ve stavu NEZADANO
    if queryset.exclude(rovnat=RovnaniChoice.NEZADANO).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na KRIVA, ale některé bedny nejsou ve stavu NEZADANO.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu NEZADANO.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.rovnat == RovnaniChoice.NEZADANO:
                bedna.rovnat = RovnaniChoice.KRIVA
                bedna.save()

    messages.success(request, f"Změněno: {queryset.count()} beden.")
    logger.info(f"Uživatel {request.user} změnil stav rovnání na KRIVA u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu rovnání na ROVNÁ SE")
def oznacit_rovna_se_action(modeladmin, request, queryset):
    """
    Změní stav rovnání vybraných beden z KRIVA na ROVNA_SE.
    """
    # kontrola, zda jsou všechny bedny v querysetu ve stavu KRIVA
    if queryset.exclude(rovnat=RovnaniChoice.KRIVA).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na ROVNA SE, ale některé bedny nejsou ve stavu KRIVA.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu KRIVA.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.rovnat == RovnaniChoice.KRIVA:
                bedna.rovnat = RovnaniChoice.ROVNA_SE
                bedna.save()

    messages.success(request, f"Změněno: {queryset.count()} beden.")
    logger.info(f"Uživatel {request.user} změnil stav rovnání na ROVNA SE u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu rovnání na VYROVNANÁ")
def oznacit_vyrovnana_action(modeladmin, request, queryset):
    """
    Změní stav rovnání vybraných beden z ROVNA_SE na VYROVNANA.
    """
    # kontrola, zda jsou všechny bedny v querysetu ve stavu ROVNA_SE
    if queryset.exclude(rovnat=RovnaniChoice.ROVNA_SE).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na VYROVNANA, ale některé bedny nejsou ve stavu ROVNA_SE.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu ROVNÁ SE.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.rovnat == RovnaniChoice.ROVNA_SE:
                bedna.rovnat = RovnaniChoice.VYROVNANA
                bedna.save()

    messages.success(request, f"Změněno: {queryset.count()} beden.")
    logger.info(f"Uživatel {request.user} změnil stav rovnání na VYROVNANÁ u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu tryskání na ČISTÁ")
def oznacit_cista_action(modeladmin, request, queryset):
    """
    Změní stav tryskání vybraných beden z NEZADANO na CISTA.
    """
    # kontrola, zda jsou všechny bedny v querysetu ve stavu NEZADANO
    if queryset.exclude(tryskat=TryskaniChoice.NEZADANO).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav tryskání na CISTA, ale některé bedny nejsou ve stavu NEZADANO.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu NEZADANO.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.tryskat == TryskaniChoice.NEZADANO:
                bedna.tryskat = TryskaniChoice.CISTA
                bedna.save()

    messages.success(request, f"Změněno: {queryset.count()} beden.")
    logger.info(f"Uživatel {request.user} změnil stav tryskání na CISTA u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu tryskání na ŠPINAVÁ")
def oznacit_spinava_action(modeladmin, request, queryset):
    """
    Změní stav tryskání vybraných beden z NEZADANO na SPINAVA.
    """
    # kontrola, zda jsou všechny bedny v querysetu ve stavu NEZADANO
    if queryset.exclude(tryskat=TryskaniChoice.NEZADANO).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav tryskání na SPINAVA, ale některé bedny nejsou ve stavu NEZADANO.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu NEZADANO.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.tryskat == TryskaniChoice.NEZADANO:
                bedna.tryskat = TryskaniChoice.SPINAVA
                bedna.save()

    messages.success(request, f"Změněno: {queryset.count()} beden.")
    logger.info(f"Uživatel {request.user} změnil stav tryskání na SPINAVA u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu tryskání na OTRYSKANÁ")
def oznacit_otryskana_action(modeladmin, request, queryset):
    """
    Změní stav tryskání vybraných beden ze SPINAVA na OTRYSKANA.
    """
    # kontrola, zda jsou všechny bedny v querysetu ve stavu SPINAVA
    if queryset.exclude(tryskat=TryskaniChoice.SPINAVA).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav tryskání na OTRYSKANÁ, ale některé bedny nejsou ve stavu SPINAVA.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu SPINAVA.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.tryskat == TryskaniChoice.SPINAVA:
                bedna.tryskat = TryskaniChoice.OTRYSKANA
                bedna.save()

    messages.success(request, f"Změněno: {queryset.count()} beden.")
    logger.info(f"Uživatel {request.user} změnil stav tryskání na OTRYSKANA u {queryset.count()} beden.")
    return None


# Akce pro zakázky:

@admin.action(description="Přijmout vybrané zakázky na sklad")
def prijmout_zakazku_action(modeladmin, request, queryset):
    """
    Přijme vybrané zakázky na sklad.

    Pro každou zakázku provede:
    - Kontrolu, že obsahuje alespoň jednu bednu ve stavu NEPRIJATO.
    - V jedné transakci a pod řádkovým zámkem (select_for_update) předvaliduje přechod všech beden
      ze stavu NEPRIJATO do stavu PRIJATO pomocí full_clean.
    - Pokud validace projde, uloží změnu stavu všech těchto beden na PRIJATO.

    Jednotlivé zakázky se zpracují nezávisle; pokud u některé validace selže, přeskočí se a pokračuje se další.
    """
    if not queryset.exists():
        return None
    
    prijato_count = 0
    preskoceno_count = 0

    for zakazka in queryset:
        # Kontrola: v zakázce musí být alespoň jedna bedna ve stavu NEPRIJATO
        if not Bedna.objects.filter(zakazka=zakazka, stav_bedny=StavBednyChoice.NEPRIJATO).exists():
            logger.info(
                f"Uživatel {request.user} se pokusil přijmout zakázku {zakazka}, ale nemá žádnou bednu ve stavu NEPRIJATO."
            )
            modeladmin.message_user(
                request,
                f"Zakázka {zakazka} neobsahuje žádné bedny ve stavu NEPRIJATO.",
                level=messages.ERROR,
            )
            preskoceno_count += 1
            continue

        try:
            with transaction.atomic():
                bedny_qs = Bedna.objects.select_for_update().filter(
                    zakazka=zakazka,
                    stav_bedny=StavBednyChoice.NEPRIJATO,
                )
                bedny = list(bedny_qs)

                # Předvalidace všech beden
                errors = []
                for bedna in bedny:
                    original_state = bedna.stav_bedny
                    bedna.stav_bedny = StavBednyChoice.PRIJATO
                    try:
                        bedna.full_clean()
                    except ValidationError as e:
                        errors.append((bedna, e))
                    finally:
                        bedna.stav_bedny = original_state

                if errors:
                    for bedna, e in errors:
                        logger.info(
                            f"Uživatel {request.user} se pokusil přijmout zakázku {zakazka}, ale bedna {bedna} neprošla validací: {e}."
                        )
                        modeladmin.message_user(
                            request,
                            f"Nelze přijmout zakázku {zakazka}, bedna {bedna} neprošla validací: {e}",
                            level=messages.ERROR,
                        )
                    preskoceno_count += 1
                    continue

                # Uložení přechodu stavů
                for bedna in bedny:
                    bedna.stav_bedny = StavBednyChoice.PRIJATO
                    bedna.save()

            prijato_count += 1

        except Exception as e:
            logger.error(
                f"Nastala chyba {e} při přijímání zakázky {zakazka}, zakázka nebyla přijata."
            )
            modeladmin.message_user(
                request,
                f"Nastala chyba {e} při přijímání zakázky {zakazka}.",
                level=messages.ERROR,
            )

    if prijato_count:
        modeladmin.message_user(
            request,
            f"Přijato na sklad: {prijato_count} zakázek.",
            level=messages.SUCCESS,
        )

    return None

@admin.action(description="Expedice vybraných zakázek")
def expedice_zakazek_action(modeladmin, request, queryset):
    """
    Expeduje vybrané zakázky a jejich bedny.

    Průběh:
    1. Kontrola querysetu a zakázek.     
    2. Získání všech zákazníků, kteří mají kamiony spojené s vybranými zakázkami.
    3. Vytvoří se formulář pro výběr odběratele.  
    4. Pro každého zákazníka v querysetu:
        - Vytvoří se nový objekt `Kamion`:
            - `prijem_vydej=KamionChoice.VYDEJ`
            - `datum` dnešní datum
            - `zakaznik` nastavený na aktuálního zákazníka
            - `odberatel` zvolený odběratel z formuláře
    5. Pro každou zakázku daného zákazníka:
        - Zkontroluje se, zda všechny bedny v zakázce mají stav `K_EXPEDICI`.
        - Pokud ano, vyexpeduje celou zakázku.
        - Pokud ne, vyexpeduje bedny K_EXPEDICI a vytvoří novou zakázku se stejnými daty jako původní a převede do ní bedny, které nejsou ve stavu `K_EXPEDICI`.            
    6. Po úspěšném průběhu odešle `messages.success`. V případě nesplnění podmínek vrátí chybu pomocí `messages.error` a akce se přeruší.
    """        
    if not queryset.exists():
        return None

    utilita_kontrola_zakazek(modeladmin, request, queryset)

    zakaznici = Zakaznik.objects.filter(kamiony__zakazky_prijem__in=queryset).distinct()

    if 'apply' in request.POST:
        form = OdberatelForm(request.POST)
        if form.is_valid():
            odberatel = form.cleaned_data['odberatel']

            vytvorene_kamiony = []
            with transaction.atomic():
                for zakaznik in zakaznici:
                    try:
                        kamion = Kamion.objects.create(
                            zakaznik=zakaznik,
                            datum=datetime.date.today(),
                            prijem_vydej=KamionChoice.VYDEJ,
                            odberatel=odberatel,
                        )
                        vytvorene_kamiony.append(kamion.cislo_dl)
                        zakazky_zakaznika = queryset.filter(kamion_prijem__zakaznik=zakaznik)
                        utilita_expedice_zakazek(modeladmin, request, zakazky_zakaznika, kamion)                        
                    except Exception as e:
                        logger.error(f"Nastala chyba {e} při vytváření kamionu pro zákazníka {zakaznik.zkraceny_nazev}.")
                        modeladmin.message_user(request, f"Nastala chyba {e} při vytváření kamionu pro zákazníka {zakaznik.zkraceny_nazev}", level=messages.ERROR)
                        return
            logger.info(f"Uživatel {request.user} úspěšně expedoval zakázky do nových kamionů: {', '.join(vytvorene_kamiony)}.")
            modeladmin.message_user(request, f"Zakázky byly úspěšně expedovány, vytvořené kamiony výdeje {', '.join(vytvorene_kamiony)}.", level=messages.SUCCESS)
            return
    else:
        logger.info(f"Uživatel {request.user} expeduje zakázky do nového kamionu.")
        form = OdberatelForm()

    return render(request, 'admin/expedice_kamionu_form.html', {
        'zakazky': queryset,
        'form': form,
        'title': "Expedice zakázek nového kamionu",
        'action': "expedice_zakazek_action",
    })

@admin.action(description="Expedice vybraných zakázek do existujícího kamiónu")
def expedice_zakazek_kamion_action(modeladmin, request, queryset):
    """
    Expeduje vybrané zakázky do existujícího kamionu zákazníka.
    """
    zakaznici = queryset.values_list('kamion_prijem__zakaznik', flat=True).distinct()
    if zakaznici.count() != 1:
        logger.error(f"Uživatel {request.user} se pokusil expedovat zakázky do existujícího kamionu, ale vybrané zakázky nepatří jednomu zákazníkovi.")
        modeladmin.message_user(request, "Všechny vybrané zakázky musí patřit jednomu zákazníkovi.", level=messages.ERROR)
        return
    
    utilita_kontrola_zakazek(modeladmin, request, queryset)

    zakaznik_id = zakaznici[0]

    if 'apply' in request.POST:
        form = VyberKamionVydejForm(request.POST, zakaznik=zakaznik_id)
        if form.is_valid():
            kamion = form.cleaned_data['kamion']
            utilita_expedice_zakazek(modeladmin, request, queryset, kamion)
            logger.info(f"Uživatel {request.user} úspěšně expedoval zakázky do kamionu {kamion.cislo_dl} zákazníka {kamion.zakaznik.nazev}.")
            modeladmin.message_user(request, f"Zakázky byly úspěšně expedovány do kamionu {kamion} zákazníka {kamion.zakaznik.nazev}.", level=messages.SUCCESS)
            return
    else:
        logger.info(f"Uživatel {request.user} expeduje zakázky do existujícího kamionu zákazníka {Zakaznik.objects.get(id=zakaznik_id).nazev}.")
        form = VyberKamionVydejForm(zakaznik=zakaznik_id)

    return render(request, 'admin/expedice_zakazek_form.html', {
        'zakazky': queryset,
        'form': form,
        'title': "Expedice do existujícího kamionu",
        'action': "expedice_zakazek_kamion_action",
    })

@admin.action(description="Vytisknout karty beden z vybraných zakázek")
def tisk_karet_beden_zakazek_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami beden ze zvolených zakázkách. Zakázky mohou být pouze od jednoho zákazníka.
    Zakázky musí obsahovat alespoň jednu bednu.
    """
    if queryset.values_list('kamion_prijem__zakaznik', flat=True).distinct().count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty beden z více zákazníků.")
        modeladmin.message_user(request, "Zakázky musí být od jednoho zákazníka.", level=messages.ERROR)
        return None
    
    bedny = Bedna.objects.filter(zakazka__in=queryset)
    if not bedny.exists():
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty beden, ale v označených zakázkách nejsou žádné bedny.")
        modeladmin.message_user(request, "V označených zakázkách nejsou žádné bedny.", level=messages.ERROR)
        return None

    zakaznik_zkratka = queryset.first().kamion_prijem.zakaznik.zkratka
    if zakaznik_zkratka:
        filename = f"karty_beden_{zakaznik_zkratka.lower()}.pdf"
        html_path = f"orders/karta_bedny_{zakaznik_zkratka.lower()}.html"
        response = utilita_tisk_dokumentace(modeladmin, request, bedny, html_path, filename)
        logger.info(f"Uživatel {request.user} tiskne karty beden pro {bedny.count()} vybraných beden.")
        return response
    else:
        logger.error(f"Zakázka {queryset.first()} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.")
        modeladmin.message_user(request, "Zakázka nemá přiřazeného zákazníka nebo zákazník nemá zkratku.", level=messages.ERROR)
        return None

@admin.action(description="Vytisknout KKK z vybraných zakázek")
def tisk_karet_kontroly_kvality_zakazek_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami kontroly kvality ze zvolených zakázkách. Zakázky musí být od jednoho zákazníka.
    Vybrané zakázky musí obsahovat alespoň jednu bednu.
    """
    if queryset.values_list('kamion_prijem__zakaznik', flat=True).distinct().count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty beden z více zákazníků.")
        modeladmin.message_user(request, "Zakázky musí být od jednoho zákazníka.", level=messages.ERROR)
        return None
    
    bedny = Bedna.objects.filter(zakazka__in=queryset)
    if not bedny.exists():
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty kontroly kvality, ale v označených zakázkách nejsou žádné bedny.")
        modeladmin.message_user(request, "V označených zakázkách nejsou žádné bedny.", level=messages.ERROR)
        return None
    
    zakaznik_zkratka = queryset.first().kamion_prijem.zakaznik.zkratka
    if zakaznik_zkratka:
        filename = f"karty_kontroly_kvality_{zakaznik_zkratka.lower()}.pdf"
        html_path = f"orders/karta_kontroly_kvality_{zakaznik_zkratka.lower()}.html"
        response = utilita_tisk_dokumentace(modeladmin, request, bedny, html_path, filename)
        logger.info(f"Uživatel {request.user} tiskne karty kontroly kvality pro {bedny.count()} vybraných beden.")
        return response
    else:
        logger.error(f"Zakázka {queryset.first()} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.")
        modeladmin.message_user(request, "Zakázka nemá přiřazeného zákazníka nebo zákazník nemá zkratku.", level=messages.ERROR)
        return None

@admin.action(description="Vrácení vybraných zakázek z expedice")
def vratit_zakazky_z_expedice_action(modeladmin, request, queryset):
    """
    Vrátí vybrané zakázky z expedice.
    
    Průběh:
    1. Pro každou zakázku v querysetu:
        - Zkontroluje se, zda má stav expedice (expedovano=True).
        - Pokud ano, nastaví se expedovano=False a kamion_vydej=None.
        - Všechny bedny v zakázce se převedou na stav K_EXPEDICI.
    2. Po úspěšném průběhu odešle `messages.success`.
    """
    for zakazka in queryset:
        if not zakazka.expedovano:
            logger.info(f"Uživatel {request.user} se pokusil vrátit zakázku {zakazka}, ale ta není vyexpedována.")
            modeladmin.message_user(request, f"Zakázka {zakazka} není vyexpedována.", level=messages.ERROR)
            continue
        
        zakazka.expedovano = False
        zakazka.kamion_vydej = None
        zakazka.save()

        # Převede všechny bedny na stav K_EXPEDICI
        for bedna in zakazka.bedny.all():
            bedna.stav_bedny = StavBednyChoice.K_EXPEDICI
            bedna.save()
        logger.info(f"Uživatel {request.user} úspěšně vrátil zakázku {zakazka} z expedice.")

    modeladmin.message_user(request, "Vybrané zakázky byly úspěšně vráceny z expedice.", level=messages.SUCCESS)

# Akce pro kamiony:

@admin.action(description="Importovat dodací list pro vybraný kamion příjem bez zakázek")
def import_kamionu_action(modeladmin, request, queryset):
    """
    Importuje dodací list pro vybraný kamion.
    Předpokládá, že je vybrán pouze jeden kamion a to kamion s příznakem příjem.
    Pokud je vybráno více kamionů, zobrazí se chybová zpráva.
    Zatím je import pouze pro zákazníka Eurotec (EUR).
    """
    # Pokud je vybráno více kamionů, zobrazí se chybová zpráva
    if queryset.count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil importovat kamion, ale vybral více než jeden kamion.")
        modeladmin.message_user(request, "Vyber pouze jeden kamion.", level=messages.ERROR)
        return
    kamion = queryset.first()
    # Zkontroluje, zda je kamion s příznakem příjem
    if kamion.prijem_vydej != 'P':
        logger.info(f"Uživatel {request.user} se pokusil importovat kamion {kamion.cislo_dl}, ale není to kamion s příznakem příjem.")
        modeladmin.message_user(request, "Import je možný pouze pro kamiony příjem.", level=messages.ERROR)
        return
    # Zkontroluje, zda ke kamionu ještě nejsou přiřazeny žádné zakázky
    if kamion.zakazky_prijem.exists():
        logger.info(f"Uživatel {request.user} se pokusil importovat kamion {kamion.cislo_dl}, ale kamion již obsahuje zakázky.")
        modeladmin.message_user(request, "Kamion již obsahuje zakázky, nelze provést import.", level=messages.ERROR)
        return
    # Import pro zákazníka Eurotec
    if kamion.zakaznik.zkratka == "EUR":
        logger.info(f"Uživatel {request.user} importuje kamion {kamion.cislo_dl} pro zákazníka Eurotec.")
        return redirect(f'./import-zakazek/?kamion={kamion.pk}')
    else:
        # Pokud není pro zákazníka zatím import umožněn, zobrazí se chybová zpráva
        logger.info(f"Uživatel {request.user} se pokusil importovat kamion {kamion.cislo_dl}, ale není to kamion pro zákazníka Eurotec.")
        modeladmin.message_user(request, "Import je zatím možný pouze pro zákazníka Eurotec.", level=messages.ERROR)
        return
    
@admin.action(description="Přijmout kamion na sklad")
def prijmout_kamion_action(modeladmin, request, queryset):
    """
    Přijme vybraný kamion na sklad.
    Předpokládá, že je vybrán pouze jeden kamion a to kamion s příznakem příjem, který obsahuje aspoň 
    jednu bednu ve stavu bedny NEPRIJATO. Převede všechny bedny ze stavu NEPRIJATO do stavu PRIJATO.
    Pokud je vybráno více kamionů, zobrazí se chybová zpráva.
    """
    # Pokud je vybráno více kamionů, zobrazí se chybová zpráva
    if queryset.count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil přijmout kamion, ale vybral více než jeden kamion.")
        modeladmin.message_user(request, "Vyber pouze jeden kamion.", level=messages.ERROR)
        return
    kamion = queryset.first()
    # Zkontroluje, zda je kamion s příznakem příjem
    if kamion.prijem_vydej != 'P':
        logger.info(f"Uživatel {request.user} se pokusil přijmout kamion {kamion.cislo_dl}, ale není to kamion s příznakem příjem.")
        modeladmin.message_user(request, "Přijmout kamion je možné pouze u kamionů příjem.", level=messages.ERROR)
        return
    # Zkontroluje, zda kamion obsahuje aspoň jednu bednu ve stavu NEPRIJATO
    if not Bedna.objects.filter(zakazka__kamion_prijem=kamion, stav_bedny=StavBednyChoice.NEPRIJATO).exists():
        logger.info(f"Uživatel {request.user} se pokusil přijmout kamion {kamion.cislo_dl}, ale neobsahuje žádné bedny ve stavu NEPRIJATO.")
        modeladmin.message_user(request, "Kamion neobsahuje žádné bedny ve stavu NEPRIJATO.", level=messages.ERROR)
        return
    # Předvalidace a uložení v jedné transakci pod řádkovým zámkem
    with transaction.atomic():
        bedny_qs = Bedna.objects.select_for_update().filter(
            zakazka__kamion_prijem=kamion,
            stav_bedny=StavBednyChoice.NEPRIJATO,
        )
        bedny = list(bedny_qs)

        # Nejprve všechny zvalidovat pro přechod do PRIJATO
        errors = []
        for bedna in bedny:
            original_state = bedna.stav_bedny
            bedna.stav_bedny = StavBednyChoice.PRIJATO
            try:
                bedna.full_clean()
            except ValidationError as e:
                errors.append((bedna, e))
            finally:
                bedna.stav_bedny = original_state

        if errors:
            for bedna, e in errors:
                logger.info(
                    f"Uživatel {request.user} se pokusil přijmout kamion {kamion.cislo_dl}, ale bedna {bedna} neprošla validací: {e}."
                )
                modeladmin.message_user(
                    request,
                    f"Nelze přijmout kamion, bedna {bedna} neprošla validací: {e}",
                    level=messages.ERROR,
                )
            return

        # Vše OK – proveď přechod stavu a ulož všechny
        for bedna in bedny:
            try:
                bedna.stav_bedny = StavBednyChoice.PRIJATO
                bedna.save()
            except Exception as e:
                logger.error(
                    f"Nastala chyba {e} při přijímání bedny {bedna} z kamionu {kamion.cislo_dl}, kamion nebyl přijat."
                )
                modeladmin.message_user(
                    request,
                    f"Nastala chyba {e} při přijímání bedny {bedna} z kamionu {kamion.cislo_dl}.",
                    level=messages.ERROR,
                )
                return
            
    logger.info(f"Uživatel {request.user} přijal kamion {kamion.cislo_dl} na sklad.")
    modeladmin.message_user(request, f"Kamion {kamion.cislo_dl} byl přijat na sklad.", level=messages.SUCCESS)
    return

@admin.action(description="Vytisknout dodací list vybraného kamionu výdej")
def tisk_dodaciho_listu_kamionu_action(modeladmin, request, queryset):
    """
    Vytiskne dodací list pro vybraný kamion do PDF.
    Předpokládá, že je vybrán pouze jeden kamion a to kamion s příznakem výdej.
    Pokud je vybráno více kamionů, zobrazí se chybová zpráva.
    """
    # Pokud je vybráno více kamionů, zobrazí se chybová zpráva
    if queryset.count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil tisknout dodací list, ale vybral více než jeden kamion.")
        modeladmin.message_user(request, "Vyberte pouze jeden kamion.", level=messages.ERROR)
        return
    kamion = queryset.first()
    # Zkontroluje, zda je kamion s příznakem výdej
    if kamion.prijem_vydej != 'V':
        logger.info(f"Uživatel {request.user} se pokusil tisknout dodací list kamionu {kamion.cislo_dl}, ale není to kamion s příznakem výdej.")
        modeladmin.message_user(request, "Tisk DL je možný pouze pro kamiony výdej.", level=messages.ERROR)
        return

    zakaznik_zkratka = kamion.zakaznik.zkratka
    if zakaznik_zkratka:
        html_path = f"orders/dodaci_list_{zakaznik_zkratka.lower()}.html"
        filename = f'dodaci_list_{kamion.cislo_dl}.pdf'
        response = utilita_tisk_dl_a_proforma_faktury(modeladmin, request, kamion, html_path, filename)
        logger.info(f"Uživatel {request.user} tiskne dodací list kamionu {kamion.cislo_dl} pro zákazníka {zakaznik_zkratka}.")
        return response
    else:
        logger.error(f"Kamion {kamion} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.")
        modeladmin.message_user(request, "Kamion nemá přiřazeného zákazníka nebo zákazník nemá zkratku.", level=messages.ERROR)
        return None

@admin.action(description="Vytisknout proforma fakturu vybraného kamionu výdej")
def tisk_proforma_faktury_kamionu_action(modeladmin, request, queryset):
    """
    Vytiskne proforma fakturu pro vybraný kamion do PDF.
    Předpokládá, že je vybrán pouze jeden kamion a to kamion s příznakem výdej.
    Pokud je vybráno více kamionů, zobrazí se chybová zpráva.
    """
    # Pokud je vybráno více kamionů, zobrazí se chybová zpráva
    if queryset.count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil tisknout proforma fakturu, ale vybral více než jeden kamion.")
        modeladmin.message_user(request, "Vyberte pouze jeden kamion.", level=messages.ERROR)
        return
    kamion = queryset.first()
    # Zkontroluje, zda je kamion s příznakem výdej
    if kamion.prijem_vydej != 'V':
        logger.info(f"Uživatel {request.user} se pokusil tisknout proforma fakturu kamionu {kamion.cislo_dl}, ale není to kamion s příznakem výdej.")
        modeladmin.message_user(request, "Tisk proforma faktury je možný pouze pro kamiony výdej.", level=messages.ERROR)
        return

    zakaznik_zkratka = kamion.zakaznik.zkratka
    if zakaznik_zkratka:
        html_path = f"orders/proforma_faktura_{zakaznik_zkratka.lower()}.html"
        filename = f'proforma_faktura_{kamion.cislo_dl}.pdf'
        response = utilita_tisk_dl_a_proforma_faktury(modeladmin, request, kamion, html_path, filename)
        logger.info(f"Uživatel {request.user} tiskne proforma fakturu kamionu {kamion.cislo_dl} pro zákazníka {zakaznik_zkratka}.")
        return response


@admin.action(description="Vytisknout karty beden z vybraného kamionu příjem se zakázkami")
def tisk_karet_beden_kamionu_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami beden z vybraného kamionu.
    Musí být vybrán pouze jeden kamion, jinak se zobrazí chybová zpráva.
    Musí se jednat o kamion s příznakem příjem, jinak se zobrazí chybová zpráva.
    Tisknou se pouze karty beden, které nejsou již expedovány.
    Pokud jsou v kamionu bedny nepřijaté, zobrazí se chybová zpráva a tisk se přeruší.
    """
    if queryset.count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty beden, ale vybral více než jeden kamion.")
        modeladmin.message_user(request, "Vyberte pouze jeden kamion.", level=messages.ERROR)
        return None
    if queryset.first().prijem_vydej != 'P':
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty beden kamionu {queryset.first().cislo_dl}, ale není to kamion s příznakem příjem.")
        modeladmin.message_user(request, "Tisk karet beden je možný pouze pro kamiony příjem.", level=messages.ERROR)
        return None
    bedny = Bedna.objects.filter(zakazka__kamion_prijem__in=queryset).exclude(stav_bedny=StavBednyChoice.EXPEDOVANO)
    if not bedny.exists():
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty beden, ale v označeném kamionu nejsou žádné bedny skladem.")
        modeladmin.message_user(request, "V označeném kamionu nejsou žádné bedny skladem.", level=messages.ERROR)
        return None
    
    if bedny.filter(stav_bedny=StavBednyChoice.NEPRIJATO).exists():
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty beden kamionu {queryset.first().cislo_dl}, ale některé bedny nejsou přijaty.")
        modeladmin.message_user(request, "Některé bedny v označeném kamionu nejsou přijaty, lze tisknout pouze komplet přijatý kamion.", level=messages.ERROR)
        return None

    zakaznik_zkratka = queryset.first().zakaznik.zkratka
    if zakaznik_zkratka:
        filename = f"karty_beden_{zakaznik_zkratka.lower()}.pdf"
        html_path = f"orders/karta_bedny_{zakaznik_zkratka.lower()}.html"
        response = utilita_tisk_dokumentace(modeladmin, request, bedny, html_path, filename)
        logger.info(f"Uživatel {request.user} tiskne karty beden pro {bedny.count()} vybraných beden.")
        return response
    else:
        logger.error(f"Kamion {queryset.first()} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.")
        modeladmin.message_user(request, "Kamion nemá přiřazeného zákazníka nebo zákazník nemá zkratku.", level=messages.ERROR)
        return None

@admin.action(description="Vytisknout KKK z vybraného kamionu příjem se zakázkami")
def tisk_karet_kontroly_kvality_kamionu_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami kontroly kvality z vybraného kamionu.
    Musí být vybrán pouze jeden kamion, jinak se zobrazí chybová zpráva.
    Musí se jednat o kamion s příznakem příjem, jinak se zobrazí chybová zpráva.
    Tisknou se pouze karty beden, které nejsou již expedovány.
    Pokud jsou v kamionu bedny nepřijaté, zobrazí se chybová zpráva a tisk se přeruší.
    """
    if queryset.count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty kontroly kvality, ale vybral více než jeden kamion.")
        modeladmin.message_user(request, "Vyberte pouze jeden kamion.", level=messages.ERROR)
        return None
    if queryset.first().prijem_vydej != 'P':
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty kontroly kvality kamionu {queryset.first().cislo_dl}, ale není to kamion s příznakem příjem.")
        modeladmin.message_user(request, "Tisk karet beden je možný pouze pro kamiony příjem.", level=messages.ERROR)
        return None
    bedny = Bedna.objects.filter(zakazka__kamion_prijem__in=queryset).exclude(stav_bedny=StavBednyChoice.EXPEDOVANO)
    if not bedny.exists():
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty kontroly kvality, ale v označeném kamionu nejsou žádné bedny.")
        modeladmin.message_user(request, "V označeném kamionu nejsou žádné bedny.", level=messages.ERROR)
        return None
    
    if bedny.filter(stav_bedny=StavBednyChoice.NEPRIJATO).exists():
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty kontroly kvality kamionu {queryset.first().cislo_dl}, ale některé bedny nejsou přijaty.")
        modeladmin.message_user(request, "Některé bedny v označeném kamionu nejsou přijaty, lze tisknout pouze komplet přijatý kamion.", level=messages.ERROR)
        return None    
    
    zakaznik_zkratka = queryset.first().zakaznik.zkratka
    if zakaznik_zkratka:
        filename = f"karty_kontroly_kvality_{zakaznik_zkratka.lower()}.pdf"
        html_path = f"orders/karta_kontroly_kvality_{zakaznik_zkratka.lower()}.html"
        response = utilita_tisk_dokumentace(modeladmin, request, bedny, html_path, filename)
        logger.info(f"Uživatel {request.user} tiskne karty kontroly kvality pro {bedny.count()} vybraných beden.")
        return response
    else:
        logger.error(f"Kamion {queryset.first()} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.")
        modeladmin.message_user(request, "Kamion nemá přiřazeného zákazníka nebo zákazník nemá zkratku.", level=messages.ERROR)
        return None