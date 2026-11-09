"""Other characters' name tags (players, and mobs once hit): a row of light glyphs on a darkened box."""
import cv2
import numpy as np

from .hud import ui_mask


def text_mask(frame) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    return ((hsv[:, :, 2] > 180) & (hsv[:, :, 1] < 50)).astype(np.uint8)


def find_tags(frame, rows=None) -> list:
    """(x, y, w, h) of name tags. Needs >= 4 separate glyphs (a pale mob body is one solid shape).
    `rows` (y0, y1): only look in that band (cheaper; boxes are still in frame coordinates)."""
    if rows is not None:
        y0, y1 = max(0, int(rows[0])), min(frame.shape[0], int(rows[1]))
        return [(x, y + y0, w, h) for x, y, w, h in _find_tags(frame[y0:y1], ui_mask(frame.shape)[y0:y1])]
    return _find_tags(frame, ui_mask(frame.shape))


def _find_tags(frame, world) -> list:
    text = text_mask(frame) & world
    line = cv2.dilate(text, np.ones((3, 7), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(line)
    v = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[:, :, 2].astype(np.float32)
    tags = []
    for i in range(1, n):
        x, y, w, h, _ = (int(c) for c in st[i])
        if not (7 <= h <= 16 and 20 <= w <= 150):
            continue
        sub = text[y:y + h, x:x + w]
        if not 0.12 <= sub.mean() <= 0.6:
            continue
        _, _, g_st, _ = cv2.connectedComponentsWithStats(sub)
        if len([g for g in g_st[1:] if g[4] >= 4 and g[3] <= 13 and g[2] <= 12]) < 4:
            continue
        box = v[y:y + h, x:x + w][sub == 0]
        around = np.concatenate([v[max(0, y - 6):max(0, y - 2), x:x + w].ravel(), v[y + h + 2:y + h + 6, x:x + w].ravel()])
        if box.size and around.size and box.mean() < around.mean() - 15:
            tags.append((x - 3, y - 3, w + 6, h + 6))
    return tags


def tag_body(tag, above=130, pad=18) -> tuple:
    """Area owned by the character standing on a tag. Tall, so a dead player's floating ghost is covered too."""
    x, y, w, h = tag[:4]
    c = x + w / 2
    half = max(w / 2, 25) + pad
    return (int(c - half), y - above, int(2 * half), above + h)
