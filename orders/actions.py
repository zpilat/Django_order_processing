from django.contrib import admin, messages
from django.shortcuts import redirect
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.shortcuts import render
from django.db import transaction
from django import forms
from django.forms import formset_factory
from django.template.response import TemplateResponse

import datetime
from weasyprint import HTML

from .models import Zakazka, Bedna, Kamion, Zakaznik, StavBednyChoice, Pozice
from .utils import utilita_tisk_dokumentace, utilita_expedice_zakazek, utilita_kontrola_zakazek, utilita_tisk_dl_a_proforma_faktury
from .forms import VyberKamionVydejForm, OdberatelForm, KNavezeniForm
from .choices import KamionChoice, StavBednyChoice

import logging
logger = logging.getLogger('orders')

# Akce pro bedny:

@admin.action(description="Vytisknout karty bedny")
def tisk_karet_beden_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartou bedny pro označené bedny.
    """
    # Upraví popis zakázky na zkrácenou verzi, aby se vlezla do pole v kartě bedny.
    filename = "karty_beden.pdf"
    html_path = "orders/karta_bedny_eur.html"
    logger.info(f"Uživatel {request.user} tiskne karty beden pro {queryset.count()} vybraných beden.")
    return utilita_tisk_dokumentace(modeladmin, request, queryset, html_path, filename)

@admin.action(description="Vytisknout KKK")
def tisk_karet_kontroly_kvality_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartou kontroly kvality pro označené bedny.
    """
    # Upraví popis zakázky na zkrácenou verzi, aby se vlezla do pole v kartě bedny.
    filename = "karty_kontroly_kvality.pdf"
    html_path = "orders/karta_kontroly_kvality_eur.html"
    response = utilita_tisk_dokumentace(modeladmin, request, queryset, html_path, filename)
    logger.info(f"Uživatel {request.user} tiskne karty kontroly kvality pro {queryset.count()} vybraných beden.")
    return response

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
                "artikl": bedna.zakazka.artikl,
                "typ_hlavy": bedna.zakazka.typ_hlavy,
                "popis": bedna.zakazka.popis,
                "poznamka": bedna.poznamka,
                "pozice": bedna.pozice
            } for bedna in qs
        ]
        formset = KNavezeniFormSet(data=request.POST, initial=initial, prefix="ozn")
        # Pokud formset není validní, znovu se vykreslí s hodnotami
        if not formset.is_valid():           
            messages.error(request, "Formulář není validní.")
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

            for f in formset.forms:
                bedna_id = f.cleaned_data["bedna_id"]
                poznamka = f.cleaned_data["poznamka"]
                pozice = f.cleaned_data["pozice"]
                b = bedny_map.get(bedna_id)
                if not b:
                    continue

                pid = pozice.pk
                # Pokud by přiřazení přesáhlo kapacitu, jen si to poznačíme pro warning
                if obsazenost[pid] + 1 > kapacita[pid]:
                    prekrocena_kapacita += 1

                # Přesun + změna stavu (bez ohledu na kapacitu)
                b.pozice = pozice
                b.poznamka = poznamka
                b.stav_bedny = StavBednyChoice.K_NAVEZENI
                b.save(update_fields=["pozice", "poznamka", "stav_bedny"])

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
            "artikl": bedna.zakazka.artikl,
            "typ_hlavy": bedna.zakazka.typ_hlavy,
            "popis": bedna.zakazka.popis,
            "poznamka": bedna.poznamka,
            "pozice": bedna.pozice
        } for bedna in queryset
    ]
    formset = KNavezeniFormSet(initial=initial, prefix="ozn")
    return _render_oznacit_k_navezeni(modeladmin, request, queryset, formset)        

    
# Akce pro zakázky:

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

@admin.action(description="Expedice do existujícího kamionu")
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
    Vytvoří PDF s kartami beden ze zvolených zakázkách.
    """
    bedny = Bedna.objects.filter(zakazka__in=queryset)
    if not bedny.exists():
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty beden, ale v označených zakázkách nejsou žádné bedny.")
        modeladmin.message_user(request, "V označených zakázkách nejsou žádné bedny.", level=messages.ERROR)
        return None
    filename = "karty_beden.pdf"
    html_path = "orders/karta_bedny_eur.html"
    logger.info(f"Uživatel {request.user} tiskne karty beden pro {bedny.count()} vybraných beden.")
    return utilita_tisk_dokumentace(modeladmin, request, bedny, html_path, filename)

@admin.action(description="Vytisknout KKK z vybraných zakázek")
def tisk_karet_kontroly_kvality_zakazek_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami kontroly kvality ze zvolených zakázkách.
    """
    bedny = Bedna.objects.filter(zakazka__in=queryset)
    if not bedny.exists():
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty kontroly kvality, ale v označených zakázkách nejsou žádné bedny.")
        modeladmin.message_user(request, "V označených zakázkách nejsou žádné bedny.", level=messages.ERROR)
        return None
    filename = "karty_kontroly_kvality.pdf"
    string = "orders/karta_kontroly_kvality_eur.html"
    logger.info(f"Uživatel {request.user} tiskne karty kontroly kvality pro {bedny.count()} vybraných beden.")
    return utilita_tisk_dokumentace(modeladmin, request, bedny, string, filename)

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

