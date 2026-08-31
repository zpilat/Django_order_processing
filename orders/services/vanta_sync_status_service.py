"""Čtení stavu synchronizace exportů z analyzátoru Vanta."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone


@dataclass(frozen=True)
class VantaSyncStatus:
    path: Path
    checked_at: datetime | None = None
    available: bool | None = None
    running: bool = False
    remote_files: int | None = None
    downloaded_files: int | None = None
    remaining_files: int | None = None
    error: str | None = None
    read_error: str | None = None
    stale: bool = False

    @property
    def blocks_import(self) -> bool:
        """Blokuje pouze čerstvý stav, který potvrzuje nedokončenou synchronizaci."""
        if self.read_error or self.stale:
            return False
        return self.running or bool(self.remaining_files)

    @property
    def level(self) -> str:
        if self.blocks_import:
            return 'error'
        if self.read_error or self.stale or self.available is not True:
            return 'warning'
        return 'success'

    @property
    def message(self) -> str:
        if self.read_error:
            return (
                f'Stav synchronizace Vanty není k dispozici ({self.read_error}). '
                'Nemusí být k dispozici všechna měření.'
            )
        if self.stale:
            return (
                'Poslední informace o synchronizaci Vanty je zastaralá. '
                'Nemusí být k dispozici všechna měření.'
            )
        if self.running:
            return 'Synchronizace Vanty právě probíhá. Obnovte náhled přibližně za minutu.'
        if self.remaining_files:
            return (
                f'Vanta je dostupná, ale zbývá stáhnout {self.remaining_files} '
                f'{_format_file_count(self.remaining_files)}. '
                'Import je do dokončení synchronizace zablokován; obnovte náhled přibližně za minutu.'
            )
        if self.available is False:
            detail = f' ({self.error})' if self.error else ''
            return (
                f'Vanta při poslední kontrole nebyla dostupná{detail}. '
                'Nemusí být k dispozici všechna měření.'
            )
        if self.available is True and self.remaining_files == 0:
            if self.downloaded_files:
                return (
                    'Synchronizace Vanty je dokončená; při poslední kontrole bylo staženo '
                    f'{self.downloaded_files} {_format_file_count(self.downloaded_files)}.'
                )
            return 'Synchronizace Vanty je dokončená; žádné soubory nečekají na stažení.'
        return (
            'Stav synchronizace Vanty není jednoznačný. '
            'Nemusí být k dispozici všechna měření.'
        )


def _format_file_count(count: int) -> str:
    if count == 1:
        return 'soubor'
    if 2 <= count <= 4:
        return 'soubory'
    return 'souborů'


def _optional_nonnegative_int(data: dict, key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f'položka {key} musí být nezáporné celé číslo nebo null')
    return value


def _parse_datetime(value: object, key: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f'položka {key} musí být textové datum nebo null')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError(f'položka {key} neobsahuje platné datum') from exc
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def get_vanta_sync_status(
    *,
    incoming_dir: str | Path | None = None,
    status_path: str | Path | None = None,
    now: datetime | None = None,
) -> VantaSyncStatus:
    """Načte stavový JSON vytvářený skriptem vanta-sync.sh."""
    if status_path is None:
        source_dir = Path(incoming_dir or settings.CHEMISTRY_INCOMING_DIR)
        filename = getattr(
            settings,
            'VANTA_SYNC_STATUS_FILENAME',
            '.vanta-sync-status.json',
        )
        path = source_dir / filename
    else:
        path = Path(status_path)

    if not path.is_file():
        return VantaSyncStatus(path=path, read_error='stavový soubor neexistuje')

    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('kořen musí být objekt')

        available = data.get('available')
        if available is not None and not isinstance(available, bool):
            raise ValueError('položka available musí být true, false nebo null')

        running = data.get('running', False)
        if not isinstance(running, bool):
            raise ValueError('položka running musí být true nebo false')

        error = data.get('error')
        if error is not None and not isinstance(error, str):
            raise ValueError('položka error musí být text nebo null')

        checked_at = _parse_datetime(data.get('checked_at'), 'checked_at')
        remote_files = _optional_nonnegative_int(data, 'remote_files')
        downloaded_files = _optional_nonnegative_int(data, 'downloaded_files')
        remaining_files = _optional_nonnegative_int(data, 'remaining_files')
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return VantaSyncStatus(path=path, read_error=f'nelze načíst stavový soubor: {exc}')

    max_age_seconds = max(
        1,
        int(getattr(settings, 'VANTA_SYNC_STATUS_MAX_AGE_SECONDS', 180)),
    )
    current_time = now or timezone.now()
    stale = checked_at is None or checked_at < current_time - timedelta(seconds=max_age_seconds)

    return VantaSyncStatus(
        path=path,
        checked_at=checked_at,
        available=available,
        running=running,
        remote_files=remote_files,
        downloaded_files=downloaded_files,
        remaining_files=remaining_files,
        error=error,
        stale=stale,
    )
