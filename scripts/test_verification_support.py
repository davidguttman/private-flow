"""Prerequisite discovery only: no adb calls, devices, or HTTP servers."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from verification_support import adb_command, emulator_grpc_ini, required_file


class VerificationSupportTests(unittest.TestCase):
    def test_sdk_variables_and_serial(self):
        with tempfile.TemporaryDirectory() as directory:
            adb = Path(directory) / 'platform-tools' / ('adb.exe' if os.name == 'nt' else 'adb')
            adb.parent.mkdir()
            adb.touch()
            adb.chmod(0o700)
            for variable in ('ANDROID_HOME', 'ANDROID_SDK_ROOT'):
                with self.subTest(variable=variable), patch.dict(os.environ, {variable: directory, 'ANDROID_SERIAL': 'fixture-device'}, clear=True):
                    self.assertEqual(adb_command(), [str(adb), '-s', 'fixture-device'])

    def test_falls_back_to_path(self):
        with patch.dict(os.environ, {'ANDROID_HOME': '/missing-sdk'}, clear=True), patch('verification_support.shutil.which', return_value='/fixture/adb'):
            self.assertEqual(adb_command(), ['/fixture/adb', '-s', 'emulator-5556'])

    def test_missing_adb_has_actionable_error(self):
        with patch.dict(os.environ, {}, clear=True), patch('verification_support.shutil.which', return_value=None):
            with self.assertRaisesRegex(SystemExit, 'ANDROID_HOME.*ANDROID_SDK_ROOT.*PATH'):
                adb_command()

    def test_baseline_requires_explicit_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / 'baseline.apk'
            apk.touch()
            with patch.dict(os.environ, {'PRIVATE_FLOW_BASELINE_APK': str(apk)}, clear=True):
                self.assertEqual(required_file('PRIVATE_FLOW_BASELINE_APK', 'the 0.2.1 APK'), apk)
            for value in ('', str(Path(directory) / 'missing.apk'), directory):
                with self.subTest(value=value), patch.dict(os.environ, {'PRIVATE_FLOW_BASELINE_APK': value}, clear=True):
                    with self.assertRaisesRegex(SystemExit, 'PRIVATE_FLOW_BASELINE_APK.*0.2.1 APK'):
                        required_file('PRIVATE_FLOW_BASELINE_APK', 'the 0.2.1 APK')

    def test_ini_discovery_and_explicit_selection(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'XDG_RUNTIME_DIR': directory}, clear=True):
            folder = Path(directory) / 'avd' / 'running'
            folder.mkdir(parents=True)
            with self.assertRaisesRegex(SystemExit, 'PRIVATE_FLOW_EMULATOR_INI'):
                emulator_grpc_ini()
            first = folder / 'pid1.ini'
            first.touch()
            self.assertEqual(emulator_grpc_ini(), first)
            (folder / 'pid2.ini').touch()
            with self.assertRaisesRegex(SystemExit, 'exactly one emulator'):
                emulator_grpc_ini()
            with patch.dict(os.environ, {'PRIVATE_FLOW_EMULATOR_INI': str(first)}):
                self.assertEqual(emulator_grpc_ini(), first)


if __name__ == '__main__':
    unittest.main()
