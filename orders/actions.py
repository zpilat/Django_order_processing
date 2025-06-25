from django.contrib import admin, messages
from django.shortcuts import redirect
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.forms.models import model_to_dict
from django.shortcuts import render

import datetime
import re
from weasyprint import HTML

from .models import Zakazka, Bedna, Kamion, Zakaznik, StavBednyChoice
from .utils import utilita_tisk_dokumentace, expedice_zakazek, kontrola_zakazek, utilita_zkraceni_popisu_beden
from .forms import VyberKamionForm

# Akce pro bedny:

@admin.action(description="Vytisknout kartu bedny do PDF")
def tisk_karet_beden_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartou bedny pro označené bedny.
    """
    # Upraví popis zakázky na zkrácenou verzi, aby se vlezla do pole v kartě bedny.
    if queryset.count() > 0:
        filename = "karty_beden.pdf"
        string = "orders/karta_bedny_eur.html"
        return utilita_tisk_dokumentace(modeladmin, request, queryset, string, filename)
    else:
        messages.error(request, "Neoznačili jste žádnou bednu.")
        return None

@admin.action(description="Vytisknout KKK do PDF")
def tisk_karet_kontroly_kvality_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartou kontroly kvality pro označené bedny.
    """
    # Upraví popis zakázky na zkrácenou verzi, aby se vlezla do pole v kartě bedny.
    if queryset.count() > 0:
        filename = "karty_kontroly_kvality.pdf"
        string = "orders/karta_kontroly_kvality_eur.html"
        response = utilita_tisk_dokumentace(modeladmin, request, queryset, string, filename)
        return response
    else:
        messages.error(request, "Neoznačili jste žádnou bednu.")
        return None
    
# Akce pro zakázky:

@admin.action(description="Expedice vybraných zakázek")
def expedice_zakazek_action(modeladmin, request, queryset):
    """
    Expeduje vybrané zakázky a jejich bedny.

    Průběh:
    1. Kontrola querysetu a zakázek.       
    2. Pro každého zákazníka v querysetu:
        - Vytvoří se nový objekt `Kamion`:
            - `prijem_vydej='V'` (výdej)
            - `datum` dnešní datum
            - `zakaznik` nastavený na aktuálního zákazníka
            - `cislo_dl` s prefixem zkratky zákazníka a dnešním datem
    3. Pro každou zakázku daného zákazníka:
        - Zkontroluje se, zda všechny bedny v zakázce mají stav `K_EXPEDICI`.
        - Pokud ano, vyexpeduje celou zakázku.
        - Pokud ne, vyexpeduje bedny K_EXPEDICI a vytvoří novou zakázku se stejnými daty jako původní a převede do ní bedny, které nejsou ve stavu `K_EXPEDICI`.            
    4. Po úspěšném průběhu odešle `messages.success`. V případě nesplnění podmínek vrátí chybu pomocí `messages.error` a akce se přeruší.
    """
    if not queryset.exists():
        messages.error(request, "Neoznačili jste žádnou zakázku.")
        return
        
    kontrola_zakazek(modeladmin, request, queryset)

    zakaznici = Zakaznik.objects.filter(kamiony__zakazky_prijem__in=queryset).distinct()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    for zakaznik in zakaznici:
        kamion = Kamion.objects.create(
            zakaznik=zakaznik,
            cislo_dl=f"{zakaznik.zkratka} - {today_str}",
            datum=datetime.date.today(),
            prijem_vydej='V',
        )

        zakazky_zakaznika = queryset.filter(kamion_prijem__zakaznik=zakaznik)
        expedice_zakazek(modeladmin, request, zakazky_zakaznika, kamion)

    messages.success(request, f"Zakázky byly úspěšně expedovány, byl vytvořen nový kamion výdeje {kamion.cislo_dl}.")
    

