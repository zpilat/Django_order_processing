from django.conf import settings

from .choices import TypZarizeniChoice
from .models import SarzeKrok


def environment_flags(request):
    return {
        "is_debug": bool(settings.DEBUG),
    }


def otevrene_kroky_nakladani(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'otevrene_kroky_nakladani': []}
    if not (
        user.has_perm('orders.view_sarzekrok')
        and user.has_perm('orders.view_sarzekrokbedna')
    ):
        return {'otevrene_kroky_nakladani': []}

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
    return {'otevrene_kroky_nakladani': kroky}
