import json
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.text import get_valid_filename
from django.urls import reverse

from orders import actions
from orders.admin import KamionAdmin
from orders.choices import KamionChoice
from orders.models import Bedna, Kamion, Predpis, TypHlavy, Zakazka, Zakaznik
from orders.services.chemistry_import_service import (
    apply_chemistry_import,
    build_chemistry_import_preview,
)
from orders.services.vanta_probe_service import VantaProbeResult


class ChemistryImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.zakaznik = Zakaznik.objects.create(
            nazev='Chemie test',
            zkraceny_nazev='Chemie',
            zkratka='CHM',
            ciselna_rada=700000,
        )
        cls.predpis = Predpis.objects.create(
            nazev='Chemie předpis',
            skupina=1,
            zakaznik=cls.zakaznik,
        )
        cls.typ_hlavy = TypHlavy.objects.create(nazev='CH', popis='Chemie')
        cls.kamion = Kamion.objects.create(zakaznik=cls.zakaznik, datum=date(2026, 8, 21))
        cls.zakazka = Zakazka.objects.create(
            kamion_prijem=cls.kamion,
            artikl='CHEM-1',
            prumer=Decimal('10'),
            delka=Decimal('50'),
            predpis=cls.predpis,
            typ_hlavy=cls.typ_hlavy,
            popis='Chemický import',
        )
        cls.bedna_1 = Bedna.objects.create(zakazka=cls.zakazka)
        cls.bedna_2 = Bedna.objects.create(zakazka=cls.zakazka)

        cls.jiny_kamion = Kamion.objects.create(zakaznik=cls.zakaznik, datum=date(2026, 8, 22))
        cls.jina_zakazka = Zakazka.objects.create(
            kamion_prijem=cls.jiny_kamion,
            artikl='CHEM-2',
            prumer=Decimal('10'),
            delka=Decimal('50'),
            predpis=cls.predpis,
            typ_hlavy=cls.typ_hlavy,
            popis='Jiný kamion',
        )
        cls.jina_bedna = Bedna.objects.create(zakazka=cls.jina_zakazka)

        User = get_user_model()
        cls.user = User.objects.create_superuser('chemie-admin', 'chemie@example.com', 'pass')

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.incoming = Path(self.temp_dir.name) / 'incoming'
        self.archive = self.incoming / 'archiv'
        self.incoming.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_measurement(
        self,
        *,
        box_number,
        timestamp,
        ca='0',
        p='0',
        zn='0',
        missing_element=None,
    ):
        elements = {
            'Ca': ca,
            'P': p,
            'Zn': zn,
        }
        chemistry = [
            {
                'elementName': element,
                'concentration': float(value),
                'error': 0.001,
            }
            for element, value in elements.items()
            if element != missing_element
        ]
        data = {
            'analysis': {'dailyId': 2},
            'chemistry': chemistry,
            'testInfo': {'info': str(box_number)},
        }
        path = self.incoming / f'chemistry-948596-{timestamp}.json'
        path.write_text(json.dumps(data), encoding='utf-8')
        return path

    def _request(self, *, confirm=False):
        data = {
            'action': 'import_chemickych_mereni_action',
            '_selected_action': str(self.kamion.pk),
        }
        if confirm:
            data['confirm_chemistry_import'] = '1'
        request = RequestFactory().post('/', data)
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def _probe_result(self, *, available=True, pending_files=(), error=None):
        return VantaProbeResult(
            checked_at=timezone.now(),
            available=available,
            pending_files=tuple(pending_files),
            error=error,
        )

    def test_preview_selects_latest_measurement_without_scaling_percentages(self):
        self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-13-24-58',
            ca='0.1', p='0.2', zn='0.3',
        )
        latest = self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-13-31-04',
            ca='0.1234567', p='0', zn='1.25',
        )
        self._write_measurement(
            box_number=self.jina_bedna.cislo_bedny,
            timestamp='2026-08-21-13-32-00',
            ca='9', p='9', zn='9',
        )

        preview = build_chemistry_import_preview(
            self.kamion,
            incoming_dir=self.incoming,
            archive_root=self.archive,
        )

        self.assertTrue(preview.can_import)
        self.assertEqual(len(preview.rows), 1)
        row = preview.rows[0]
        self.assertEqual(row.selected_file.path, latest)
        self.assertEqual(row.repeated_measurements, 1)
        self.assertEqual(row.obsah_ca, Decimal('0.123457'))
        self.assertEqual(row.obsah_p, Decimal('0.000000'))
        self.assertEqual(row.obsah_zn, Decimal('1.250000'))
        self.assertEqual(preview.missing_box_numbers, [self.bedna_2.cislo_bedny])

    def test_latest_invalid_measurement_blocks_that_box(self):
        self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-10-00-00',
            ca='0.1', p='0.2', zn='0.3',
        )
        self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-11-00-00',
            ca='0.4', p='0.5', zn='0.6',
            missing_element='P',
        )

        preview = build_chemistry_import_preview(
            self.kamion,
            incoming_dir=self.incoming,
            archive_root=self.archive,
        )

        self.assertFalse(preview.can_import)
        self.assertEqual(preview.rows, [])
        self.assertTrue(any('chybějí prvky P' in error for error in preview.errors))

    def test_legacy_hidden_status_json_is_ignored(self):
        self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-13-24-58',
            ca='0.1', p='0.2', zn='0.3',
        )
        legacy_status = self.incoming / '.vanta-sync-status.json'
        legacy_status.write_text('{"available": true}', encoding='utf-8')

        preview = build_chemistry_import_preview(
            self.kamion,
            incoming_dir=self.incoming,
            archive_root=self.archive,
        )

        self.assertTrue(preview.can_import)
        self.assertFalse(
            any(legacy_status.name in warning for warning in preview.warnings)
        )

    def test_apply_updates_boxes_and_archives_only_files_of_selected_truck(self):
        old_file = self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-09-00-00',
            ca='0.1', p='0.2', zn='0.3',
        )
        latest_file = self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-10-00-00',
            ca='1.1', p='1.2', zn='1.3',
        )
        box_2_file = self._write_measurement(
            box_number=self.bedna_2.cislo_bedny,
            timestamp='2026-08-21-10-01-00',
            ca='2.1', p='2.2', zn='2.3',
        )
        other_file = self._write_measurement(
            box_number=self.jina_bedna.cislo_bedny,
            timestamp='2026-08-21-10-02-00',
            ca='3.1', p='3.2', zn='3.3',
        )
        latest_data = json.loads(latest_file.read_text(encoding='utf-8'))

        preview = build_chemistry_import_preview(
            self.kamion,
            incoming_dir=self.incoming,
            archive_root=self.archive,
        )
        history_count = self.bedna_1.history.count()
        result = apply_chemistry_import(preview, archive_root=self.archive)

        self.assertEqual(result.imported_count, 2)
        self.assertEqual(result.processed_file_count, 3)
        self.assertEqual(result.archive_errors, [])
        self.bedna_1.refresh_from_db()
        self.bedna_2.refresh_from_db()
        self.assertEqual(self.bedna_1.obsah_ca, Decimal('1.100000'))
        self.assertEqual(self.bedna_1.obsah_p, Decimal('1.200000'))
        self.assertEqual(self.bedna_1.obsah_zn, Decimal('1.300000'))
        self.assertEqual(self.bedna_2.obsah_ca, Decimal('2.100000'))
        self.assertEqual(self.bedna_1.history.count(), history_count)

        archive_dir = self.archive / get_valid_filename(str(self.kamion))
        archived_old_box_1 = archive_dir / f'{self.bedna_1.cislo_bedny}_2026-08-21-09-00-00.json'
        archived_box_1 = archive_dir / f'{self.bedna_1.cislo_bedny}_2026-08-21-10-00-00.json'
        archived_box_2 = archive_dir / f'{self.bedna_2.cislo_bedny}_2026-08-21-10-01-00.json'
        self.assertTrue(archived_old_box_1.exists())
        self.assertTrue(archived_box_1.exists())
        self.assertTrue(archived_box_2.exists())
        self.assertEqual(json.loads(archived_box_1.read_text(encoding='utf-8')), latest_data)
        self.assertFalse(old_file.exists())
        self.assertFalse(latest_file.exists())
        self.assertFalse(box_2_file.exists())
        self.assertTrue(other_file.exists())

    def test_reimported_identical_file_does_not_update_values(self):
        source = self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-13-24-58',
            ca='0.1', p='0.2', zn='0.3',
        )
        preview = build_chemistry_import_preview(
            self.kamion,
            incoming_dir=self.incoming,
            archive_root=self.archive,
        )
        apply_chemistry_import(preview, archive_root=self.archive)

        archive_dir = self.archive / get_valid_filename(str(self.kamion))
        archived = archive_dir / f'{self.bedna_1.cislo_bedny}_2026-08-21-13-24-58.json'
        shutil.copy2(archived, source)

        repeated_preview = build_chemistry_import_preview(
            self.kamion,
            incoming_dir=self.incoming,
            archive_root=self.archive,
        )
        self.assertTrue(repeated_preview.can_import)
        self.assertFalse(repeated_preview.rows[0].update_values)
        self.assertIn('Již importované', repeated_preview.rows[0].status)

        history_count = self.bedna_1.history.count()
        result = apply_chemistry_import(repeated_preview, archive_root=self.archive)

        self.assertEqual(result.updated_count, 0)
        self.assertEqual(result.unchanged_count, 1)
        self.assertEqual(result.processed_file_count, 1)
        self.assertFalse(source.exists())
        self.assertTrue(archived.exists())
        self.assertEqual(self.bedna_1.history.count(), history_count)

    def test_reimported_older_file_cannot_replace_newer_archived_measurement(self):
        old_source = self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-09-00-00',
            ca='0.1', p='0.2', zn='0.3',
        )
        self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-10-00-00',
            ca='1.1', p='1.2', zn='1.3',
        )
        preview = build_chemistry_import_preview(
            self.kamion,
            incoming_dir=self.incoming,
            archive_root=self.archive,
        )
        apply_chemistry_import(preview, archive_root=self.archive)

        archive_dir = self.archive / get_valid_filename(str(self.kamion))
        archived_old = archive_dir / f'{self.bedna_1.cislo_bedny}_2026-08-21-09-00-00.json'
        shutil.copy2(archived_old, old_source)

        stale_preview = build_chemistry_import_preview(
            self.kamion,
            incoming_dir=self.incoming,
            archive_root=self.archive,
        )
        self.assertFalse(stale_preview.rows[0].update_values)
        self.assertIn('Starší měření', stale_preview.rows[0].status)
        result = apply_chemistry_import(stale_preview, archive_root=self.archive)

        self.bedna_1.refresh_from_db()
        self.assertEqual(result.updated_count, 0)
        self.assertEqual(self.bedna_1.obsah_ca, Decimal('1.100000'))
        self.assertEqual(self.bedna_1.obsah_p, Decimal('1.200000'))
        self.assertEqual(self.bedna_1.obsah_zn, Decimal('1.300000'))
        self.assertFalse(old_source.exists())

    def test_newer_measurement_updates_values_and_keeps_older_archive(self):
        self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-09-00-00',
            ca='0.1', p='0.2', zn='0.3',
        )
        first_preview = build_chemistry_import_preview(
            self.kamion,
            incoming_dir=self.incoming,
            archive_root=self.archive,
        )
        apply_chemistry_import(first_preview, archive_root=self.archive)

        self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-10-00-00',
            ca='1.1', p='1.2', zn='1.3',
        )
        newer_preview = build_chemistry_import_preview(
            self.kamion,
            incoming_dir=self.incoming,
            archive_root=self.archive,
        )

        self.assertTrue(newer_preview.rows[0].update_values)
        self.assertIn('Novější měření', newer_preview.rows[0].status)
        result = apply_chemistry_import(newer_preview, archive_root=self.archive)

        self.bedna_1.refresh_from_db()
        archive_dir = self.archive / get_valid_filename(str(self.kamion))
        self.assertEqual(result.updated_count, 1)
        self.assertEqual(self.bedna_1.obsah_ca, Decimal('1.100000'))
        self.assertTrue(
            (archive_dir / f'{self.bedna_1.cislo_bedny}_2026-08-21-09-00-00.json').exists()
        )
        self.assertTrue(
            (archive_dir / f'{self.bedna_1.cislo_bedny}_2026-08-21-10-00-00.json').exists()
        )

    def test_same_timestamp_with_different_content_is_conflict(self):
        self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-09-00-00',
            ca='0.1', p='0.2', zn='0.3',
        )
        first_preview = build_chemistry_import_preview(
            self.kamion,
            incoming_dir=self.incoming,
            archive_root=self.archive,
        )
        apply_chemistry_import(first_preview, archive_root=self.archive)

        conflicting_source = self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-09-00-00',
            ca='9.1', p='9.2', zn='9.3',
        )
        conflicting_preview = build_chemistry_import_preview(
            self.kamion,
            incoming_dir=self.incoming,
            archive_root=self.archive,
        )

        self.assertFalse(conflicting_preview.can_import)
        self.assertTrue(any('jiný obsah' in error for error in conflicting_preview.errors))
        self.assertTrue(conflicting_source.exists())

    @patch('orders.actions.probe_vanta_exports')
    def test_admin_action_renders_preview_and_confirmed_import(self, probe_mock):
        probe_mock.return_value = self._probe_result()
        self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-13-24-58',
            ca='0.1', p='0.2', zn='0.3',
        )
        admin_object = KamionAdmin(Kamion, AdminSite())
        queryset = Kamion.objects.filter(pk=self.kamion.pk)

        with self.settings(
            CHEMISTRY_INCOMING_DIR=self.incoming,
            CHEMISTRY_ARCHIVE_DIR=self.archive,
        ):
            response = actions.import_chemickych_mereni_action(
                admin_object,
                self._request(),
                queryset,
            )
            self.assertIsInstance(response, TemplateResponse)
            self.assertEqual(response.context_data['preview'].rows[0].bedna, self.bedna_1)
            response.render()
            self.assertContains(response, str(self.bedna_1.cislo_bedny))

            response = actions.import_chemickych_mereni_action(
                admin_object,
                self._request(confirm=True),
                queryset,
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('admin:orders_kamion_changelist'))
        self.assertEqual(probe_mock.call_count, 2)
        self.bedna_1.refresh_from_db()
        self.assertEqual(self.bedna_1.obsah_ca, Decimal('0.100000'))

    @patch('orders.actions.probe_vanta_exports')
    def test_admin_action_blocks_confirmation_while_files_are_waiting(self, probe_mock):
        probe_mock.return_value = self._probe_result(
            pending_files=('chemistry-a.json', 'chemistry-b.json'),
        )
        self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-13-24-58',
            ca='0.1', p='0.2', zn='0.3',
        )
        admin_object = KamionAdmin(Kamion, AdminSite())
        queryset = Kamion.objects.filter(pk=self.kamion.pk)

        with self.settings(
            CHEMISTRY_INCOMING_DIR=self.incoming,
            CHEMISTRY_ARCHIVE_DIR=self.archive,
        ):
            response = actions.import_chemickych_mereni_action(
                admin_object,
                self._request(confirm=True),
                queryset,
            )

        self.assertIsInstance(response, TemplateResponse)
        self.assertTrue(response.context_data['vanta_probe'].blocks_import)
        self.assertFalse(response.context_data['can_confirm_import'])
        response.render()
        self.assertContains(response, 'čeká na stažení 2 JSONy')
        self.assertContains(response, 'Obnovit náhled')
        self.bedna_1.refresh_from_db()
        self.assertIsNone(self.bedna_1.obsah_ca)

    @patch('orders.actions.probe_vanta_exports')
    def test_unavailable_vanta_warns_but_does_not_block_import(self, probe_mock):
        probe_mock.return_value = self._probe_result(
            available=False,
            error='Vanta není dostupná',
        )
        self._write_measurement(
            box_number=self.bedna_1.cislo_bedny,
            timestamp='2026-08-21-13-24-58',
            ca='0.1', p='0.2', zn='0.3',
        )
        admin_object = KamionAdmin(Kamion, AdminSite())
        queryset = Kamion.objects.filter(pk=self.kamion.pk)

        with self.settings(
            CHEMISTRY_INCOMING_DIR=self.incoming,
            CHEMISTRY_ARCHIVE_DIR=self.archive,
        ):
            preview_response = actions.import_chemickych_mereni_action(
                admin_object,
                self._request(),
                queryset,
            )
            preview_response.render()
            self.assertContains(preview_response, 'kontrola Vanty se nezdařila')
            self.assertTrue(preview_response.context_data['can_confirm_import'])

            result_response = actions.import_chemickych_mereni_action(
                admin_object,
                self._request(confirm=True),
                queryset,
            )

        self.assertEqual(result_response.status_code, 302)
        self.bedna_1.refresh_from_db()
        self.assertEqual(self.bedna_1.obsah_ca, Decimal('0.100000'))

    def test_admin_action_rejects_vydej_kamion(self):
        vydej = Kamion.objects.create(
            zakaznik=self.zakaznik,
            datum=date(2026, 8, 23),
            prijem_vydej=KamionChoice.VYDEJ,
        )
        admin_object = KamionAdmin(Kamion, AdminSite())

        response = actions.import_chemickych_mereni_action(
            admin_object,
            self._request(),
            Kamion.objects.filter(pk=vydej.pk),
        )

        self.assertIsNone(response)
