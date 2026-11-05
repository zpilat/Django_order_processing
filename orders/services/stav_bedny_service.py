from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef

from orders.choices import (
    RovnaniChoice, TryskaniChoice, TypZarizeniChoice, TypZkouskyChoice,
    UvolneniKontrolyChoice, VysledekKontrolyChoice,
)
from orders.models import KontrolaBedny, MereniBedny, Sarze, SarzeKrokBedna
from orders.services.mereni_bedny_service import omezeni_uvolneni_prohybem


def vyhodnotit_tryskani_pri_zakaleni(bedna):
    """Vrátí nový stav tryskání a neotryskané šarže pro případné varování.

    Počítá zahájené i dokončené kroky Tryskače obsahující přímo tuto bednu.
    Samotné vyhodnocení nic neukládá; volající uloží stav spolu se Zakalením.
    """
    zahajene_tryskani = SarzeKrokBedna.objects.filter(
        bedna=bedna,
        krok__sarze_id=OuterRef('pk'),
        krok__zarizeni__typ_zarizeni=TypZarizeniChoice.TRYSKAC,
    )
    sarze = list(
        Sarze.objects.filter(kroky__krok_bedny__bedna=bedna)
        .annotate(otryskana=Exists(zahajene_tryskani))
        .order_by('cislo_sarze', 'pk')
        .distinct()
    )
    neotryskane = [item for item in sarze if not item.otryskana]
    if sarze and not neotryskane:
        return TryskaniChoice.OTRYSKANA, []
    if (
        bedna.tryskat == TryskaniChoice.SPINAVA
        and neotryskane
        and len(neotryskane) < len(sarze)
    ):
        return bedna.tryskat, neotryskane
    return bedna.tryskat, []


def duvody_nevyhodnotitelneho_prohybu(bedna):
    """Povinné podklady pro potvrzení Zkontrolováno; QS maximum je volitelné."""
    duvody = []
    if not MereniBedny.objects.filter(
        kontrola__bedna=bedna, typ_zkousky=TypZkouskyChoice.PROHYB_PO_TZ,
    ).exists():
        duvody.append('Změřte a uložte Prohyb po TZ.')
    if bedna.limity_prohybu['bezny'] is None:
        duvody.append('Pro zákazníka není nastavené standardní maximum prohybu.')
    if bedna.zakazka.kamion_prijem.zakaznik.max_krivych_vrutu is None:
        duvody.append('U zákazníka nastavte maximální povolený počet křivých ve vzorku.')
    return duvody


