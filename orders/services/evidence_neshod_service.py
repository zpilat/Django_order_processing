"""Neměnné podklady případu neshody při jeho založení z kontroly bedny."""

from datetime import datetime
from decimal import Decimal

from orders.choices import TypZkouskyChoice, UvolneniKontrolyChoice
from orders.models import KontrolaBedny, ZaznamNeshody

from .mereni_bedny_service import pozadavek_zkousky, rozsah_mereni_zakaznika


def jmeno_uzivatele(user):
    return (user.get_full_name() or user.get_username()) if user else ''


def decimal_text(value):
    return str(value) if value is not None else None


def snapshot_zkousky_pro_zobrazeni(snapshot):
    """Převede uložená čísla a časy pro čitelné zobrazení beze změny snapshotu."""
    return [
        {
            **group,
            'mereni': [
                {**item, 'hodnota': Decimal(item['hodnota']), 'zmereno_at': datetime.fromisoformat(item['zmereno_at'])}
                for item in group['mereni']
            ],
            'limity_prohybu': {
                key: Decimal(value) if value is not None else None
                for key, value in (group['limity_prohybu'] or {}).items()
            },
        }
        for group in snapshot.get('zkousky', [])
    ]


def zaznamenat_neshodu(kontrola, *, previous_status, user):
    """Volající drží zámek bedny a ukládá kontrolu i záznam v jedné transakci.

    Stejný stav ani opakovaný požadavek nevytvářejí nový případ. Další vstup do
    Neshody má nový historický záznam a založí další nezávislý případ.
    """
    if (
        kontrola.uvolneni != UvolneniKontrolyChoice.NESHODA
        or previous_status == UvolneniKontrolyChoice.NESHODA
    ):
        return None

    bedna = kontrola.bedna
    zakazka = bedna.zakazka
    zakaznik = zakazka.kamion_prijem.zakaznik
    predpis = zakazka.predpis
    measurements = list(kontrola.mereni.select_related('zmeril').order_by('typ_zkousky', 'poradi', 'pk'))
    limity = {key: decimal_text(value) for key, value in bedna.limity_prohybu.items()}
    zkousky = []
    for kind in TypZkouskyChoice:
        requirement = pozadavek_zkousky(predpis, kind)
        zkousky.append({
            'typ': kind.value,
            'nazev': str(kind.label),
            'pozadavek': requirement,
            'rozsah_mereni': rozsah_mereni_zakaznika(zakaznik, kind),
            'limity_prohybu': limity if kind in (
                TypZkouskyChoice.PROHYB_PO_TZ, TypZkouskyChoice.PROHYB_PO_KOULENI,
                TypZkouskyChoice.PROHYB_PO_ROVNANI,
            ) else None,
            'mereni': [
                {
                    'id': item.pk, 'poradi': item.poradi,
                    'hodnota': str(item.hodnota),
                    'zmeril_id': item.zmeril_id, 'zmeril': jmeno_uzivatele(item.zmeril),
                    'zmereno_at': item.zmereno_at.isoformat(),
                }
                for item in measurements if item.typ_zkousky == kind
            ],
        })

    source = kontrola.history.order_by('-history_id').first()
    duvody = [
        {'kod': name, 'nazev': str(KontrolaBedny._meta.get_field(name).verbose_name)}
        for name in KontrolaBedny.NESHODA_FIELDS if getattr(kontrola, name)
    ]
    snapshot = {
        'verze': 1,
        'bedna': {
            'id': bedna.pk, 'cislo_bedny': bedna.cislo_bedny,
            'behalter_nr': bedna.behalter_nr, 'sarze_materialu': bedna.sarze,
            'material': bedna.material, 'vyrobni_zakazka': bedna.vyrobni_zakazka,
            'hmotnost': decimal_text(bedna.hmotnost), 'mnozstvi': bedna.mnozstvi,
            'stav': bedna.stav_bedny, 'stav_popis': bedna.get_stav_bedny_display(),
            'rovnani': bedna.get_rovnat_display(), 'tryskani': bedna.get_tryskat_display(),
        },
        'zakazka': {
            'id': zakazka.pk, 'puvodni_zakazka_id': zakazka.puvodni_zakazka_id,
            'artikl': zakazka.artikl, 'popis': zakazka.popis,
            'prumer': str(zakazka.prumer), 'delka': str(zakazka.delka),
            'celozavit': zakazka.celozavit,
        },
        'zakaznik': {
            'id': zakaznik.pk, 'nazev': zakaznik.nazev,
            'zkraceny_nazev': zakaznik.zkraceny_nazev, 'zkratka': zakaznik.zkratka,
            'pocet_vrutu_pro_kontrolu_prohybu': zakaznik.pocet_vrutu_pro_kontrolu_prohybu,
            'max_krivych_vrutu': zakaznik.max_krivych_vrutu,
        },
        'kontrola': {
            'id': kontrola.pk, 'historie_id': source.history_id,
            'uvolneni': kontrola.uvolneni, 'uvolneni_popis': kontrola.get_uvolneni_display(),
            'cistota': kontrola.get_cistota_display(), 'ulozeni': kontrola.get_ulozeni_display(),
            'pocet_krivych_vrutu_prvni_mereni': kontrola.pocet_krivych_vrutu_prvni_mereni,
            'pocet_krivych_vrutu_druhe_mereni': kontrola.pocet_krivych_vrutu_druhe_mereni,
            'duvody': duvody, 'poznamka': kontrola.poznamka,
        },
        'predpis': {'id': predpis.pk, 'nazev': predpis.nazev},
        'zkousky': zkousky,
    }
    zaznam, _ = ZaznamNeshody.objects.get_or_create(
        zdroj_historie_id=source.history_id,
        defaults={
            'bedna': bedna, 'zjisteno_at': kontrola.uvolneni_zmeneno_at,
            'zjistil': user, 'zjistil_jmeno': jmeno_uzivatele(user),
            'zakaznik': zakaznik.nazev, 'zakaznik_zkratka': zakaznik.zkratka,
            'zakazka': zakazka.artikl, 'oznaceni_bedny': str(bedna.cislo_bedny),
            'dil': f'{zakazka.prumer} × {zakazka.delka}',
            'sarze_materialu': bedna.sarze or '',
            'duvody': duvody, 'popis': kontrola.poznamka, 'snapshot': snapshot,
        },
    )
    return zaznam
