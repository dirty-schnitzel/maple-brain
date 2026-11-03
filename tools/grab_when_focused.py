import ctypes, sys, time
from ctypes import wintypes
import mss, mss.tools
u = ctypes.windll.user32; u.SetProcessDPIAware()
h = u.FindWindowW(None, 'MapleStory')
deadline = time.time() + 180
while u.GetForegroundWindow() != h:
    if time.time() > deadline:
        sys.exit('timed out: MapleStory never became the foreground window')
    time.sleep(0.25)
time.sleep(1.5)  # let fullscreen finish redrawing
if u.GetForegroundWindow() != h:
    sys.exit('focus left the game before capture; nothing saved')
r = wintypes.RECT(); u.GetClientRect(h, ctypes.byref(r))
p = wintypes.POINT(0, 0); u.ClientToScreen(h, ctypes.byref(p))
with mss.MSS() as s:
    img = s.grab({'left': p.x, 'top': p.y, 'width': r.right, 'height': r.bottom})
    mss.tools.to_png(img.rgb, img.size, output=sys.argv[1])
print('saved', r.right, 'x', r.bottom)
