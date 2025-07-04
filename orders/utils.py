from django.contrib import messages
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.forms.models import model_to_dict
from django.db import transaction

from .choices import StavBednyChoice
from .models import Zakazka, Bedna

from weasyprint import HTML

import re
import gc
import logging
logger = logging.getLogger('orders')


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
    """
    Utilita pro tisk dokumentace.
    """
    gc.collect()  # Uvolní paměť před generováním PDF
    if queryset.count() > 0:
        from io import BytesIO
        pdf_buffer = BytesIO()
        all_html = ""
        for bedna in queryset:
            # Zkrátí popis pro každou bednu do prvního slova začínajícího číslicí.
            utilita_zkraceni_popisu_beden(bedna)
            context = {"bedna": bedna}
            html = render_to_string(html_path, context)
            all_html += html + '<p style="page-break-after: always"></p>'  # Oddělí stránky

        pdf_file = HTML(string=all_html).write_pdf()
        response = HttpResponse(pdf_file, content_type="application/pdf")
        response['Content-Disposition'] = f'inline; filename={filename}'
        return response
    else:
        messages.error(request, "Není vybrána žádná bedna k tisku.")
        return None

def utilita_tisk_dl_a_proforma_faktury(modeladmin, request, kamion, html_path, filename):
    """
    Tiskne dodací list a proforma fakturu pro vybraný kamion a daného zákazníka.
    """
    context = {"kamion": kamion}
    html_string = render_to_string(html_path, context)
    pdf_file = HTML(string=html_string).write_pdf()
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response    

@transaction.atomic
def utilita_expedice_zakazek(modeladmin, request, queryset, kamion):
    """
    Expeduje vybrané zakázky a jejich bedny.
    Pokud zakázka obsahuje bedny, které nejsou ve stavu K_EXPEDICI, vytvoří novou zakázku pro tyto bedny.
    Bedny ve stavu K_EXPEDICI jsou expedovány a jejich stav je změněn na EXPEDOVANO.
    Zakázka je poté expedována do zadaného kamionu a její stav expedovano je nastaven na True.
    """
    for zakazka in queryset:
        bedny = zakazka.bedny.all()
        bedny_k_expedici = bedny.filter(stav_bedny=StavBednyChoice.K_EXPEDICI)
        bedny_ne_k_expedici = bedny.exclude(stav_bedny=StavBednyChoice.K_EXPEDICI)

        if bedny_ne_k_expedici.exists():
            # Vytvoří novou zakázku
            zakazka_data = model_to_dict(zakazka, exclude=['id', 'kamion_vydej', 'expedovano'])
            zakazka_data['kamion_prijem'] = zakazka.kamion_prijem
            nova_zakazka = Zakazka.objects.create(**zakazka_data)
            logger.info(f"Uživatel {request.user} vytvořil novou zakázku {nova_zakazka} pro neexpedovatelné bedny ze zakázky ID {zakazka}.")

            for bedna in bedny_ne_k_expedici:
                bedna.zakazka = nova_zakazka
                bedna.save()
                logger.info(f"Uživatel {request.user} přesunul bednu {bedna} do nové zakázky ID {nova_zakazka}.")

        for bedna in bedny_k_expedici:
            bedna.stav_bedny = StavBednyChoice.EXPEDOVANO
            bedna.save()
            logger.info(f"Uživatel {request.user} expedoval bednu {bedna} (stav nastaven na EXPEDOVANO).")

        zakazka.kamion_vydej = kamion
        zakazka.expedovano = True
        zakazka.save()
        logger.info(f"Uživatel {request.user} expedoval zakázku {zakazka} do kamionu {kamion}.")

def utilita_kontrola_zakazek(modeladmin, request, queryset):
    """
    Kontroluje zakázky na přítomnost beden a jejich stav.
    Pokud zakázka nemá žádné bedny nebo žádné bedny ve stavu K_EXPEDICI, zobrazí chybovou zprávu.
    Pro zákazníka s příznakem pouze_komplet mohou být expedovány pouze kompletní zakázky, které mají všechny bedny ve stavu `K_EXPEDICI`.
    """
    for zakazka in queryset:
        if not zakazka.bedny.exists():
            messages.error(request, f"Zakázka {zakazka} nemá žádné bedny.")
            return

        if not any(bedna.stav_bedny == StavBednyChoice.K_EXPEDICI for bedna in zakazka.bedny.all()):
            messages.error(request, f"Zakázka {zakazka} nemá žádné bedny ve stavu K_EXPEDICI.")
            return
    
        if zakazka.kamion_prijem.zakaznik.pouze_komplet:
            if not all(bedna.stav_bedny == StavBednyChoice.K_EXPEDICI for bedna in zakazka.bedny.all()):
                messages.error(request, f"Zakázka {zakazka} pro zákazníka s nastaveným příznakem 'Pouze kompletní zakázky' musí mít všechny bedny ve stavu K_EXPEDICI.")
                return
            
def utilita_zkraceni_popisu_beden(bedna):
    """
    Zkrátí popis zakázky do prvního slova začínající číslicí.
    """
    match = re.match(r"^(.*?)(\s+\d+.*)?$", bedna.zakazka.popis)    
    if match:
        bedna.zakazka.popis = match.group(1).strip()