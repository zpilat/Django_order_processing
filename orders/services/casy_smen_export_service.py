"""Měsíční CSV pater po směnách ze stejných výpočtů jako denní přehled."""

import csv
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from io import StringIO

from django.utils import timezone

from orders.services.casy_nakladani_service import build_casy_nakladani_prehled
from orders.services.casy_smen_service import REPORT_TIMEZONE, SHIFT_SCHEMES, _at_hour
from orders.services.casy_vykladani_service import build_casy_vykladani_prehled


SCHEME_HOURS = {'twelve': 12, 'eight': 8}


def last_complete_shift_month(*, now=None):
    """Vrátí data hranic posledního měsíce ukončeného směnou v 06:00."""
    now = now or timezone.now()
    end = timezone.localdate(now, timezone=REPORT_TIMEZONE).replace(day=1)
    if now < _at_hour(end, 6):
        end = (end - timedelta(days=1)).replace(day=1)
    start = (end - timedelta(days=1)).replace(day=1)
    return start, end


def _headers():
    headers = ['Datum směn']
    for key, _title, shifts in SHIFT_SCHEMES:
        for _label, start, end in shifts:
            shift = f'{SCHEME_HOURS[key]}h {start % 24:02d}:00–{end % 24:02d}:00'
            headers.extend((f'Naložená patra {shift}', f'Vyložená patra {shift}'))
    return [*headers, 'Stav evidence']


def _floor_value(value):
    return format(value.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP), 'f').replace('.', ',')


def _evidence_status(loading, unloading):
    notes = []
    for label, report in (('Nakládání', loading), ('Vykládání', unloading)):
        if report['invalid_steps']:
            notes.append(f"{label}: chybné kroky {report['invalid_steps']}")
        if report['incomplete_steps']:
            notes.append(f"{label}: neuzavřené kroky {report['incomplete_steps']}")
    if loading['historical_end_steps']:
        notes.append(f"Nakládání: konec podle historie uzavření u kroků {loading['historical_end_steps']}")
    if unloading['repeated_batches']:
        notes.append(f"Vykládání: šarže s více průchody {unloading['repeated_batches']}")
    return '; '.join(notes) or 'OK'


def build_mesicni_export_pater(*, now=None):
    now = now or timezone.now()
    start, end = last_complete_shift_month(now=now)
    output = StringIO(newline='')
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';', lineterminator='\r\n')
    writer.writerow(_headers())
    for offset in range((end - start).days):
        day = start + timedelta(days=offset)
        loading = build_casy_nakladani_prehled(date_value=day, now=now)
        unloading = build_casy_vykladani_prehled(date_value=day, now=now)
        reports = {
            'loading': {scheme['key']: scheme['rows'] for scheme in loading['schemes']},
            'unloading': {scheme['key']: scheme['rows'] for scheme in unloading['schemes']},
        }
        row = [day.strftime('%d.%m.%Y')]
        for key, _title, shifts in SHIFT_SCHEMES:
            for index in range(len(shifts)):
                row.extend(
                    _floor_value(reports[phase][key][index]['patra'])
                    for phase in ('loading', 'unloading')
                )
        writer.writerow([*row, _evidence_status(loading, unloading)])
    return {
        'start': start, 'end': end,
        'filename': f'patra_smeny_{start:%Y-%m}.csv',
        'content': output.getvalue(),
    }
