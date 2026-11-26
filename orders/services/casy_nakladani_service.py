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


def _historical_closing_times(steps, *, now):
    """Přesný čas doloženého uzavření, které stále odpovídá evidovanému konci."""
    if not steps:
        return {}
    previous_ends = {}
    closings = {}
    for event in (
        SarzeKrok.history.filter(id__in=[step.pk for step in steps], history_date__lte=now)
        .order_by('id', 'history_date', 'history_id')
        .values('id', 'datum_konce', 'konec', 'history_date', 'history_type')
    ):
        step_id = event['id']
        end = (event['datum_konce'], event['konec'])
        previous = previous_ends.get(step_id)
        if (
            event['history_type'] == '~' and previous == (None, None)
            and all(value is not None for value in end)
        ):
            closings[step_id] = (end, event['history_date'].astimezone(datetime_timezone.utc))
        elif event['history_type'] != '~' or end != previous:
            # Založení již uzavřeného kroku ani oprava konce nejsou uzavřením.
            # Znovuotevření ruší předchozí uzavření; běžné další uložení ho neposouvá.
            closings.pop(step_id, None)
        previous_ends[step_id] = end
    return {
        step.pk: closings[step.pk][1]
        for step in steps
        if step.pk in closings and closings[step.pk][0] == (step.datum_konce, step.konec)
    }


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
    later_closing_history = SarzeKrok.history.filter(
        id=OuterRef('pk'), history_type='~', history_date__gt=window_start,
        history_date__lte=now, datum_konce__isnull=False, konec__isnull=False,
    )
    steps = list(
        SarzeKrok.objects
        .filter(zarizeni__typ_zarizeni=TypZarizeniChoice.NAKLADANI)
        .annotate(
            has_floor_history=Exists(history_before_end),
            has_later_closing_history=Exists(later_closing_history),
        )
        .filter(Q(datum__lte=window_end.date()) | Q(has_floor_history=True))
        .filter(
            Q(datum_konce__isnull=True) | Q(konec__isnull=True)
            | Q(datum_konce__gt=date_value)
            | Q(datum_konce=date_value, konec__gte=time(6))
            | Q(has_later_closing_history=True)
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

    recorded_finishes = {}
    conflicting_steps = []
    for step in steps:
        if step.datum_konce is None or step.konec is None:
            continue
        recorded_finish = datetime.combine(
            step.datum_konce, step.konec, tzinfo=REPORT_TIMEZONE,
        ).astimezone(datetime_timezone.utc)
        recorded_finishes[step.pk] = recorded_finish
        starts = [first_saves.get((step.pk, floor)) for floor in sorted(floors_by_step[step.pk])]
        if (
            starts and all(start is not None for start in starts)
            and all(right > left for left, right in zip(starts, starts[1:]))
            and end_of_minute(recorded_finish) <= starts[-1] and recorded_finish <= now
        ):
            conflicting_steps.append(step)
    historical_finishes = _historical_closing_times(conflicting_steps, now=now)

    details = []
    incomplete_steps = 0
    invalid_steps = 0
    historical_end_steps = 0
    for step in steps:
        floors = sorted(floors_by_step[step.pk])
        starts = [first_saves.get((step.pk, floor)) for floor in floors]
        recorded_finish = recorded_finishes.get(step.pk)
        closed = recorded_finish is not None
        finish = end_of_minute(recorded_finish) if closed else None
        end_from_history = step.pk in historical_finishes and historical_finishes[step.pk] > starts[-1]
        if end_from_history:
            finish = historical_finishes[step.pk]
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
        elif end_from_history:
            historical_end_steps += 1

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
            status = 'Započteno'
            if not closed:
                status = (
                    'Patro započteno, podíl šarže až po uzavření.' if end is not None
                    else 'Rozpracováno, čeká na konec patra.'
                )
            elif end_from_history and index == len(floors) - 1:
                status = 'Započteno; konec podle historie uzavření.'
            details.append({
                'step': step, 'floor': floor, 'start': start, 'end': end,
                'recorded_end': recorded_finish if index == len(floors) - 1 else None,
                'end_from_history': end_from_history and index == len(floors) - 1,
                'hours': hours, 'invalid': bool(error),
                'status': error or status,
            })

    finish_shift_schemes(schemes)

    return {
        'date': date_value, 'date_iso': date_value.isoformat(),
        'start': window_start, 'end': window_end,
        'schemes': schemes, 'details': details,
        'incomplete_steps': incomplete_steps, 'invalid_steps': invalid_steps,
        'historical_end_steps': historical_end_steps,
    }
