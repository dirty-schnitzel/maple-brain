import sys, cv2
f = cv2.imread(sys.argv[1]); x0, y0, x1, y1 = (int(v) for v in sys.argv[2:6])
cv2.imwrite(sys.argv[6], cv2.resize(f[y0:y1, x0:x1], None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC))
