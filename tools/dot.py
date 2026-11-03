import sys, cv2, numpy as np
img = cv2.imread(sys.argv[1]); s = 1.875; X0 = 439
# minimap map-area box in 768-space, read off the screenshot: x 67..184, y 72..177
x0, y0, x1, y1 = 60, 66, 192, 182
mm = img[round(y0*s):round(y1*s), X0+round(x0*s):X0+round(x1*s)]
cv2.imwrite(sys.argv[2], cv2.resize(mm, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST))
hsv = cv2.cvtColor(mm, cv2.COLOR_BGR2HSV)
for name, lo, hi in [('yellow', (20, 150, 180), (35, 255, 255)), ('red', (0, 170, 150), (8, 255, 255)), ('green', (45, 150, 150), (75, 255, 255))]:
    m = cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
    n, _, st, ce = cv2.connectedComponentsWithStats(m)
    blobs = [(int(ce[i][0]), int(ce[i][1]), int(st[i][2]), int(st[i][3]), int(st[i][4])) for i in range(1, n) if st[i][4] >= 6]
    print(name, 'blobs (cx,cy,w,h,area) in full-res minimap px:', sorted(blobs, key=lambda b: -b[4])[:8])
