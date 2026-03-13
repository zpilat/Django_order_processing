from django.contrib import messages
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.forms.models import model_to_dict
from django.db import transaction
from django.contrib.staticfiles import finders
from django.utils import timezone
from django.utils.html import format_html

import csv

from .choices import StavBednyChoice, RovnaniChoice, TryskaniChoice, ZinkovaniChoice
from django.db.models import When, Value, Q
from .models import Zakazka, Bedna

import pandas as pd

from weasyprint import HTML, CSS

import gc
import logging
logger = logging.getLogger('orders')

from .services.pdf_cards_service import build_cards_pdf
from .services.expedice_service import (
    expedice_beden_do_existujiciho_kamionu,
    expedice_zakazek_do_existujiciho_kamionu,
)
from .services.exceptions import ServiceValidationError, ServiceOperationError


def truncate_with_title(text, max_len=15):
    if text is None:
        return '-'
    text = str(text)
    if not text:
        return '-'
    if len(text) <= max_len:
        return text
    short = f"{text[:max_len]}..."
    return format_html('<span title="{}">{}</span>', text, short)


def build_postup_vyroby_cases():
    """Vrátí seznam Django ORM `When(...)` výrazů replikujících logiku property `Bedna.postup_vyroby`.

    Použití v adminu:
        from django.db.models import Case, Value, IntegerField
        qs.annotate(
            postup_vyroby_value=Case(*build_postup_vyroby_cases(), default=Value(0), output_field=IntegerField())
        )

    Udržuje jediný zdroj pravdy pro výpočet postupu (SQL ekvivalent). Po změně property aktualizovat i tuto funkci.
    """
    good_rovnat = [RovnaniChoice.ROVNA, RovnaniChoice.VYROVNANA]
    good_tryskat = [TryskaniChoice.CISTA, TryskaniChoice.OTRYSKANA]
    good_zinkovat = [ZinkovaniChoice.NEZINKOVAT, ZinkovaniChoice.UVOLNENO]
    return [
        When(stav_bedny=StavBednyChoice.NEPRIJATO, then=Value(0)),
        When(stav_bedny=StavBednyChoice.PRIJATO, then=Value(10)),
        When(stav_bedny=StavBednyChoice.K_NAVEZENI, then=Value(20)),
        When(stav_bedny=StavBednyChoice.NAVEZENO, then=Value(30)),
        When(stav_bedny=StavBednyChoice.DO_ZPRACOVANI, then=Value(40)),
        When(stav_bedny=StavBednyChoice.ZAKALENO, then=Value(50)),
        # ZKONTROLOVANO varianty (od nejužší po obecnou)
        When(stav_bedny=StavBednyChoice.ZKONTROLOVANO, rovnat__in=good_rovnat, tryskat__in=good_tryskat, zinkovat__in=good_zinkovat, then=Value(95)),
        When(stav_bedny=StavBednyChoice.ZKONTROLOVANO, rovnat__in=good_rovnat, tryskat__in=good_tryskat, then=Value(85)),
        When(stav_bedny=StavBednyChoice.ZKONTROLOVANO, rovnat__in=good_rovnat, zinkovat__in=good_zinkovat, then=Value(85)),
        When(stav_bedny=StavBednyChoice.ZKONTROLOVANO, tryskat__in=good_tryskat, zinkovat__in=good_zinkovat, then=Value(85)),
        When(stav_bedny=StavBednyChoice.ZKONTROLOVANO, tryskat__in=good_tryskat, then=Value(75)),
        When(stav_bedny=StavBednyChoice.ZKONTROLOVANO, rovnat__in=good_rovnat, then=Value(75)),
        When(stav_bedny=StavBednyChoice.ZKONTROLOVANO, zinkovat__in=good_zinkovat, then=Value(75)),
        When(stav_bedny=StavBednyChoice.ZKONTROLOVANO, then=Value(60)),
        When(stav_bedny__in=[StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO], then=Value(100)),
    ]


