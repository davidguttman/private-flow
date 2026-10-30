#!/usr/bin/env python3
"""Real microphone + editor regression; loopback text responses, no inference.

Requires installed current debug and androidTest APKs, permissions/accessibility,
normal keyboard, and saved connection http://127.0.0.1:8768 with a test token.
Only a disposable, already-running emulator is accepted. No baseline APK needed.
"""
import base64
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import subprocess
import threading
import time
import wave
import xml.etree.ElementTree as ET

from verification_support import adb_command

ROOT = Path(__file__).resolve().parents[1]
ADB = adb_command()
OUT = ROOT / 'evidence' / 'insertion-formatting'


def adb(*args):
    return subprocess.check_output(ADB + list(args), timeout=30)


def shell(*args):
    return adb('shell', *args).decode()


def tap(x, y):
    shell('input', 'tap', str(x), str(y))


def window():
    for _ in range(50):
        text = shell('dumpsys', 'window', 'windows')
        if 'Private Flow Bubble' in text:
            block = text[text.index('Private Flow Bubble'):].split('Window #', 1)[0]
            match = re.search(r'Frames:.*? frame=\[(\d+),(\d+)\]\[(\d+),(\d+)\]', block)
            if match and 'Surface: shown=true' in block:
                return tuple(map(int, match.groups()))
        time.sleep(.1)
    raise AssertionError('Bubble missing: check accessibility, overlay permission and keyboard')


def open_editor(initial='', start=None, end=None, mode='normal'):
    start = len(initial) if start is None else start
    end = start if end is None else end
    # Base64 avoids adb shell/newline quoting and XML whitespace normalization.
    encoded = base64.b64encode(initial.encode()).decode()
    shell('am', 'start', '-W', '--activity-clear-top', '-n',
          'dev.privateflow.test/dev.privateflow.fixtures.PlaceholderEditorActivity',
          '--es', 'mode', mode, '--es', 'initialBase64', encoded or "''",
          '--ei', 'start', str(start), '--ei', 'end', str(end))
    time.sleep(.8)
    window()


def observe():
    # UiAutomator may interrupt accessibility: never attach during recording.
    shell('uiautomator', 'dump', '/sdcard/formatting.xml')
    tree = ET.fromstring(shell('cat', '/sdcard/formatting.xml'))
    values = [n.attrib['text'] for n in tree.iter('node')
              if n.attrib.get('content-desc') == 'Editor observation']
    assert len(values) == 1, 'Install the current androidTest editor fixture APK'
    marker, encoded, start, end = values[0].split(':')
    assert marker == 'editor'
    return base64.b64decode(encoded).decode(), int(start), int(end)


