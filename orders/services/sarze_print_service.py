from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
import django.utils.timezone as timezone
from weasyprint import HTML

from ..choices import TypZarizeniChoice
from ..models import SarzeKrok


def get_tisk_pruvodky_vruty_krok(sarze):
    """
    Vrátí první krok šarže pro tisk průvodky vrutů a případnou validační chybu.
    """
    krok = (
        SarzeKrok.objects
        .filter(sarze=sarze, poradi=1)
        .select_related('sarze', 'zarizeni')
        .order_by('pk')
        .first()
    )
    if krok is None:
        return None, f'Šarže {sarze} nemá první krok.'

    if krok.zarizeni.typ_zarizeni != TypZarizeniChoice.NAKLADANI:
        return None, f'První krok šarže {sarze} není pracoviště Nakládání.'

    if not krok.krok_bedny.filter(bedna__isnull=False).exists():
        return None, f'Šarže {sarze} neobsahuje v prvním kroku žádné vruty.'

    return krok, None


def build_tisk_pruvodky_vruty_response(request, krok, filename):
    items = (
        krok.krok_bedny
        .select_related('bedna', 'bedna__zakazka', 'bedna__zakazka__predpis')
        .order_by('-patro', 'pk')
    )

    fake_skupiny = set()
    for item in items:
        if item.bedna:
            fake_skupiny.add(item.bedna.fake_skupina_TZ)
        else:
            fake_skupiny.add(None)
    spolecna_skupina_TZ = next(iter(fake_skupiny)) if len(fake_skupiny) == 1 else None

    html_string = render_to_string(
        'orders/print/rychle_zalozeni_sarze_print.html',
        {
            'krok': krok,
            'items': items,
            'spolecna_skupina_TZ': spolecna_skupina_TZ,
            'generated_at': timezone.now(),
        },
    )
    base_url = getattr(settings, 'WEASYPRINT_BASEURL', None) or request.build_absolute_uri('/')
    pdf_bytes = HTML(string=html_string, base_url=base_url).write_pdf()

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    response['Content-Length'] = str(len(pdf_bytes))
    return response
