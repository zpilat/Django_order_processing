import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase

from orders.services.vanta_probe_service import probe_vanta_exports


class VantaProbeTests(SimpleTestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.auth_file = Path(self.temp_dir.name) / 'credentials'
        self.auth_file.write_text('username=test\npassword=test\n', encoding='utf-8')

    def tearDown(self):
        self.temp_dir.cleanup()

    def _settings(self):
        return self.settings(
            VANTA_SMBCLIENT_COMMAND='smbclient',
            VANTA_SMB_REMOTE='//192.168.1.152/Vanta',
            VANTA_SMB_REMOTE_DIR='exports',
            VANTA_SMB_AUTH_FILE=self.auth_file,
            VANTA_PROBE_TIMEOUT_SECONDS=5,
        )

    @patch('orders.services.vanta_probe_service.subprocess.run')
    def test_probe_reports_waiting_json_files(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                '  chemistry-948596-2026-08-21-13-24-58.json  A  123  Mon Aug 31\n'
                '  result.csv                                      A  456  Mon Aug 31\n'
                '  chemistry-948596-2026-08-21-13-25-58.json  A  789  Mon Aug 31\n'
            ),
            stderr='',
        )

        with self._settings():
            result = probe_vanta_exports()

        self.assertTrue(result.available)
        self.assertTrue(result.blocks_import)
        self.assertEqual(result.pending_count, 2)
        self.assertIn('čeká na stažení 2 JSONy', result.message)
        run_mock.assert_called_once()
        self.assertNotIn('shell', run_mock.call_args.kwargs)
        self.assertEqual(run_mock.call_args.kwargs['timeout'], 5)

    @patch('orders.services.vanta_probe_service.subprocess.run')
    def test_empty_remote_directory_allows_import(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='  .  D  0  Mon Aug 31\n  ..  D  0  Mon Aug 31\n',
            stderr='',
        )

        with self._settings():
            result = probe_vanta_exports()

        self.assertTrue(result.available)
        self.assertFalse(result.blocks_import)
        self.assertEqual(result.pending_count, 0)

    @patch('orders.services.vanta_probe_service.subprocess.run')
    def test_unavailable_vanta_warns_but_allows_import(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout='',
            stderr='NT_STATUS_IO_TIMEOUT',
        )

        with self._settings():
            result = probe_vanta_exports()

        self.assertFalse(result.available)
        self.assertFalse(result.blocks_import)
        self.assertEqual(result.level, 'warning')

    @patch('orders.services.vanta_probe_service.subprocess.run')
    def test_timeout_warns_but_allows_import(self, run_mock):
        run_mock.side_effect = subprocess.TimeoutExpired(cmd=['smbclient'], timeout=5)

        with self._settings():
            result = probe_vanta_exports()

        self.assertFalse(result.available)
        self.assertFalse(result.blocks_import)
        self.assertIn('limit 5 sekund', result.message)

    @patch('orders.services.vanta_probe_service.subprocess.run')
    def test_missing_credentials_do_not_start_smbclient(self, run_mock):
        missing_auth_file = Path(self.temp_dir.name) / 'missing-credentials'

        with self.settings(VANTA_SMB_AUTH_FILE=missing_auth_file):
            result = probe_vanta_exports()

        self.assertFalse(result.available)
        self.assertFalse(result.blocks_import)
        self.assertIn('chybí přihlašovací soubor', result.message)
        run_mock.assert_not_called()