def get_verbose_name_for_column(model, field_chain):
    """
    Vrátí verbose_name (popisek) i pro zanořené (řetězené) pole včetně FK (např. 'zakazka__celozavit').
    """
    fields = field_chain.split('__')
    current_model = model
    for i, field_name in enumerate(fields):
        field = current_model._meta.get_field(field_name)
        if i == len(fields) - 1:
            return field.verbose_name.capitalize()
        current_model = field.remote_field.model
    return field_chain  # fallback

def utilita_tisk_dokumentace(modeladmin, request, queryset, html_path, filename):
    """Utilita pro tisk dokumentace s jednou šablonou na bednu."""
    return utilita_tisk_dokumentace_sablony(modeladmin, request, queryset, [html_path], filename)


def utilita_tisk_dokumentace_sablony(modeladmin, request, queryset, html_paths, filename):
    """
    Vytvoří PDF, které na každou bednu rendruje všechny dodané šablony za sebou.
    """
    try:
        return build_cards_pdf(
            bedny_qs=queryset,
            template_paths=html_paths,
            filename=filename,
            request=request,
        )
    except ServiceValidationError as exc:
        logger.warning(
            f"Uživatel {getattr(request, 'user', None)}: tisk dokumentace se nepodařil kvůli validaci: {exc}"
        )
        messages.error(request, str(exc))
        return None
    except Exception:
        logger.exception("Neočekávaná chyba při generování PDF dokumentace.")
        messages.error(request, "Došlo k chybě při generování PDF dokumentace.")
        return None

def utilita_tisk_dl_a_proforma_faktury(modeladmin, request, kamion, html_path, filename):
    """
    Tiskne dodací list, proforma fakturu a přehled zakázek pro vybraný kamion a daného zákazníka.
    """
    context = {"kamion": kamion}
    if request and hasattr(request, "user") and request.user.is_authenticated:
        user_last_name = (
            request.user.last_name
            or request.user.get_full_name()
            or request.user.get_username()
        )
        context["user_last_name"] = user_last_name
    html_string = render_to_string(html_path, context)
    stylesheets = []
    css_path = finders.find('orders/css/pdf_shared.css')
    if css_path:
        stylesheets.append(CSS(filename=css_path))
    else:
        logger.warning("Nepodařilo se najít CSS 'orders/css/pdf_shared.css' pro tisk DL/proforma faktury/přehled zakázek.")

    base_url = request.build_absolute_uri('/') if request else None
    pdf_file = HTML(string=html_string, base_url=base_url).write_pdf(stylesheets=stylesheets)
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    logger.info(f"Uživatel {request.user} vygeneroval PDF dokumentaci pro kamion {kamion}.")
    return response    


def _format_decimal_csv(value):
    if value is None:
        return ''
    text = format(value, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text.replace('.', ',')


def utilita_export_beden_zinkovani_csv(bedny_qs, filename_prefix="bedny_zinkovani", sort_like_dl=False):
    order_fields = ('zakazka_id', 'id') if sort_like_dl else ('cislo_bedny',)
    rows = list(bedny_qs.select_related('zakazka').order_by(*order_fields))

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f"{filename_prefix}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')

    writer = csv.writer(response, delimiter=';', quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        'Číslo bedny',
        'Č.b. zák.',
        'FA/Bestell',
        'Popis',
        'Artikl',
        'Rozměr',        
        'Hmotnost kg',
        'Množství ks',
        'Vrstva',
        'Povrch',
    ])

    for bedna in rows:
        zakazka = getattr(bedna, 'zakazka', None)
        rozmer = f"{getattr(zakazka, 'prumer', '')} x {getattr(zakazka, 'delka', '')}" if zakazka else ''
        writer.writerow([
            bedna.cislo_bedny,
            getattr(bedna, 'behalter_nr', '') if zakazka else '',
            getattr(bedna, 'vyrobni_zakazka', '') if zakazka else '',
            getattr(zakazka, 'popis', '') if zakazka else '',
            getattr(zakazka, 'artikl', '') if zakazka else '',
            rozmer,
            _format_decimal_csv(getattr(bedna, 'hmotnost', None)),
            getattr(bedna, 'mnozstvi', '') or '',
            getattr(zakazka, 'vrstva', '') if zakazka else '',
            getattr(zakazka, 'povrch', '') if zakazka else '',
        ])

    logger.info(f"Vyexportováno {len(rows)} beden pro zinkování do CSV.")
    return response


