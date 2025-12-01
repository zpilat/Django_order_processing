import logging
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction

from orders.choices import STAV_BEDNY_VYPOCET_ROZPRACOVANOSTI
from orders.models import Bedna, Rozpracovanost


logger = logging.getLogger('orders')


class Command(BaseCommand):
    help = (
        "Vypočítá rozpracovanost po zákaznících: spočítá bedny ve stavech "
        "využívaných pro měsíční report a uloží jejich počet a celkovou cenu."
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
        ).select_related("zakazka__kamion_prijem__zakaznik")

        agregace = defaultdict(lambda: {"pocet": 0, "cena": Decimal("0.00"), "nazev_zakaznika": ""})

        for bedna in bedny_qs.iterator():
            zakaznik = bedna.zakazka.kamion_prijem.zakaznik
            if zakaznik is None:
                continue

            zaznam = agregace[zakaznik.pk]
            zaznam["pocet"] += 1
            zaznam["nazev_zakaznika"] = zakaznik.zkraceny_nazev or zakaznik.nazev
            zaznam["cena"] += bedna.cena_za_bednu

        if not agregace:
            self.stdout.write("Nenalezeny žádné bedny odpovídající podmínkám.")
            return

        if dry_run:
            for zaznam in agregace.values():
                cena = zaznam["cena"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                self.stdout.write(
                    f"{zaznam['nazev_zakaznika']}: {zaznam['pocet']} beden, cena {cena} € (DRY RUN)"
                )
            return

        nove_zaznamy = [
            Rozpracovanost(
                zakaznik=zaznam["nazev_zakaznika"],
                beden_rozpracovanych=zaznam["pocet"],
                cena_za_kaleni=zaznam["cena"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            )
            for zaznam in agregace.values()
        ]

        with transaction.atomic():
            Rozpracovanost.objects.bulk_create(nove_zaznamy)

        logger.info(
            f"Uloženo {len(nove_zaznamy)} záznamů měsíční rozpracovanosti (celkem {sum(z['pocet'] for z in agregace.values())} beden)."
        )
