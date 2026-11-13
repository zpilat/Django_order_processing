"""Pilotní přenos položek proformy SPX do dodacího listu OMEGY.

Formát KROS ImportExport_28_00_2025.xls, list Fakturacia: T01, typ 2.
Export nic neukládá; nejde o vystavení ani zaúčtování faktury.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from orders.choices import KamionChoice, StavBednyChoice
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
    crate_number: int
    order_number: str
    article: str
    description: str
    dimension: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal
    operation: str = 'Kalení'

    @property
    def name(self):
        # Standardní R02 nemá samostatná pole pro objednávku a rozměr.
        # Údaje proto zůstávají i v názvu, bez závislosti na tiskové sestavě.
        return ' | '.join((
            self.operation, f'Obj. {self.order_number}', f'Art. {self.article}',
            self.description, self.dimension,
        ))


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
        return sum((line.quantity for line in self.lines), Decimal('0.0'))

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
                'R02', _text(line.name, f'Bedna {line.crate_number}'),
                _number(line.quantity), 'kg', _number(line.unit_price), '0',
            ]
            item[9] = 'V'  # Volná položka; nezakládá skladovou kartu.
            item[18] = line.article  # Volné označení položky, nejvýše 50 znaků.
            records.append(item)
        return (''.join('\t'.join(record) + '\r\n' for record in records)).encode('cp1250')


def build_spx_delivery_note(kamion):
    """Pouze kalení SPX, s výběrem a výpočtem odpovídajícím proformě po bednách."""
    customer = kamion.zakaznik
    if kamion.prijem_vydej != KamionChoice.VYDEJ or customer.zkratka != 'SPX':
        raise ServiceValidationError('Pilotní export OMEGA je dostupný pouze pro kamion výdej zákazníka SPX.')
    if customer.fakturovat_rovnani or customer.fakturovat_tryskani:
        raise ServiceValidationError('Pilotní export podporuje pouze kalení; SPX má zapnuté účtování dalších operací.')
    if not customer.proforma_po_bednach:
        raise ServiceValidationError('Pilotní export SPX vyžaduje proformu po bednách.')
    number = _text(kamion.cislo_dl, 'Číslo dodacího listu', 20)
    partner_name = _text(customer.nazev, 'Název partnera', 75)
    if not number or not partner_name:
        raise ServiceValidationError('Pro export musí být vyplněno číslo dodacího listu a název zákazníka.')

    crates = Bedna.objects.filter(
        zakazka__kamion_vydej=kamion, fakturovat=True, nefakturovat_kaleni=False,
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
            total=(crate.hmotnost * unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        ))
    if not lines:
        raise ServiceValidationError('Kamion neobsahuje žádnou bednu určenou k fakturaci kalení.')
    note = OmegaDeliveryNote(number, kamion.datum, partner_name, tuple(lines))
    note.to_bytes()  # Stejné kontroly textu v náhledu i při stažení.
    return note
