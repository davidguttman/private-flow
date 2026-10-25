import contextlib
import io
import json
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
import urllib.request
import wave
from server import BridgeServer, clean_pause_ellipses

RAW="Synthetic robots... ...assemble widgets. And... ...they're still... ...testing them."
CLEAN="Synthetic robots assemble widgets. And they're still testing them."

class PauseCleanupTests(unittest.TestCase):
    def test_synthetic_example(self):
        self.assertEqual(clean_pause_ellipses(RAW),CLEAN)

    def test_unicode_and_adjacent_words(self):
        self.assertEqual(clean_pause_ellipses('Well… …this...works.'),'Well this works.')

    def test_ordinary_punctuation_is_unchanged(self):
        text='Dr. Chen paid $3.14 at example.com using v0.2.2. Really? Yes!'
        self.assertEqual(clean_pause_ellipses(text),text)

    def test_line_breaks_and_unrelated_spacing_are_preserved(self):
        self.assertEqual(clean_pause_ellipses('First...\n\n  Second … thought.'),'First\n\n  Second thought.')
        self.assertEqual(clean_pause_ellipses('Indented:\n  one\n  two'),'Indented:\n  one\n  two')

    def test_does_not_leave_spaces_before_punctuation(self):
        self.assertEqual(clean_pause_ellipses('Wait..., really...?'),'Wait, really?')
        self.assertEqual(clean_pause_ellipses('(...hello...)'),'(hello)')

    def test_does_not_rewrite_speech(self):
        self.assertEqual(clean_pause_ellipses('Um, I, I think... yes.'),'Um, I, I think yes.')

    def test_authenticated_http_response_is_cleaned(self):
        with tempfile.TemporaryDirectory() as state:
            with contextlib.redirect_stdout(io.StringIO()):
                server=BridgeServer(('127.0.0.1',0),state,str(Path(__file__).with_name('voxtype.toml')))
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                req=urllib.request.Request(base+'/pair',data=json.dumps({'code':server.pair_code}).encode(),headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req) as r:token=json.load(r)['token']
                audio=io.BytesIO()
                with wave.open(audio,'wb') as w:
                    w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes(b'\0'*6400)
                output='Loading audio file: fixture.wav\nAudio format: 16000 Hz\nProcessing 3200 samples...\n\n'+RAW+'\n'
                with patch('server.subprocess.run',return_value=types.SimpleNamespace(returncode=0,stdout=output)):
                    req=urllib.request.Request(base+'/transcribe',data=audio.getvalue(),headers={'Authorization':'Bearer '+token,'Content-Type':'audio/wav'})
                    with urllib.request.urlopen(req) as response:self.assertEqual(json.load(response),{'text':CLEAN})
            finally:server.shutdown();server.server_close();worker.join()

if __name__=='__main__':unittest.main()
