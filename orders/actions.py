from django.contrib import admin, messages
from django.shortcuts import redirect
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.shortcuts import render

import datetime
from weasyprint import HTML

from .models import Zakazka, Bedna, Kamion, Zakaznik, StavBednyChoice
from .utils import utilita_tisk_dokumentace, utilita_expedice_zakazek, utilita_kontrola_zakazek, utilita_tisk_dl_a_proforma_faktury
from .forms import VyberKamionVydejForm
from .choices import KamionChoice, StavBednyChoice

# Akce pro bedny:

@admin.action(description="Vytisknout karty bedny")
def tisk_karet_beden_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartou bedny pro označené bedny.
    """
    # Upraví popis zakázky na zkrácenou verzi, aby se vlezla do pole v kartě bedny.
    if queryset.count() > 0:
        filename = "karty_beden.pdf"
        html_path = "orders/karta_bedny_eur.html"
        return utilita_tisk_dokumentace(modeladmin, request, queryset, html_path, filename)
    else:
        messages.error(request, "Neoznačili jste žádnou bednu.")
        return None

@admin.action(description="Vytisknout KKK")
def tisk_karet_kontroly_kvality_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartou kontroly kvality pro označené bedny.
    """
    # Upraví popis zakázky na zkrácenou verzi, aby se vlezla do pole v kartě bedny.
    if queryset.count() > 0:
        filename = "karty_kontroly_kvality.pdf"
        html_path = "orders/karta_kontroly_kvality_eur.html"
        response = utilita_tisk_dokumentace(modeladmin, request, queryset, html_path, filename)
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
            - `prijem_vydej=KamionChoice.VYDEJ`
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
        
    utilita_kontrola_zakazek(modeladmin, request, queryset)

    zakaznici = Zakaznik.objects.filter(kamiony__zakazky_prijem__in=queryset).distinct()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    for zakaznik in zakaznici:
        kamion = Kamion.objects.create(
            zakaznik=zakaznik,
            datum=datetime.date.today(),
            prijem_vydej=KamionChoice.VYDEJ,
        )
        kamion.cislo_dl=f"EXP-{int(kamion.poradove_cislo):03d}-{kamion.datum.year}-{kamion.zakaznik.zkratka}"
        kamion.save()

        zakazky_zakaznika = queryset.filter(kamion_prijem__zakaznik=zakaznik)
        utilita_expedice_zakazek(modeladmin, request, zakazky_zakaznika, kamion)

    messages.success(request, f"Zakázky byly úspěšně expedovány, byl vytvořen nový kamion výdeje {kamion.cislo_dl}.")


@admin.action(description="Vytisknout karty beden z vybraných zakázek")
def tisk_karet_beden_zakazek_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami beden ze zvolených zakázkách.
    """
    if not queryset.exists():
        messages.error(request, "Neoznačili jste žádnou zakázku.")
        return None
    bedny = Bedna.objects.filter(zakazka__in=queryset)
    if not bedny.exists():
        messages.error(request, "V označených zakázkách nejsou žádné bedny.")
        return None
    filename = "karty_beden.pdf"
    html_path = "orders/karta_bedny_eur.html"
    return utilita_tisk_dokumentace(modeladmin, request, bedny, html_path, filename)

@admin.action(description="Vytisknout KKK z vybraných zakázek")
def tisk_karet_kontroly_kvality_zakazek_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami kontroly kvality ze zvolených zakázkách.
    """
    if not queryset.exists():
        messages.error(request, "Neoznačili jste žádnou zakázku.")
        return None
    bedny = Bedna.objects.filter(zakazka__in=queryset)
    if not bedny.exists():
        messages.error(request, "V označených zakázkách nejsou žádné bedny.")
        return None
    filename = "karty_kontroly_kvality.pdf"
    string = "orders/karta_kontroly_kvality_eur.html"
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
    
    utilita_kontrola_zakazek(modeladmin, request, queryset)

    zakaznik_id = zakaznici[0]

    if 'apply' in request.POST:
        form = VyberKamionVydejForm(request.POST, zakaznik=zakaznik_id)
        if form.is_valid():
            kamion = form.cleaned_data['kamion']
            utilita_expedice_zakazek(modeladmin, request, queryset, kamion)

            messages.success(
                request,
                f"Zakázky byly úspěšně expedovány do kamionu {kamion} zákazníka {kamion.zakaznik.nazev}."
            )
            return
    else:
        form = VyberKamionVydejForm(zakaznik=zakaznik_id)

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


@admin.action(description="Vytisknout dodací list kamionu")
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
        zkratka = kamion.zakaznik.zkratka.lower()
        html_path = f"orders/dodaci_list_{zkratka}.html"
        filename = f'dodaci_list_{kamion.cislo_dl}.pdf'
        return utilita_tisk_dl_a_proforma_faktury(modeladmin, request, kamion, html_path, filename)
    # Pokud není pro zákazníka zatím tisk DL umožněn, zobrazí se chybová zpráva
    else:
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
        modeladmin.message_user(request, "Tisk proforma faktury je možný pouze pro kamiony výdej.", level=messages.ERROR)
        return
    # Zkontroluje, zda je kamion pro zákazníka Eurotec
    if kamion.zakaznik.zkratka == "EUR":
        zkratka = kamion.zakaznik.zkratka.lower()
        html_path = f"orders/proforma_faktura_{zkratka}.html"
        filename = f'proforma_faktura_{kamion.cislo_dl}.pdf'
        return utilita_tisk_dl_a_proforma_faktury(modeladmin, request, kamion, html_path, filename)
    # Pokud není pro zákazníka zatím tisk proforma faktury umožněn, zobrazí se chybová zpráva
    else:
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
    html_path = "orders/karta_bedny_eur.html"
    return utilita_tisk_dokumentace(modeladmin, request, bedny, html_path, filename)

@admin.action(description="Vytisknout KKK z vybraného kamionu")
def tisk_karet_kontroly_kvality_kamionu_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami kontroly kvality z vybraného kamionu.
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
    filename = "karty_kontroly_kvality.pdf"
    html_path = "orders/karta_kontroly_kvality_eur.html"
    return utilita_tisk_dokumentace(modeladmin, request, bedny, html_path, filename)