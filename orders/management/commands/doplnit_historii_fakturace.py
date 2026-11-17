import csv
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from orders.services.billing_history_repair_service import repair_billing_history
from orders.services.exceptions import ServiceValidationError


class Command(BaseCommand):
    help = 'Rekonstruuje chybějící historii migrace 0250; výchozí režim pouze čte, --apply zapisuje jen historii.'
    requires_migrations_checks = True

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--apply', action='store_true', help='Doplnit historii v jedné transakci.')
        mode.add_argument('--rollback', action='store_true', help='Ověřit skutečný zápis a vrátit jej zpět, bez posunu ID.')
        parser.add_argument('--csv', type=Path, help='Uložit návrh změn do CSV (UTF-8, oddělovač středník).')

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                plan = repair_billing_history(apply=options['apply'], rollback=options['rollback'])
                if options['csv']:
                    with options['csv'].open('w', encoding='utf-8-sig', newline='') as stream:
                        writer = csv.DictWriter(stream, fieldnames=list(plan.rows[0]) if plan.rows else ['id'], delimiter=';')
                        writer.writeheader()
                        writer.writerows(plan.rows)
        except ServiceValidationError as error:
            raise CommandError(str(error)) from error
        except OSError as error:
            raise CommandError(f'CSV se nepodařilo uložit, databázové změny vráceny zpět: {error}') from error
        if options['rollback']:
            self.stdout.write('ZKOUŠKA ZÁPISU ÚSPĚŠNÁ; změny vráceny zpět, čítač historie nezměněn.')
        elif options['apply']:
            self.stdout.write('HISTORIE DOPLNĚNA; aktuální bedny a původní historie nezměněny.')
        else:
            self.stdout.write('NÁHLED BEZ ZÁPISU; pro zkoušku použijte --rollback, pro doplnění --apply.')
        self.stdout.write(f'Čas dokončení migrace 0250: {timezone.localtime(plan.migration_at).isoformat()}')
        self.stdout.write(f'Záznamy historie k doplnění: {len(plan.records)}')
        self.stdout.write(f'První pozdější uložení: {plan.first_saved}; dosud bez dalšího uložení: {plan.not_saved}')
        self.stdout.write(f'Již doplněno: {plan.already_recorded}; bez změny fakturačních voleb: {plan.unchanged}')
        for code, count in sorted(Counter(row['zakaznik'] for row in plan.rows).items()):
            self.stdout.write(f'{code}: {count}')
        for issue in plan.issues:
            self.stdout.write(f'KE KONTROLE: {issue}')
        if plan.issues:
            self.stdout.write('Zápis je kvůli nejednoznačným datům zablokovaný.')
