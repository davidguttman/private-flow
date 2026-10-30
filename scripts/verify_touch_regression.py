"""Real Android input checks; delayed loopback fixture isolates transcription UI."""
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from PIL import Image
from verification_support import adb_command

ADB=adb_command()
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence'/'touch-0.2.1'
OUT.mkdir(parents=True,exist_ok=True)
requests=[]
received=threading.Event()
expected='Private transcription finished.'
class Fixture(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        assert self.path=='/transcribe'
        self.rfile.read(int(self.headers['Content-Length']))
        requests.append(self.path);received.set()
        time.sleep(8)
        body=json.dumps({'text':expected}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers()
        self.wfile.write(body)
server=ThreadingHTTPServer(('127.0.0.1',8768),Fixture)
threading.Thread(target=server.serve_forever,daemon=True).start()

def adb(*args):return subprocess.check_output(ADB+list(args),timeout=30)
def shell(*args):return adb('shell',*args).decode()
def dump():
    shell('uiautomator','dump','/sdcard/touch-test.xml')
    return ET.fromstring(shell('cat','/sdcard/touch-test.xml'))
def rect(n):return tuple(map(int,re.findall(r'\d+',n.attrib['bounds'])))
def center(b):return (b[0]+b[2])//2,(b[1]+b[3])//2
def tap(x,y):shell('input','tap',str(x),str(y))
def window():
    for _ in range(40):
        text=shell('dumpsys','window','windows')
        if 'Private Flow Bubble' in text:
            block=text[text.index('Private Flow Bubble'):].split('Window #',1)[0]
            match=re.search(r'Frames:.*? frame=\[(\d+),(\d+)\]\[(\d+),(\d+)\]',block)
            if match and 'mDrawState=HAS_DRAWN' in block and 'Surface: shown=true' in block:return tuple(map(int,match.groups())),block
        time.sleep(.1)
    raise AssertionError('Bubble not found')
def capture(name):
    raw=adb('exec-out','screencap','-p');(OUT/name).write_bytes(raw)
    return Image.open(io.BytesIO(raw)).convert('RGB')
def ink(image,b):
    background=image.getpixel((b[0]+1,b[1]+1))
    return sum(max(abs(c[i]-background[i]) for i in range(3))>=3 for c in image.crop(b).getdata())
def open_editor(opacity,size):
    shell('am','start','-W','--activity-clear-top','-n','dev.privateflow/.MainActivity')
    tree=dump()
    seeks={n.attrib.get('content-desc'):n for n in tree.iter('node') if n.attrib.get('class')=='android.widget.SeekBar'}
    a,b,c,d=rect(seeks['Bubble size']);tap(round(a+42+(c-a-84)*size/3),(b+d)//2)
    a,b,c,d=rect(seeks['Bubble opacity']);tap(round(a+42+(c-a-84)*(opacity-20)/80),(b+d)//2)
    for _ in range(4):
        nodes=[n for n in dump().iter('node') if n.attrib.get('text')=='Try dictation']
        if nodes:tap(*center(rect(nodes[0])));break
        shell('input','swipe','800','1800','800','800','400');time.sleep(.2)
    else:raise AssertionError('Try dictation missing')
    fields=[n for n in dump().iter('node') if n.attrib.get('class')=='android.widget.EditText']
    assert fields
    tap(*center(rect(fields[0])))
    bounds,block=window()
    alpha=re.search(r'(?<![A-Za-z])alpha=([0-9.]+)',block)
    assert alpha is None or float(alpha.group(1))==1.0,block
    return bounds

def recording():return '.CaptureService' in shell('dumpsys','activity','services','dev.privateflow')
def cancel():
    b,_=window();height=b[3]-b[1]
    tap(b[0]+round(height/2),(b[1]+b[3])//2);time.sleep(.6)
    assert not recording(),'Cancel did not stop capture'

try:
    adb('reverse','tcp:8768','tcp:8768')
    shell('settings','delete','secure','enabled_accessibility_services')
    shell('settings','put','secure','enabled_accessibility_services','dev.privateflow/.FlowAccessibilityService')
    results=[]
    for opacity,size in [(20,0),(40,1),(60,2),(80,3),(100,1)]:
        bounds=open_editor(opacity,size)
        assert bounds[2]-bounds[0]>=126 and bounds[3]-bounds[1]>=126,'Touch target smaller than 48 dp'
        full=capture(f'{opacity}-full.png')
        tap(*center(bounds));time.sleep(.6)
        assert recording(),f'Normal bubble tap failed at {opacity}%'
        cancel()
        time.sleep(5.4)
        dot,block=window()
        assert dot==bounds,'Idle input window moved/shrank'
        small=capture(f'{opacity}-dot.png')
        assert ink(small,dot)<ink(full,bounds)/3,'Artwork did not shrink to a dot'
        # Deliberately miss the tiny artwork but hit its accessible touch box.
        tap(dot[0]+21,(dot[1]+dot[3])//2);time.sleep(.6)
        assert recording(),f'Dot hit target failed at {opacity}%'
        cancel()
        assert not requests,'Cancelled recordings unexpectedly uploaded'
        results.append({'opacity':opacity,'size_index':size,'stable_touch_bounds':bounds,'normal_tap':True,'dot_edge_tap':True})
        print('Verified touch at',opacity,'percent, size',size,flush=True)
    # Finish one real microphone recording against the delayed local fixture.
    bounds=open_editor(100,2)
    tap(*center(bounds));time.sleep(.8)
    rec,_=window();capture('recording.png')
    x0,y0,x1,y1=rec;done=(x1-(y1-y0)//2,(y0+y1)//2)
    tap(*done)
    assert received.wait(3),'Upload never started'
    time.sleep(.2)
    progress=capture('transcribing.png')
    # The cream Done button must be gone, not merely disabled.
    cream=(252,253,226)
    assert sum(c==cream for c in progress.crop(rec).getdata())==0,'Done button still visible during transcription'
    assert 'Transcribing on your computer' in shell('dumpsys','notification','--noredact'),'Notification still says listening'
    for _ in range(3):tap(*done)
    time.sleep(5.2)
    assert window()[0]==rec,'Transcription indicator shrank while waiting'
    assert len(requests)==1,'Repeated Done presses duplicated transcription'
    time.sleep(3)
    fields=[n.attrib.get('text') for n in dump().iter('node') if n.attrib.get('class')=='android.widget.EditText']
    assert fields==[expected+' '],fields
    capture('inserted.png')
    result={'touch_matrix':results,'processing':['Done removed immediately','spinner and label shown (screenshot)','notification updated','no idle shrinking while waiting','repeated Done-area taps submit only once','result inserted exactly once'],'backend':'delayed loopback fixture; real microphone capture; no inference performed'}
    (OUT/'verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)
finally:
    server.shutdown();server.server_close()
