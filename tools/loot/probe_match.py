"""Masked template match of drop sprites over the ground band of one frame; prints the best hits per template.
usage: probe_match.py FRAME FEET TEMPLATE_DIR..."""
import sys, glob, os
import cv2, numpy as np
f = cv2.imread(sys.argv[1]); feet = int(sys.argv[2])
y0, y1 = feet - 55, feet + 8
band = f[y0:y1]
for d in sys.argv[3:]:
    for p in sorted(glob.glob(os.path.join(d, "*.png"))):
        im = cv2.imread(p, cv2.IMREAD_UNCHANGED)
        t, m = np.ascontiguousarray(im[..., :3]), (im[..., 3] > 200).astype(np.uint8)
        r = cv2.matchTemplate(band, t, cv2.TM_CCOEFF_NORMED, mask=m); r[~np.isfinite(r)] = -1
        hits = []
        for _ in range(4):
            _, s, _, loc = cv2.minMaxLoc(r)
            if s < 0.6: break
            hits.append((round(s, 2), loc[0], y0 + loc[1]))
            r[max(0, loc[1]-10):loc[1]+10, max(0, loc[0]-15):loc[0]+15] = -1
        print(f"{os.path.basename(p):22s} {im.shape[1]}x{im.shape[0]} {hits}")
