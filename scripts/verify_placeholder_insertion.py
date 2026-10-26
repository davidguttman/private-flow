"""Reproduce the old placeholder bug; verify native insertion without heuristics."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from verification_support import adb_command, required_file

BASELINE_APK=required_file('PRIVATE_FLOW_BASELINE_APK', 'the Private Flow 0.2.1 baseline APK')
ADB=adb_command()
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence'/'insertion-0.2.2';OUT.mkdir(parents=True,exist_ok=True)
transcript='Dictation.'
received=threading.Event()
class Backend(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        time.sleep(.3)
        data=json.dumps({'text':transcript}).encode()
        self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);received.set()
server=ThreadingHTTPServer(('127.0.0.1',8768),Backend)
threading.Thread(target=server.serve_forever,daemon=True).start()
def adb(*args):return subprocess.check_output(ADB+list(args),timeout=30)
def sh(*args):return adb('shell',*args).decode()
def tap(x,y):sh('input','tap',str(x),str(y))
def window():
    for _ in range(50):
        s=sh('dumpsys','window','windows')
        if 'Private Flow Bubble' in s:
            b=s[s.index('Private Flow Bubble'):].split('Window #',1)[0]
            m=re.search(r'Frames:.*? frame=\[(\d+),(\d+)\]\[(\d+),(\d+)\]',b)
            if m and 'Surface: shown=true' in b:return tuple(map(int,m.groups()))
        time.sleep(.1)
    raise AssertionError('Bubble missing')
def rebind():
    sh('am','start','-W','-n','dev.privateflow/.MainActivity')
    sh('settings','delete','secure','enabled_accessibility_services')
    sh('settings','put','secure','enabled_accessibility_services','dev.privateflow/.FlowAccessibilityService')
    time.sleep(.5)
def exercise(mode,initial='',start=None,end=None):
    received.clear()
    start=len(initial) if start is None else start;end=start if end is None else end
    sh('am','start','-W','--activity-clear-top','-n','dev.privateflow.test/dev.privateflow.fixtures.PlaceholderEditorActivity','--es','mode',mode,'--es','initial',"'"+initial.replace("'","'\\''")+"'",'--ei','start',str(start),'--ei','end',str(end))
    time.sleep(.8)
    b=window();tap((b[0]+b[2])//2,(b[1]+b[3])//2)
    time.sleep(.7)
    assert '.CaptureService' in sh('dumpsys','activity','services','dev.privateflow'),'Recording never started'
    b=window();tap(b[2]-(b[3]-b[1])//2,(b[1]+b[3])//2)
    assert received.wait(4),'No transcription request'
    time.sleep(.6)
    # Only observe after asynchronous insertion has completed.
    sh('uiautomator','dump','/sdcard/insertion.xml')
    tree=ET.fromstring(sh('cat','/sdcard/insertion.xml'))
    texts=[n.attrib.get('text','') for n in tree.iter('node') if n.attrib.get('class')=='android.widget.EditText']
    assert len(texts)==1,texts
    return texts[0]
try:
    adb('reverse','tcp:8768','tcp:8768')
    original_keyboard=sh('settings','get','secure','default_input_method')
    # Same lying accessibility node, same real input field and recording path.
    adb('install','-r','-d',str(BASELINE_APK));rebind()
    baseline=exercise('unmarked-no-hint')
    assert baseline==transcript+'Message',repr(baseline)
    print('Reproduced 0.2.1 placeholder append:',repr(baseline),flush=True)
    (OUT/'baseline.txt').write_text(baseline)
    adb('install','-r',str(ROOT/'app/build/outputs/apk/debug/app-debug.apk'));rebind()
    rows=[]
    cases=[('unmarked-no-hint','',0,0),('unmarked-with-hint','',0,0),('normal','',0,0),('normal','Message',7,7),('normal','Message',0,0),('normal','Before after',7,7),('normal','Before old after',7,10)]
    for mode,initial,start,end in cases:
        actual=exercise(mode,initial,start,end)
        expected=initial[:start]+transcript+initial[end:]
        assert actual==expected,(mode,initial,actual,expected)
        rows.append({'mode':mode,'initial':initial,'selection':[start,end],'actual':actual})
        print('Verified:',rows[-1],flush=True)
    assert sh('settings','get','secure','default_input_method')==original_keyboard,'Normal keyboard changed'
    logs=sh('logcat','-d','-s','PrivateFlow:D','*:S')
    assert logs.count('Insertion: native accessibility input connection')>=len(cases),'Not using the native editor connection'
    (OUT/'native-method.log').write_text(logs)
    (OUT/'result.png').write_bytes(adb('exec-out','screencap','-p'))
    (OUT/'verification.json').write_text(json.dumps({'baseline':baseline,'cases':rows,'normal_keyboard_unchanged':True,'native_connection_used':True,'backend':'loopback transcript fixture; real Android field editing and microphone capture'},indent=2))
finally:
    server.shutdown();server.server_close()
