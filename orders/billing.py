"""Společná pravidla fakturace kalení, rovnání a tryskání.

Ceníkové sazby nezávisí na přepínačích ani technologických stavech bedny.
Ty rozhodují pouze o zahrnutí bedny do částky, hmotnosti a počtu dané operace.
Částky se počítají pomocí Decimal a zaokrouhlují HALF_UP na cent: po bednách
na každé bedně, po zakázkách až po sečtení fakturovaných hmotností operace.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from orders.choices import RovnaniChoice, TryskaniChoice


BILLING_OPERATIONS = ('kaleni', 'rovnani', 'tryskani')
_OPERATION_LABELS = {'kaleni': 'kalení', 'rovnani': 'rovnání', 'tryskani': 'tryskání'}
_UNIT_PRICE_FIELDS = {
    'kaleni': 'cena_za_kg',
    'rovnani': 'cena_rovnani_za_kg',
    'tryskani': 'cena_tryskani_za_kg',
}


def operation_conditions(operation):
    """Podmínky pro QuerySet i kontrolu jedné bedny; cenu zde neposuzujeme."""
    if operation not in BILLING_OPERATIONS:
        raise ValueError(f'Neznámá fakturovaná operace: {operation}')
    conditions = {'fakturovat': True, f'fakturovat_{operation}': True}
    if operation == 'rovnani':
        conditions['rovnat'] = RovnaniChoice.VYROVNANA
    elif operation == 'tryskani':
        conditions['tryskat'] = TryskaniChoice.OTRYSKANA
    return conditions


def is_operation_billable(crate, operation):
    """Zda se bedna započítá do počtu, hmotnosti i částky dané operace."""
    return all(getattr(crate, field) == value for field, value in operation_conditions(operation).items())


def operation_unit_price(order, operation):
    """Aktuální ceníková sazba zakázky v EUR/kg, bez podmínek fakturace."""
    return getattr(order, _UNIT_PRICE_FIELDS[operation])


def billed_amount(weight, unit_price):
    """Hmotnost krát sazba, jediné peněžní zaokrouhlení HALF_UP na cent.

    Nevyplněné hodnoty poskytují nulu pro průběžné zobrazení. Před vydáním
    proformy se kladná hmotnost a jednoznačná kladná cena ověřují samostatně.
    """
    weight = Decimal(str(weight)) if weight is not None else Decimal('0')
    unit_price = Decimal(str(unit_price)) if unit_price is not None else Decimal('0')
    if not weight or not unit_price:
        return Decimal('0.00')
    return (weight * unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class BillingSummary:
    """Počet, hmotnost a částka téhož výběru beden pro jednu operaci."""

    count: int
    weight: Decimal
    total: Decimal


def summarize_operation(crates, operation, unit_price, *, per_crate):
    """Ocení pouze předané bedny podle způsobu fakturace zákazníka.

    Při per_crate=True sčítá jednotlivě zaokrouhlené částky. Jinak zaokrouhlí
    až součin celkové fakturované hmotnosti a sazby této zakázky. Výběr nesmí
    obsahovat bedny různých zakázek s různými sazbami. Rozpracovanost předává
    pouze bedny vybraného snímku, nikoli všechny bedny související zakázky.
    """
    selected = [crate for crate in crates if is_operation_billable(crate, operation)]
    weight = sum((Decimal(str(crate.hmotnost or 0)) for crate in selected), Decimal('0.0'))
    total = (
        sum((billed_amount(crate.hmotnost, unit_price) for crate in selected), Decimal('0.00'))
        if per_crate else billed_amount(weight, unit_price)
    )
    return BillingSummary(count=len(selected), weight=weight, total=total)


def validate_proforma_pricing(truck):
    """Chyby bránící vydání proformy; kontroluje jen skutečně účtované operace.

    Prázdné zakázky a nefakturované bedny cenu nevyžadují. Zapnuté rovnání
    bez stavu Vyrovnaná ani tryskání bez Otryskaná ji rovněž nevyžadují.
    Stejnou kontrolu používá adminová akce i přímé otevření PDF.
    """
    # Lokální import dovoluje používat čisté výpočty také z models.py.
    from orders.models import Cena

    errors = []
    orders = truck.zakazky_vydej.select_related('kamion_prijem__zakaznik').prefetch_related('bedny')
    for order in orders:
        crates = list(order.bedny.all())
        required = {
            operation: any(is_operation_billable(crate, operation) for crate in crates)
            for operation in BILLING_OPERATIONS
        }
        if not any(required.values()):
            continue
        label = order.artikl or order.pk
        customer = order.kamion_prijem.zakaznik
        if customer.pk != truck.zakaznik_id:
            errors.append(f'Zakázka {label}: zákazník příjmu neodpovídá zákazníkovi výdeje.')
            continue
        for crate in crates:
            if any(is_operation_billable(crate, operation) for operation in BILLING_OPERATIONS):
                if crate.hmotnost is None or crate.hmotnost <= 0:
                    errors.append(f'Bedna {crate.cislo_bedny}: chybí kladná fakturovaná hmotnost.')
        if not order.predpis_id or order.delka is None:
            errors.append(f'Zakázka {label}: chybí předpis nebo délka pro výpočet ceny.')
            continue
        try:
            price = Cena.objects.get(
                predpis=order.predpis, zakaznik=customer,
                delka_min__lte=order.delka, delka_max__gt=order.delka,
            )
        except Cena.DoesNotExist:
            errors.append(f'Zakázka {label}: nenalezena cena pro předpis {order.predpis} a délku {order.delka}.')
            continue
        except Cena.MultipleObjectsReturned:
            errors.append(f'Zakázka {label}: nalezeno více cen pro předpis {order.predpis} a délku {order.delka}. Opravte ceník.')
            continue
        for operation, needed in required.items():
            rate = getattr(price, _UNIT_PRICE_FIELDS[operation])
            if needed and (rate is None or rate <= 0):
                errors.append(f'Zakázka {label}: cena {_OPERATION_LABELS[operation]} za kg musí být větší než 0.')
    return errors
