"""Načtení a archivace chemických měření z analyzátoru Vanta."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils.text import get_valid_filename

from orders.models import Bedna, Kamion


logger = logging.getLogger('orders')

REQUIRED_ELEMENTS = ('Ca', 'P', 'Zn')
CONCENTRATION_QUANTUM = Decimal('0.000001')
FILENAME_RE = re.compile(
    r'^chemistry-(?P<device>\d+)-'
    r'(?P<timestamp>\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})\.json$',
    re.IGNORECASE,
)
ARCHIVE_FILENAME_RE = re.compile(
    r'^(?P<box>\d+)_'
    r'(?P<timestamp>\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})\.json$',
    re.IGNORECASE,
)


class ChemistryImportError(Exception):
    """Chyba, kvůli které nelze potvrdit import chemických měření."""


@dataclass(frozen=True)
class ParsedChemistryFile:
    path: Path
    box_number: int
    measured_at: datetime
    raw_data: dict
    digest: str

    @property
    def file_name(self) -> str:
        return self.path.name


@dataclass(frozen=True)
class ArchivedChemistryFile:
    path: Path
    box_number: int
    measured_at: datetime
    digest: str


@dataclass
class ChemistryImportRow:
    bedna: Bedna
    selected_file: ParsedChemistryFile
    source_files: list[ParsedChemistryFile]
    obsah_ca: Decimal
    obsah_p: Decimal
    obsah_zn: Decimal
    update_values: bool
    status: str

    @property
    def repeated_measurements(self) -> int:
        return max(0, len(self.source_files) - 1)


@dataclass
class ChemistryImportPreview:
    kamion: Kamion
    incoming_dir: Path
    archive_dir: Path
    rows: list[ChemistryImportRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_box_numbers: list[int] = field(default_factory=list)

    @property
    def can_import(self) -> bool:
        return bool(self.rows) and not self.errors


@dataclass
class ChemistryImportResult:
    updated_count: int
    unchanged_count: int
    processed_file_count: int
    archive_errors: list[str] = field(default_factory=list)

    @property
    def imported_count(self) -> int:
        """Zpětně kompatibilní pojmenování počtu aktualizovaných beden."""
        return self.updated_count


def _reject_json_constant(value: str):
    raise ValueError(f'neplatná číselná konstanta {value}')


def _read_json_file(path: Path) -> tuple[dict, str]:
    raw_bytes = path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    text = raw_bytes.decode('utf-8-sig')
    data = json.loads(
        text,
        parse_float=Decimal,
        parse_constant=_reject_json_constant,
    )
    if not isinstance(data, dict):
        raise ValueError('kořen JSONu musí být objekt')
    return data, digest


def _get_box_number(data: dict) -> int:
    test_info = data.get('testInfo')
    if not isinstance(test_info, dict):
        raise ValueError('chybí objekt testInfo')

    raw_number = str(test_info.get('info', '')).strip()
    if not re.fullmatch(r'\d+', raw_number):
        raise ValueError(f'neplatné číslo bedny v testInfo.info: {raw_number!r}')
    return int(raw_number)


def _get_measurement_time(path: Path) -> datetime:
    match = FILENAME_RE.fullmatch(path.name)
    if not match:
        raise ValueError('název neodpovídá formátu chemistry-ČÍSLO-RRRR-MM-DD-HH-MM-SS.json')
    try:
        return datetime.strptime(match.group('timestamp'), '%Y-%m-%d-%H-%M-%S')
    except ValueError as exc:
        raise ValueError('název obsahuje neplatné datum nebo čas') from exc


def _get_concentrations(data: dict, file_name: str) -> dict[str, Decimal]:
    chemistry = data.get('chemistry')
    if not isinstance(chemistry, list):
        raise ValueError(f'{file_name}: chybí seznam chemistry')

    concentrations: dict[str, Decimal] = {}
    for item in chemistry:
        if not isinstance(item, dict):
            continue
        element = item.get('elementName')
        if element not in REQUIRED_ELEMENTS:
            continue
        if element in concentrations:
            raise ValueError(f'{file_name}: prvek {element} je uveden vícekrát')

        raw_value = item.get('concentration')
        if raw_value is None or isinstance(raw_value, bool):
            raise ValueError(f'{file_name}: prvek {element} nemá platnou koncentraci')
        try:
            value = raw_value if isinstance(raw_value, Decimal) else Decimal(str(raw_value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(f'{file_name}: prvek {element} nemá platnou koncentraci') from exc
        if not value.is_finite() or value < 0 or value > 100:
            raise ValueError(f'{file_name}: koncentrace prvku {element} musí být v rozsahu 0 až 100 %')
        concentrations[element] = value.quantize(CONCENTRATION_QUANTUM, rounding=ROUND_HALF_UP)

    missing = [element for element in REQUIRED_ELEMENTS if element not in concentrations]
    if missing:
        raise ValueError(f'{file_name}: chybějí prvky {", ".join(missing)}')
    return concentrations


def _format_box_numbers(numbers: list[int], limit: int = 20) -> str:
    shown = ', '.join(str(number) for number in numbers[:limit])
    if len(numbers) > limit:
        shown += f' a dalších {len(numbers) - limit}'
    return shown


def build_chemistry_import_preview(
    kamion: Kamion,
    *,
    incoming_dir: Path | str | None = None,
    archive_root: Path | str | None = None,
) -> ChemistryImportPreview:
    """Připraví náhled nejnovějšího měření pro každou bednu kamionu."""
    source_dir = Path(incoming_dir or settings.CHEMISTRY_INCOMING_DIR)
    archive_root_path = Path(archive_root or settings.CHEMISTRY_ARCHIVE_DIR)
    archive_dir = _get_archive_directory(kamion, archive_root_path)
    preview = ChemistryImportPreview(
        kamion=kamion,
        incoming_dir=source_dir,
        archive_dir=archive_dir,
    )

    bedny = list(
        Bedna.objects.filter(zakazka__kamion_prijem=kamion)
        .select_related('zakazka')
        .order_by('cislo_bedny')
    )
    if not bedny:
        preview.errors.append('Vybraný kamion neobsahuje žádné bedny.')
        return preview
    bedny_by_number = {bedna.cislo_bedny: bedna for bedna in bedny}

    if not source_dir.exists():
        preview.errors.append(f'Vstupní adresář neexistuje: {source_dir}')
        return preview
    if not source_dir.is_dir():
        preview.errors.append(f'Nastavená vstupní cesta není adresář: {source_dir}')
        return preview

    try:
        json_paths = sorted(
            path for path in source_dir.iterdir()
            if path.is_file() and path.suffix.lower() == '.json'
        )
    except OSError as exc:
        preview.errors.append(f'Vstupní adresář nelze načíst: {exc}')
        return preview

    archived_files: dict[int, list[ArchivedChemistryFile]] = defaultdict(list)
    archived_by_box_and_time: dict[tuple[int, datetime], ArchivedChemistryFile] = {}
    if archive_dir.exists():
        if not archive_dir.is_dir():
            preview.errors.append(f'Nastavená archivní cesta není adresář: {archive_dir}')
            return preview
        try:
            archive_paths = sorted(
                path for path in archive_dir.iterdir()
                if path.is_file() and path.suffix.lower() == '.json'
            )
        except OSError as exc:
            preview.errors.append(f'Archivní adresář nelze načíst: {exc}')
            return preview

        for path in archive_paths:
            match = ARCHIVE_FILENAME_RE.fullmatch(path.name)
            if not match:
                legacy_match = re.fullmatch(r'(?P<box>\d+)\.json', path.name, re.IGNORECASE)
                if legacy_match and int(legacy_match.group('box')) in bedny_by_number:
                    preview.errors.append(
                        f'Archivní soubor {path.name} neobsahuje datum a čas měření v názvu.'
                    )
                else:
                    preview.warnings.append(f'Neplatně pojmenovaný archivní soubor byl ignorován: {path.name}.')
                continue

            box_number = int(match.group('box'))
            if box_number not in bedny_by_number:
                continue
            try:
                measured_at = datetime.strptime(match.group('timestamp'), '%Y-%m-%d-%H-%M-%S')
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except (OSError, ValueError) as exc:
                preview.errors.append(f'Archivní soubor {path.name} nelze načíst: {exc}')
                continue

            archived = ArchivedChemistryFile(
                path=path,
                box_number=box_number,
                measured_at=measured_at,
                digest=digest,
            )
            archived_files[box_number].append(archived)
            archived_by_box_and_time[(box_number, measured_at)] = archived

    candidates: dict[int, list[ParsedChemistryFile]] = defaultdict(list)
    ignored_invalid: list[str] = []

    for path in json_paths:
        try:
            data, digest = _read_json_file(path)
            box_number = _get_box_number(data)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            ignored_invalid.append(f'{path.name}: {exc}')
            continue

        if box_number not in bedny_by_number:
            continue

        try:
            measured_at = _get_measurement_time(path)
        except ValueError as exc:
            preview.errors.append(f'{path.name} (bedna {box_number}): {exc}')
            continue

        candidates[box_number].append(
            ParsedChemistryFile(
                path=path,
                box_number=box_number,
                measured_at=measured_at,
                raw_data=data,
                digest=digest,
            )
        )

    if ignored_invalid:
        preview.warnings.append(
            'Některé JSONy nešlo přiřadit a zůstanou ve vstupním adresáři: '
            + '; '.join(ignored_invalid)
        )

    for box_number, bedna in sorted(bedny_by_number.items()):
        box_candidates = candidates.get(box_number, [])
        box_archives = sorted(
            archived_files.get(box_number, []),
            key=lambda item: item.measured_at,
        )
        chemistry_values = (bedna.obsah_ca, bedna.obsah_p, bedna.obsah_zn)
        chemistry_full = all(value is not None for value in chemistry_values)
        chemistry_empty = all(value is None for value in chemistry_values)

        if not chemistry_full and not chemistry_empty:
            preview.errors.append(
                f'Bedna {box_number}: chemické hodnoty jsou vyplněné pouze částečně.'
            )
            continue
        if chemistry_empty and box_archives:
            preview.errors.append(
                f'Bedna {box_number}: archiv obsahuje měření, ale chemické hodnoty v databázi jsou prázdné.'
            )
            continue
        if chemistry_full and not box_archives:
            if box_candidates:
                preview.warnings.append(
                    f'Bedna {box_number}: chemické hodnoty jsou vyplněné, ale archiv chybí; '
                    'bude obnoven z nejnovějšího vstupního měření.'
                )
            else:
                preview.errors.append(
                    f'Bedna {box_number}: chemické hodnoty jsou vyplněné, ale archivní JSON chybí.'
                )
                continue

        if not box_candidates:
            if chemistry_empty and not box_archives:
                preview.missing_box_numbers.append(box_number)
            continue

        box_candidates.sort(key=lambda item: (item.measured_at, item.file_name))
        times = [item.measured_at for item in box_candidates]
        duplicate_times = sorted({item for item in times if times.count(item) > 1})
        if duplicate_times:
            duplicate_time = duplicate_times[-1]
            names = ', '.join(
                item.file_name for item in box_candidates if item.measured_at == duplicate_time
            )
            preview.errors.append(f'Bedna {box_number}: více měření má shodný čas ({names}).')
            continue

        archive_conflicts = []
        for source_file in box_candidates:
            archived = archived_by_box_and_time.get((box_number, source_file.measured_at))
            if archived and archived.digest != source_file.digest:
                archive_conflicts.append(source_file.file_name)
        if archive_conflicts:
            preview.errors.append(
                f'Bedna {box_number}: stejné datum a čas má v archivu jiný obsah '
                f'({", ".join(archive_conflicts)}).'
            )
            continue

        selected = box_candidates[-1]
        try:
            concentrations = _get_concentrations(selected.raw_data, selected.file_name)
        except ValueError as exc:
            preview.errors.append(f'Bedna {box_number}: {exc}')
            continue

        if chemistry_empty or not box_archives:
            update_values = True
            status = 'Nové měření – hodnoty budou uloženy'
        else:
            latest_archive = box_archives[-1]
            if selected.measured_at > latest_archive.measured_at:
                update_values = True
                status = 'Novější měření – hodnoty budou aktualizovány'
            elif selected.measured_at == latest_archive.measured_at:
                update_values = False
                status = 'Již importované měření – hodnoty zůstanou beze změny'
            else:
                update_values = False
                status = 'Starší měření – hodnoty zůstanou beze změny'

        preview.rows.append(
            ChemistryImportRow(
                bedna=bedna,
                selected_file=selected,
                source_files=box_candidates,
                obsah_ca=concentrations['Ca'],
                obsah_p=concentrations['P'],
                obsah_zn=concentrations['Zn'],
                update_values=update_values,
                status=status,
            )
        )

    if preview.missing_box_numbers:
        preview.warnings.append(
            f'Bez nalezeného měření je {len(preview.missing_box_numbers)} beden: '
            f'{_format_box_numbers(preview.missing_box_numbers)}.'
        )

    if not preview.rows and not preview.errors:
        preview.errors.append('Pro vybraný kamion nebylo nalezeno žádné nové ani opakované měření.')
    return preview


def _verify_source_files(preview: ChemistryImportPreview) -> None:
    """Ověří, že se soubory mezi načtením náhledu a potvrzením nezměnily."""
    for row in preview.rows:
        for source_file in row.source_files:
            try:
                current_digest = hashlib.sha256(source_file.path.read_bytes()).hexdigest()
            except OSError as exc:
                raise ChemistryImportError(
                    f'Soubor {source_file.file_name} už nelze načíst: {exc}'
                ) from exc
            if current_digest != source_file.digest:
                raise ChemistryImportError(
                    f'Soubor {source_file.file_name} se během importu změnil. Spusťte náhled znovu.'
                )


def _get_archive_directory(kamion: Kamion, archive_root: Path) -> Path:
    directory_name = get_valid_filename(str(kamion))
    if not directory_name:
        directory_name = f'kamion-{kamion.pk}'
    return archive_root / directory_name


def apply_chemistry_import(
    preview: ChemistryImportPreview,
    *,
    archive_root: Path | str | None = None,
) -> ChemistryImportResult:
    """Uloží pouze novější výsledky a všechny rozpoznané JSONy archivuje."""
    if not preview.can_import:
        raise ChemistryImportError('Import nelze potvrdit, dokud náhled obsahuje chyby.')

    _verify_source_files(preview)

    root = Path(archive_root or settings.CHEMISTRY_ARCHIVE_DIR)
    archive_dir = _get_archive_directory(preview.kamion, root)
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ChemistryImportError(f'Nelze vytvořit archivní adresář {archive_dir}: {exc}') from exc

    bedna_ids = [row.bedna.pk for row in preview.rows]
    with transaction.atomic():
        locked_bedny = {
            bedna.pk: bedna
            for bedna in Bedna.objects.select_for_update().filter(pk__in=bedna_ids)
        }
        if len(locked_bedny) != len(bedna_ids):
            raise ChemistryImportError('Některá bedna byla během importu odstraněna.')

        to_update = []
        for row in preview.rows:
            bedna = locked_bedny[row.bedna.pk]
            original_values = (row.bedna.obsah_ca, row.bedna.obsah_p, row.bedna.obsah_zn)
            current_values = (bedna.obsah_ca, bedna.obsah_p, bedna.obsah_zn)
            if current_values != original_values:
                raise ChemistryImportError(
                    f'Chemické hodnoty bedny {bedna.cislo_bedny} se během importu změnily. '
                    'Spusťte náhled znovu.'
                )
            if not row.update_values:
                continue
            bedna.obsah_ca = row.obsah_ca
            bedna.obsah_p = row.obsah_p
            bedna.obsah_zn = row.obsah_zn
            to_update.append(bedna)
        if to_update:
            Bedna.objects.bulk_update(to_update, ['obsah_ca', 'obsah_p', 'obsah_zn'])

    archive_errors: list[str] = []
    processed_file_count = 0
    for row in preview.rows:
        for source_file in row.source_files:
            timestamp = source_file.measured_at.strftime('%Y-%m-%d-%H-%M-%S')
            destination = archive_dir / f'{row.bedna.cislo_bedny}_{timestamp}.json'
            try:
                if destination.exists():
                    archived_digest = hashlib.sha256(destination.read_bytes()).hexdigest()
                    if archived_digest != source_file.digest:
                        raise OSError('cílový soubor existuje s jiným obsahem')
                    source_file.path.unlink()
                else:
                    os.replace(source_file.path, destination)
                processed_file_count += 1
            except OSError as exc:
                message = (
                    f'Bedna {row.bedna.cislo_bedny}: soubor {source_file.file_name} '
                    f'nelze archivovat do {destination}: {exc}'
                )
                archive_errors.append(message)
                logger.error(message)
                break

    return ChemistryImportResult(
        updated_count=sum(1 for row in preview.rows if row.update_values),
        unchanged_count=sum(1 for row in preview.rows if not row.update_values),
        processed_file_count=processed_file_count,
        archive_errors=archive_errors,
    )
