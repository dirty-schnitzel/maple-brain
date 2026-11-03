"""Find round minimap markers (player = yellow, others = red) in a normalized 1366x768 frame."""
import sys, cv2, numpy as np
f = cv2.imread(sys.argv[1]); x0, y0, x1, y1 = (int(v) for v in sys.argv[2:6])
mm = f[y0:y1, x0:x1]; hsv = cv2.cvtColor(mm, cv2.COLOR_BGR2HSV)
cv2.imwrite(sys.argv[6], cv2.resize(mm, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST))
for name, ranges in [('yellow', [((20, 150, 180), (35, 255, 255))]),
                     ('red', [((0, 150, 140), (8, 255, 255)), ((170, 150, 140), (180, 255, 255))])]:
    m = sum(cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8)) for lo, hi in ranges).clip(0, 255).astype(np.uint8)
    n, _, st, ce = cv2.connectedComponentsWithStats(m)
    all_ = [(int(ce[i][0]), int(ce[i][1]), int(st[i][2]), int(st[i][3]), int(st[i][4])) for i in range(1, n) if st[i][4] >= 4]
    dots = [b for b in all_ if b[2] <= 8 and b[3] <= 8 and abs(b[2] - b[3]) <= 2]
    print(f'{name}: {len(all_)} blobs, {len(dots)} round dots <=8px: {dots}')
    if len(all_) > len(dots): print('   rejected:', [b for b in all_ if b not in dots])
