import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import wave
from server import BridgeServer, MAX_AUDIO

class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()):
            cls.server = BridgeServer(('127.0.0.1', 0), cls.temp.name, str(Path(__file__).parent/'testdata'/'voxtype.toml'))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.token = None

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.temp.cleanup()

    def request(self, path, data=None, token=None, mime='application/json'):
        headers={'Content-Type':mime}
        if token: headers['Authorization']='Bearer '+token
        req=urllib.request.Request(self.url+path,data=data,headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=120) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as response:
            with response:
                return response.code,json.load(response)

    def test_protocol_and_actual_voxtype(self):
        self.assertEqual(self.request('/health')[0],401)
        self.assertEqual(self.request('/transcribe',b'no audio')[0],401)
        self.assertEqual(self.request('/pair',b'{"code":"wrong"}')[0],403)
        code=self.server.pair_code
        status,payload=self.request('/pair',json.dumps({'code':code}).encode())
        self.assertEqual(status,200); token=payload['token']
        self.assertNotIn(token,self.server.tokens_file.read_text())
        self.assertEqual(self.request('/pair',json.dumps({'code':code}).encode())[0],403)
        self.assertEqual(self.request('/health',token=token)[0],200)
        self.assertEqual(self.request('/transcribe',b'not wav',token,'audio/wav')[0],400)
        bad=io.BytesIO()
        with wave.open(bad,'wb') as w:
            w.setparams((2,2,44100,0,'NONE','not compressed'));w.writeframes(b'\0'*10000)
        self.assertEqual(self.request('/transcribe',bad.getvalue(),token,'audio/wav')[0],400)
        fixture=Path(os.environ.get('PRIVATE_FLOW_TEST_WAV','/nonexistent'))
        if not fixture.exists():
            print('Protocol verified; real transcription skipped (set PRIVATE_FLOW_TEST_WAV)')
            return
        status,payload=self.request('/transcribe',fixture.read_bytes(),token,'audio/wav')
        self.assertEqual(status,200,payload)
        self.assertIn(os.environ.get('PRIVATE_FLOW_EXPECTED_TEXT','Okay, do that'),payload['text'])
        self.assertNotIn('Loading audio',payload['text'])
        self.assertNotIn('Processing ',payload['text'])
        self.server.transcription.acquire()
        try:self.assertEqual(self.request('/transcribe',fixture.read_bytes(),token,'audio/wav')[0],429)
        finally:self.server.transcription.release()
        print('Verified: auth, single-use pairing, hashed credentials, WAV validation, real local transcription, clean text, concurrency limit')

if __name__=='__main__':unittest.main()
