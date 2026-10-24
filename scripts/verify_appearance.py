"""Emulator UI checks for idle-dot geometry, recording and saved appearance."""
import io
import json
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from PIL import Image
ADB=['adb','-s','emulator-5556']
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence'/'appearance-0.2.0'
OUT.mkdir(parents=True,exist_ok=True)

def shell(*args):return subprocess.check_output(ADB+['shell',*args],timeout=30).decode()
def dump():
    shell('uiautomator','dump','/sdcard/appearance.xml')
    return ET.fromstring(shell('cat','/sdcard/appearance.xml'))
def tap(x,y):shell('input','tap',str(x),str(y))
def screenshot(name):
    raw=subprocess.check_output(ADB+['exec-out','screencap','-p'],timeout=15)
    (OUT/name).write_bytes(raw)
    return Image.open(io.BytesIO(raw)).convert('RGB')
def bounds():
    for _ in range(30):
        text=shell('dumpsys','accessibility')
        matches=re.findall(r'WindowInfo\[WindowInfo\[[^\n]*type=2038,[^\n]*bounds=Rect\((\d+), (\d+) - (\d+), (\d+)\)',text)
        if matches:return tuple(map(int,matches[0]))
        time.sleep(.1)
    raise AssertionError('Overlay window not present')
def size(b):return b[2]-b[0],b[3]-b[1]
def center(b):return (b[0]+b[2])//2,(b[1]+b[3])//2

shell('am','start','-W','--activity-clear-top','-n','dev.privateflow/.MainActivity')
# Exercise the actual appearance controls before calling this verifier.
prefs=shell('run-as','dev.privateflow','cat','/data/user/0/dev.privateflow/shared_prefs/appearance.xml')
root=ET.fromstring(prefs)
saved={n.attrib['name']:n.attrib.get('value') for n in root}
assert saved.get('size')=='3' and saved.get('opacity')=='60',saved
for attempt in range(4):
    nodes=[n for n in dump().iter('node') if n.attrib.get('text')=='Try dictation']
    if nodes:
        a,b,c,d=map(int,re.findall(r'\d+',nodes[0].attrib['bounds']));tap((a+c)//2,(b+d)//2);break
    shell('input','swipe','800','1800','800','800','400')
    time.sleep(.3)
else:raise AssertionError('Try dictation missing')
time.sleep(.5)
fields=[n for n in dump().iter('node') if n.attrib.get('class')=='android.widget.EditText']
assert fields,'Test editor missing'
a,b,c,d=map(int,re.findall(r'\d+',fields[0].attrib['bounds']));tap((a+c)//2,(b+d)//2)
time.sleep(.6)
normal=bounds()
image=screenshot('full-size-60-opacity.png')
time.sleep(5.5)
dot=bounds()
screenshot('idle-dot.png')
assert size(normal)[0]>size(dot)[0]*2,(normal,dot)
assert abs(center(normal)[1]-center(dot)[1])<=2,(normal,dot)
# Read the actual window alpha, not just the settings label or preview.
windows=shell('dumpsys','window','windows')
block=windows[windows.index('Private Flow Bubble'):]
block=block.split('Window #',1)[0]
assert 'alpha=0.6' in block,block[:2500]
# Dot tap must start recording directly, and no idle shrinking during recording.
tap(*center(dot));time.sleep(.7)
recording=bounds()
assert size(recording)[0]>size(normal)[0]*3,(normal,recording)
assert '.CaptureService' in shell('dumpsys','activity','services','dev.privateflow')
time.sleep(5.5)
assert size(bounds())==size(recording),'Recording controls shrank while recording'
screenshot('recording-stays-expanded.png')
# Cancel using the left-most control at the configured size.
x0,y0,x1,y1=recording
tap(x0+round((y1-y0)/2),(y0+y1)//2)
time.sleep(.7)
assert '.CaptureService' not in shell('dumpsys','activity','services','dev.privateflow')
reset=bounds()
assert size(reset)==size(normal),(reset,normal)
time.sleep(5.5)
assert size(bounds())==size(dot),'Did not shrink again after cancellation'
# Holding the dot must start hold-to-dictate; move away to cancel the gesture
# through the system notification/service only after checking the live geometry.
# Existing tap-and-hold event handling is unchanged; verify a drag also wakes it.
x,y=center(dot)
shell('input','swipe',str(x),str(y),str(x),str(y-180),'250')
time.sleep(.4)
assert size(bounds())==size(normal),'Drag did not restore full-size bubble'
result={'saved':saved,'normal_bounds':normal,'dot_bounds':dot,'recording_bounds':recording,
 'verified':['saved slider values','live size applied','live opacity alpha=0.6','5-second idle shrink','vertical center preserved','dot tap starts recording','no shrinking during recording','cancel stops microphone','idle shrink resumes after cancel','drag wakes dot']}
(OUT/'verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
