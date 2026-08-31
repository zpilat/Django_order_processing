import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase
from django.utils import timezone

from orders.services.vanta_sync_status_service import get_vanta_sync_status


class VantaSyncStatusTests(SimpleTestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.incoming = Path(self.temp_dir.name)
        self.now = timezone.now()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_status(self, **overrides):
        data = {
            'checked_at': self.now.isoformat(),
            'available': True,
            'running': False,
            'remote_files': 3,
            'downloaded_files': 3,
            'remaining_files': 0,
            'error': None,
        }
        data.update(overrides)
        path = self.incoming / '.vanta-sync-status.json'
        path.write_text(json.dumps(data), encoding='utf-8')
        return path

    def test_completed_sync_allows_import(self):
        self._write_status()

        status = get_vanta_sync_status(incoming_dir=self.incoming, now=self.now)

        self.assertFalse(status.blocks_import)
        self.assertEqual(status.level, 'success')
        self.assertIn('dokončená', status.message)

    def test_running_sync_blocks_import(self):
        self._write_status(running=True, remaining_files=None)

        status = get_vanta_sync_status(incoming_dir=self.incoming, now=self.now)

        self.assertTrue(status.blocks_import)
        self.assertIn('právě probíhá', status.message)

    def test_known_remaining_files_block_import(self):
        self._write_status(remaining_files=5)

        status = get_vanta_sync_status(incoming_dir=self.incoming, now=self.now)

        self.assertTrue(status.blocks_import)
        self.assertIn('zbývá stáhnout 5 souborů', status.message)

    def test_unavailable_vanta_only_warns(self):
        self._write_status(
            available=False,
            remote_files=None,
            downloaded_files=0,
            remaining_files=None,
            error='Vanta není dostupná',
        )

        status = get_vanta_sync_status(incoming_dir=self.incoming, now=self.now)

        self.assertFalse(status.blocks_import)
        self.assertEqual(status.level, 'warning')
        self.assertIn('nebyla dostupná', status.message)

    def test_stale_running_status_does_not_block_indefinitely(self):
        self._write_status(
            checked_at=(self.now - timedelta(minutes=10)).isoformat(),
            running=True,
        )

        with self.settings(VANTA_SYNC_STATUS_MAX_AGE_SECONDS=180):
            status = get_vanta_sync_status(incoming_dir=self.incoming, now=self.now)

        self.assertTrue(status.stale)
        self.assertFalse(status.blocks_import)
        self.assertIn('zastaralá', status.message)

    def test_missing_or_invalid_status_does_not_crash_import(self):
        missing = get_vanta_sync_status(incoming_dir=self.incoming, now=self.now)
        self.assertFalse(missing.blocks_import)
        self.assertIsNotNone(missing.read_error)

        path = self.incoming / '.vanta-sync-status.json'
        path.write_text('{not-json', encoding='utf-8')
        invalid = get_vanta_sync_status(incoming_dir=self.incoming, now=self.now)
        self.assertFalse(invalid.blocks_import)
        self.assertIsNotNone(invalid.read_error)
