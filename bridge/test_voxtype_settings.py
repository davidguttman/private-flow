import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import tomllib
import types
import unittest
from unittest.mock import patch
import urllib.request
import wave
from server import BridgeServer
from voxtype_settings import default_config_path,read_settings,apply_text_settings,SettingsError

BASE=(Path(__file__).parent/'testdata'/'voxtype.toml').read_text()
class VoxtypeSettingsTests(unittest.TestCase):
    def test_default_follows_xdg(self):
        with patch.dict(os.environ,{'XDG_CONFIG_HOME':'/fixture/config'}):
            self.assertEqual(default_config_path(),Path('/fixture/config/voxtype/config.toml'))

    def test_explicit_replacements_use_case_insensitive_word_boundaries(self):
        options={'text':{'replacements':{'vox type':'voxtype','rust':'Rust'}}}
        self.assertEqual(apply_text_settings('VOX TYPE uses rust, not rusty.',options),'voxtype uses Rust, not rusty.')

    def test_spoken_punctuation_matches_voxtype_examples(self):
        config={'text':{'spoken_punctuation':True,'replacements':{'voxtype':'Voxtype'}}}
        self.assertEqual(apply_text_settings('I use voxtype period',config),'I use Voxtype.')
        self.assertEqual(apply_text_settings('function open paren close paren',config),'function()')
        self.assertEqual(apply_text_settings('line one new line line two',config),'line one\nline two')

    def test_postprocessor_failure_and_empty_output_preserve_text(self):
        for command in ['exit 1',"printf ''"]:
            self.assertEqual(apply_text_settings('unchanged',{'output':{'post_process':{'command':command}}}),'unchanged')

    def test_rejects_cloud_backend_without_invoking_it(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'config.toml'
            for source in ['engine="soniox"','[whisper]\nmode="remote"','[whisper]\nbackend="remote"']:
                path.write_text(source)
                with self.assertRaises(SettingsError):read_settings(path)

    def test_default_http_uses_current_host_config_and_daemon_text_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)/'config';path=home/'voxtype'/'config.toml';path.parent.mkdir(parents=True)
            source=BASE.replace('language = "auto"','language = "en"')+'''\n[text.replacements]\n"vox type" = "voxtype"\n"gonna" = "going to"\n[output.post_process]\ncommand = "tr '[:lower:]' '[:upper:]'"\n'''
            path.write_text(source)
            with patch.dict(os.environ,{'XDG_CONFIG_HOME':str(home)}),contextlib.redirect_stdout(io.StringIO()):
                server=BridgeServer(('127.0.0.1',0),str(Path(temp)/'devices'))
            self.assertEqual(Path(server.config),path)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            snapshots=[];real_run=subprocess.run
            def fake_voxtype(command,**kwargs):
                if command[0]==server.voxtype:
                    snapshot=Path(command[command.index('--config')+1]);snapshots.append(snapshot)
                    self.assertNotEqual(snapshot,path)
                    self.assertEqual(snapshot.read_text(),path.read_text())
                    self.assertEqual(snapshot.stat().st_mode & 0o777,0o600)
                    self.assertEqual(tomllib.loads(snapshot.read_text())['whisper']['language'],'en')
                    return types.SimpleNamespace(returncode=0,stdout='Loading audio file: fixture.wav\nProcessing 3200 samples...\n\nI use vox type and gonna test...\n')
                return real_run(command,**kwargs)
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                req=urllib.request.Request(base+'/pair',data=json.dumps({'code':server.pair_code}).encode())
                with urllib.request.urlopen(req) as response:token=json.load(response)['token']
                audio=io.BytesIO()
                with wave.open(audio,'wb') as w:
                    w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes(b'\0'*6400)
                def request():
                    req=urllib.request.Request(base+'/transcribe',data=audio.getvalue(),headers={'Content-Type':'audio/wav','Authorization':'Bearer '+token})
                    with urllib.request.urlopen(req) as response:return json.load(response)['text']
                with patch('subprocess.run',side_effect=fake_voxtype):
                    self.assertEqual(request(),'I USE VOXTYPE AND GOING TO TEST')
                    # Same live server; editing normal config affects next request.
                    path.write_text(source.replace('"voxtype"','"desktop edit"'))
                    self.assertEqual(request(),'I USE DESKTOP EDIT AND GOING TO TEST')
                self.assertTrue(all(not p.exists() for p in snapshots),'Private snapshots retained after request')
            finally:server.shutdown();server.server_close();worker.join()

if __name__=='__main__':unittest.main()
