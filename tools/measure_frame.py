import sys, cv2, numpy as np
img = cv2.imread(sys.argv[1]); H, W = img.shape[:2]
cols = np.where(img.max(axis=(0, 2)) > 12)[0]
x0, x1 = cols[0], cols[-1] + 1; w = x1 - x0
print(f'frame {W}x{H}; game area x={x0}..{x1} width={w} -> aspect {w/H:.4f} (16:9={16/9:.4f}); scale vs 768 tall = {H/768:.4f}; implied base width {w*768/H:.1f}')
game = img[:, x0:x1]
small = cv2.resize(game, (round(w * 768 / H), 768), interpolation=cv2.INTER_AREA)
cv2.imwrite(sys.argv[2], small)
cv2.imwrite(sys.argv[3], small[0:40, 0:300])
