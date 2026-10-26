"""Portable prerequisites shared by the local Android verification scripts."""
import os
from pathlib import Path
import shutil


def adb_command():
    """Use the selected SDK's adb, or adb on PATH; preserve the fixture serial."""
    executable = 'adb.exe' if os.name == 'nt' else 'adb'
    for variable in ('ANDROID_HOME', 'ANDROID_SDK_ROOT'):
        sdk = os.environ.get(variable)
        if sdk:
            candidate = Path(sdk).expanduser() / 'platform-tools' / executable
            if candidate.is_file() and os.access(candidate, os.X_OK):
                adb = str(candidate)
                break
    else:
        adb = shutil.which('adb')
    if not adb:
        raise SystemExit('Android adb is required: set ANDROID_HOME or ANDROID_SDK_ROOT to an SDK with platform-tools, or put adb on PATH')
    return [adb, '-s', os.environ.get('ANDROID_SERIAL', 'emulator-5556')]


def required_file(variable, description):
    value = os.environ.get(variable)
    path = Path(value).expanduser() if value else None
    if path is None or not path.is_file():
        raise SystemExit(f'Set {variable} to {description} (an existing file)')
    return path


def emulator_grpc_ini():
    """Find a single local emulator token file; require selection if ambiguous."""
    if os.environ.get('PRIVATE_FLOW_EMULATOR_INI'):
        return required_file('PRIVATE_FLOW_EMULATOR_INI', 'the target emulator running pid*.ini file')
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if not runtime and hasattr(os, 'getuid'):
        runtime = f'/run/user/{os.getuid()}'
    matches = sorted((Path(runtime) / 'avd' / 'running').glob('pid*.ini')) if runtime else []
    if len(matches) != 1:
        raise SystemExit('Set PRIVATE_FLOW_EMULATOR_INI to the target emulator running pid*.ini file; automatic discovery requires exactly one emulator')
    return matches[0]
