from django.contrib import admin, messages
from django.shortcuts import redirect
import datetime
from .models import Zakazka, Bedna, Kamion, Zakaznik, StavBednyChoice


@admin.action(description="Expedice vybraných zakázek")
def expedice_zakazek(modeladmin, request, queryset):
    """
    Expeduje vybrané zakázky a jejich bedny.

    Podmínky:
    - Zakázky musí být označeny jako kompletní (`komplet=True`).
    - Všechny bedny v těchto zakázkách musí mít stav `K_EXPEDICI`.

    Průběh:
    1. Pro každého zákazníka v querysetu:
       - Vytvoří se nový objekt `Kamion`:
         - `prijem_vydej='V'` (výdej)
         - `datum` dnešní datum
         - `zakaznik` nastavený na aktuálního zákazníka
         - `cislo_dl` s prefixem zkratky zákazníka a dnešním datem
    2. Pro každou zakázku daného zákazníka:
       - Převede všechny bedny na stav `EXPEDOVANO`.
       - Nastaví pole `kamion_vydej` na právě vytvořený kamion.
       - Označí `zakazka.expedovano = True`.
    3. Po úspěšném průběhu odešle `messages.success`.

    V případě nesplnění podmínek vrátí chybu pomocí `messages.error` a akce se přeruší.
    """
    # 1) Kontrola kompletivity zakázek
    if not all(z.komplet for z in queryset):
        messages.error(
            request,
            "Všechny vybrané zakázky musí být kompletní (komplet=True)."
        )
        return

    # 2) Kontrola stavu beden
    all_bedny_ready = all(
        bedna.stav_bedny == StavBednyChoice.K_EXPEDICI
        for z in queryset
        for bedna in z.bedny.all()
    )
    if not all_bedny_ready:
        messages.error(
            request,
            "Všechny bedny ve vybraných zakázkách musí být ve stavu K_EXPEDICI."
        )
        return

    # 3) Vlastní expedice
    zakaznici = Zakaznik.objects.filter(kamiony__zakazky_prijem__in=queryset).distinct()
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    for zakaznik in zakaznici:
        kamion = Kamion.objects.create(
            zakazka=zakaznik,
            cislo_dl=f"{zakaznik.zkratka} - {today_str}",
            datum=datetime.date.today(),
            prijem_vydej='V',
        )

        zakazky_zakaznika = queryset.filter(
            kamion_prijem__zakazka=zakaznik
        )

        for zakazka in zakazky_zakaznika:
            # Expedice beden
            for bedna in Bedna.objects.filter(zakazka=zakazka):
                bedna.stav_bedny = StavBednyChoice.EXPEDOVANO
                bedna.save()

            # Expedice zakázky
            zakazka.kamion_vydej = kamion
            zakazka.expedovano = True
            zakazka.save()

    messages.success(request, f"Zakázky byly úspěšně expedovány, byl vytvořen nový kamion výdeje {kamion.cislo_dl}.")


@admin.action(description="Importovat dodací list pro vybraný kamion")
def import_zakazek_beden_action(modeladmin, request, queryset):
    if queryset.count() != 1:
        modeladmin.message_user(request, "Vyber pouze jeden kamion.", level=messages.ERROR)
        return
    kamion = queryset.first()
    return redirect(f'./import-zakazek/?kamion={kamion.pk}')