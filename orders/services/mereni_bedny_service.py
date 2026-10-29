import hashlib
import json
from dataclasses import dataclass

from django.utils import timezone

from orders.choices import TypZkouskyChoice, UvolneniKontrolyChoice
from orders.models import KontrolaBedny, MereniBedny
from orders.quality_card_labels import minimum_samples_labels, minimum_values_labels


@dataclass(frozen=True)
class OmezeniUvolneniProhybem:
    typ_zkousky: TypZkouskyChoice
    povolene_stavy: tuple
    zprava: str

    @property
    def stav(self):
        if self.povolene_stavy == (UvolneniKontrolyChoice.NESHODA,):
            return 'nevyhovuje'
        return 'odchylka'


def omezeni_uvolneni_prohybem(bedna):
    """Vyhodnotí uložený prohyb po rovnání, jinak po TZ; koulení ignoruje."""
    maximum = bedna.zakazka.kamion_prijem.zakaznik.max_krivych_vrutu
    limity = bedna.limity_prohybu
    bezny_limit = limity['bezny']
    if maximum is None or bezny_limit is None:
        return None

    hodnoty = {
        TypZkouskyChoice.PROHYB_PO_TZ: [],
        TypZkouskyChoice.PROHYB_PO_ROVNANI: [],
    }
    for typ, hodnota in MereniBedny.objects.filter(
        kontrola__bedna=bedna, typ_zkousky__in=hodnoty,
    ).values_list('typ_zkousky', 'hodnota'):
        hodnoty[typ].append(hodnota)
    typ = (
        TypZkouskyChoice.PROHYB_PO_ROVNANI
        if hodnoty[TypZkouskyChoice.PROHYB_PO_ROVNANI]
        else TypZkouskyChoice.PROHYB_PO_TZ
    )
    qs_limit = limity['pro_uvolneni_s_odchylkou']
    horni_limit = qs_limit if qs_limit is not None else bezny_limit
    nad_hornim = sum(hodnota > horni_limit for hodnota in hodnoty[typ])
    nad_beznym = sum(hodnota > bezny_limit for hodnota in hodnoty[typ])
    if nad_hornim > maximum:
        pocet = nad_hornim
        hranice = 'QS limitem' if qs_limit is not None else 'běžným limitem'
        stavy = (UvolneniKontrolyChoice.NESHODA,)
        pokyn = 'Lze uložit pouze Neshodu s důvodem Křivost.'
    elif qs_limit is not None and nad_beznym > maximum:
        pocet = nad_beznym
        hranice = 'běžným limitem'
        stavy = (UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU, UvolneniKontrolyChoice.NESHODA)
        pokyn = 'Lze uložit Uvolněno QS s odchylkou nebo Neshodu, vždy s důvodem Křivost.'
    else:
        return None
    return OmezeniUvolneniProhybem(
        typ_zkousky=typ,
        povolene_stavy=stavy,
        zprava=(
            f'{typ.label}: počet hodnot nad {hranice} je {pocet}, '
            f'povolený počet křivých vrutů je {maximum}. {pokyn}'
        ),
    )


def rozsah_mereni_zakaznika(zakaznik, typ_zkousky):
    if typ_zkousky in (
        TypZkouskyChoice.PROHYB_PO_TZ, TypZkouskyChoice.PROHYB_PO_KOULENI,
        TypZkouskyChoice.PROHYB_PO_ROVNANI,
    ):
        labels = minimum_values_labels(
            zakaznik.min_hodnot_prohyb, {},
            sample_count=zakaznik.pocet_vrutu_pro_kontrolu_prohybu,
        )
    else:
        field = {
            TypZkouskyChoice.OHYB: 'min_hodnot_mechanicke',
            TypZkouskyChoice.KRUT: 'min_hodnot_mechanicke',
            TypZkouskyChoice.TVRDOST_POVRCHU: 'min_hodnot_tvrdost',
            TypZkouskyChoice.TVRDOST_JADRA: 'min_hodnot_tvrdost',
        }.get(typ_zkousky)
        if field is None:
            return ''
        labels = minimum_samples_labels(getattr(zakaznik, field), {})
    return labels.get('main', '')


def pozadavek_zkousky(predpis, typ_zkousky):
    fields = {
        TypZkouskyChoice.OHYB: ('ohyb', 'popis_ohyb', 'popis_ohyb_2'),
        TypZkouskyChoice.KRUT: ('krut', 'popis_krut', 'popis_krut_2'),
        TypZkouskyChoice.TVRDOST_POVRCHU: ('povrch', 'popis_povrch', 'popis_povrch_2'),
        TypZkouskyChoice.TVRDOST_JADRA: ('jadro', 'popis_jadro', 'popis_jadro_2'),
        TypZkouskyChoice.VRSTVA: ('vrstva', 'popis_vrstva', 'popis_vrstva_2'),
    }.get(typ_zkousky)
    if fields is None:
        return {'hodnota': '', 'hodnota_2': '', 'popisy': []}
    return {
        'hodnota': getattr(predpis, fields[0]) or '',
        'hodnota_2': (predpis.vrstva_2 or '') if typ_zkousky == TypZkouskyChoice.VRSTVA else '',
        'popisy': [getattr(predpis, name) for name in fields[1:] if getattr(predpis, name)],
    }


def mereni_snapshot(measurements):
    """Detect edits made since the form was opened, including additions/deletions."""
    data = [
        [item.pk, str(item.hodnota), item.zmeril_id, item.zmereno_at.isoformat()]
        for item in measurements
    ]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode('utf-8')).hexdigest()


def kontrola_snapshot(kontrola):
    data = None if kontrola is None else [
        kontrola.pk, kontrola.cistota, kontrola.ulozeni, kontrola.uvolneni,
        kontrola.poznamka, kontrola.uvolneni_zmenil_id,
        kontrola.uvolneni_zmeneno_at.isoformat() if kontrola.uvolneni_zmeneno_at else None,
        kontrola.pocet_krivych_vrutu_prvni_mereni, kontrola.pocet_krivych_vrutu_druhe_mereni,
        *(getattr(kontrola, name) for name in KontrolaBedny.NESHODA_FIELDS),
    ]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode('utf-8')).hexdigest()


def ulozit_mereni_zkousky(kontrola, typ_zkousky, formset, user):
    """Caller holds the bedna lock and has validated the formset and snapshot."""
    existing = {item.pk: item for item in formset.measurements}
    next_order = max((item.poradi for item in existing.values()), default=0)
    measured_at = timezone.now()
    for form in formset.forms:
        data = form.cleaned_data
        item = existing.get(data.get('id'))
        if data.get('DELETE'):
            if item is not None:
                item._history_user = user
                item.delete()
            continue
        if not form.has_changed():
            continue
        if item is None:
            next_order += 1
            item = MereniBedny(
                kontrola=kontrola, typ_zkousky=typ_zkousky, poradi=next_order,
                zmeril=user, zmereno_at=measured_at,
            )
        item.hodnota = data['hodnota']
        item._history_user = user
        # Editing a value preserves the original measuring person/date.
        item.save()
