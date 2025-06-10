from django.contrib import admin, messages
from django.shortcuts import redirect
from django.forms.models import model_to_dict
import datetime
from .models import Zakazka, Bedna, Kamion, Zakaznik, StavBednyChoice


@admin.action(description="Expedice vybraných zakázek")
def expedice_zakazek(modeladmin, request, queryset):
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


@admin.action(description="Importovat dodací list pro vybraný kamion")
def import_zakazek_beden_action(modeladmin, request, queryset):
    if queryset.count() != 1:
        modeladmin.message_user(request, "Vyber pouze jeden kamion.", level=messages.ERROR)
        return
    kamion = queryset.first()
    return redirect(f'./import-zakazek/?kamion={kamion.pk}')