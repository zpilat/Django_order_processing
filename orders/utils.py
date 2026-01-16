from django.contrib import messages
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.forms.models import model_to_dict
from django.db import transaction
from django.contrib.staticfiles import finders
from django.utils import timezone

from .choices import StavBednyChoice, RovnaniChoice, TryskaniChoice
from django.db.models import When, Value
from .models import Zakazka, Bedna

import pandas as pd

from weasyprint import HTML, CSS

import re
import gc
import logging
logger = logging.getLogger('orders')


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
    return [
        When(stav_bedny=StavBednyChoice.NEPRIJATO, then=Value(0)),
        When(stav_bedny=StavBednyChoice.PRIJATO, then=Value(10)),
        When(stav_bedny=StavBednyChoice.K_NAVEZENI, then=Value(20)),
        When(stav_bedny=StavBednyChoice.NAVEZENO, then=Value(30)),
        When(stav_bedny=StavBednyChoice.DO_ZPRACOVANI, then=Value(40)),
        When(stav_bedny=StavBednyChoice.ZAKALENO, then=Value(50)),
        # ZKONTROLOVANO varianty (od nejužší po obecnou)
        When(stav_bedny=StavBednyChoice.ZKONTROLOVANO, rovnat__in=good_rovnat, tryskat__in=good_tryskat, then=Value(90)),
        When(stav_bedny=StavBednyChoice.ZKONTROLOVANO, rovnat__in=good_rovnat, then=Value(75)),
        When(stav_bedny=StavBednyChoice.ZKONTROLOVANO, tryskat__in=good_tryskat, then=Value(75)),
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
    if not html_paths:
        logger.error("Chybí šablony pro tisk dokumentace.")
        messages.error(request, "Není k dispozici žádná šablona pro tisk dokumentace.")
        return None

    gc.collect()  # Uvolní paměť před generováním PDF
    if queryset.count() > 0:
        from io import BytesIO
        pdf_buffer = BytesIO()
        all_html = ""
        generated_at = timezone.now()
        user_last_name = ""
        if request and hasattr(request, "user") and request.user.is_authenticated:
            user_last_name = (
                request.user.last_name
                or request.user.get_full_name()
                or request.user.get_username()
            )

        for bedna in queryset:
            context = {"bedna": bedna}
            context["generated_at"] = generated_at
            context["user_last_name"] = user_last_name
            for html_path in html_paths:
                html = render_to_string(html_path, context)
                all_html += html + '<p style="page-break-after: always"></p>'  # Oddělí stránky

        stylesheets = []
        css_path = finders.find('orders/css/pdf_shared.css')
        if css_path:
            stylesheets.append(CSS(filename=css_path))
        else:
            logger.warning("Nepodařilo se najít CSS 'orders/css/pdf_shared.css' pro tisk dokumentace.")

        base_url = request.build_absolute_uri('/') if request else None
        pdf_file = HTML(string=all_html, base_url=base_url).write_pdf(stylesheets=stylesheets)
        response = HttpResponse(pdf_file, content_type="application/pdf")
        response['Content-Disposition'] = f'inline; filename={filename}'
        logger.info(
            "Uživatel %s vygeneroval PDF dokumentaci pro %s beden (%s šablon na bednu).",
            getattr(request, 'user', None),
            queryset.count(),
            len(html_paths),
        )
        return response
    else:
        logger.warning(
            "Uživatel %s se pokusil tisknout dokumentaci, ale nebyly vybrány žádné bedny.",
            getattr(request, 'user', None),
        )
        messages.error(request, "Není vybrána žádná bedna k tisku.")
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

@transaction.atomic
def utilita_expedice_zakazek(modeladmin, request, queryset, kamion):
    """
    Expeduje vybrané zakázky a jejich bedny.
    - Nastaví stav beden na EXPEDOVANO.
    - Přiřadí zakázkám `kamion_vydej` na daný kamion.
    - Pokud zakázka obsahuje i bedny, které nejsou ve stavu K_EXPEDICI,
        vytvoří novou zakázku (se stejnými daty jako původní) a přesune tam pouze bedny ve stavu K_EXPEDICI.
    - Nastaví příznak `expedovano` na zakázce.
    """
    for zakazka in queryset:
        bedny = zakazka.bedny.all()
        bedny_k_expedici = bedny.filter(stav_bedny=StavBednyChoice.K_EXPEDICI)
        bedny_ne_k_expedici = bedny.exclude(stav_bedny=StavBednyChoice.K_EXPEDICI)

        if not bedny_k_expedici.exists():
            logger.info(f"Zakázka {zakazka} nemá žádné bedny ve stavu K_EXPEDICI, přeskočeno.")
            continue

        if bedny_ne_k_expedici.exists():
            # Vytvoří novou zakázku pro expedované bedny – původní ponechá neexpedované
            exclude = {'id', 'kamion_vydej', 'expedovano'}
            zakazka_data = {}
            puvodni_zakazka = zakazka.puvodni_zakazka or zakazka
            for field in Zakazka._meta.fields:
                if field.name in exclude:
                    continue
                if field.is_relation and getattr(field, 'many_to_one', False):
                    # FK pole
                    zakazka_data[field.attname] = getattr(zakazka, field.attname)
                else:
                    zakazka_data[field.name] = getattr(zakazka, field.name)

            zakazka_data['puvodni_zakazka_id'] = puvodni_zakazka.id

            nova_zakazka = Zakazka.objects.create(**zakazka_data)
            logger.info(
                f"Uživatel {request.user} vytvořil novou zakázku {nova_zakazka} pro expedované bedny ze zakázky ID {zakazka}."
            )

            for bedna in bedny_k_expedici:
                bedna.zakazka = nova_zakazka
                bedna.stav_bedny = StavBednyChoice.EXPEDOVANO
                bedna.save()
                logger.info(f"Uživatel {request.user} přesunul a expedoval bednu {bedna} do zakázky ID {nova_zakazka}.")

            nova_zakazka.kamion_vydej = kamion
            nova_zakazka.expedovano = True
            nova_zakazka.save()

            # Původní zakázku necháváme s neexpedovanými bednami, kamion ani expedovano se nemění
        else:
            # všechny bedny jsou K_EXPEDICI
            for bedna in bedny_k_expedici:
                bedna.stav_bedny = StavBednyChoice.EXPEDOVANO
                bedna.save()
                logger.info(f"Uživatel {request.user} expedoval bednu {bedna} (stav nastaven na EXPEDOVANO).")

            zakazka.kamion_vydej = kamion
            zakazka.expedovano = True
            zakazka.save()
            logger.info(f"Uživatel {request.user} expedoval zakázku {zakazka} do kamionu {kamion}.")
            
@transaction.atomic
def utilita_expedice_beden(modeladmin, request, bedny_qs, kamion):
    """
    Expeduje vybrané bedny do zadaného kamionu (výdej).

    - Nastaví stav beden na EXPEDOVANO.
    - Přiřadí jejich zakázkám `kamion_vydej` na daný kamion.
    - Pro bedny, které nejsou vybrány k expedici, vytvoří novou zakázku (se stejnými daty jako původní) a přesune je tam.
    - Nastaví příznak `expedovano` na původní zakázce.
    """
    # Zpracováváme po zakázkách kvůli nastavení příznaku expedovano a případnému rozdělení zakázky
    zakazky = Zakazka.objects.filter(bedny__in=bedny_qs).distinct()
    for zakazka in zakazky:
        vybrane_bedny = bedny_qs.filter(zakazka=zakazka)
        vybrane_ids = list(vybrane_bedny.values_list('pk', flat=True))

        zbyvajici_ids = list(zakazka.bedny.exclude(pk__in=vybrane_ids).values_list('pk', flat=True))
        zbyvajici_bedny = Bedna.objects.filter(pk__in=zbyvajici_ids)

        if zbyvajici_bedny.exists():
            # Vytvoř novou zakázku pro expedované bedny (vybrane_bedny)
            exclude = {'id', 'kamion_vydej', 'expedovano'}
            zakazka_data = {}
            puvodni_zakazka = zakazka.puvodni_zakazka or zakazka
            for field in Zakazka._meta.fields:
                if field.name in exclude:
                    continue
                if field.is_relation and getattr(field, 'many_to_one', False):
                    zakazka_data[field.attname] = getattr(zakazka, field.attname)
                else:
                    zakazka_data[field.name] = getattr(zakazka, field.name)
            zakazka_data['puvodni_zakazka_id'] = puvodni_zakazka.id
            nova_zakazka = Zakazka.objects.create(**zakazka_data)
            logger.info(
                f"Uživatel {request.user} vytvořil novou zakázku {nova_zakazka} pro expedované bedny ze zakázky ID {zakazka}."
            )

            for bedna in vybrane_bedny:
                bedna.stav_bedny = StavBednyChoice.EXPEDOVANO
                bedna.zakazka = nova_zakazka
                bedna.save()
                logger.info(
                    f"Uživatel {request.user} přesunul a expedoval bednu {bedna} do zakázky ID {nova_zakazka}."
                )

            nova_zakazka.kamion_vydej = kamion
            nova_zakazka.expedovano = True
            nova_zakazka.save()

            # Původní zakázka zůstává bez změny kamionu a expedovano, s neexpedovanými bednami
        else:
            # Vybrány byly všechny bedny zakázky
            for bedna in vybrane_bedny:
                bedna.stav_bedny = StavBednyChoice.EXPEDOVANO
                bedna.save()
                logger.info(f"Uživatel {request.user} expedoval bednu {bedna} (stav nastaven na EXPEDOVANO).")

            zakazka.kamion_vydej = kamion
            zakazka.expedovano = True
            zakazka.save()

            logger.info(
                f"Uživatel {request.user} expedoval {vybrane_bedny.count()} beden zakázky {zakazka} do kamionu {kamion}. "
                f"Zakázka expedovano={zakazka.expedovano}. Nová zakázka pro zbytek: nevytvořena (vše expedováno)."
            )

def utilita_kontrola_zakazek(modeladmin, request, queryset):
    """
    Kontroluje zakázky na přítomnost beden a jejich stav.
    Pokud zakázka nemá žádné bedny nebo žádné bedny ve stavu K_EXPEDICI, zobrazí chybovou zprávu.
    Pro zákazníka s příznakem pouze_komplet mohou být expedovány pouze kompletní zakázky, které mají všechny bedny ve stavu `K_EXPEDICI`.
    """
    for zakazka in queryset:
        if not zakazka.bedny.exists():
            logger.warning(f"Zakázka {zakazka} nemá žádné bedny.")
            messages.error(request, f"Zakázka {zakazka} nemá žádné bedny.")
            return

        if not any(bedna.stav_bedny == StavBednyChoice.K_EXPEDICI for bedna in zakazka.bedny.all()):
            logger.warning(f"Zakázka {zakazka} nemá žádné bedny ve stavu K_EXPEDICI.")
            messages.error(request, f"Zakázka {zakazka} nemá žádné bedny ve stavu K_EXPEDICI.")
            return
    
        if zakazka.kamion_prijem.zakaznik.pouze_komplet:
            if not all(bedna.stav_bedny == StavBednyChoice.K_EXPEDICI for bedna in zakazka.bedny.all()):
                logger.warning(f"Zakázka {zakazka} pro zákazníka s příznakem 'Pouze kompletní zakázky' musí mít všechny bedny ve stavu K_EXPEDICI.")
                messages.error(request, f"Zakázka {zakazka} pro zákazníka s nastaveným příznakem 'Pouze kompletní zakázky' musí mít všechny bedny ve stavu K_EXPEDICI.")
                return

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
            pass
    return errors
