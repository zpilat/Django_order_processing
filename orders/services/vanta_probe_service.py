"""Aktuální, pouze čtecí kontrola exportů na analyzátoru Vanta."""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone


logger = logging.getLogger('orders')

JSON_FILE_LINE_RE = re.compile(
    r'^\s*(?P<filename>.+?\.json)\s+[A-Z]+\s+\d+\s+',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VantaProbeResult:
    checked_at: datetime
    available: bool
    pending_files: tuple[str, ...] = ()
    error: str | None = None

    @property
    def pending_count(self) -> int:
        return len(self.pending_files)

    @property
    def blocks_import(self) -> bool:
        return self.available and self.pending_count > 0

    @property
    def level(self) -> str:
        if self.blocks_import:
            return 'error'
        if not self.available:
            return 'warning'
        return 'success'

    @property
    def message(self) -> str:
        if self.blocks_import:
            return (
                f'Na Vantě čeká na stažení {self.pending_count} '
                f'{_format_file_count(self.pending_count)}. '
                'Import je do dokončení synchronizace zablokován; '
                'obnovte náhled přibližně za minutu.'
            )
        if not self.available:
            detail = f' ({self.error})' if self.error else ''
            return (
                f'Aktuální kontrola Vanty se nezdařila{detail}. '
                'Nemusí být k dispozici všechna měření.'
            )
        return (
            'Vanta je dostupná; při aktuální kontrole nebyly nalezeny '
            'žádné JSONy čekající na stažení.'
        )


def _format_file_count(count: int) -> str:
    if count == 1:
        return 'JSON'
    if 2 <= count <= 4:
        return 'JSONy'
    return 'JSONů'


def _extract_json_filenames(listing: str) -> tuple[str, ...]:
    filenames = []
    for line in listing.splitlines():
        match = JSON_FILE_LINE_RE.match(line)
        if match:
            filenames.append(match.group('filename').strip())
    return tuple(sorted(set(filenames)))


def probe_vanta_exports() -> VantaProbeResult:
    """Jedním SMB výpisem zjistí, zda na Vantě čekají JSON exporty."""
    checked_at = timezone.now()
    command = getattr(settings, 'VANTA_SMBCLIENT_COMMAND', 'smbclient')
    remote = getattr(settings, 'VANTA_SMB_REMOTE', '//192.168.1.152/Vanta')
    remote_dir = getattr(settings, 'VANTA_SMB_REMOTE_DIR', 'exports')
    auth_file = Path(
        getattr(settings, 'VANTA_SMB_AUTH_FILE', '/etc/vanta-sync/credentials')
    )
    timeout_seconds = max(
        1,
        int(getattr(settings, 'VANTA_PROBE_TIMEOUT_SECONDS', 5)),
    )

    if not auth_file.is_file():
        return VantaProbeResult(
            checked_at=checked_at,
            available=False,
            error=f'chybí přihlašovací soubor {auth_file}',
        )

    try:
        completed = subprocess.run(
            [
                command,
                remote,
                '-A',
                str(auth_file),
                '-c',
                f'cd "{remote_dir}"; ls',
            ],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning(
            'Aktuální kontrola Vanty překročila limit %s sekund.',
            timeout_seconds,
        )
        return VantaProbeResult(
            checked_at=timezone.now(),
            available=False,
            error=f'dotaz překročil limit {timeout_seconds} sekund',
        )
    except OSError as exc:
        logger.warning('Aktuální kontrolu Vanty nelze spustit: %s', exc)
        return VantaProbeResult(
            checked_at=timezone.now(),
            available=False,
            error='na serveru nelze spustit smbclient',
        )

    checked_at = timezone.now()
    if completed.returncode != 0:
        logger.warning(
            'Aktuální kontrola Vanty selhala s kódem %s: %s',
            completed.returncode,
            completed.stderr.strip(),
        )
        return VantaProbeResult(
            checked_at=checked_at,
            available=False,
            error='Vanta není dostupná nebo nelze načíst adresář exports',
        )

    return VantaProbeResult(
        checked_at=checked_at,
        available=True,
        pending_files=_extract_json_filenames(completed.stdout),
    )
