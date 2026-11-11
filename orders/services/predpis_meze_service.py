"""Návrh jednorázového převodu textových požadavků; nehodnotí měření beden."""

from dataclasses import dataclass
from decimal import Decimal
import re


DRUHY_ZKOUSEK = ('ohyb', 'krut', 'jadro', 'povrch', 'vrstva')
NUMBER = r'\d+(?:[.,]\d+)?'
UNITS = {
    'ohyb': r'[°˚]?',
    'krut': r'Nm',
    'jadro': rf'HV\s*{NUMBER}(?:\s*\(\s*HV\s*{NUMBER}\s*\))?',
    'povrch': rf'HV\s*{NUMBER}',
    'vrstva': 'mm',
}
CHD = rf'CHD\s+{NUMBER}\s+HV\s*{NUMBER}'


@dataclass(frozen=True)
class NavrhMezi:
    stav: str
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    poznamka: str = ''


def normalizovat(text):
    text = (text or '').replace('–', '-').replace('—', '-').replace('\u00a0', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def _decimal(text):
    return Decimal(text.replace(',', '.'))


def _hodnota(text, druh, *, zakaznik, nazev):
    text = normalizovat(text)
    if text in ('', '-') or text.casefold() == 'neměří se':
        return NavrhMezi('bez_meze')
    unit = UNITS[druh]

    # Výjimky odsouhlasené 11. 11. 2026 jsou vázané na obsah a označení,
    # nikoli na primární klíče z vývojové databáze.
    if (
        druh == 'jadro' and zakaznik == 'EUR'
        and nazev in ('00829_Ø7,4', '00829_Ø7,5')
        and re.fullmatch(r'300\s*-\s*400\s*\(350\s*-\s*500\)\s*HV0,3', text)
    ):
        return NavrhMezi('prevod', Decimal('350'), Decimal('500'), 'Potvrzené nové hodnoty v závorce.')
    if druh == 'vrstva':
        match = re.fullmatch(rf'(?P<value>{NUMBER})\s*mm', text, re.IGNORECASE)
        if match and _decimal(match['value']) in (Decimal('0.15'), Decimal('0.3')):
            return NavrhMezi('prevod', _decimal(match['value']), poznamka='Potvrzená samostatná hodnota vrstvy je minimum.')
        if (
            zakaznik == 'EUR' and nazev == '00432_Ø7,5'
            and re.fullmatch(r'min\.\s*0,2\s*-\s*0,4\s*mm', text, re.IGNORECASE)
        ):
            return NavrhMezi('prevod', Decimal('0.2'), Decimal('0.4'), 'Potvrzený rozsah přes prefix min.')
        match = re.fullmatch(rf'{CHD}\s*min\.?\s*(?P<value>{NUMBER})\s*mm', text, re.IGNORECASE)
        if match:
            return NavrhMezi('prevod', _decimal(match['value']), poznamka='Minimum v mm za označením CHD/HV.')

    match = re.fullmatch(rf'(?P<side>min|max)\.?\s*(?P<value>{NUMBER})\s*{unit}', text, re.IGNORECASE)
    if match:
        value = _decimal(match['value'])
        return NavrhMezi('prevod', value if match['side'].lower() == 'min' else None,
                         value if match['side'].lower() == 'max' else None, 'Jednostranná mez.')
    first_unit = r'[°˚]?' if druh == 'ohyb' else ''
    match = re.fullmatch(rf'(?P<minimum>{NUMBER})\s*{first_unit}\s*-\s*(?P<maximum>{NUMBER})\s*{unit}', text, re.IGNORECASE)
    if match:
        minimum, maximum = _decimal(match['minimum']), _decimal(match['maximum'])
        if minimum <= maximum:
            return NavrhMezi('prevod', minimum, maximum, 'Číselný rozsah bez čísel z označení metody.')
    return NavrhMezi('rucne', poznamka='Nejednoznačný nebo neznámý formát; zkontrolujte původní podklad.')


def navrh_mezi(predpis, druh):
    context = {'zakaznik': predpis.zakaznik.zkratka, 'nazev': predpis.nazev}
    if druh != 'vrstva':
        return _hodnota(getattr(predpis, druh), druh, **context)

    candidates, methods = set(), False
    for value in (predpis.vrstva, predpis.vrstva_2):
        parsed = _hodnota(value, druh, **context)
        if parsed.stav == 'prevod':
            candidates.add((parsed.minimum, parsed.maximum))
        elif parsed.stav == 'rucne':
            text = normalizovat(value)
            if re.fullmatch(CHD, text, re.IGNORECASE) or text.casefold() == 'průběh tvrdosti':
                methods = True
            else:
                return parsed
    if len(candidates) > 1:
        return NavrhMezi('rucne', poznamka='Vrstva a Vrstva 2 obsahují rozdílné meze.')
    if candidates:
        minimum, maximum = candidates.pop()
        return NavrhMezi('prevod', minimum, maximum, 'Společná mez v mm z Vrstva / Vrstva 2.')
    return NavrhMezi('metodika' if methods else 'bez_meze', poznamka='Bez číselné meze vrstvy v mm.')
