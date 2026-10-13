"""Synthetic MediaPipe-style hand landmarks for unit tests.

Local frame: wrist at (0,0), middle-finger MCP at (0,1) (palm length = 1),
y up.  Fingers curl in the sagittal plane (as seen from the camera, a curled
finger's tip drops back toward the palm), which is what the 2D landmarks of a
real hand look like.
"""
import math

SCALE = 0.2          # palm length in normalised frame units
BASES = {"index": (-0.28, 0.96), "middle": (0.0, 1.0), "ring": (0.27, 0.95), "pinky": (0.52, 0.85)}
LENS = {"index": (0.38, 0.22, 0.20), "middle": (0.42, 0.25, 0.22), "ring": (0.40, 0.23, 0.20), "pinky": (0.30, 0.18, 0.17)}
SPLAY = {"index": -6, "middle": 0, "ring": 6, "pinky": 12}
IDS = {"index": 5, "middle": 9, "ring": 13, "pinky": 17}
THUMB_BASE = (-0.18, 0.22)
THUMB_TIPS = {
    "up": (-0.55, 1.20), "down": (-0.55, -0.76), "side": (-1.0, 0.65),
    "rest": (-0.85, 0.75), "fold": (0.10, 0.70), "wrap": (-0.05, 0.85), "sideways_fist": (-0.95, 0.30),
}


def _finger(name, curl, splay_extra=0.0):
    bx, by = BASES[name]
    ang = math.radians(SPLAY[name] + splay_extra)
    segs = LENS[name]
    angles = [math.radians(a * curl) for a in (90, 180, 250)]
    pts, (x, y) = [(bx, by)], (bx, by)
    for L, a in zip(segs, angles):
        run = L * math.cos(a)
        x += run * math.sin(ang)
        y += run * math.cos(ang)
        pts.append((x, y))
    return pts   # mcp, pip, dip, tip


def make_hand(curls=None, thumb="fold", cx=0.5, cy=0.75, pinch=False, splay=None):
    """curls: dict finger->0..1 (0 extended, 1 folded). thumb: key of THUMB_TIPS or (x,y)."""
    curls = dict({"index": 0, "middle": 0, "ring": 0, "pinky": 0}, **(curls or {}))
    splay = splay or {}
    local = {0: (0.0, 0.0)}
    tips = {}
    for n in IDS:
        f = _finger(n, curls[n], splay.get(n, 0.0))
        for k, p in enumerate(f):
            local[IDS[n] + k] = p
        tips[n] = f[3]
    tip = tips["index"] if pinch else (THUMB_TIPS[thumb] if isinstance(thumb, str) else thumb)
    bx, by = THUMB_BASE
    local[1] = (bx, by)
    local[2] = (bx + 0.43 * (tip[0] - bx), by + 0.43 * (tip[1] - by))
    local[3] = (bx + 0.72 * (tip[0] - bx), by + 0.72 * (tip[1] - by))
    local[4] = tip
    return [[cx + local[i][0] * SCALE, cy - local[i][1] * SCALE, 0.0] for i in range(21)]


POSES = {
    "INDEX_POINT": lambda **k: make_hand({"middle": 1, "ring": 1, "pinky": 1}, "fold", **k),
    "PINCH": lambda **k: make_hand({"index": 0.15, "middle": 0.6, "ring": 0.6, "pinky": 0.6}, pinch=True, **k),
    "FIST": lambda **k: make_hand({"index": 1, "middle": 1, "ring": 1, "pinky": 1}, "wrap", **k),
    "THUMBS_UP": lambda **k: make_hand({"index": 1, "middle": 1, "ring": 1, "pinky": 1}, "up", **k),
    "THUMBS_DOWN": lambda **k: make_hand({"index": 1, "middle": 1, "ring": 1, "pinky": 1}, "down", **k),
    "SCREENSHOT": lambda **k: make_hand({"middle": 1, "ring": 1}, "side", **k),
    "PEACE": lambda **k: make_hand({"ring": 1, "pinky": 1}, "fold", splay={"index": -8, "middle": 8}, **k),
    "OPEN_PALM": lambda **k: make_hand({}, "rest", **k),
}


def pose(name, **kw):
    return POSES[name](**kw)
