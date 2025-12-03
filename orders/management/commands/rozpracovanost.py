import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from orders.choices import STAV_BEDNY_VYPOCET_ROZPRACOVANOSTI
from orders.models import Bedna, Rozpracovanost


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

        bedna_ids = list(bedny_qs.values_list("pk", flat=True))

        if not bedna_ids:
            self.stdout.write("Nenalezeny žádné bedny odpovídající podmínkám.")
            return

        if dry_run:
            self.stdout.write(f"Nalezeno {len(bedna_ids)} beden ve vybraných stavech (DRY RUN).")
            return

        with transaction.atomic():
            zaznam = Rozpracovanost.objects.create()
            zaznam.bedny.set(bedna_ids)

        logger.info(
            f"Uložen záznam rozpracovanosti s {len(bedna_ids)} bednami ve stavech pro výpočet rozpracovanosti.",
        )