@admin.action(description="Vytisknout karty beden z vybraných zakázek v PDF")
def tisk_karet_beden_zakazek_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami beden ze zvolených zakázek.
    """
    if not queryset.exists():
        messages.error(request, "Neoznačili jste žádnou zakázku.")
        return None
    bedny = Bedna.objects.filter(zakazka__in=queryset)
    if not bedny.exists():
        messages.error(request, "V označených zakázkách nejsou žádné bedny.")
        return None
    filename = "karty_beden.pdf"
    string = "orders/karta_bedny_eur.html"
    return utilita_tisk_dokumentace(modeladmin, request, bedny, string, filename)

@admin.action(description="Vrácení vybraných zakázek z expedice")
def vratit_zakazky_z_expedice_action(modeladmin, request, queryset):
    """
    Vrátí vybrané zakázky z expedice.
    
    Průběh:
    1. Zkontroluje se, zda je alespoň jedna zakázka vybrána.
    2. Pro každou zakázku v querysetu:
        - Zkontroluje se, zda má stav expedice (expedovano=True).
        - Pokud ano, nastaví se expedovano=False a kamion_vydej=None.
        - Všechny bedny v zakázce se převedou na stav K_EXPEDICI.
    3. Po úspěšném průběhu odešle `messages.success`.
    """
    if not queryset.exists():
        messages.error(request, "Neoznačili jste žádnou zakázku.")
        return

    for zakazka in queryset:
        if not zakazka.expedovano:
            messages.error(request, f"Zakázka {zakazka} není vyexpedována.")
            continue
        
        zakazka.expedovano = False
        zakazka.kamion_vydej = None
        zakazka.save()

        # Převede všechny bedny na stav K_EXPEDICI
        for bedna in zakazka.bedny.all():
            bedna.stav_bedny = StavBednyChoice.K_EXPEDICI
            bedna.save()

    messages.success(request, "Vybrané zakázky byly úspěšně vráceny z expedice.")

@admin.action(description="Expedice do existujícího kamionu")
def expedice_zakazek_kamion_action(modeladmin, request, queryset):
    if not queryset.exists():
        messages.error(request, "Neoznačili jste žádnou zakázku.")
        return

    zakaznici = queryset.values_list('kamion_prijem__zakaznik', flat=True).distinct()
    if zakaznici.count() != 1:
        messages.error(request, "Všechny vybrané zakázky musí patřit jednomu zákazníkovi.")
        return
    
    kontrola_zakazek(modeladmin, request, queryset)

    zakaznik_id = zakaznici[0]

    if 'apply' in request.POST:
        form = VyberKamionForm(request.POST, zakaznik=zakaznik_id)
        if form.is_valid():
            kamion = form.cleaned_data['kamion']
            expedice_zakazek(modeladmin, request, queryset, kamion)

            messages.success(
                request,
                f"Zakázky byly úspěšně expedovány do kamionu {kamion} zákazníka {kamion.zakaznik.nazev}."
            )
            return
    else:
        form = VyberKamionForm(zakaznik=zakaznik_id)

    return render(request, 'admin/expedice_zakazek_form.html', {
        'zakazky': queryset,
        'form': form,
        'title': "Expedice do existujícího kamionu",
        'action': "expedice_zakazek_kamion_action",
    })


# Akce pro kamiony:

@admin.action(description="Importovat dodací list pro vybraný kamion")
def import_kamionu_action(modeladmin, request, queryset):
    """
    Importuje dodací list pro vybraný kamion.
    Předpokládá, že je vybrán pouze jeden kamion a to kamion s příznakem příjem.
    Pokud je vybráno více kamionů, zobrazí se chybová zpráva.
    Zatím je import pouze pro zákazníka Eurotec (EUR).
    """
    # Zkontroluje, zda je vybrán alespoň jeden kamion
    if not queryset.exists():
        modeladmin.message_user(request, "Neoznačili jste žádný kamion.", level=messages.ERROR)
        return
    # Pokud je vybráno více kamionů, zobrazí se chybová zpráva
    if queryset.count() != 1:
        modeladmin.message_user(request, "Vyber pouze jeden kamion.", level=messages.ERROR)
        return
    kamion = queryset.first()
    # Zkontroluje, zda je kamion s příznakem příjem
    if kamion.prijem_vydej != 'P':
        modeladmin.message_user(request, "Import je možný pouze pro kamiony příjem.", level=messages.ERROR)
        return
    # Zkontroluje, zda ke kamionu ještě nejsou přiřazeny žádné zakázky
    if kamion.zakazky_prijem.exists():
        modeladmin.message_user(request, "Kamion již obsahuje zakázky, nelze provést import.", level=messages.ERROR)
        return
    # Import pro zákazníka Eurotec
    if kamion.zakaznik.zkratka == "EUR":
        return redirect(f'./import-zakazek/?kamion={kamion.pk}')
    else:
        # Pokud není pro zákazníka zatím import umožněn, zobrazí se chybová zpráva
        modeladmin.message_user(request, "Import je zatím možný pouze pro zákazníka Eurotec.", level=messages.ERROR)
        return


@admin.action(description="Vytisknout dodací list kamionu do PDF")
def tisk_dodaciho_listu_kamionu_action(modeladmin, request, queryset):
    """
    Vytiskne dodací list pro vybraný kamion do PDF.
    Předpokládá, že je vybrán pouze jeden kamion a to kamion s příznakem výdej.
    Pokud je vybráno více kamionů, zobrazí se chybová zpráva.
    Zatím je tisk pouze pro zákazníka Eurotec (EUR).
    """
    if not queryset.exists():
        modeladmin.message_user(request, "Neoznačili jste žádný kamion.", level=messages.ERROR)
        return
    # Pokud je vybráno více kamionů, zobrazí se chybová zpráva
    if queryset.count() != 1:
        modeladmin.message_user(request, "Vyberte pouze jeden kamion.", level=messages.ERROR)
        return
    kamion = queryset.first()
    # Zkontroluje, zda je kamion s příznakem výdej
    if kamion.prijem_vydej != 'V':
        modeladmin.message_user(request, "Tisk DL je možný pouze pro kamiony výdej.", level=messages.ERROR)
        return
    # Zkontroluje, zda je kamion pro zákazníka Eurotec
    if kamion.zakaznik.zkratka == "EUR":
        context = {"kamion": kamion}
        html_string = render_to_string("orders/dodaci_list_eur.html", context)
        pdf_file = HTML(string=html_string).write_pdf()
        response = HttpResponse(pdf_file, content_type="application/pdf")
        response['Content-Disposition'] = f'inline; filename="dodaci_list_{kamion.cislo_dl}.pdf"'
        return response
    # Pokud není pro zákazníka zatím tisk DL umožněn, zobrazí se chybová zpráva
    else:
        modeladmin.message_user(request, "Tisk DL je zatím možný pouze pro zákazníka Eurotec.", level=messages.ERROR)
        return


@admin.action(description="Vytisknout karty beden z vybraného kamionu v PDF")
def tisk_karet_beden_kamionu_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami beden z vybraného kamionu.
    Musí být vybrán pouze jeden kamion, jinak se zobrazí chybová zpráva.
    Musí se jednat o kamion s příznakem příjem, jinak se zobrazí chybová zpráva.
    Tisknou se pouze karty beden, které nejsou již expedovány.
    """
    if not queryset.exists():
        messages.error(request, "Neoznačili jste žádný kamion.")
        return None
    if queryset.count() != 1:
        messages.error(request, "Vyberte pouze jeden kamion.")
        return None
    if queryset.first().prijem_vydej != 'P':
        messages.error(request, "Tisk karet beden je možný pouze pro kamiony příjem.")
        return None
    bedny = Bedna.objects.filter(zakazka__kamion_prijem__in=queryset).exclude(stav_bedny=StavBednyChoice.EXPEDOVANO)
    if not bedny.exists():
        messages.error(request, "V označeném kamionu nejsou žádné bedny.")
        return None
    filename = "karty_beden.pdf"
    string = "orders/karta_bedny_eur.html"
    return utilita_tisk_dokumentace(modeladmin, request, bedny, string, filename)
