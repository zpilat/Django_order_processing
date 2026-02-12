import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from orders.choices import STAV_BEDNY_VYPOCET_ROZPRACOVANOSTI
from orders.models import Bedna, Rozpracovanost, RozpracovanostBednaSnapshot


logger = logging.getLogger('orders')


class Command(BaseCommand):
    help = (
        "Vytvoří záznam rozpracovanosti: uloží všechny bedny ve stavech "
        "používaných pro měsíční report do jednoho snapshotu."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Pouze vypíše výsledky bez uložení do databáze.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        bedny_qs = Bedna.objects.filter(
            stav_bedny__in=STAV_BEDNY_VYPOCET_ROZPRACOVANOSTI,
            zakazka__kamion_prijem__isnull=False,
        )
        snapshot_rows = list(
            bedny_qs.values('pk', 'stav_bedny', 'tryskat', 'rovnat', 'zinkovat')
        )

        if not snapshot_rows:
            self.stdout.write("Nenalezeny žádné bedny odpovídající podmínkám.")
            return

        if dry_run:
            self.stdout.write(f"Nalezeno {len(snapshot_rows)} beden ve vybraných stavech (DRY RUN).")
            return

        with transaction.atomic():
            zaznam = Rozpracovanost.objects.create()
            RozpracovanostBednaSnapshot.objects.bulk_create([
                RozpracovanostBednaSnapshot(
                    rozpracovanost=zaznam,
                    bedna_id=row['pk'],
                    stav_bedny=row['stav_bedny'],
                    tryskat=row['tryskat'],
                    rovnat=row['rovnat'],
                    zinkovat=row['zinkovat'],
                )
                for row in snapshot_rows
            ], batch_size=500)

        logger.info(
            f"Uložen záznam rozpracovanosti s {len(snapshot_rows)} bednami ve stavech pro výpočet rozpracovanosti.",
        )
