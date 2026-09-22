from django.db.models import Prefetch
from django.utils import timezone

from orders.choices import TypZkouskyChoice
from orders.models import MereniBedny

from .exceptions import ServiceValidationError
from .pdf_cards_service import build_cards_pdf, build_context_for_bedna


PRINTED_MEASUREMENTS_PER_TEST = 10
TEMPLATE_DIRECTORY = 'orders/karta_kontroly_kvality/vyplnene'
SUPPORTED_CUSTOMERS = ('eur',)
MEASUREMENT_COLUMNS = (
    TypZkouskyChoice.OHYB, TypZkouskyChoice.KRUT, TypZkouskyChoice.PROHYB_PO_TZ,
    TypZkouskyChoice.PROHYB_PO_KOULENI, TypZkouskyChoice.PROHYB_PO_ROVNANI,
    TypZkouskyChoice.TVRDOST_POVRCHU, TypZkouskyChoice.TVRDOST_JADRA,
)


def user_name(user):
    return (user.get_full_name() or user.get_username()) if user else ''


def measuring_people(items):
    return ', '.join(dict.fromkeys(user_name(item.zmeril) for item in items if item.zmeril))


def resolve_filled_customer_template(customer_code):
    code = (customer_code or '').lower()
    if code not in SUPPORTED_CUSTOMERS:
        raise ServiceValidationError('Tisk vyplněných karet kontroly kvality je zatím dostupný pouze pro zákazníka EUR.')
    return f'{TEMPLATE_DIRECTORY}/karta_kontroly_kvality_{code}.html', f'vyplnene_karty_kontroly_kvality_{code}.pdf'


def build_filled_context(bedna, generated_at, printing_user):
    kontrola = bedna.kontrola
    measurements = kontrola.print_measurements
    groups = {kind: [] for kind in MEASUREMENT_COLUMNS}
    for item in measurements:
        group = groups[item.typ_zkousky]
        if len(group) < PRINTED_MEASUREMENTS_PER_TEST:
            group.append(item)
    measurement_dates = [timezone.localdate(item.zmereno_at) for item in measurements]
    context = build_context_for_bedna(bedna, generated_at, printing_user)
    context['quality_card'] = {
        'kontrola': kontrola,
        'datum_mereni_od': min(measurement_dates, default=None),
        'datum_mereni_do': max(measurement_dates, default=None),
        'uvolnil': user_name(kontrola.uvolnil),
        'rows': [
            [groups[kind][index].hodnota if index < len(groups[kind]) else None
             for kind in MEASUREMENT_COLUMNS]
            for index in range(PRINTED_MEASUREMENTS_PER_TEST)
        ],
        'kontrolovali': [measuring_people(groups[kind]) for kind in MEASUREMENT_COLUMNS],
    }
    return context


def build_filled_quality_cards_pdf(bedny_qs, request):
    if not bedny_qs.exists():
        raise ServiceValidationError('Není vybrána žádná bedna k tisku.')
    if bedny_qs.values('zakazka__kamion_prijem__zakaznik').distinct().count() != 1:
        raise ServiceValidationError('Pro tisk vyplněných karet musí být bedny od jednoho zákazníka.')
    customer_code = bedny_qs.first().zakazka.kamion_prijem.zakaznik.zkratka
    template, filename = resolve_filled_customer_template(customer_code)
    missing_controls = bedny_qs.filter(kontrola__isnull=True)
    if missing_controls.exists():
        numbers = ', '.join(map(str, missing_controls.values_list('cislo_bedny', flat=True)[:20]))
        raise ServiceValidationError(f'Chybí uložená kontrola u beden: {numbers}.')
    bedny_qs = bedny_qs.select_related(
        'zakazka__kamion_prijem__zakaznik', 'zakazka__predpis', 'kontrola__uvolnil',
    ).prefetch_related(Prefetch(
        'kontrola__mereni', queryset=MereniBedny.objects.select_related('zmeril').order_by('poradi', 'pk'),
        to_attr='print_measurements',
    )).order_by('cislo_bedny')
    generated_at = timezone.now()
    printing_user = user_name(request.user)
    return build_cards_pdf(
        bedny_qs=bedny_qs, template_paths=[template], filename=filename,
        request=request, generated_at=generated_at, user_display_name=printing_user,
        context_builder=lambda bedna: build_filled_context(bedna, generated_at, printing_user),
    )
