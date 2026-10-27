#!/usr/bin/env python3
"""Real drag/rebind/process-restart regression; disposable emulator only.

Requires debug app + editor-fixture APKs installed and overlay permission.
Does not pair, record audio, install APKs, or change appearance/connection prefs.
Restores the original position keys and accessibility service list on exit.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET

from verification_support import adb_command

PACKAGE = 'dev.privateflow'
SERVICE = PACKAGE + '/.FlowAccessibilityService'
PREFS = 'shared_prefs/appearance.xml'
KEYS = {'bubble_right', 'bubble_y_fraction'}
OUT = Path(__file__).resolve().parents[1] / 'evidence' / 'bubble-position'


def main():
    command = adb_command()
    if not command[2].startswith('emulator-'):
        raise SystemExit('Refusing non-emulator ANDROID_SERIAL; use a disposable test emulator')

    def adb(*args):
        return subprocess.check_output(command + list(args), timeout=30)

    def shell(*args):
        return adb('shell', *args).decode().strip()

    if shell('getprop', 'ro.kernel.qemu') != '1':
        raise SystemExit('Refusing device without emulator property ro.kernel.qemu=1')

    def prefs():
        result = subprocess.run(command + ['shell', 'run-as', PACKAGE, 'cat', PREFS],
                                capture_output=True, timeout=30)
        if result.returncode:
            if b'No such file' in result.stderr + result.stdout:
                return ET.Element('map')
            raise RuntimeError(result.stderr.decode() + result.stdout.decode())
        return ET.fromstring(result.stdout)

    def write_position(entries):
        # Call only while app/service is stopped. Preserve every unrelated key.
        root = prefs()
        for node in list(root):
            if node.attrib.get('name') in KEYS:
                root.remove(node)
        root.extend(entries)
        payload = ET.tostring(root, encoding='unicode')
        script = 'mkdir -p shared_prefs; printf %s ' + shlex.quote(payload) + ' > ' + PREFS
        shell('run-as', PACKAGE, 'sh', '-c', shlex.quote(script))

    original_services = shell('settings', 'get', 'secure', 'enabled_accessibility_services')
    original_enabled = shell('settings', 'get', 'secure', 'accessibility_enabled')
    original_position = [n for n in prefs() if n.attrib.get('name') in KEYS]
    others = [s for s in original_services.split(':') if s and s != 'null' and s not in
              (SERVICE, PACKAGE + '/dev.privateflow.FlowAccessibilityService')]
    OUT.mkdir(parents=True, exist_ok=True)

    def service(enabled):
        entries = others + ([SERVICE] if enabled else [])
        shell('settings', 'put', 'secure', 'enabled_accessibility_services',
              shlex.quote(':'.join(entries)))
        time.sleep(.6)

    def editor():
        shell('am', 'start', '-W', '--activity-clear-top', '-n',
              PACKAGE + '.test/dev.privateflow.fixtures.PlaceholderEditorActivity')
        time.sleep(.6)

    def window():
        for _ in range(50):
            text = shell('dumpsys', 'window', 'windows')
            if 'Private Flow Bubble' in text:
                block = text[text.index('Private Flow Bubble'):].split('Window #', 1)[0]
                match = re.search(r'Frames:.*? frame=\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]', block)
                if match and 'Surface: shown=true' in block:
                    return tuple(map(int, match.groups()))
            time.sleep(.1)
        raise AssertionError('Bubble not found; check fixture APK, overlay and accessibility permission')

    def same(expected):
        actual = window()
        assert all(abs(a-b) <= 2 for a, b in zip(expected, actual)), (expected, actual)
        return actual

    def process_restart():
        service(False)
        shell('am', 'force-stop', PACKAGE)
        shell('am', 'start', '-W', '-n', PACKAGE + '/.MainActivity')
        service(True)
        editor()

    rows = []
    try:
        service(False)
        shell('am', 'force-stop', PACKAGE)
        write_position([])
        shell('am', 'start', '-W', '-n', PACKAGE + '/.MainActivity')
        service(True)
        editor()
        initial = window()
        size = re.findall(r'(\d+)x(\d+)', shell('wm', 'size'))[-1]
        width, height = map(int, size)
        assert initial[0] > width / 2, ('First-run side', initial)
        assert abs(initial[1] - height / 2) < height * .1, ('First-run Y', initial)
        assert not [n for n in prefs() if n.attrib.get('name') in KEYS], 'Showing bubble saved position'
        for right, fraction in [(False, .28), (True, .40)]:
            b = window()
            x, y = (b[0]+b[2])//2, (b[1]+b[3])//2
            dest_x = width - 80 if right else 80
            shell('input', 'swipe', str(x), str(y), str(dest_x), str(round(height*fraction)), '250')
            time.sleep(.4)
            dragged = window()
            assert (dragged[0] > width/2) == right, dragged
            assert abs(dragged[1]-initial[1]) > 50, ('Drag did not move', dragged)
            assert '.CaptureService' not in shell('dumpsys', 'activity', 'services', PACKAGE), 'Drag started recording'
            entries = {n.attrib['name']: n.attrib.get('value') for n in prefs() if n.attrib.get('name') in KEYS}
            assert entries.get('bubble_right') == str(right).lower(), ('Drag preference wiring', entries)
            assert 'bubble_y_fraction' in entries, entries
            service(False)
            service(True)
            editor()
            same(dragged)
            process_restart()
            same(dragged)
            time.sleep(5.5)
            same(dragged)  # Idle shrinking must not move the touch window.
            (OUT / ('right.png' if right else 'left.png')).write_bytes(adb('exec-out', 'screencap', '-p'))
            rows.append({'right': right, 'bounds': dragged, 'service_rebind': True, 'process_restart': True})
        # Seed a formerly off-screen position to verify the service uses the clamp.
        service(False)
        shell('am', 'force-stop', PACKAGE)
        write_position([ET.Element('boolean', name='bubble_right', value='false'),
                        ET.Element('float', name='bubble_y_fraction', value='-10.0')])
        shell('am', 'start', '-W', '-n', PACKAGE + '/.MainActivity')
        service(True)
        editor()
        clamped = window()
        assert 0 <= clamped[1] < height*.2 and clamped[3] <= height, clamped
        result = {'first_run': initial, 'drags': rows, 'clamped': clamped}
        (OUT / 'verification.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
    finally:
        service(False)
        shell('am', 'force-stop', PACKAGE)
        write_position(original_position)
        for key, value in [('enabled_accessibility_services', original_services),
                           ('accessibility_enabled', original_enabled)]:
            if value == 'null':
                shell('settings', 'delete', 'secure', key)
            else:
                shell('settings', 'put', 'secure', key, shlex.quote(value))


if __name__ == '__main__':
    main()
