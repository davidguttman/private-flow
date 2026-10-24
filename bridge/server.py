#!/usr/bin/env python3
"""Private, bounded Voxtype HTTP bridge. Bind only loopback or a Tailscale IP."""
import argparse
import hashlib
import hmac
import io
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_AUDIO = 16000 * 2 * 300 + 4096

class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, state_dir, config):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.state_dir, 0o700)
        self.tokens_file = self.state_dir / 'devices.json'
        self.tokens = json.loads(self.tokens_file.read_text()) if self.tokens_file.exists() else []
        self.pair_code = secrets.token_hex(4)
        self.pair_until = time.monotonic() + 900
        pairing_file = self.state_dir / 'pairing-code'
        pairing_file.write_text(self.pair_code)
        os.chmod(pairing_file, 0o600)
        self.pair_attempts = {}
        self.lock = threading.Lock()
        self.transcription = threading.BoundedSemaphore(1)
        self.config = config
        self.voxtype = shutil.which('voxtype')
        if not self.voxtype:
            raise RuntimeError('voxtype is not installed')
        super().__init__(address, Handler)
        print(f'Private Flow bridge: http://{address[0]}:{self.server_port}', flush=True)
        print(f'Pairing code (15 minutes, single use): {self.pair_code}', flush=True)

    def authorize(self, token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            return any(hmac.compare_digest(digest, value) for value in self.tokens)

class Handler(BaseHTTPRequestHandler):
    server: BridgeServer
    def log_message(self, *args):
        pass  # Do not log transcripts, credentials, or request paths.

    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def reply(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def authorized(self):
        value = self.headers.get('Authorization', '')
        return value.startswith('Bearer ') and self.server.authorize(value[7:])

    def body(self, limit):
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('Chunked uploads are not supported')
        try:
            size = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            raise ValueError('Content-Length is required')
        if not 0 < size <= limit:
            raise ValueError('Invalid or oversized upload')
        result = self.rfile.read(size)
        if len(result) != size:
            raise ValueError('Incomplete upload')
        return result

    def do_GET(self):
        if self.path != '/health':
            return self.reply(404, {'error': 'Not found'})
        if not self.authorized():
            return self.reply(401, {'error': 'Pair this device first'})
        self.reply(200, {'status': 'ok', 'engine': 'voxtype', 'processing': 'local'})

    def do_POST(self):
        if self.path == '/pair':
            return self.pair()
        if self.path != '/transcribe':
            return self.reply(404, {'error': 'Not found'})
        if not self.authorized():
            return self.reply(401, {'error': 'Pair this device first'})
        if not self.server.transcription.acquire(blocking=False):
            return self.reply(429, {'error': 'Computer is transcribing another recording. Try again.'})
        try:
            if self.headers.get('Content-Type', '').split(';')[0] != 'audio/wav':
                raise ValueError('Send a WAV recording')
            data = self.body(MAX_AUDIO)
            with wave.open(io.BytesIO(data), 'rb') as audio:
                if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype()) != (1,2,16000,'NONE'):
                    raise ValueError('Audio must be 16-kHz mono PCM16 WAV')
                frames = audio.getnframes()
                if not 1600 <= frames <= 16000 * 300:
                    raise ValueError('Recording must be between 0.1 seconds and 5 minutes')
                if len(audio.readframes(frames)) != frames * 2:
                    raise ValueError('Truncated WAV recording')
            # Private RAM-backed scratch file, removed on every exit path.
            scratch = '/dev/shm' if Path('/dev/shm').is_dir() else None
            with tempfile.TemporaryDirectory(prefix='private-flow-', dir=scratch) as directory:
                source = Path(directory) / 'audio.wav'
                source.write_bytes(data)
                os.chmod(source, 0o600)
                cmd = [self.server.voxtype, '-q', '--config', self.server.config, 'transcribe', str(source)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=110)
                if result.returncode:
                    return self.reply(503, {'error': 'Local Voxtype transcription failed'})
                preamble, separator, text = result.stdout.partition('\n\n')
                if not separator or not preamble.startswith('Loading audio file:') or 'Processing ' not in preamble:
                    return self.reply(503, {'error': 'Unexpected Voxtype output format'})
                text = text.strip()
                self.reply(200, {'text': text})
        except (ValueError, wave.Error, EOFError) as error:
            self.reply(400, {'error': str(error)})
        except subprocess.TimeoutExpired:
            self.reply(504, {'error': 'Local transcription timed out'})
        except (OSError, TimeoutError):
            self.reply(503, {'error': 'Local transcription could not finish'})
        finally:
            self.server.transcription.release()

    def pair(self):
        try:
            payload = json.loads(self.body(1024))
            code = payload.get('code', '')
            if not isinstance(code, str):
                raise ValueError('Invalid pairing code')
        except (ValueError, TypeError, AttributeError):
            return self.reply(400, {'error': 'Invalid pairing request'})
        with self.server.lock:
            now = time.monotonic()
            address = self.client_address[0]
            history = [t for t in self.server.pair_attempts.get(address, []) if t > now - 60]
            history.append(now)
            self.server.pair_attempts[address] = history
            if len(history) > 5:
                return self.reply(429, {'error': 'Too many pairing attempts. Wait one minute.'})
            if now > self.server.pair_until or not self.server.pair_code or not hmac.compare_digest(code, self.server.pair_code):
                return self.reply(403, {'error': 'Pairing code expired or incorrect'})
            token = secrets.token_urlsafe(32)
            self.server.tokens.append(hashlib.sha256(token.encode()).hexdigest())
            temporary = self.server.tokens_file.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.server.tokens))
            os.chmod(temporary, 0o600)
            temporary.replace(self.server.tokens_file)
            self.server.pair_code = ''
            (self.server.state_dir / 'pairing-code').unlink(missing_ok=True)
        self.reply(200, {'token': token})

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--state-dir', default=str(Path.home()/'.local/share/private-flow'))
    parser.add_argument('--config', default=str(Path(__file__).with_name('voxtype.toml')))
    args = parser.parse_args()
    address = ipaddress.ip_address(args.bind)
    if not address.is_loopback and address not in ipaddress.ip_network('100.64.0.0/10'):
        parser.error('Bind only to loopback or your encrypted Tailscale IP')
    BridgeServer((args.bind, args.port), args.state_dir, args.config).serve_forever()
