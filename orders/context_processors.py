from django.conf import settings

from .choices import TypZarizeniChoice
from .models import SarzeKrok


def _build_pracoviste_nakladani_links():
    kroky = (
        SarzeKrok.objects
        .filter(
            sarze__isnull=False,
            sarze__cislo_pracoviste__isnull=False,
            zarizeni__typ_zarizeni=TypZarizeniChoice.NAKLADANI,
            konec__isnull=True,
        )
        .select_related('sarze', 'zarizeni')
        .order_by('sarze__cislo_pracoviste', '-pk')
    )
    krok_by_pracoviste = {}
    for krok in kroky:
        krok_by_pracoviste.setdefault(krok.sarze.cislo_pracoviste, krok)

    return [
        {
            'cislo_pracoviste': cislo_pracoviste,
            'krok': krok_by_pracoviste.get(cislo_pracoviste),
            'is_open': cislo_pracoviste in krok_by_pracoviste,
        }
        for cislo_pracoviste in range(1, 7)
    ]


def _get_posledni_uzavrena_nakladani_sarze():
    krok = (
        SarzeKrok.objects
        .filter(
            sarze__isnull=False,
            poradi=1,
            zarizeni__typ_zarizeni=TypZarizeniChoice.NAKLADANI,
            datum_konce__isnull=False,
            konec__isnull=False,
        )
        .select_related('sarze', 'zarizeni')
        .order_by('-datum_konce', '-konec', '-pk')
        .first()
    )
    return krok.sarze if krok else None


def environment_flags(request):
    return {
        "is_debug": bool(settings.DEBUG),
    }


def otevrene_kroky_nakladani(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {
            'otevrene_kroky_nakladani': [],
            'pracoviste_nakladani_links': [],
            'posledni_uzavrena_sarze_s_krokem_nakladani': None,
        }
    if not (
        user.has_perm('orders.view_sarzekrok')
        and user.has_perm('orders.view_sarzekrokbedna')
    ):
        return {
            'otevrene_kroky_nakladani': [],
            'pracoviste_nakladani_links': [],
            'posledni_uzavrena_sarze_s_krokem_nakladani': None,
        }

    pracoviste_links = _build_pracoviste_nakladani_links()
    return {
        'otevrene_kroky_nakladani': [
            item['krok'] for item in pracoviste_links if item['is_open']
        ],
        'pracoviste_nakladani_links': pracoviste_links,
        'posledni_uzavrena_sarze_s_krokem_nakladani': _get_posledni_uzavrena_nakladani_sarze(),
    }
