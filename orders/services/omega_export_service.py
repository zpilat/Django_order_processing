"""Přenos položek proformy SPX a EUR do dodacího listu OMEGY.

Formát KROS ImportExport_28_00_2025.xls, list Fakturacia: T01, typ 2.
Export nic neukládá; nejde o vystavení ani zaúčtování faktury.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Q

from orders.billing import (
    billed_amount, is_operation_billable, operation_conditions,
    summarize_operation, validate_proforma_pricing,
)
from orders.choices import KamionChoice, StavBednyChoice, TryskaniChoice
from orders.models import Bedna

from .exceptions import ServiceValidationError


def _text(value, label, max_length=None):
    value = str(value or '').strip()
    if any(ord(char) < 32 for char in value):
        raise ServiceValidationError(f'{label}: text obsahuje tabulátor nebo jiný řídicí znak.')
    if max_length and len(value) > max_length:
        raise ServiceValidationError(f'{label}: OMEGA dovoluje nejvýše {max_length} znaků.')
    try:
        value.encode('cp1250')
    except UnicodeEncodeError as exc:
        raise ServiceValidationError(f'{label}: text obsahuje znak nepodporovaný kódováním Windows-1250.') from exc
    return value


def _number(value):
    return format(value, 'f')


@dataclass(frozen=True)
class OmegaLine:
    crate_number: int | None
    order_number: str
    article: str
    description: str
    dimension: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal
    operation: str = 'Kalení'
    unit: str = 'kg'
    order_id: int | None = None

    @property
    def name(self):
        return self.description

    @property
    def source(self):
        if self.crate_number is not None:
            return f'Bedna {self.crate_number}'
        if self.order_id is not None:
            return f'Zakázka {self.order_id}'
        return 'Souhrn kamionu'


@dataclass(frozen=True)
class OmegaDeliveryNote:
    number: str
    issued_on: date
    partner_name: str
    lines: tuple[OmegaLine, ...]

    @property
    def total(self):
        return sum((line.total for line in self.lines), Decimal('0.00'))

    @property
    def weight(self):
        # Souhrn tryskání je 1 ks, nesmí se přičíst ke kilogramům kalení.
        return sum((line.quantity for line in self.lines if line.unit == 'kg'), Decimal('0.0'))

    def to_bytes(self):
        # Pozice jsou číslované od 1 včetně R01. Prázdná pole se nezkracují.
        header = [''] * 43
        header[0:7] = [
            'R01', self.number, self.partner_name, '',
            self.issued_on.strftime('%d.%m.%Y'),
            self.issued_on.strftime('%d.%m.%Y'),
            self.issued_on.strftime('%d.%m.%Y'),
        ]
        header[7:16] = ['0'] * 9
        # Technický nulový rozpis DPH podkladu; režim finální faktury řeší OMEGA.
        header[9] = _number(self.total)
        header[16] = _number(self.total)
        header[17] = '2'  # Dodací list, nikoli odběratelská faktura (0).
        header[32] = self.number
        header[33] = self.number
        header[39:43] = ['EUR', '1', '1', _number(self.total)]
        records = [['R00', 'T01'], header]
        for line in self.lines:
            item = [''] * 19
            item[0:6] = [
                'R02', _text(line.name, f'{line.source}, název položky'),
                _number(line.quantity), _text(line.unit, 'Měrná jednotka', 5), _number(line.unit_price), '0',
            ]
            item[9] = 'V'  # Volná položka; nezakládá skladovou kartu.
            item[10] = _text(line.article, 'Artikl')  # Cudzí názov / Item no.
            # Ověřené přiřazení: Číslo -> objednávka, Vlastný text -> rozměr.
            # Pole 17 (JKPOV) zůstává prázdné.
            item[17] = _text(line.order_number, 'Číslo položky (pole 18)', 20)
            item[18] = _text(line.dimension, 'Rozměr (pole 19 / C115_Volne)', 50)
            records.append(item)
        return (''.join('\t'.join(record) + '\r\n' for record in records)).encode('cp1250')


def _check_no_zinc(kamion):
    """Společná blokace pro všechny zákazníky do zavedení ceny a exportu zinkování."""
    if Bedna.objects.filter(
        zakazka__kamion_vydej=kamion, fakturovat=True, fakturovat_zinkovani=True,
    ).exists():
        raise ServiceValidationError(
            'Export OMEGA je zastaven: některá fakturovaná bedna má zapnuté '
            'Fakturovat zinkování. Export zinkování zatím není podporován.'
        )


def build_omega_delivery_note(kamion):
    """Společný vstup; další zákazníci dostanou vlastní explicitní pravidla."""
    _check_no_zinc(kamion)
    builders = {'SPX': build_spx_delivery_note, 'EUR': build_eur_delivery_note}
    builder = builders.get(kamion.zakaznik.zkratka)
    if builder is None:
        raise ServiceValidationError('Export OMEGA nyní podporuje pouze zákazníky SPX a EUR.')
    return builder(kamion)


def build_spx_delivery_note(kamion):
    """Kalení SPX: shodný výběr a HALF_UP každé bedny jako na proformě po bednách.

    Fakturaci po zakázkách ani další operace pilot nepodporuje. Hlavička
    dokladu sčítá zaokrouhlené řádky, nepřepočítává celkovou hmotnost sazbou.
    """
    customer = kamion.zakaznik
    if kamion.prijem_vydej != KamionChoice.VYDEJ or customer.zkratka != 'SPX':
        raise ServiceValidationError('Pilotní export OMEGA je dostupný pouze pro kamion výdej zákazníka SPX.')
    _check_no_zinc(kamion)
    if Bedna.objects.filter(zakazka__kamion_vydej=kamion).filter(
        Q(**operation_conditions('rovnani')) | Q(**operation_conditions('tryskani'))
    ).exists():
        raise ServiceValidationError('Pilotní export podporuje pouze kalení; SPX má zapnuté účtování dalších operací.')
    if not customer.proforma_po_bednach:
        raise ServiceValidationError('Pilotní export SPX vyžaduje proformu po bednách.')
    number = _text(kamion.cislo_dl, 'Číslo dodacího listu', 20)
    partner_name = _text(customer.nazev, 'Název partnera', 75)
    if not number or not partner_name:
        raise ServiceValidationError('Pro export musí být vyplněno číslo dodacího listu a název zákazníka.')

    crates = Bedna.objects.filter(
        zakazka__kamion_vydej=kamion, **operation_conditions('kaleni'),
    ).select_related('zakazka__kamion_prijem__zakaznik', 'zakazka__predpis').order_by('zakazka_id', 'id')
    lines = []
    prices = {}
    for crate in crates:
        order = crate.zakazka
        label = f'Bedna {crate.cislo_bedny}'
        if order.kamion_prijem.zakaznik_id != customer.pk:
            raise ServiceValidationError(f'{label}: zákazník příjmu neodpovídá zákazníkovi výdeje.')
        if crate.stav_bedny != StavBednyChoice.EXPEDOVANO:
            raise ServiceValidationError(f'{label}: export vyžaduje stav Expedováno.')
        if crate.hmotnost is None or crate.hmotnost <= 0:
            raise ServiceValidationError(f'{label}: chybí kladná fakturovaná hmotnost.')
        if order.pk not in prices:
            prices[order.pk] = order.cena_za_kg
        unit_price = prices[order.pk]
        if unit_price <= 0:
            raise ServiceValidationError(f'{label}: chybí jednoznačná kladná cena kalení. Zkontrolujte ceník.')
        order_number = _text(crate.vyrobni_zakazka, f'{label}, výrobní zakázka', 20)
        article = _text(order.artikl, f'{label}, artikl', 50)
        description = _text(order.popis, f'{label}, popis')
        if not order_number or not article or not description:
            raise ServiceValidationError(f'{label}: vyplňte výrobní zakázku, artikl a popis.')
        dimension = f'{_number(order.prumer.normalize())}x{_number(order.delka.normalize())}'
        lines.append(OmegaLine(
            crate_number=crate.cislo_bedny, order_number=order_number,
            article=article, description=description, dimension=dimension,
            quantity=crate.hmotnost, unit_price=unit_price,
            total=billed_amount(crate.hmotnost, unit_price),
        ))
    if not lines:
        raise ServiceValidationError('Kamion neobsahuje žádnou bednu určenou k fakturaci kalení.')
    note = OmegaDeliveryNote(number, kamion.datum, partner_name, tuple(lines))
    note.to_bytes()  # Stejné kontroly textu v náhledu i při stažení.
    return note


def build_eur_delivery_note(kamion):
    """Kalení po zakázkách a souhrny tryskání podle sazeb za částky proformy EUR."""
    customer = kamion.zakaznik
    if kamion.prijem_vydej != KamionChoice.VYDEJ or customer.zkratka != 'EUR':
        raise ServiceValidationError('Export EUR je dostupný pouze pro kamion výdej zákazníka EUR.')
    _check_no_zinc(kamion)
    if customer.proforma_po_bednach:
        raise ServiceValidationError('Export EUR vyžaduje fakturaci po zakázkách (Proforma po bednách = Ne).')
    number = _text(kamion.cislo_dl, 'Číslo dodacího listu', 20)
    partner_name = _text(customer.nazev, 'Název partnera', 75)
    if not number or not partner_name:
        raise ServiceValidationError('Pro export musí být vyplněno číslo dodacího listu a název zákazníka.')

    orders = list(kamion.zakazky_vydej.select_related(
        'kamion_prijem__zakaznik', 'predpis',
    ).prefetch_related('bedny').order_by('id'))
    for order in orders:
        crates = list(order.bedny.all())
        if order.kamion_prijem.zakaznik_id != customer.pk and any(
            is_operation_billable(crate, operation)
            for crate in crates for operation in ('kaleni', 'tryskani', 'rovnani')
        ):
            raise ServiceValidationError(
                f'Zakázka {order.artikl}: zákazník příjmu neodpovídá zákazníkovi výdeje.'
            )
        # Kontrola sazby platí pro všechny otryskané bedny kamionu, i vyřazené
        # z fakturace. Do částky níže vstupují pouze skutečně účtované bedny.
        blasted = [crate for crate in crates if crate.tryskat == TryskaniChoice.OTRYSKANA]
        if blasted and order.cena_tryskani_za_kg <= 0:
            numbers = ', '.join(str(crate.cislo_bedny) for crate in blasted)
            raise ServiceValidationError(
                f'Zakázka {order.artikl}, bedny {numbers}: chybí jednoznačná kladná cena tryskání. Zkontrolujte ceník.'
            )
    errors = validate_proforma_pricing(kamion)
    if errors:
        raise ServiceValidationError('Nelze exportovat podklad EUR: ' + '; '.join(errors))
    if kamion.cena_rovnani_za_kamion_vydej != 0:
        raise ServiceValidationError('Export EUR je zastaven: rovnání má na proformě nenulovou částku.')

    lines = []
    blasting_by_rate = {}
    for order in orders:
        crates = list(order.bedny.all())
        for crate in crates:
            if any(is_operation_billable(crate, operation) for operation in ('kaleni', 'tryskani')):
                if crate.stav_bedny != StavBednyChoice.EXPEDOVANO:
                    raise ServiceValidationError(f'Bedna {crate.cislo_bedny}: export vyžaduje stav Expedováno.')
        heat = summarize_operation(crates, 'kaleni', order.cena_za_kg, per_crate=False)
        if heat.count:
            article = _text(order.artikl, f'Zakázka {order.pk}, artikl pro Číslo', 20)
            short_description = _text(order.zkraceny_popis, f'Zakázka {order.pk}, zkrácený popis')
            if not article or not short_description:
                raise ServiceValidationError(f'Zakázka {order.pk}: vyplňte artikl a zkrácený popis.')
            dimension = f'{_number(order.prumer.normalize())}x{_number(order.delka.normalize())}'.replace('.', ',')
            lines.append(OmegaLine(
                crate_number=None, order_id=order.pk, order_number=article, article='',
                description=f'{short_description}, {dimension}', dimension='',
                quantity=heat.weight, unit_price=order.cena_za_kg, total=heat.total,
            ))
        # Součet zaokrouhlených částek zakázek, jako cena_tryskani_za_kamion_vydej.
        blasting_rate = order.cena_tryskani_za_kg
        blasted = summarize_operation(crates, 'tryskani', blasting_rate, per_crate=False)
        if blasted.count:
            weight, total = blasting_by_rate.get(blasting_rate, (Decimal('0.0'), Decimal('0.00')))
            blasting_by_rate[blasting_rate] = (weight + blasted.weight, total + blasted.total)
    for blasting_rate, (blasted_weight, blasted_total) in sorted(blasting_by_rate.items()):
        weight_text = _number(blasted_weight.normalize()).replace('.', ',')
        rate_text = _number(blasting_rate).replace('.', ',')
        lines.append(OmegaLine(
            crate_number=None, order_number='', article='', dimension='', operation='Tryskání',
            description=f'Sandblasting of screws ({weight_text}kg x {rate_text}EUR)',
            quantity=Decimal('1'), unit='ks', unit_price=blasted_total, total=blasted_total,
        ))
    if not lines:
        raise ServiceValidationError('Kamion neobsahuje žádné fakturované kalení ani tryskání.')
    note = OmegaDeliveryNote(number, kamion.datum, partner_name, tuple(lines))
    note.to_bytes()
    return note
