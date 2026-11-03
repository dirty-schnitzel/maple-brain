import ctypes, sys
from ctypes import wintypes
import mss, mss.tools
u = ctypes.windll.user32; u.SetProcessDPIAware()
h = u.FindWindowW(None, 'MapleStory')
print('hwnd', h, 'minimized', bool(u.IsIconic(h)), 'visible', bool(u.IsWindowVisible(h)))
r = wintypes.RECT(); u.GetClientRect(h, ctypes.byref(r))
p = wintypes.POINT(0, 0); u.ClientToScreen(h, ctypes.byref(p))
print('client', r.right, 'x', r.bottom, 'at', p.x, p.y)
if r.right and r.bottom and not u.IsIconic(h):
    with mss.mss() as s:
        img = s.grab({'left': p.x, 'top': p.y, 'width': r.right, 'height': r.bottom})
        mss.tools.to_png(img.rgb, img.size, output=sys.argv[1])
        print('saved', sys.argv[1])