class Fixture(BaseHTTPRequestHandler):
    transcript = ''
    received = threading.Event()
    errors = []
    requests = 0

    def log_message(self, *args):
        pass

    def do_POST(self):
        try:
            assert self.path == '/transcribe', self.path
            body = self.rfile.read(int(self.headers['Content-Length']))
            with wave.open(io.BytesIO(body), 'rb') as wav:
                assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16000)
                assert wav.getnframes() >= 1600, 'No real microphone capture'
            type(self).requests += 1
            payload = json.dumps({'text': self.transcript}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as error:
            self.errors.append(repr(error))
        finally:
            self.received.set()


def dictate(text):
    Fixture.transcript = text
    Fixture.received.clear()
    before = Fixture.requests
    x0, y0, x1, y1 = window()
    tap((x0+x1)//2, (y0+y1)//2)
    time.sleep(.8)
    assert '.CaptureService' in shell('dumpsys', 'activity', 'services', 'dev.privateflow'), 'Recording did not start'
    x0, y0, x1, y1 = window()
    tap(x1-(y1-y0)//2, (y0+y1)//2)
    assert Fixture.received.wait(5), 'No microphone upload received'
    assert not Fixture.errors, Fixture.errors
    assert Fixture.requests == before+1, 'Missing/duplicate upload'
    time.sleep(.8)  # commitText and confirmation are asynchronous


def run():
    if not ADB[-1].startswith('emulator-') or shell('getprop', 'ro.kernel.qemu').strip() != '1':
        raise SystemExit('Use a disposable emulator; refusing a physical device')
    OUT.mkdir(parents=True, exist_ok=True)
    original_keyboard = shell('settings', 'get', 'secure', 'default_input_method')
    server = ThreadingHTTPServer(('127.0.0.1', 8768), Fixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    rows = []

    def check(name, expected, cursor):
        actual = observe()
        assert actual == (expected, cursor, cursor), (name, actual, (expected, cursor, cursor))
        rows.append({'case': name, 'actual': actual})
        print('Verified', name, repr(actual), flush=True)

    try:
        adb('reverse', 'tcp:8768', 'tcp:8768')
        # Explicit outputs rather than duplicating production formatting logic.
        cases = [
            ('empty', '', 0, 0, 'Hello.', 'Hello. ', 'normal'),
            ('unmarked-no-hint', '', 0, 0, 'Alice', 'Alice ', 'unmarked-no-hint'),
            ('unmarked-with-hint', '', 0, 0, 'Alice', 'Alice ', 'unmarked-with-hint'),
            ('literal-Message', 'Message', 7, 7, 'Alice', 'alice ', 'normal'),
            ('field-start', 'tail', 0, 0, 'Alice', 'Alice ', 'normal'),
            ('mid-sentence', 'Before after', 7, 7, 'Hello WORLD.', 'hello WORLD. ', 'normal'),
            ('no-leading-smart-space', 'Before', 6, 6, 'Hello', 'hello ', 'normal'),
            ('proper-name', 'We met ', 7, 7, 'Alice Smith', 'alice Smith ', 'normal'),
            ('acronym', 'We use ', 7, 7, 'NASA', 'nASA ', 'normal'),
            ('I-no-exception', 'Then ', 5, 5, 'I agree.', 'i agree. ', 'normal'),
            ('sentence-period', 'Done. ', 6, 6, 'Alice', 'Alice ', 'normal'),
            ('sentence-bang', 'Done! ', 6, 6, 'Alice', 'Alice ', 'normal'),
            ('sentence-question', 'Done? ', 6, 6, 'Alice', 'Alice ', 'normal'),
            ('paragraph', 'Earlier\n  ', 10, 10, 'Alice', 'Alice ', 'normal'),
            ('replacement', 'Before old after', 7, 10, 'Alice.', 'alice. ', 'normal'),
            ('existing-space', 'Before  after', 7, 7, 'Alice', 'alice ', 'normal'),
            ('existing-punctuation', 'Before ,after', 7, 7, 'Alice.', 'alice. ', 'normal'),
            ('trailing-space-normalized', 'Before ', 7, 7, 'Alice   ', 'alice ', 'normal'),
            ('punctuation-preserved', 'Before ', 7, 7, '“Hello!”', '“hello!” ', 'normal'),
            ('context-unavailable', 'Before ', 7, 7, 'Alice', 'Alice ', 'no-context'),
            ('short-context', 'x' + ' '*300, 301, 301, 'Alice', 'Alice ', 'normal'),
        ]
        for name, initial, start, end, transcript, insertion, mode in cases:
            open_editor(initial, start, end, mode)
            dictate(transcript)
            expected = initial[:start] + insertion + initial[end:]
            cursor = start + len(insertion)
            check(name, expected, cursor)
            # Real Android keyboard event path; no fixture mutation or runtime hook.
            shell('input', 'text', 'typed')
            check(name+'-typing', expected[:cursor]+'typed'+expected[cursor:], cursor+5)

        open_editor()
        dictate('Hello')
        check('sequential-first', 'Hello ', 6)
        dictate('World.')
        check('sequential-second', 'Hello world. ', 13)
        dictate('Again')
        check('sequential-sentence-start', 'Hello world. Again ', 19)
        shell('input', 'text', 'typed')
        check('sequential-typing', 'Hello world. Again typed', 24)

        open_editor('Before old after', 7, 10)
        dictate(' \n\t')
        assert observe() == ('Before old after', 7, 10), 'Blank transcript changed text/selection'
        rows.append({'case': 'blank-no-op', 'actual': ['Before old after', 7, 10]})
        assert shell('settings', 'get', 'secure', 'default_input_method') == original_keyboard, 'Normal keyboard changed'
        (OUT / 'result.png').write_bytes(adb('exec-out', 'screencap', '-p'))
        (OUT / 'verification.json').write_text(json.dumps({
            'cases': rows, 'requests': Fixture.requests, 'normal_keyboard_unchanged': True,
            'backend': 'loopback text fixture; real Android microphone WAV capture and editor insertion',
        }, indent=2))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    run()
