"""Boxes are (x, y, w, h) tuples in the normalized 1366x768 frame."""
Box = tuple


def cx(b: Box) -> float:
    return b[0] + b[2] / 2


def bottom(b: Box) -> float:
    return b[1] + b[3]


def overlaps(a: Box, b: Box, pad: float = 6) -> bool:
    return not (a[0] + a[2] + pad < b[0] or b[0] + b[2] + pad < a[0] or
                a[1] + a[3] + pad < b[1] or b[1] + b[3] + pad < a[1])