@admin.action(description="Importovat dodací list pro vybraný kamion")
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


@admin.action(description="Vytisknout dodací list kamionu")
def tisk_dodaciho_listu_kamionu_action(modeladmin, request, queryset):
    """
    Vytiskne dodací list pro vybraný kamion do PDF.
    Předpokládá, že je vybrán pouze jeden kamion a to kamion s příznakem výdej.
    Pokud je vybráno více kamionů, zobrazí se chybová zpráva.
    Zatím je tisk pouze pro zákazníka Eurotec (EUR).
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
    # Zkontroluje, zda je kamion pro zákazníka Eurotec
    if kamion.zakaznik.zkratka == "EUR":
        zkratka = kamion.zakaznik.zkratka.lower()
        html_path = f"orders/dodaci_list_{zkratka}.html"
        filename = f'dodaci_list_{kamion.cislo_dl}.pdf'
        logger.info(f"Uživatel {request.user} tiskne dodací list kamionu {kamion.cislo_dl} pro zákazníka Eurotec.")
        return utilita_tisk_dl_a_proforma_faktury(modeladmin, request, kamion, html_path, filename)
    # Pokud není pro zákazníka zatím tisk DL umožněn, zobrazí se chybová zpráva
    else:
        logger.info(f"Uživatel {request.user} se pokusil tisknout dodací list kamionu {kamion.cislo_dl}, ale pro tohoto zákazníka není tisk DL zatím možný.")
        modeladmin.message_user(request, f"Tisk DL zatím pro zákazníka {kamion.zakaznik.zkraceny_nazev} není možný", level=messages.ERROR)
        return

@admin.action(description="Vytisknout proforma fakturu kamionu")
def tisk_proforma_faktury_kamionu_action(modeladmin, request, queryset):
    """
    Vytiskne proforma fakturu pro vybraný kamion do PDF.
    Předpokládá, že je vybrán pouze jeden kamion a to kamion s příznakem výdej.
    Pokud je vybráno více kamionů, zobrazí se chybová zpráva.
    Zatím je tisk pouze pro zákazníka Eurotec (EUR).
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
    # Zkontroluje, zda je kamion pro zákazníka Eurotec
    if kamion.zakaznik.zkratka == "EUR":
        zkratka = kamion.zakaznik.zkratka.lower()
        html_path = f"orders/proforma_faktura_{zkratka}.html"
        filename = f'proforma_faktura_{kamion.cislo_dl}.pdf'
        logger.info(f"Uživatel {request.user} tiskne proforma fakturu kamionu {kamion.cislo_dl} pro zákazníka Eurotec.")
        return utilita_tisk_dl_a_proforma_faktury(modeladmin, request, kamion, html_path, filename)
    # Pokud není pro zákazníka zatím tisk proforma faktury umožněn, zobrazí se chybová zpráva
    else:
        logger.info(f"Uživatel {request.user} se pokusil tisknout proforma fakturu kamionu {kamion.cislo_dl}, ale pro tohoto zákazníka není tisk proforma faktury zatím možný.")
        modeladmin.message_user(request, f"Tisk proforma faktury zatím pro zákazníka {kamion.zakaznik.zkraceny_nazev} není možný", level=messages.ERROR)
        return

@admin.action(description="Vytisknout karty beden z vybraného kamionu")
def tisk_karet_beden_kamionu_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami beden z vybraného kamionu.
    Musí být vybrán pouze jeden kamion, jinak se zobrazí chybová zpráva.
    Musí se jednat o kamion s příznakem příjem, jinak se zobrazí chybová zpráva.
    Tisknou se pouze karty beden, které nejsou již expedovány.
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
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty beden, ale v označeném kamionu nejsou žádné bedny.")
        modeladmin.message_user(request, "V označeném kamionu nejsou žádné bedny.", level=messages.ERROR)
        return None
    filename = "karty_beden.pdf"
    html_path = "orders/karta_bedny_eur.html"
    logger.info(f"Uživatel {request.user} tiskne karty beden pro {bedny.count()} vybraných beden.")
    return utilita_tisk_dokumentace(modeladmin, request, bedny, html_path, filename)

@admin.action(description="Vytisknout KKK z vybraného kamionu")
def tisk_karet_kontroly_kvality_kamionu_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami kontroly kvality z vybraného kamionu.
    Musí být vybrán pouze jeden kamion, jinak se zobrazí chybová zpráva.
    Musí se jednat o kamion s příznakem příjem, jinak se zobrazí chybová zpráva.
    Tisknou se pouze karty beden, které nejsou již expedovány.
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
    filename = "karty_kontroly_kvality.pdf"
    html_path = "orders/karta_kontroly_kvality_eur.html"
    logger.info(f"Uživatel {request.user} tiskne karty kontroly kvality pro {bedny.count()} vybraných beden.")
    return utilita_tisk_dokumentace(modeladmin, request, bedny, html_path, filename)