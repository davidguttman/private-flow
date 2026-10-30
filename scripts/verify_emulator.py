"""Real UI + microphone injection + real Voxtype end-to-end verification."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import wave
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bridge'))
from verification_support import adb_command, required_file, emulator_grpc_ini
from server import BridgeServer, Handler
ADB=adb_command()
TEST_WAV=required_file('PRIVATE_FLOW_TEST_WAV', 'a spoken 16-kHz mono WAV fixture')
EMULATOR_INI=emulator_grpc_ini()
if os.environ.get('PRIVATE_FLOW_EMULATOR_PROTO_DIR'):
    sys.path.insert(0,str(Path(os.environ['PRIVATE_FLOW_EMULATOR_PROTO_DIR']).expanduser()))
try:
    import grpc
    import emulator_controller_pb2 as pb
    import emulator_controller_pb2_grpc as rpc
    from google.protobuf.empty_pb2 import Empty
except ImportError as error:
    raise SystemExit('Install grpcio and protobuf, and set PRIVATE_FLOW_EMULATOR_PROTO_DIR to the generated Android emulator Python gRPC modules (or put them on PYTHONPATH)') from error
ROOT=Path(__file__).resolve().parents[1]
(ROOT/'evidence').mkdir(parents=True,exist_ok=True)

def adb(*args):
    return subprocess.check_output(ADB+list(args),stderr=subprocess.STDOUT)

def shell(*args):return adb('shell',*args).decode()

def dump():
    shell('uiautomator','dump','/sdcard/private-flow-window.xml')
    return ET.fromstring(shell('cat','/sdcard/private-flow-window.xml'))

def tap(node):
    import re
    a,b,c,d=map(int,re.findall(r'\d+',node.attrib['bounds']))
    shell('input','tap',str((a+c)//2),str((b+d)//2))

def click_text(text):
    nodes=[n for n in dump().iter('node') if n.attrib.get('text')==text]
    assert nodes,f'Cannot find {text}'
    tap(nodes[0])

def screenshot(name):
    (ROOT/'evidence'/name).write_bytes(adb('exec-out','screencap','-p'))

results=[]
original_reply=Handler.reply
def capture_reply(self,status,payload):
    if self.path=='/transcribe':results.append((status,payload))
    return original_reply(self,status,payload)
Handler.reply=capture_reply

with tempfile.TemporaryDirectory() as state:
    with contextlib.redirect_stdout(io.StringIO()):
        server=BridgeServer(('127.0.0.1',8768),state,str(ROOT/'bridge/testdata/voxtype.toml'))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    adb('reverse','tcp:8768','tcp:8768')
    shell('am','start','--activity-clear-top','-n','dev.privateflow/.MainActivity')
    time.sleep(.5)
    fields=[n for n in dump().iter('node') if n.attrib.get('class')=='android.widget.EditText']
    tap(fields[0]);shell('input','keycombination','113','29');shell('input','text','http://127.0.0.1:8768')
    shell('input','keyevent','4')
    fields=[n for n in dump().iter('node') if n.attrib.get('class')=='android.widget.EditText']
    tap(fields[1]);shell('input','text',server.pair_code);shell('input','keyevent','4')
    click_text('Pair with computer');time.sleep(.7)
    assert 'Paired: ✓' in ET.tostring(dump(),encoding='unicode'),'Pairing UI failed'
    if '--messages' in sys.argv:
        shell('am','start','-a','android.intent.action.SENDTO','-d','smsto:5551234568')
        time.sleep(1)
        shell('input','tap','530','2250')
        time.sleep(.5)
        shell('input','keycombination','113','29');shell('input','keyevent','67')
    else:
        click_text('Try dictation');time.sleep(.3)
    if '--messages' not in sys.argv:
        field=[n for n in dump().iter('node') if n.attrib.get('class')=='android.widget.EditText'][0]
        tap(field);time.sleep(.5)
    screenshot('bubble-idle.png')
    assert 'type=2038' in shell('dumpsys','accessibility'),'Floating bubble missing'
    shell('input','tap','990','1404');time.sleep(.7)
    screenshot('bubble-recording.png')
    logs=shell('dumpsys','activity','services','dev.privateflow')
    assert 'CaptureService' in logs,'Recording foreground service did not start'
    client=rpc.EmulatorControllerStub(grpc.insecure_channel(os.environ.get('PRIVATE_FLOW_EMULATOR_GRPC','localhost:8556')))
    ini=EMULATOR_INI.read_text()
    grpc_token=next(line.partition('=')[2].strip() for line in ini.splitlines() if line.startswith('grpc.token'))
    metadata=(('authorization','Bearer '+grpc_token),)
    client.setMicrophoneState(pb.MicrophoneState(realAudioEnabled=False),metadata=metadata)
    with wave.open(str(TEST_WAV),'rb') as w:pcm=w.readframes(w.getnframes())
    fmt=pb.AudioFormat(samplingRate=16000,channels=pb.AudioFormat.Mono,format=pb.AudioFormat.AUD_FMT_S16)
    def packets():
        for offset in range(0,len(pcm),3200):
            yield pb.AudioPacket(format=fmt,audio=pcm[offset:offset+3200])
    client.injectAudio(packets(),timeout=30,metadata=metadata)
    time.sleep(.5)
    # Right-most expanded control is the checkmark.
    shell('input','tap','990','1404')
    # UiAutomator temporarily suppresses accessibility services. Do not attach
    # it during the live dictation: wait for the actual server response first.
    for _ in range(120):
        time.sleep(.25)
        if results:break
    assert results, 'Transcription request did not complete'
    print('Bridge response:',results)
    time.sleep(1)
    screenshot('messages-result.png' if '--messages' in sys.argv else 'dictation-result.png')
    assert results[0][0]==200,results
    # Some Compose fields are hidden from UiAutomator. Verify the real field
    # through a deliberate select-and-copy, clearing the clipboard first so
    # clipboard-fallback cannot masquerade as successful insertion.
    client.setClipboard(pb.ClipData(text='verification-empty'),metadata=metadata)
    time.sleep(.3)
    shell('input','keycombination','113','29');shell('input','keycombination','113','31')
    time.sleep(.5)
    actual=client.getClipboard(Empty(),metadata=metadata).text
    expected=results[0][1]['text'].rstrip(' ')+' '
    assert actual==expected,f'Transcript insertion changed content: {actual!r} != {expected!r}'
    client.setClipboard(pb.ClipData(text=''),metadata=metadata)
    shell('input','keyevent','123')
    print('Verified emulator'+(' (Google Messages, unsent draft)' if '--messages' in sys.argv else '')+': pairing UI → bubble → foreground microphone capture → injected speech → actual local Voxtype → editor insertion')
    server.shutdown();server.server_close()