def validate_bedny_pripraveny_k_expedici(modeladmin, request, bedny_qs, message=None):
    """Ověří, že bedny ve stavu K_EXPEDICI splňují podmínky pro expedici.

    Podmínky: rovnat v {ROVNA, VYROVNANA}, tryskat v {CISTA, OTRYSKANA}, zinkovat v {NEZINKOVAT, UVOLNENO}.
    Vrací True/False; při porušení zapíše chybovou hlášku a zaloguje.
    """
    bedny_ke_kontrole = bedny_qs.filter(stav_bedny=StavBednyChoice.K_EXPEDICI)
    if not bedny_ke_kontrole.exists():
        return True

    if (
        bedny_ke_kontrole.exclude(rovnat__in=[RovnaniChoice.ROVNA, RovnaniChoice.VYROVNANA]).exists()
        or bedny_ke_kontrole.exclude(tryskat__in=[TryskaniChoice.CISTA, TryskaniChoice.OTRYSKANA]).exists()
        or bedny_ke_kontrole.exclude(zinkovat__in=[ZinkovaniChoice.NEZINKOVAT, ZinkovaniChoice.UVOLNENO]).exists()
    ):
        text = message or "Pro expedici musí být rovnání Rovná/Vyrovnaná, tryskání Čistá/Otryskaná a zinkování Nezinkovat/Uvolněno."
        try:
            modeladmin.message_user(request, text, level=messages.ERROR)
        except Exception:
            logger.error("Nelze zapsat zprávu pro uživatele při validaci beden před expedicí.")
        logger.warning("Bedny nesplňují podmínky pro expedici (rovnání/tryskání/zinkování).")
        return False

    return True

@transaction.atomic
def utilita_expedice_zakazek(modeladmin, request, queryset, kamion):
    """
    Expeduje vybrané zakázky a jejich bedny.
    - Nastaví stav beden na EXPEDOVANO.
    - Přiřadí zakázkám `kamion_vydej` na daný kamion.
    - Pokud zakázka obsahuje i bedny, které nejsou ve stavu K_EXPEDICI,
        vytvoří novou zakázku (se stejnými daty jako původní) a přesune tam pouze bedny ve stavu K_EXPEDICI.
    - Nastaví příznak `expedovano` na zakázce.

    Vrací True při úspěchu, jinak False.
    """
    try:
        expedice_zakazek_do_existujiciho_kamionu(
            zakazky_qs=queryset,
            kamion_vydej=kamion,
            actor=getattr(request, "user", None),
        )
        return True
    except ServiceValidationError as exc:
        logger.warning(f"Expedice zakázek selhala validací: {exc}")
        messages.error(request, str(exc))
        return False
    except ServiceOperationError as exc:
        logger.error(f"Expedice zakázek selhala operací: {exc}")
        messages.error(request, str(exc))
        return False
    except Exception:
        logger.exception("Neočekávaná chyba při expedici zakázek.")
        messages.error(request, "Došlo k neočekávané chybě při expedici zakázek.")
        return False
            
@transaction.atomic
def utilita_expedice_beden(modeladmin, request, bedny_qs, kamion):
    """
    Expeduje vybrané bedny do zadaného kamionu (výdej).

    - Nastaví stav beden na EXPEDOVANO.
    - Přiřadí jejich zakázkám `kamion_vydej` na daný kamion.
    - Pro bedny, které nejsou vybrány k expedici, vytvoří novou zakázku (se stejnými daty jako původní) a přesune je tam.
    - Nastaví příznak `expedovano` na původní zakázce.

    Vrací True při úspěchu, jinak False.
    """
    try:
        expedice_beden_do_existujiciho_kamionu(
            bedny_qs=bedny_qs,
            kamion_vydej=kamion,
            actor=getattr(request, "user", None),
        )
        return True
    except ServiceValidationError as exc:
        logger.warning(f"Expedice beden selhala validací: {exc}")
        messages.error(request, str(exc))
        return False
    except ServiceOperationError as exc:
        logger.error(f"Expedice beden selhala operací: {exc}")
        messages.error(request, str(exc))
        return False
    except Exception:
        logger.exception("Neočekávaná chyba při expedici beden.")
        messages.error(request, "Došlo k neočekávané chybě při expedici beden.")
        return False

