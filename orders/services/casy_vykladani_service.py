"""Rovnoměrný odhad vykládání z celého intervalu Vykládání nebo Tryskače."""

from datetime import datetime, time, timedelta, timezone as datetime_timezone

from django.db.models import Count, Q
from django.utils import timezone

from orders.choices import TypZarizeniChoice
from orders.models import SarzeKrok
from orders.services.casy_smen_service import (
    REPORT_TIMEZONE, _at_hour, _microseconds, _present_totals,
    add_interval, build_shift_schemes, finish_shift_schemes,
)


UNLOADING_DEVICE_TYPES = (TypZarizeniChoice.VYKLADANI, TypZarizeniChoice.TRYSKAC)


def build_casy_vykladani_prehled(*, date_value=None, now=None):
    now = now or timezone.now()
    date_value = date_value or (
        timezone.localdate(now, timezone=REPORT_TIMEZONE) - timedelta(days=1)
    )
    next_day = date_value + timedelta(days=1)
    window_start = _at_hour(date_value, 6)
    window_end = _at_hour(date_value, 30)
    schemes = build_shift_schemes(date_value)
    starts_in_window = (
        Q(datum=date_value, zacatek__gte=time(6))
        | Q(datum=next_day, zacatek__lt=time(6))
    )
    steps = list(
        SarzeKrok.objects.filter(zarizeni__typ_zarizeni__in=UNLOADING_DEVICE_TYPES)
        .filter(Q(datum__isnull=True) | Q(datum__lt=next_day) | Q(datum=next_day, zacatek__lt=time(6)))
        .filter(
            Q(datum_konce__isnull=True) | Q(konec__isnull=True)
            | Q(datum_konce__gt=date_value)
            | Q(datum_konce=date_value, konec__gt=time(6))
            | starts_in_window
        )
        .select_related('sarze', 'zarizeni')
        .annotate(floor_count=Count('krok_bedny__patro', distinct=True))
        .order_by('datum', 'zacatek', 'sarze__cislo_sarze', 'poradi', 'pk')
    )
    # Kontrolujeme všechny průchody téže šarže, i když jsou v jiném dni.
    repeated_batches = {
        row['sarze_id']
        for row in (
            SarzeKrok.objects
            .filter(sarze_id__in={step.sarze_id for step in steps},
                    zarizeni__typ_zarizeni__in=UNLOADING_DEVICE_TYPES)
            .order_by().values('sarze_id').annotate(count=Count('pk')).filter(count__gt=1)
        )
    }
    details = []
    invalid_steps = 0
    incomplete_steps = 0
    visible_repeated_batches = set()
    for step in steps:
        start = (
            datetime.combine(step.datum, step.zacatek, tzinfo=REPORT_TIMEZONE)
            .astimezone(datetime_timezone.utc)
            if step.datum is not None and step.zacatek is not None else None
        )
        closed = step.datum_konce is not None and step.konec is not None
        end = (
            datetime.combine(step.datum_konce, step.konec, tzinfo=REPORT_TIMEZONE)
            .astimezone(datetime_timezone.utc)
            if closed else None
        )
        if start is not None and start >= min(window_end, now):
            continue
        if end is not None and end <= window_start and (start is None or end > start):
            continue

        error = ''
        if start is None:
            error = 'Chybí datum nebo čas začátku vykládání.'
        elif not step.floor_count:
            error = 'Krok nemá evidovaná patra.'
        elif (step.datum_konce is None) != (step.konec is None):
            error = 'Chybí datum nebo čas konce vykládání.'
        elif closed and end <= start:
            error = 'Konec vykládání není po začátku kroku.'
        elif closed and end > now:
            error = 'Konec vykládání je v budoucnosti.'

        hours = None
        if error:
            invalid_steps += 1
            status = error
        elif not closed:
            incomplete_steps += 1
            status = 'Rozpracováno, čeká na konec vykládání.'
        else:
            add_interval(schemes, start, end, floors=step.floor_count, batches=1)
            hours = _present_totals({
                'patra': 0, 'sarze': 0, 'microseconds': _microseconds(end - start),
            })['hours']
            status = 'Započteno'

        repeated = step.sarze_id in repeated_batches
        if repeated:
            visible_repeated_batches.add(step.sarze_id)
        details.append({
            'step': step, 'floor_count': step.floor_count,
            'start': start, 'end': end, 'hours': hours,
            'invalid': bool(error), 'status': status, 'repeated': repeated,
        })

    finish_shift_schemes(schemes)
    return {
        'date': date_value, 'date_iso': date_value.isoformat(),
        'start': window_start, 'end': window_end,
        'schemes': schemes, 'details': details,
        'invalid_steps': invalid_steps, 'incomplete_steps': incomplete_steps,
        'repeated_batches': len(visible_repeated_batches),
    }
