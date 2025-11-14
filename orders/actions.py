from django.contrib import admin, messages
from django.shortcuts import redirect
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.shortcuts import render
from django.db import transaction, IntegrityError, DataError
from django.utils import timezone
from django import forms
from django.forms import formset_factory
from django.template.response import TemplateResponse
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.contrib.staticfiles import finders
from django.db.models import Count, Q

import csv
import datetime
from decimal import Decimal
from weasyprint import HTML
from weasyprint import CSS

from .models import Zakazka, Bedna, Kamion, Zakaznik, Pozice
from .utils import (
    utilita_tisk_dokumentace,
    utilita_tisk_dokumentace_sablony,
    utilita_expedice_zakazek,
    utilita_kontrola_zakazek,
    utilita_tisk_dl_a_proforma_faktury,
)
from .forms import VyberKamionVydejForm, OdberatelForm, KNavezeniForm, NavezenoForm
from .choices import (
    KamionChoice,
    StavBednyChoice,
    RovnaniChoice,
    TryskaniChoice,
    STAV_BEDNY_SKLADEM,
    STAV_BEDNY_ROZPRACOVANOST,
)

import logging
logger = logging.getLogger('orders')


def _abort_if_paused_bedny(modeladmin, request, queryset, action_label):
    """Vrátí True, pokud výběr obsahuje pozastavené bedny a vypíše chybovou hlášku.

    Pozn.: queryset může být již oříznut (slice) a pak nelze volat .filter().
    V takovém případě spadne do Python fallbacku.
    """
    try:
        paused_count = queryset.filter(pozastaveno=True).count()
    except TypeError:
        paused_count = sum(1 for obj in queryset if getattr(obj, 'pozastaveno', False))
    if paused_count:
        logger.info(
            f"Uživatel {request.user} se pokusil provést akci '{action_label}', ale výběr obsahuje {paused_count} pozastavených beden."
        )
        message = _(
            f"Akci \"{action_label}\" nelze provést, protože výběr obsahuje {paused_count} pozastavených beden."
        )
        modeladmin.message_user(request, message, level=messages.ERROR)
        return True
    return False

def _abort_if_zakazky_maji_pozastavene_bedny(modeladmin, request, queryset, action_label):
    """Vrátí True, pokud vybrané zakázky obsahují pozastavené bedny."""
    paused_qs = Bedna.objects.filter(zakazka__in=queryset, pozastaveno=True)
    if paused_qs.exists():
        paused_count = paused_qs.count()
        zakazka_count = paused_qs.values("zakazka_id").distinct().count()
        logger.info(
            f"Uživatel {request.user} se pokusil provést akci '{action_label}', ale vybrané zakázky obsahují {paused_count} pozastavených beden ve {zakazka_count} zakázkách."
        )
        message = _(f"Akci \"{action_label}\" nelze provést, protože vybrané zakázky obsahují {paused_count} pozastavených beden (celkem {zakazka_count} zakázek).")
        modeladmin.message_user(request, message, level=messages.ERROR)
        return True
    return False

def _abort_if_kamiony_maji_pozastavene_bedny(modeladmin, request, queryset, action_label):
    """Vrátí True, pokud vybrané kamiony obsahují zakázky s pozastavenými bednami."""
    paused_qs = Bedna.objects.filter(zakazka__kamion_prijem__in=queryset, pozastaveno=True)
    if paused_qs.exists():
        paused_count = paused_qs.count()
        kamion_count = paused_qs.values("zakazka__kamion_prijem_id").distinct().count()
        logger.info(
            f"Uživatel {request.user} se pokusil provést akci '{action_label}', ale vybrané kamiony obsahují {paused_count} pozastavených beden ve {kamion_count} kamionech."
        )
        message = _(f"Akci \"{action_label}\" nelze provést, protože vybrané kamiony obsahují {paused_count} pozastavených beden (celkem {kamion_count} kamionů).")
        modeladmin.message_user(request, message, level=messages.ERROR)
        return True
    return False

