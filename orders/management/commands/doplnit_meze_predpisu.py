import csv
from collections import Counter
from contextlib import nullcontext
from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from orders.models import Predpis
from orders.services.predpis_meze_service import DRUHY_ZKOUSEK, navrh_mezi


class Command(BaseCommand):
    help = 'Navrhne převod textů předpisů na min/max; zapisuje pouze s --apply, existující meze a QS nepřepisuje.'
    requires_migrations_checks = True

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Zapsat jednoznačné meze a historii v jedné transakci.')
        parser.add_argument('--csv', type=Path, help='Uložit podrobný přehled do CSV (UTF-8, oddělovač středník).')

    def handle(self, *args, **options):
        apply = options['apply']
        rows, counts = [], Counter()
        try:
            with transaction.atomic() if apply else nullcontext():
                queryset = Predpis.objects.select_related('zakaznik').order_by('pk')
                if apply:
                    queryset = queryset.select_for_update(of=('self',))
                for predpis in queryset:
                    changed_fields = []
                    for kind in DRUHY_ZKOUSEK:
                        proposal = navrh_mezi(predpis, kind)
                        minimum_name, maximum_name = f'{kind}_min', f'{kind}_max'
                        saved_minimum, saved_maximum = getattr(predpis, minimum_name), getattr(predpis, maximum_name)
                        state, note = proposal.stav, proposal.poznamka
                        if proposal.stav == 'prevod':
                            if saved_minimum is not None or saved_maximum is not None:
                                state = 'hotovo' if (saved_minimum, saved_maximum) == (proposal.minimum, proposal.maximum) else 'ponechano'
                                note = 'Existující nebo částečně vyplněné meze se nepřepisují.'
                            else:
                                # Ověří přesnost a rozsah ještě před případným zápisem.
                                for name, value in ((minimum_name, proposal.minimum), (maximum_name, proposal.maximum)):
                                    if value is not None:
                                        value = predpis._meta.get_field(name).clean(value, predpis)
                                        setattr(predpis, name, value)
                                        changed_fields.append(name)
                        counts[(kind, state)] += 1
                        rows.append({
                            'id': predpis.pk, 'zakaznik': predpis.zakaznik.zkratka, 'predpis': predpis.nazev,
                            'aktivni': predpis.aktivni, 'zkouska': kind,
                            'text': getattr(predpis, kind) or '', 'text_2': (predpis.vrstva_2 or '') if kind == 'vrstva' else '',
                            'puvodni_min': saved_minimum, 'puvodni_max': saved_maximum,
                            'navrh_min': proposal.minimum, 'navrh_max': proposal.maximum,
                            'qsmax': getattr(predpis, f'{kind}_qsmax'), 'stav': state, 'poznamka': note,
                        })
                    if changed_fields:
                        predpis.full_clean()
                        counts[('predpisy', 'prevod')] += 1
                        if apply:
                            predpis._change_reason = 'Doplnění číselných mezí z textových požadavků předpisu.'
                            predpis.save(update_fields=changed_fields)
                if options['csv']:
                    with options['csv'].open('w', encoding='utf-8-sig', newline='') as stream:
                        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ['id'], delimiter=';')
                        writer.writeheader()
                        writer.writerows({key: str(value).replace('.', ',') if isinstance(value, Decimal) else value for key, value in row.items()} for row in rows)
        except (ValidationError, OSError) as error:
            raise CommandError(f'Převod nebyl dokončen: {error}') from error
        self.stdout.write('ZÁPIS DOKONČEN' if apply else 'NÁHLED BEZ ZÁPISU; pro provedení použijte --apply.')
        self.stdout.write(f"Předpisy k doplnění: {counts[('predpisy', 'prevod')]}")
        for kind in DRUHY_ZKOUSEK:
            self.stdout.write(f'{kind}: ' + ', '.join(f'{state}={counts[(kind, state)]}' for state in ('prevod', 'hotovo', 'ponechano', 'bez_meze', 'metodika', 'rucne')))
        for row in rows:
            if row['stav'] in ('rucne', 'ponechano'):
                self.stdout.write(f"Ke kontrole: {row['zakaznik']} / {row['predpis']} / {row['zkouska']} (ID {row['id']}): {row['poznamka']}")
