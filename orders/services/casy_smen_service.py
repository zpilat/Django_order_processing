"""Společné časové hranice a poměrné rozdělení práce do výrobních směn."""

from datetime import datetime, time, timedelta, timezone as datetime_timezone
from decimal import Decimal
from fractions import Fraction
from zoneinfo import ZoneInfo


REPORT_TIMEZONE = ZoneInfo('Europe/Prague')
SHIFT_SCHEMES = (
    ('twelve', '12hodinové směny', (
        ('Denní', 6, 18), ('Noční', 18, 30),
    )),
    ('eight', '8hodinové směny', (
        ('Ranní', 6, 14), ('Odpolední', 14, 22), ('Noční', 22, 30),
    )),
)


def _at_hour(day, hour):
    # Hranice jsou místní; odečítání v UTC zachová délky i při změně času.
    return datetime.combine(
        day + timedelta(days=hour // 24), time(hour % 24), tzinfo=REPORT_TIMEZONE,
    ).astimezone(datetime_timezone.utc)


def _microseconds(duration):
    return (duration.days * 86400 + duration.seconds) * 1000000 + duration.microseconds


def _empty_totals():
    return {'patra': Fraction(0), 'sarze': Fraction(0), 'microseconds': 0}


def _present_totals(totals):
    def decimal(value):
        value = Fraction(value)
        return Decimal(value.numerator) / Decimal(value.denominator)

    return {
        'patra': decimal(totals['patra']),
        'sarze': decimal(totals['sarze']),
        'hours': decimal(Fraction(totals['microseconds'], 3600000000)),
    }


def build_shift_schemes(day):
    return [
        {
            'key': key, 'title': title,
            'rows': [
                {
                    'label': label,
                    'time_label': f'{start % 24:02d}:00–{end % 24:02d}:00',
                    'start': _at_hour(day, start), 'end': _at_hour(day, end),
                    'totals': _empty_totals(),
                }
                for label, start, end in shifts
            ],
        }
        for key, title, shifts in SHIFT_SCHEMES
    ]


def add_interval(schemes, start, end, *, floors, batches):
    """Rozdělí zadané množství práce rovnoměrně přes celý uzavřený interval."""
    duration = _microseconds(end - start)
    if duration <= 0:
        raise ValueError('Interval musí mít kladnou délku.')
    for scheme in schemes:
        for shift in scheme['rows']:
            overlap = _microseconds(min(end, shift['end']) - max(start, shift['start']))
            if overlap > 0:
                share = Fraction(overlap, duration)
                shift['totals']['patra'] += share * floors
                shift['totals']['sarze'] += share * batches
                shift['totals']['microseconds'] += overlap


def finish_shift_schemes(schemes):
    for scheme in schemes:
        total = _empty_totals()
        for row in scheme['rows']:
            for field in total:
                total[field] += row['totals'][field]
            row.update(_present_totals(row.pop('totals')))
        scheme['total'] = _present_totals(total)
