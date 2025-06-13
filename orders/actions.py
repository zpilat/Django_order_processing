from django.contrib import admin, messages
from django.shortcuts import redirect
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.forms.models import model_to_dict

import datetime
from weasyprint import HTML

from .models import Zakazka, Bedna, Kamion, Zakaznik, StavBednyChoice
from .utils import utilita_tisk_karet_beden

# Akce pro bedny:

@admin.action(description="Vytisknout kartu bedny do PDF")
def tisk_karet_beden_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartou bedny nebo více označených beden.
    """
    if queryset.count() == 1:
        bedna = queryset.first()
        context = {"bedna": bedna}
        html_string = render_to_string("orders/karta_bedny_eur.html", context)
        pdf_file = HTML(string=html_string).write_pdf()
        response = HttpResponse(pdf_file, content_type="application/pdf")
        response['Content-Disposition'] = f'inline; filename="karta_bedny_{bedna.cislo_bedny}.pdf"'
        return response
    # Pokud je více beden, udělej hromadné PDF (každá bedna nová stránka)
    elif queryset.count() > 1:
        return utilita_tisk_karet_beden(modeladmin, request, queryset)
    else:
        messages.error(request, "Neoznačili jste žádnou bednu.")
        return None

# Akce pro zakázky:

@admin.action(description="Expedice vybraných zakázek")
def expedice_zakazek_action(modeladmin, request, queryset):
    """
    Expeduje vybrané zakázky a jejich bedny.

    Průběh:
    1. Zkontroluje se, zda v každé zakázce aspoň jedna bedna ve vybraných zakázkách má stav `K_EXPEDICI`.
        - V opačném případě se vrátí chyba pomocí `messages.error` a akce se přeruší.
        - Pro zákazníka s příznakem pouze_komplet mohou být expedovány pouze kompletní zakázky, které mají všechny bedny ve stavu `K_EXPEDICI`.       
    2. Pro každého zákazníka v querysetu:
        - Vytvoří se nový objekt `Kamion`:
            - `prijem_vydej='V'` (výdej)
            - `datum` dnešní datum
            - `zakaznik` nastavený na aktuálního zákazníka
            - `cislo_dl` s prefixem zkratky zákazníka a dnešním datem
    3. Pro každou zakázku daného zákazníka:
        - Zkontroluje se, zda všechny bedny v zakázce mají stav `K_EXPEDICI`.
        - Pokud ano:
            - Převede všechny bedny na stav `EXPEDOVANO`.
            - Nastaví pole `kamion_vydej` na právě vytvořený kamion.
            - Označí `zakazka.expedovano = True`.
        - Pokud ne:
            - Vytvoří novou zakázku se stejnými daty jako původní a převede do ní bedny, které nejsou ve stavu `K_EXPEDICI`.
            - Původní zakázku vyexpeduje dle předchozího postupu.
            
    4. Po úspěšném průběhu odešle `messages.success`. V případě nesplnění podmínek vrátí chybu pomocí `messages.error` a akce se přeruší.
    """
    #1
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

    #2
    zakaznici = Zakaznik.objects.filter(kamiony__zakazky_prijem__in=queryset).distinct()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    for zakaznik in zakaznici:
        kamion = Kamion.objects.create(
            zakaznik=zakaznik,
            cislo_dl=f"{zakaznik.zkratka} - {today_str}",
            datum=datetime.date.today(),
            prijem_vydej='V',
        )

        #3
        zakazky_zakaznika = queryset.filter(kamion_prijem__zakaznik=zakaznik)
        for zakazka in zakazky_zakaznika:
            # Pokud nejsou všechny bedny K_EXPEDICI, vytvoří novou zakázku s původními daty a převede do ní bedny, které nejsou v K_EXPEDICI           
            if not all(bedna.stav_bedny == StavBednyChoice.K_EXPEDICI for bedna in zakazka.bedny.all()):
                # Vytvoří novou zakázku s daty z původní zakázky
                zakazka_data = model_to_dict(zakazka, exclude=['id', 'kamion_vydej', 'expedovano'])
                zakazka_data['kamion_prijem'] = zakazka.kamion_prijem # Přidá instanci kamion_prijem místo id
                nova_zakazka = Zakazka.objects.create(**zakazka_data)

                # Převede bedny, které nejsou v K_EXPEDICI do nové zakázky
                for bedna in zakazka.bedny.exclude(stav_bedny=StavBednyChoice.K_EXPEDICI):
                    bedna.zakazka = nova_zakazka
                    bedna.save()
        
            for bedna in zakazka.bedny.filter(stav_bedny=StavBednyChoice.K_EXPEDICI):
                # Převede bedny na stav EXPEDOVANO
                bedna.stav_bedny = StavBednyChoice.EXPEDOVANO
                bedna.save()

            # Expedice zakázky
            zakazka.kamion_vydej = kamion
            zakazka.expedovano = True
            zakazka.save()

    #4
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
    return utilita_tisk_karet_beden(modeladmin, request, bedny)    


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
    bedny = Bedna.objects.filter(zakazka__kamion_prijem__in=queryset)
    if not bedny.exists():
        messages.error(request, "V označeném kamionu nejsou žádné bedny.")
        return None
    return utilita_tisk_karet_beden(modeladmin, request, bedny)