def duvody_neuplne_kontroly(bedna, *, kontrola=None, potvrzuje_mereni=False):
    """Společné podmínky dokončení, opravy zkontrolované bedny a adminu.

    Pouze zápis výstupní kontroly smí potvrdit změny měření. Uložená
    rozhodnutí a automatické důvody musejí odpovídat i aktuálním limitům.
    """
    if kontrola is None:
        kontrola = KontrolaBedny.objects.filter(bedna_id=bedna.pk).first() if bedna.pk else None
    if kontrola is None:
        return ['Nejprve vyplňte a uložte výstupní kontrolu: Čistotu, Uložení a rozhodnutí o uvolnění.']

    duvody = duvody_nevyhodnotitelneho_prohybu(bedna)
    if kontrola.vyzaduje_potvrzeni and not potvrzuje_mereni:
        duvody.append('Po změně měření uložte výstupní kontrolu bedny.')
    vysledky = (VysledekKontrolyChoice.OK, VysledekKontrolyChoice.NOK)
    for field, label in (('cistota', 'Čistotu'), ('ulozeni', 'Uložení')):
        if getattr(kontrola, field) not in vysledky:
            duvody.append(f'Vyplňte a uložte {label} (OK nebo NOK).')
    if kontrola.uvolneni not in (
        UvolneniKontrolyChoice.UVOLNENO, UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU,
        UvolneniKontrolyChoice.NESHODA,
    ):
        duvody.append('Vyberte a uložte rozhodnutí o uvolnění.')

    omezeni = omezeni_uvolneni_prohybem(bedna)
    cistota_nok = kontrola.cistota == VysledekKontrolyChoice.NOK
    ulozeni_nok = kontrola.ulozeni == VysledekKontrolyChoice.NOK
    if (
        kontrola.neshoda_krivost != (omezeni is not None)
        or kontrola.neshoda_cistota != cistota_nok
    ):
        duvody.append('Uložte výstupní kontrolu: automatické důvody neodpovídají aktuálním výsledkům.')
    if cistota_nok or ulozeni_nok:
        if kontrola.uvolneni != UvolneniKontrolyChoice.NESHODA:
            duvody.append('Při Čistotě NOK nebo Uložení NOK uložte Neshodu.')
    elif omezeni is not None and kontrola.uvolneni not in omezeni.povolene_stavy:
        duvody.append(omezeni.zprava)
    ma_duvod = any(getattr(kontrola, field) for field in KontrolaBedny.NESHODA_FIELDS)
    if kontrola.uvolneni == UvolneniKontrolyChoice.UVOLNENO and ma_duvod:
        duvody.append('Při Uvolněno uložte kontrolu bez aktuálních důvodů neshody.')
    if kontrola.uvolneni in (
        UvolneniKontrolyChoice.NESHODA, UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU,
    ) and not ma_duvod:
        duvody.append('Při Neshodě nebo Uvolněno QS s odchylkou uložte alespoň jeden důvod.')
    if ulozeni_nok and not kontrola.neshoda_jine:
        duvody.append('Při Uložení NOK uložte důvod Jiné.')
    if (ulozeni_nok or kontrola.neshoda_jine) and not kontrola.poznamka.strip():
        duvody.append('Při typu neshody "Jiné" uveďte do poznámky, o jakou neshodu se jedná.')

    chybejici_pocty = [
        label for value, label in (
            (kontrola.pocet_krivych_vrutu_prvni_mereni, 'Počet křivých 1. měření'),
            (kontrola.pocet_krivych_vrutu_druhe_mereni, 'Počet křivých 2. měření'),
        ) if value is None
    ]
    oranzovy_prohyb_po_tz = (
        omezeni is not None and omezeni.typ_zkousky == TypZkouskyChoice.PROHYB_PO_TZ
        and omezeni.stav == 'odchylka'
    )
    if (kontrola.neshoda_krivost or omezeni is not None) and chybejici_pocty and not oranzovy_prohyb_po_tz:
        if len(chybejici_pocty) == 2:
            duvody.append('Při důvodu Křivost doplňte a uložte oba počty křivých.')
        else:
            duvody.append(f'Při důvodu Křivost chybí uložený {chybejici_pocty[0]}.')
    return duvody


def vyhodnotit_stavy_pri_zkontrolovani(bedna, *, kontrola=None):
    """Vypočítá stavy z měření a z předané či uložené kontroly; nic neukládá."""
    duvody = duvody_nevyhodnotitelneho_prohybu(bedna)
    if duvody:
        # Chybějící podklady nesmějí být zaměněny za vyhovující výsledek.
        raise ValidationError(duvody)
    if kontrola is None:
        kontrola = KontrolaBedny.objects.get(bedna=bedna)
    if kontrola.cistota == VysledekKontrolyChoice.NOK:
        tryskat = TryskaniChoice.SPINAVA
    elif kontrola.cistota == VysledekKontrolyChoice.OK:
        tryskat = (
            TryskaniChoice.OTRYSKANA
            if bedna.tryskat in (TryskaniChoice.SPINAVA, TryskaniChoice.OTRYSKANA)
            else TryskaniChoice.CISTA
        )
    else:
        raise ValidationError('Vyplňte a uložte Čistotu (OK nebo NOK).')

    po_rovnani = MereniBedny.objects.filter(
        kontrola__bedna=bedna, typ_zkousky=TypZkouskyChoice.PROHYB_PO_ROVNANI,
    ).exists()
    # Stejné vyhodnocení celého vzorku jako v kontrole, včetně povoleného počtu křivých.
    omezeni = omezeni_uvolneni_prohybem(bedna)
    if omezeni is not None and omezeni.stav == 'nevyhovuje':
        rovnat = RovnaniChoice.KRIVA
    else:
        rovnat = RovnaniChoice.VYROVNANA if po_rovnani else RovnaniChoice.ROVNA
    return {'rovnat': rovnat, 'tryskat': tryskat}