def _format_decimal(value):
    """Vrátí číslo s desetinnou čárkou; prázdný řetězec pro None."""
    if value is None:
        return ''
    try:
        decimal_value = Decimal(value)
    except Exception:
        return str(value)
    text = format(decimal_value, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text.replace('.', ',')

# Akce pro bedny:

@admin.action(description="Export vyfiltrovaných beden do CSV")
def export_bedny_to_csv_action(modeladmin, request, queryset):
    """Exportuje aktuálně vyfiltrované bedny do CSV (celý queryset, ne jen stránku)."""
    select_across = request.POST.get('select_across') == '1'
    selected_ids = request.POST.getlist(admin.helpers.ACTION_CHECKBOX_NAME)

    try:
        initial_count = queryset.count()
    except Exception:
        initial_count = len(list(queryset))

    queryset = queryset.select_related(
        'zakazka',
        'zakazka__kamion_prijem',
        'zakazka__kamion_prijem__zakaznik',
        'zakazka__typ_hlavy',
        'zakazka__predpis',
    )

    zakazka_ids = list(queryset.values_list('zakazka_id', flat=True).distinct())
    all_ke_map = {}
    if zakazka_ids:
        aggregation = (
            Bedna.objects.filter(zakazka_id__in=zakazka_ids)
            .values('zakazka_id')
            .annotate(
                total=Count('id'),
                ke_total=Count('id', filter=Q(stav_bedny=StavBednyChoice.K_EXPEDICI)),
            )
        )
        all_ke_map = {row['zakazka_id']: row['total'] == row['ke_total'] and row['total'] > 0 for row in aggregation}

    rows = list(queryset.order_by('pk'))

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f"bedny_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')  # BOM pro korektní otevření v Excelu
    writer = csv.writer(response, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    header = [
        'Zákazník',
        'Datum',
        'Zakázka',
        'Číslo bedny',
        'Navezené',
        'Rozměr',
        'Do zprac.',
        'Zakal.',
        'Kontrol.',
        'Křivost',
        'Čistota',
        'K expedici',
        'Hmotnost',
        'Poznámka',
        'Hlava + závit',
        'Název',
        'Skupina',
    ]
    writer.writerow(header)

    stav_pro_navezene_x = {
        StavBednyChoice.K_NAVEZENI: 'o',
        StavBednyChoice.NAVEZENO: 'x',
    }
    do_zpracovani_states = {
        StavBednyChoice.DO_ZPRACOVANI,
        StavBednyChoice.ZAKALENO,
        StavBednyChoice.ZKONTROLOVANO,
        StavBednyChoice.K_EXPEDICI,
    }
    zakaleno_states = {
        StavBednyChoice.ZAKALENO,
        StavBednyChoice.ZKONTROLOVANO,
        StavBednyChoice.K_EXPEDICI,
    }
    zkontrolovano_states = {
        StavBednyChoice.ZKONTROLOVANO,
        StavBednyChoice.K_EXPEDICI,
    }
    rovnat_map = {
        RovnaniChoice.ROVNA: 'x',
        RovnaniChoice.KRIVA: 'křivá',
        RovnaniChoice.ROVNA_SE: 'rovná se',
        RovnaniChoice.VYROVNANA: 'vyrovnaná',
    }
    tryskat_map = {
        TryskaniChoice.CISTA: 'x',
        TryskaniChoice.SPINAVA: 'špinavá',
        TryskaniChoice.OTRYSKANA: 'otryskaná',
    }

    for bedna in rows:
        zakazka = getattr(bedna, 'zakazka', None)
        kamion_prijem = getattr(zakazka, 'kamion_prijem', None) if zakazka else None
        zakaznik = getattr(kamion_prijem, 'zakaznik', None) if kamion_prijem else None

        prumer = _format_decimal(getattr(zakazka, 'prumer', None)) if zakazka else ''
        delka = _format_decimal(getattr(zakazka, 'delka', None)) if zakazka else ''
        if prumer and delka:
            rozmer = f'{prumer} x {delka}'
        elif prumer:
            rozmer = prumer
        elif delka:
            rozmer = delka
        else:
            rozmer = ''

        stav = bedna.stav_bedny
        navezene = stav_pro_navezene_x.get(stav, '')
        do_zpracovani = 'x' if stav in do_zpracovani_states else ''
        zakaleno = 'x' if stav in zakaleno_states else ''
        zkontrolovano = 'x' if stav in zkontrolovano_states else ''

        rovnat_value = rovnat_map.get(bedna.rovnat, '')
        tryskat_value = tryskat_map.get(bedna.tryskat, '')

        all_ke = all_ke_map.get(getattr(zakazka, 'id', None), False)
        if stav == StavBednyChoice.K_EXPEDICI:
            k_expedici = 'x' if all_ke else '0'
        else:
            k_expedici = ''

        typ_hlavy = ''
        if zakazka and zakazka.typ_hlavy:
            typ_hlavy = str(zakazka.typ_hlavy)
        if zakazka and zakazka.celozavit:
            typ_hlavy = f"{typ_hlavy} + VG" if typ_hlavy else 'VG'

        datum = ''
        if zakazka and zakazka.kamion_prijem and zakazka.kamion_prijem.datum:
            datum = zakazka.kamion_prijem.datum.strftime('%d.%m.%Y')

        writer.writerow([
            str(zakaznik) if zakaznik else '',
            datum,
            getattr(zakazka, 'artikl', '') if zakazka else '',
            bedna.cislo_bedny,
            navezene,
            rozmer,
            do_zpracovani,
            zakaleno,
            zkontrolovano,
            rovnat_value,
            tryskat_value,
            k_expedici,
            _format_decimal(bedna.hmotnost),
            bedna.poznamka or '',
            typ_hlavy,
            getattr(zakazka, 'zkraceny_popis', '') if zakazka else '',
            getattr(getattr(zakazka, 'predpis', None), 'skupina', '') if zakazka else '',
        ])

    logger.info(
        f"Uživatel {getattr(request, 'user', None)} exportoval {len(rows)} beden do CSV.",
    )
    return response

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


@admin.action(description="Vytisknout karty bedny + KKK")
def tisk_karet_bedny_a_kontroly_action(modeladmin, request, queryset):
    """Vytvoří PDF, kde má každá bedna svoji kartu a navazující kartu kontroly kvality."""
    if queryset.values('zakazka__kamion_prijem__zakaznik').distinct().count() != 1:
        logger.error(
            "Uživatel %s se pokusil tisknout kombinované karty beden, ale vybral bedny od více zákazníků.",
            getattr(request, 'user', None),
        )
        modeladmin.message_user(
            request,
            "Pro tisk kombinovaných karet musí být vybrány bedny od jednoho zákazníka.",
            level=messages.ERROR,
        )
        return None

    first_bedna = queryset.first()
    if not first_bedna or not first_bedna.zakazka or not first_bedna.zakazka.kamion_prijem:
        logger.error("Tisk kombinovaných karet selhal: chybí zakázka nebo kamion příjem u vybrané bedny.")
        modeladmin.message_user(request, "Bedna nemá kompletní vazby pro tisk.", level=messages.ERROR)
        return None

    zakaznik = first_bedna.zakazka.kamion_prijem.zakaznik
    zakaznik_zkratka = getattr(zakaznik, 'zkratka', None)
    if zakaznik_zkratka:
        zkratka_lower = zakaznik_zkratka.lower()
        filename = f"karty_bedny_a_kontroly_{zkratka_lower}.pdf"
        html_paths = [
            f"orders/karta_bedny_{zkratka_lower}.html",
            f"orders/karta_kontroly_kvality_{zkratka_lower}.html",
        ]
        response = utilita_tisk_dokumentace_sablony(modeladmin, request, queryset, html_paths, filename)
        if response:
            logger.info(
                "Uživatel %s tiskne kombinované karty bedny+KKK pro %s vybraných beden.",
                getattr(request, 'user', None),
                queryset.count(),
            )
        return response

    logger.error("Bedna %s nemá přiřazeného zákazníka nebo zákazník nemá zkratku.", first_bedna)
    modeladmin.message_user(
        request,
        "Bedna nemá přiřazeného zákazníka nebo zákazník nemá zkratku.",
        level=messages.ERROR,
    )
    return None

@admin.action(description="Přijmout vybrané bedny na sklad", permissions=('change',))
def prijmout_bedny_action(modeladmin, request, queryset):
    """
    Přijme vybrané bedny (NEPRIJATO -> PRIJATO) v režimu ČÁSTEČNÉHO ÚSPĚCHU.

    - Každá bedna je validována a ukládána samostatně.
    - Chybné bedny se přeskočí a zobrazí se pro ně chybové zprávy.
    - Úspěšné se přepnou do stavu PRIJATO ihned (bez globálního rollbacku).
    - Bedny, které nejsou ve stavu NEPRIJATO, jsou hlášeny jako chyba a ponechány beze změny.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Přijmout bedny na sklad"):
        return None

    success = 0
    failures = 0

    # Pro deterministiku pořadí (stabilita logů) seřadíme podle PK
    for bedna in queryset.order_by('pk'):
        if bedna.stav_bedny != StavBednyChoice.NEPRIJATO:
            modeladmin.message_user(
                request,
                f"Bedna {bedna} není ve stavu NEPRIJATO.",
                level=messages.ERROR,
            )
            failures += 1
            continue

        original_state = bedna.stav_bedny
        bedna.stav_bedny = StavBednyChoice.PRIJATO
        try:
            bedna.full_clean()
            bedna.save()
            success += 1
        except ValidationError as e:
            bedna.stav_bedny = original_state
            for msg in e.messages:
                modeladmin.message_user(
                    request,
                    f"Bedna {bedna}: {msg}",
                    level=messages.ERROR,
                )
            failures += 1
        except (IntegrityError, DataError) as e:
            bedna.stav_bedny = original_state
            modeladmin.message_user(
                request,
                f"Bedna {bedna}: {e}",
                level=messages.ERROR,
            )
            failures += 1
        except Exception as e:  # Neočekávané
            bedna.stav_bedny = original_state
            logger.exception(f"Neočekávaná chyba při přijímání bedny {bedna}")
            modeladmin.message_user(
                request,
                f"Bedna {bedna}: Neočekávaná chyba: {e}",
                level=messages.ERROR,
            )
            failures += 1

    if success:
        modeladmin.message_user(
            request,
            f"Přijato na sklad: {success} beden.",
            level=messages.SUCCESS,
        )

    if failures and success:
        modeladmin.message_user(
            request,
            f"Nepřijato: {failures} beden – viz chybové zprávy výše.",
            level=messages.WARNING,
        )
        logger.info(f"Uživatel {request.user} přijal na sklad {success} beden (částečný režim), {failures} mělo chybu.")
    elif failures and not success:
        modeladmin.message_user(
            request,
            "Žádná bedna nebyla přijata (všechny měly chybu).",
            level=messages.ERROR,
        )
        logger.info(f"Uživatel {request.user} se pokusil přijmout bedny na sklad, ale žádná nebyla přijata (všechny měly chybu).")

    return None

def _render_oznacit_k_navezeni(modeladmin, request, queryset, formset):
    """
    Interní funkce vykreslení mezikroku akce (formset s volbou pozic).
    """
    action = request.POST.get("action") or request.GET.get("action") or "oznacit_k_navezeni_action"
    pozice = Pozice.objects.all().order_by('kod')
    context = {
        **modeladmin.admin_site.each_context(request),
        "title": "Zvol pozice pro vybrané bedny",
        "queryset": queryset,
        "formset": formset,
        "vsechny_pozice": pozice,
        "opts": modeladmin.model._meta,
        "action_name": action,
        "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
    }
    return TemplateResponse(request, "admin/bedna/oznacit_k_navezeni.html", context)    

@admin.action(description="Změna stavu bedny na K_NAVEZENI", permissions=('change',))
def oznacit_k_navezeni_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden na K_NAVEZENI a přidá k bedně zvolenou pozici.
    Zkontroluje zda nejsou v querysetu pozastavené bedny a zda jsou všechny ve stavu PRIJATO.
    Pokud nejsou podmínky splněny, akce se přeruší s chybovou hláškou.
    1) GET: zobrazí formset s výběrem pozice pro každou vybranou bednu.
    2) POST (apply): validace kapacit + uložení (stav PRIJATO -> K_NAVEZENI a přiřazení pozice).
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu na K_NAVEZENÍ"):
        return None


    bedny_errors = [bedna for bedna in queryset if bedna.stav_bedny != StavBednyChoice.PRIJATO]
    if bedny_errors:
        logger.info(
            f"Uživatel {request.user} se pokusil změnit stav na K_NAVEZENÍ, ale následující bedny nejsou v PRIJATO: {', '.join(str(b) for b in bedny_errors)}"
        )
        for bedna in bedny_errors:
            modeladmin.message_user(
                request,
                f"Bedna {bedna} není ve stavu PRIJATO, nelze změnit na K NAVEZENÍ.",
                level=messages.ERROR,
            )
        return None

    KNavezeniFormSet = formset_factory(KNavezeniForm, extra=0)

    if request.method == "POST" and ("apply" in request.POST or "apply_open_dashboard" in request.POST):
        redirect_requested = "apply_open_dashboard" in request.POST
        select_ids = request.POST.getlist(admin.helpers.ACTION_CHECKBOX_NAME)
        qs = Bedna.objects.filter(pk__in=select_ids)            
        if _abort_if_paused_bedny(modeladmin, request, qs, "Změna stavu na K_NAVEZENÍ"):
            return None

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
                    messages.warning(request, f"Bedna s ID {bedna_id} nebyla nalezena, přeskočena.")
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

        if redirect_requested:
            return redirect("dashboard_bedny_k_navezeni")
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

@admin.action(description="Změna stavu bedny na NAVEZENO", permissions=('change',))
def oznacit_navezeno_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden z K_NAVEZENI na NAVEZENO.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu na NAVEZENO"):
        return None

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

@admin.action(description="Navezení beden (PŘIJATO, K_NAVEZENÍ -> NAVEZENO)")
def oznacit_prijato_navezeno_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden z PŘIJATO na NAVEZENO, pouze pro uživatele s oprávněním 'mark_bedna_navezeno'.
    1) Zkontroluje, zda není bedna pozastavena.
    2) Zkontroluje, zda jsou všechny bedny ve stavu PŘIJATO nebo K_NAVEZENI.
    3) Provede změnu stavu na NAVEZENO.
    4) Zaznamená akci do logu a zobrazí zprávu o úspěchu.
    5) Pokud nejsou splněny podmínky, zobrazí chybovou zprávu a akci přeruší.
    6) Tato akce je určena pro uživatele s oprávněním 'mark_bedna_navezeno' nebo 'change_bedna' - zajišťuje to get_actions v BednaAdmin.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Navezení beden (PŘIJATO, K_NAVEZENÍ -> NAVEZENO)"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu PŘIJATO
    if queryset.exclude(stav_bedny__in=[StavBednyChoice.PRIJATO, StavBednyChoice.K_NAVEZENI]).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na NAVEZENO, ale některé bedny nejsou ve stavu PŘIJATO nebo K_NAVEZENÍ.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu PŘIJATO nebo K_NAVEZENÍ.", level=messages.ERROR)
        return None
    
    NavezenoFormSet = formset_factory(NavezenoForm, extra=0)

    if request.method == "POST" and "apply" in request.POST:
        select_ids = request.POST.getlist(admin.helpers.ACTION_CHECKBOX_NAME)
        qs = Bedna.objects.filter(pk__in=select_ids)
        if _abort_if_paused_bedny(modeladmin, request, qs, "Navezení beden (PŘIJATO, K_NAVEZENÍ -> NAVEZENO)"):
            return None
        
        initial = [
            {
                "bedna_id": bedna.pk,
                "cislo": bedna.cislo_bedny,
                "pozice": bedna.pozice
            } for bedna in qs
        ]
        formset = NavezenoFormSet(data=request.POST, initial=initial, prefix="ozn")

        # Pokud formset není validní, znovu se vykreslí s hodnotami
        if not formset.is_valid():
            messages.error(request, "Formulář není validní.")
            action = request.POST.get("action") or request.GET.get("action") or "oznacit_prijato_navezeno_action"
            pozice = Pozice.objects.all().order_by('kod')
            context = {
                **modeladmin.admin_site.each_context(request),
                "title": "Potvrďte navezení vybraných beden",
                "queryset": qs,
                "formset": formset,
                "vsechny_pozice": pozice,
                "opts": modeladmin.model._meta,
                "action_name": action,
                "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
            }
            return TemplateResponse(request, "admin/bedna/oznacit_navezeno.html", context)
        

        # Pokud je vše validní, provedeme změnu stavu
        with transaction.atomic():
            vybrane_ids = [f.cleaned_data["bedna_id"] for f in formset.forms]
            bedny_map = {
                b.pk: b for b in Bedna.objects.select_for_update().filter(pk__in=vybrane_ids)
            }

            for form in formset.forms:
                bedna_id = form.cleaned_data["bedna_id"]
                pozice = form.cleaned_data["pozice"]

                bedna = bedny_map.get(bedna_id)
                if not bedna:
                    messages.warning(request, f"Bedna s ID {bedna_id} nebyla nalezena, přeskočena.")
                    continue

                if bedna.stav_bedny in [StavBednyChoice.PRIJATO, StavBednyChoice.K_NAVEZENI]:
                    bedna.stav_bedny = StavBednyChoice.NAVEZENO
                    bedna.pozice = pozice
                    bedna.save()

        messages.success(request, f"Navezeno: {qs.count()} beden.")
        logger.info(f"Uživatel {request.user} změnil stav na NAVEZENO u {qs.count()} beden.")

        return None
    
    # GET – předvyplň formset
    initial = [
        {
            "bedna_id": bedna.pk,
            "cislo": bedna.cislo_bedny,
            "pozice": bedna.pozice
        } for bedna in queryset
    ]
    formset = NavezenoFormSet(initial=initial, prefix="ozn")
    action = request.POST.get("action") or request.GET.get("action") or "oznacit_prijato_navezeno_action"
    pozice = Pozice.objects.all().order_by('kod')
    context = {
        **modeladmin.admin_site.each_context(request),
        "title": "Potvrďte navezení vybraných beden",
        "queryset": queryset,
        "formset": formset,
        "vsechny_pozice": pozice,
        "opts": modeladmin.model._meta,
        "action_name": action,
        "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
    }
    return TemplateResponse(request, "admin/bedna/oznacit_navezeno.html", context)

@admin.action(description="Vrátit bedny do stavu PŘIJATO", permissions=('change',))
def vratit_bedny_do_stavu_prijato_action(modeladmin, request, queryset):
    """
    Vrátí vybrané bedny ze stavu K NAVEZENÍ do PŘIJATO.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Vrácení beden do stavu PŘIJATO"):
        return None

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

@admin.action(description="Změna stavu bedny na DO ZPRACOVÁNÍ", permissions=('change',))
def oznacit_do_zpracovani_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden ze stavu ROZPRACOVANOST (NAVEZENO, DO_ZPRACOVANI, ZAKALENO, ZKONTROLOVANO) na DO_ZPRACOVANI.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu na DO ZPRACOVÁNÍ"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu ROZPRACOVANOST (NAVEZENO, DO_ZPRACOVANI, ZAKALENO, ZKONTROLOVANO)
    if queryset.exclude(stav_bedny__in=STAV_BEDNY_ROZPRACOVANOST).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na DO ZPRACOVÁNÍ, ale některé bedny nejsou ve stavu ROZPRACOVANOST.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu ROZPRACOVANOST.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.stav_bedny in STAV_BEDNY_ROZPRACOVANOST:
                bedna.stav_bedny = StavBednyChoice.DO_ZPRACOVANI
                bedna.save()

    messages.success(request, f"Do zpracování: {queryset.count()} beden.")
    logger.info(f"Uživatel {request.user} změnil stav na DO ZPRACOVÁNÍ u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu bedny na ZAKALENO", permissions=('change',))
def oznacit_zakaleno_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden ze stavu ROZPRACOVANOST (NAVEZENO, DO_ZPRACOVANI, ZAKALENO, ZKONTROLOVANO) na ZAKALENO.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu na ZAKALENO"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu ROZPRACOVANOST
    if queryset.exclude(stav_bedny__in=STAV_BEDNY_ROZPRACOVANOST).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na ZAKALENO, ale některé bedny nejsou ve stavu ROZPRACOVANOST.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu ROZPRACOVANOST.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.stav_bedny in STAV_BEDNY_ROZPRACOVANOST:
                bedna.stav_bedny = StavBednyChoice.ZAKALENO
                bedna.save()

    messages.success(request, f"Zakaleno: {queryset.count()} beden.")
    logger.info(f"Uživatel {request.user} změnil stav na ZAKALENO u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu bedny na ZKONTROLOVÁNO", permissions=('change',))
def oznacit_zkontrolovano_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden na ZKONTROLOVANO.
    Může měnit všechny bedny ve stavu ROZPRACOVANOST (NAVEZENO, DO_ZPRACOVANI, ZAKALENO, ZKONTROLOVANO) na ZKONTROLOVANO.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu na ZKONTROLOVÁNO"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu ROZPRACOVANOST
    if queryset.exclude(stav_bedny__in=STAV_BEDNY_ROZPRACOVANOST).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na ZKONTROLOVANO, ale některé bedny nejsou ve stavu ROZPRACOVANOST.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu ROZPRACOVANOST.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.stav_bedny in STAV_BEDNY_ROZPRACOVANOST:
                bedna.stav_bedny = StavBednyChoice.ZKONTROLOVANO
                bedna.save()

    messages.success(request, f"Zkontrolováno: {queryset.count()} beden.")
    logger.info(f"Uživatel {request.user} změnil stav na ZKONTROLOVANO u {queryset.count()} beden.")
    return None


@admin.action(description="Změna stavu bedny na K_EXPEDICI", permissions=('change',))
def oznacit_k_expedici_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden ze stavu ROZPRACOVANOST (NAVEZENO, DO_ZPRACOVANI, ZAKALENO nebo ZKONTROLOVANO) na K_EXPEDICI.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu na K EXPEDICI"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu ROZPRACOVANOST (NAVEZENO, DO_ZPRACOVANI, ZAKALENO, ZKONTROLOVANO)
    if queryset.exclude(stav_bedny__in=STAV_BEDNY_ROZPRACOVANOST).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na K_EXPEDICI, ale některé bedny nejsou ve stavu ROZPRACOVANOST.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu ROZPRACOVANOST.", level=messages.ERROR)
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
            if bedna.stav_bedny in STAV_BEDNY_ROZPRACOVANOST:
                bedna.stav_bedny = StavBednyChoice.K_EXPEDICI
                bedna.save()

    messages.success(request, f"Změněno na K EXPEDICI: {queryset.count()} beden.")
    logger.info(f"Uživatel {request.user} změnil stav na K_EXPEDICI u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu rovnání na ROVNÁ", permissions=('change',))
def oznacit_rovna_action(modeladmin, request, queryset):
    """
    Změní stav rovnání vybraných beden z NEZADANO na ROVNA.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna rovnání na ROVNÁ"):
        return None

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

@admin.action(description="Změna stavu rovnání na KŘIVÁ", permissions=('change',))
def oznacit_kriva_action(modeladmin, request, queryset):
    """
    Změní stav rovnání vybraných beden z NEZADANO na KRIVA.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna rovnání na KŘIVÁ"):
        return None

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

@admin.action(description="Přesun beden na rovnání (ROVNÁ SE)", permissions=('change',))
def oznacit_rovna_se_action(modeladmin, request, queryset):
    """
    Změní stav rovnání vybraných beden z KRIVA na ROVNA_SE.
    Vytiskne seznam beden k rovnání.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna rovnání na ROVNÁ SE"):
        return None

    bedny = list(queryset.select_related("zakazka__kamion_prijem__zakaznik"))
    if not bedny:
        messages.error(request, "Nebyla vybrána žádná bedna.")
        logger.warning("Akce 'oznacit_rovna_se' byla spuštěna bez vybraných beden.")
        return None

    if any(bedna.rovnat != RovnaniChoice.KRIVA for bedna in bedny):
        logger.info(
            "Uživatel %s se pokusil změnit stav na ROVNA SE, ale alespoň jedna bedna není ve stavu KRIVA.",
            request.user,
        )
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu KRIVA.", level=messages.ERROR)
        return None

    try:
        with transaction.atomic():
            for bedna in bedny:
                bedna.rovnat = RovnaniChoice.ROVNA_SE
                bedna.save()
        logger.info(
            "Uživatel %s změnil stav rovnání na ROVNA SE u %s beden.",
            request.user,
            len(bedny),
        )
        modeladmin.message_user(request, f"Změněno: {len(bedny)} beden.", level=messages.SUCCESS)

    except Exception as e:
        logger.error(f"Chyba při změně stavu rovnání na ROVNA SE: {e}")
        modeladmin.message_user(request, "Došlo k chybě při změně stavu rovnání.", level=messages.ERROR)
        return None

    generated_at = timezone.now()
    user_last_name = ""
    if request.user.is_authenticated:
        user_last_name = (
            request.user.last_name
            or request.user.get_full_name()
            or request.user.get_username()
        )

    total_weight = sum(
        (bedna.hmotnost if bedna.hmotnost is not None else Decimal("0"))
        for bedna in bedny
    )
    total_count = len(bedny)

    context = {
        "bedny": bedny,
        "generated_at": generated_at,
        "user_last_name": user_last_name,
        "total_weight": total_weight,
        "total_count": total_count,
    }

    html_path = "orders/seznam_beden_k_rovnani.html"
    html_string = render_to_string(html_path, context)

    stylesheets = []
    css_path = finders.find('orders/css/pdf_shared.css')
    if css_path:
        stylesheets.append(CSS(filename=css_path))
    else:
        logger.warning("Nepodařilo se najít CSS 'orders/css/pdf_shared.css' pro tisk seznamu beden k rovnání.")

    base_url = request.build_absolute_uri('/')
    pdf_file = HTML(string=html_string, base_url=base_url).write_pdf(stylesheets=stylesheets)

    filename = "seznam_beden_k_rovnani.pdf"
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response['Content-Disposition'] = f'inline; filename={filename}'
    logger.info(
        "Uživatel %s tiskne seznam beden k rovnání (%s ks).",
        request.user,
        total_count,
    )
    return response

@admin.action(description="Změna stavu rovnání na VYROVNANÁ", permissions=('change',))
def oznacit_vyrovnana_action(modeladmin, request, queryset):
    """
    Změní stav rovnání vybraných beden z ROVNA_SE na VYROVNANA.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna rovnání na VYROVNANÁ"):
        return None

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

@admin.action(description="Změna stavu tryskání na ČISTÁ", permissions=('change',))
def oznacit_cista_action(modeladmin, request, queryset):
    """
    Změní stav tryskání vybraných beden z NEZADANO na CISTA.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna tryskání na ČISTÁ"):
        return None

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

@admin.action(description="Změna stavu tryskání na ŠPINAVÁ", permissions=('change',))
def oznacit_spinava_action(modeladmin, request, queryset):
    """
    Změní stav tryskání vybraných beden z NEZADANO na SPINAVA.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna tryskání na ŠPINAVÁ"):
        return None

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

@admin.action(description="Změna stavu tryskání na OTRYSKANÁ", permissions=('change',))
def oznacit_otryskana_action(modeladmin, request, queryset):
    """
    Změní stav tryskání vybraných beden ze SPINAVA na OTRYSKANA.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna tryskání na OTRYSKANÁ"):
        return None

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

@admin.action(description="Přijmout vybrané zakázky na sklad", permissions=('change',))
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

    if _abort_if_zakazky_maji_pozastavene_bedny(modeladmin, request, queryset, "Přijmout vybrané zakázky na sklad"):
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
                        # Použije se e.messages (seznam chybových zpráv), aby odpadl slovník s __all__a podobně
                        logger.info(
                            f"Uživatel {request.user} se pokusil přijmout zakázku {zakazka}, ale bedna {bedna} neprošla validací: {e.messages}."
                        )
                        modeladmin.message_user(
                            request,
                            f"Nelze přijmout zakázku {zakazka}, bedna {bedna} neprošla validací: {e.messages}",
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
        
    if preskoceno_count:
        modeladmin.message_user(
            request,
            f"Přeskočeno: {preskoceno_count} zakázek.",
            level=messages.WARNING,
        )

    return None

@admin.action(description="Expedice vybraných zakázek", permissions=('change',))
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
        - Pokud nemá žádné bedny ve stavu `K_EXPEDICI`, zakázka se přeskočí.      
    6. Po úspěšném průběhu odešle `messages.success`. V případě nesplnění podmínek vrátí chybu pomocí `messages.error` a akce se přeruší.
    """        
    if not queryset.exists():
        return None

    if _abort_if_zakazky_maji_pozastavene_bedny(modeladmin, request, queryset, "Expedice zakázek do nového kamionu"):
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

@admin.action(description="Expedice vybraných zakázek do existujícího kamiónu", permissions=('change',))
def expedice_zakazek_kamion_action(modeladmin, request, queryset):
    """
    Expeduje vybrané zakázky do existujícího kamionu zákazníka.
    """
    zakaznici = queryset.values_list('kamion_prijem__zakaznik', flat=True).distinct()
    if zakaznici.count() != 1:
        logger.error(f"Uživatel {request.user} se pokusil expedovat zakázky do existujícího kamionu, ale vybrané zakázky nepatří jednomu zákazníkovi.")
        modeladmin.message_user(request, "Všechny vybrané zakázky musí patřit jednomu zákazníkovi.", level=messages.ERROR)
        return
    
    if _abort_if_zakazky_maji_pozastavene_bedny(modeladmin, request, queryset, "Expedice zakázek do existujícího kamionu"):
        return None

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

@admin.action(description="Vrácení vybraných zakázek z expedice", permissions=('change',))
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

@admin.action(description="Importovat dodací list pro vybraný kamion příjem bez zakázek", permissions=('change',))
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
    if kamion.prijem_vydej != KamionChoice.PRIJEM:
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
    
@admin.action(description="Přijmout kamion na sklad", permissions=('change',))
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
    if kamion.prijem_vydej != KamionChoice.PRIJEM:
        logger.info(f"Uživatel {request.user} se pokusil přijmout kamion {kamion.cislo_dl}, ale není to kamion s příznakem příjem.")
        modeladmin.message_user(request, "Přijmout kamion je možné pouze u kamionů příjem.", level=messages.ERROR)
        return

    if _abort_if_kamiony_maji_pozastavene_bedny(modeladmin, request, queryset, "Přijmout kamion na sklad"):
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
            # Použije se e.messages (seznam chybových zpráv), aby odpadl slovník s __all__a podobně
            for bedna, e in errors:
                logger.info(
                    f"Uživatel {request.user} se pokusil přijmout kamion {kamion.cislo_dl}, ale bedna {bedna} neprošla validací: {e.messages}."
                )
                modeladmin.message_user(
                    request,
                    f"Nelze přijmout kamion, bedna {bedna} neprošla validací: {e.messages}",
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
            
    logger.info(f"Uživatel {request.user} přijal kamion {kamion} na sklad.")
    modeladmin.message_user(request, f"Kamion {kamion} byl přijat na sklad.", level=messages.SUCCESS)
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
    if kamion.prijem_vydej != KamionChoice.VYDEJ:
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
    if kamion.prijem_vydej != KamionChoice.VYDEJ:
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
    if queryset.first().prijem_vydej != KamionChoice.PRIJEM:
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
    if queryset.first().prijem_vydej != KamionChoice.PRIJEM:
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