def utilita_kontrola_zakazek(modeladmin, request, queryset):
    """
    Kontroluje zakázky na přítomnost beden a jejich stav.
    Pokud zakázka nemá žádné bedny nebo žádné bedny ve stavu K_EXPEDICI, zobrazí chybovou zprávu.
    Pro zákazníka s příznakem pouze_komplet mohou být expedovány pouze kompletní zakázky, které mají všechny bedny ve stavu `K_EXPEDICI`.

    Vrací True, pokud kontroly prošly, jinak False.
    """
    for zakazka in queryset:
        bedny_qs = zakazka.bedny.all()

        if not bedny_qs.exists():
            logger.warning(f"Zakázka {zakazka} nemá žádné bedny.")
            messages.error(request, f"Zakázka {zakazka} nemá žádné bedny.")
            return False

        if not bedny_qs.filter(stav_bedny=StavBednyChoice.K_EXPEDICI).exists():
            logger.warning(f"Zakázka {zakazka} nemá žádné bedny ve stavu K_EXPEDICI.")
            messages.error(request, f"Zakázka {zakazka} nemá žádné bedny ve stavu K_EXPEDICI.")
            return False
    
        if zakazka.kamion_prijem.zakaznik.pouze_komplet:
            if bedny_qs.exclude(stav_bedny=StavBednyChoice.K_EXPEDICI).exists():
                logger.warning(f"Zakázka {zakazka} pro zákazníka s příznakem 'Pouze kompletní zakázky' musí mít všechny bedny ve stavu K_EXPEDICI.")
                messages.error(request, f"Zakázka {zakazka} pro zákazníka s nastaveným příznakem 'Pouze kompletní zakázky' musí mít všechny bedny ve stavu K_EXPEDICI.")
                return False

    # Dodatečná kontrola stavu rovnání/tryskání/zinkování pro bedny určené k expedici
    bedny_k_expedici = Bedna.objects.filter(zakazka__in=queryset, stav_bedny=StavBednyChoice.K_EXPEDICI)
    if not validate_bedny_pripraveny_k_expedici(modeladmin, request, bedny_k_expedici):
        return False

    return True

def utilita_validate_excel_upload(uploaded_file):
    """
    Validuje nahraný Excel soubor pro import zakázek.
    Kontroluje, zda je soubor přítomen, má správnou příponu a není prázdný.
    Pokouší se načíst soubor pomocí pandas pro ověření, že je platný.
    Vrací seznam chybových zpráv, pokud nějaké jsou.
    """
    errors: list[str] = []

    if not uploaded_file:
        errors.append("Soubor chybí.")
        return errors

    name = uploaded_file.name.casefold()

    if not name.endswith('.xlsx'):
        errors.append("Soubor musí mít příponu .xlsx.")
        return errors

    if uploaded_file.size == 0:
        errors.append("Soubor je prázdný.")
        return errors

    # Volitelný lehký sanity read: při chybě uživatele pouze varujeme do logu,
    # vlastní čtení a validace obsahu proběhne v import procesu.
    try:
        pd.read_excel(uploaded_file, nrows=1, engine="openpyxl")
    except Exception:
        logger.warning("Sanity read selhal, soubor nemusí být plnohodnotné .xlsx, pokračuji a ověřím při importu.")
    finally:
        try:
            uploaded_file.seek(0)
        except Exception:
            logger.warning("Nepodařilo se vrátit ukazatel nahraného souboru na začátek.", exc_info=True)
    return errors
