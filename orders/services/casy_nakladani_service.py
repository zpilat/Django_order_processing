"""Rozdělení intervalů nakládání pater mezi směny bez změn výrobní evidence."""

from collections import defaultdict
from datetime import datetime, time, timedelta, timezone as datetime_timezone
from fractions import Fraction

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from orders.choices import TypZarizeniChoice
from orders.models import SarzeKrok, SarzeKrokBedna
from orders.services.casy_smen_service import (
    REPORT_TIMEZONE, _at_hour, _microseconds, _present_totals,
    add_interval, build_shift_schemes, end_of_minute, finish_shift_schemes,
)


FLOOR_DELETED_REASON = 'Smazání celého patra při nakládání.'


def build_casy_nakladani_prehled(*, date_value=None, now=None):
    now = now or timezone.now()
    date_value = date_value or (
        timezone.localdate(now, timezone=REPORT_TIMEZONE) - timedelta(days=1)
    )
    window_start = _at_hour(date_value, 6)
    window_end = _at_hour(date_value, 30)
    schemes = build_shift_schemes(date_value)

    history_before_end = SarzeKrokBedna.history.filter(
        krok_id=OuterRef('pk'), history_type='+', history_date__lt=window_end,
    )
    steps = list(
        SarzeKrok.objects
        .filter(zarizeni__typ_zarizeni=TypZarizeniChoice.NAKLADANI)
        .annotate(has_floor_history=Exists(history_before_end))
        .filter(Q(datum__lte=window_end.date()) | Q(has_floor_history=True))
        .filter(
            Q(datum_konce__isnull=True) | Q(konec__isnull=True)
            | Q(datum_konce__gt=date_value)
            | Q(datum_konce=date_value, konec__gte=time(6))
        )
        .select_related('sarze', 'zarizeni')
        .order_by('sarze__cislo_sarze', 'poradi', 'pk')
    )
    step_ids = [step.pk for step in steps]
    floors_by_step = defaultdict(set)
    for step_id, floor in (
        SarzeKrokBedna.objects.filter(krok_id__in=step_ids)
        .order_by().values_list('krok_id', 'patro').distinct()
    ):
        floors_by_step[step_id].add(floor)

    first_saves = {}
    # Zahrnuje i smazané řádky: běžné uložení nahrazuje celé rozložení patra.
    # Výslovné smazání celého patra začíná při příštím založení novou návaznost.
    for event in (
        SarzeKrokBedna.history.filter(krok_id__in=step_ids, history_date__lte=now)
        .filter(Q(history_type='+') | Q(history_type='-', history_change_reason=FLOOR_DELETED_REASON))
        .order_by('history_date', 'history_id')
        .values('krok_id', 'patro', 'history_type', 'history_date')
    ):
        key = (event['krok_id'], event['patro'])
        if event['history_type'] == '-':
            first_saves.pop(key, None)
        else:
            first_saves.setdefault(key, event['history_date'].astimezone(datetime_timezone.utc))

    details = []
    incomplete_steps = 0
    invalid_steps = 0
    for step in steps:
        floors = sorted(floors_by_step[step.pk])
        starts = [first_saves.get((step.pk, floor)) for floor in floors]
        closed = step.datum_konce is not None and step.konec is not None
        recorded_finish = (
            datetime.combine(step.datum_konce, step.konec, tzinfo=REPORT_TIMEZONE)
            .astimezone(datetime_timezone.utc)
            if closed else None
        )
        finish = end_of_minute(recorded_finish) if closed else None
        known_starts = [start for start in starts if start is not None]
        # Chybějící historii zobrazujeme jen u kroku, který mohl zasáhnout období.
        evidence_start = min(known_starts) if known_starts else (
            datetime.combine(step.datum, step.zacatek, tzinfo=REPORT_TIMEZONE)
            .astimezone(datetime_timezone.utc)
            if step.datum is not None else None
        )
        if evidence_start is None or evidence_start >= min(window_end, now):
            continue
        if finish is not None and finish <= window_start:
            continue

        error = ''
        if not floors:
            error = 'Krok nemá evidovaná patra.'
        elif any(start is None for start in starts):
            error = 'Chybí první uložení některého patra.'
        elif any(right <= left for left, right in zip(starts, starts[1:])):
            error = 'Začátky pater nejsou v rostoucím pořadí.'
        elif closed and finish <= starts[-1]:
            error = 'Konec nakládání není po začátku posledního patra.'
        elif closed and recorded_finish > now:
            error = 'Konec nakládání je v budoucnosti.'
        if error:
            invalid_steps += 1
        elif not closed:
            incomplete_steps += 1

        if not floors:
            details.append({
                'step': step, 'floor': None, 'start': evidence_start, 'end': finish,
                'recorded_end': recorded_finish,
                'hours': None, 'status': error, 'invalid': True,
            })
        for index, floor in enumerate(floors):
            start = starts[index]
            end = starts[index + 1] if index + 1 < len(floors) else finish
            if not error and end is not None:
                add_interval(
                    schemes, start, end, floors=1,
                    batches=Fraction(1, len(floors)) if closed else 0,
                )
            # U vadného kroku ukážeme všechna patra kvůli dohledání chyby.
            if not error and (
                start >= min(window_end, now)
                or (end is not None and end <= window_start)
            ):
                continue
            hours = (
                _present_totals({'patra': 0, 'sarze': 0, 'microseconds': _microseconds(end - start)})['hours']
                if start is not None and end is not None and end > start else None
            )
            details.append({
                'step': step, 'floor': floor, 'start': start, 'end': end,
                'recorded_end': recorded_finish if index == len(floors) - 1 else None,
                'hours': hours, 'invalid': bool(error),
                'status': error or (
                    'Započteno' if closed else (
                        'Patro započteno, podíl šarže až po uzavření.' if end is not None
                        else 'Rozpracováno, čeká na konec patra.'
                    )
                ),
            })

    finish_shift_schemes(schemes)

    return {
        'date': date_value, 'date_iso': date_value.isoformat(),
        'start': window_start, 'end': window_end,
        'schemes': schemes, 'details': details,
        'incomplete_steps': incomplete_steps, 'invalid_steps': invalid_steps,
    }
