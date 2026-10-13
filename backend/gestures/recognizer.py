"""Landmark-geometry gesture classifier for AIRCONTROL.

Every static pose is decided from MediaPipe hand landmarks, normalised by hand
size (wrist -> middle-finger MCP), so results do not depend on how far the hand
is from the camera.  Each finger is classified as Extended (E), Folded (F) or
ambiguous (None).  A pose only matches when every finger it depends on is
*clearly* E or F; otherwise the result is UNKNOWN - a gesture is never forced.

Evaluation order (highest priority first, matches the project spec):
    PINCH -> SCREENSHOT (ILY) -> THUMBS_UP -> THUMBS_DOWN -> FIST
          -> OPEN_PALM -> PEACE -> INDEX_POINT
Motion gestures (swipe / vertical scroll) are evaluated last and only
override a weak pose, never PINCH / SCREENSHOT / THUMBS_*.

recognize() returns (gesture, confidence, motion) where gesture is one of:
    NONE (no hand), UNKNOWN (hand but no confident pose), PINCH, SCREENSHOT,
    THUMBS_UP, THUMBS_DOWN, FIST, OPEN_PALM, PEACE, INDEX_POINT, VERTICAL_SCROLL
Swipes are returned as motion["swipe_event"] ("SWIPE_LEFT"/"SWIPE_RIGHT"/None)
because they are momentary, not a held pose.
"""
import math
import time
from collections import deque

DEFAULT_PARAMS = {
    # confidence below this => UNKNOWN
    "min_confidence": 0.85,
    # pinch: thumb-tip/index-tip distance divided by palm size
    "pinch_threshold": 0.30,
    "pinch_release": 0.42,           # hysteresis: once pinching, stay until above this
    # finger state: d(tip,wrist) / d(pip,wrist)
    "finger_extended_ratio": 1.20,
    "finger_folded_ratio": 1.00,
    "finger_ext_span": 0.10,
    "finger_fold_span": 0.30,
    # thumb state: d(thumb_tip, pinky_mcp) / palm size
    "thumb_extended_ratio": 0.90,
    "thumb_folded_ratio": 0.72,
    "thumb_ext_span": 0.30,
    "thumb_fold_span": 0.25,
    "thumb_open_min": 0.60,          # open palm needs thumb at least this open
    "thumb_vertical_min": 0.60,      # thumbs up/down: cos(angle to vertical)
    # motion
    "swipe_min_distance": 0.28,      # fraction of frame width inside the window
    "swipe_window_ms": 280,
    "swipe_cooldown_ms": 700,
    "swipe_dominance": 2.0,
    "index_swipe_factor": 1.4,       # swiping with a bare index must be bigger
    "scroll_min_speed": 0.55,        # frame heights per second
    "scroll_dominance": 1.5,
    "scroll_hold_ms": 250,
    "scroll_window_ms": 200,
}

FINGERS = {"index": (5, 6, 8), "middle": (9, 10, 12), "ring": (13, 14, 16), "pinky": (17, 18, 20)}
SWIPE_POSES = {"OPEN_PALM", "INDEX_POINT", "UNKNOWN"}


def _clip(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def _conf(margin):
    """Map a 0..1 evidence margin to a 0.78..1.0 confidence."""
    return 0.78 + 0.22 * _clip(margin)


class GestureRecognizer:
    def __init__(self, params=None, aspect=1.0):
        self.p = dict(DEFAULT_PARAMS)
        if params:
            self.configure(params)
        self.aspect = float(aspect) if aspect else 1.0
        self.debug = {}
        self.reset()

    # ------------------------------------------------------------------ setup
    def configure(self, params):
        for k, v in (params or {}).items():
            if k in DEFAULT_PARAMS:
                self.p[k] = v

    def reset(self):
        self._pinching = False
        self._palm = deque()
        self._tip = deque()
        self._prev_tip = None
        self._prev_t = None
        self._vx = 0.0
        self._vy = 0.0
        self._scroll_until = 0.0
        self._scroll_v = 0.0
        self._last_swipe = -1e9
        self._index_since = None      # when the raw pose became INDEX_POINT (continuous)

    # ----------------------------------------------------------- geometry util
    def _pt(self, pts, i):
        return (pts[i][0] * self.aspect, pts[i][1])

    @staticmethod
    def _d(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _finger_state(self, pts, name):
        _, pip_i, tip_i = FINGERS[name]
        wrist = self._pt(pts, 0)
        d_tip = self._d(self._pt(pts, tip_i), wrist)
        d_pip = max(self._d(self._pt(pts, pip_i), wrist), 1e-6)
        r = d_tip / d_pip
        p = self.p
        if r >= p["finger_extended_ratio"]:
            return "E", _clip((r - p["finger_extended_ratio"]) / p["finger_ext_span"]), r
        if r <= p["finger_folded_ratio"]:
            return "F", _clip((p["finger_folded_ratio"] - r) / p["finger_fold_span"]), r
        return None, 0.0, r

    def _thumb(self, pts, palm):
        """Return (ratio, state, margin) for the thumb."""
        r = self._d(self._pt(pts, 4), self._pt(pts, 17)) / palm
        p = self.p
        if r >= p["thumb_extended_ratio"]:
            return r, "E", _clip((r - p["thumb_extended_ratio"]) / p["thumb_ext_span"])
        if r <= p["thumb_folded_ratio"]:
            return r, "F", _clip((p["thumb_folded_ratio"] - r) / p["thumb_fold_span"])
        return r, None, 0.0

    def _thumb_not_extended_margin(self, r):
        p = self.p
        if r >= p["thumb_extended_ratio"]:
            return None
        return _clip((p["thumb_extended_ratio"] - r) / p["thumb_ext_span"])

    def _thumb_vertical(self, pts):
        """Return cos of angle between thumb direction (MCP->tip) and vertical, signed: + up, - down."""
        a, b = self._pt(pts, 2), self._pt(pts, 4)
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy)
        if n < 1e-6:
            return 0.0
        return -dy / n  # image y grows downward

    # -------------------------------------------------------- static pose logic
    def classify_pose(self, points):
        """Static pose only (no motion). Returns (gesture, confidence)."""
        if len(points) != 21:
            return "NONE", 0.0
        p = self.p
        palm = max(self._d(self._pt(points, 0), self._pt(points, 9)), 1e-6)
        fs = {n: self._finger_state(points, n) for n in FINGERS}
        st = {n: v[0] for n, v in fs.items()}
        mg = {n: v[1] for n, v in fs.items()}
        t_ratio, t_state, t_margin = self._thumb(points, palm)
        pinch_d = self._d(self._pt(points, 4), self._pt(points, 8)) / palm
        self.debug = {"palm": palm, "pinch_d": pinch_d, "thumb_ratio": t_ratio,
                      "finger_ratios": {n: round(v[2], 3) for n, v in fs.items()},
                      "states": dict(st, thumb=t_state)}

        # 1) PINCH - beats every static pose. Index must not be curled into a fist.
        limit = p["pinch_release"] if self._pinching else p["pinch_threshold"]
        index_open = fs["index"][2] > p["finger_folded_ratio"]
        if pinch_d <= limit and index_open:
            self._pinching = True
            margin = _clip((limit - pinch_d) / (limit * 0.6))
            return "PINCH", _conf(margin)
        self._pinching = False

        def need(*names):
            return all(st[n] == "E" for n in names[0]) and all(st[n] == "F" for n in names[1])

        up = self._thumb_vertical(points)

        # 2) SCREENSHOT = ILY: thumb + index + pinky extended, middle + ring folded
        if t_state == "E" and st["index"] == "E" and st["pinky"] == "E" \
                and st["middle"] == "F" and st["ring"] == "F":
            m = min(t_margin, mg["index"], mg["pinky"], mg["middle"], mg["ring"])
            return "SCREENSHOT", _conf(m)

        # 3/4) THUMBS_UP / THUMBS_DOWN: thumb extended + all four fingers folded + direction
        if t_state == "E" and all(st[n] == "F" for n in FINGERS):
            base = min(t_margin, *(mg[n] for n in FINGERS))
            vmin = p["thumb_vertical_min"]
            if up >= vmin:
                return "THUMBS_UP", _conf(min(base, _clip((up - vmin) / 0.3)))
            if -up >= vmin:
                return "THUMBS_DOWN", _conf(min(base, _clip((-up - vmin) / 0.3)))
            return "UNKNOWN", 0.4  # thumb out sideways with fist: not a defined gesture

        # 6) FIST: four fingers folded, thumb not extended
        if all(st[n] == "F" for n in FINGERS):
            tm = self._thumb_not_extended_margin(t_ratio)
            if tm is not None:
                return "FIST", _conf(min(tm, *(mg[n] for n in FINGERS)))

        # 7) OPEN_PALM: four fingers extended, thumb at least partly open
        if all(st[n] == "E" for n in FINGERS) and t_ratio >= p["thumb_open_min"]:
            tm = _clip((t_ratio - p["thumb_open_min"]) / 0.3)
            return "OPEN_PALM", _conf(min(tm, *(mg[n] for n in FINGERS)))

        # 8) PEACE: index + middle extended, ring + pinky folded (thumb free)
        if st["index"] == "E" and st["middle"] == "E" and st["ring"] == "F" and st["pinky"] == "F":
            return "PEACE", _conf(min(mg.values()))

        # 9) INDEX_POINT: only the index extended (thumb free, pinch already excluded)
        if st["index"] == "E" and st["middle"] == "F" and st["ring"] == "F" and st["pinky"] == "F":
            return "INDEX_POINT", _conf(min(mg.values()))

        return "UNKNOWN", 0.3

    # ------------------------------------------------------------------ public
    def recognize(self, points, now=None):
        now = time.perf_counter() if now is None else now
        motion = {"scroll": 0.0, "swipe": 0.0, "swipe_event": None}
        if len(points) != 21:
            self.reset()
            return "NONE", 0.0, motion

        gesture, conf = self.classify_pose(points)
        if gesture not in ("UNKNOWN", "NONE") and conf < self.p["min_confidence"]:
            gesture = "UNKNOWN"          # insufficient confidence - do not force a gesture

        self._update_motion(points, now)
        motion["swipe"], motion["scroll"] = self._vx, self._vy

        # scroll (index pose only, and only once the pose has been held for a moment:
        # extending the finger itself moves the fingertip and must not look like a scroll)
        if gesture == "INDEX_POINT":
            if self._index_since is None:
                self._index_since = now
        else:
            self._index_since = None
        scroll_v = self._scroll_check(now, gesture)
        if gesture == "INDEX_POINT" and scroll_v is not None:
            gesture, conf = "VERTICAL_SCROLL", max(conf, 0.9)
            motion["scroll"] = scroll_v

        # swipe (lowest priority; only from open palm / index / unknown)
        if gesture in SWIPE_POSES or gesture == "VERTICAL_SCROLL":
            if gesture != "VERTICAL_SCROLL":
                motion["swipe_event"] = self._swipe_check(now, gesture)
        return gesture, conf, motion

    # ------------------------------------------------------------------ motion
    def _update_motion(self, points, now):
        tip = (points[8][0], points[8][1])
        palm = (points[9][0], points[9][1])
        if self._prev_tip is not None and self._prev_t is not None:
            dt = max(now - self._prev_t, 1e-3)
            ivx, ivy = (tip[0] - self._prev_tip[0]) / dt, (tip[1] - self._prev_tip[1]) / dt
            self._vx = 0.5 * ivx + 0.5 * self._vx
            self._vy = 0.5 * ivy + 0.5 * self._vy
        self._prev_tip, self._prev_t = tip, now
        self._palm.append((now, palm[0], palm[1]))
        self._tip.append((now, tip[0], tip[1]))
        keep = max(self.p["swipe_window_ms"], self.p["scroll_window_ms"]) / 1000.0 + 0.05
        for q in (self._palm, self._tip):
            while q and now - q[0][0] > keep:
                q.popleft()

    def _window(self, q, now, ms):
        pts = [s for s in q if now - s[0] <= ms / 1000.0]
        return pts

    def _scroll_check(self, now, pose):
        # use the palm (middle MCP), not the fingertip: it does not move when fingers change shape
        w = self._window(self._palm, now, self.p["scroll_window_ms"])
        held = self._index_since is not None and now - self._index_since >= 0.15
        if pose == "INDEX_POINT" and held and len(w) >= 3 and w[-1][0] - w[0][0] >= 0.06:
            dt = w[-1][0] - w[0][0]
            vx, vy = (w[-1][1] - w[0][1]) / dt, (w[-1][2] - w[0][2]) / dt
            if abs(vy) >= self.p["scroll_min_speed"] and abs(vy) >= self.p["scroll_dominance"] * abs(vx):
                self._scroll_until = now + self.p["scroll_hold_ms"] / 1000.0
                self._scroll_v = vy
        if pose == "INDEX_POINT" and now < self._scroll_until:
            return self._scroll_v
        return None

    def _swipe_check(self, now, pose):
        if now - self._last_swipe < self.p["swipe_cooldown_ms"] / 1000.0:
            return None
        w = self._window(self._palm, now, self.p["swipe_window_ms"])
        if len(w) < 3:
            return None
        dx, dy = w[-1][1] - w[0][1], w[-1][2] - w[0][2]
        need = self.p["swipe_min_distance"] * (self.p["index_swipe_factor"] if pose == "INDEX_POINT" else 1.0)
        if abs(dx) >= need and abs(dx) >= self.p["swipe_dominance"] * abs(dy):
            self._last_swipe = now
            self._palm.clear()
            self._scroll_until = 0.0
            return "SWIPE_RIGHT" if dx > 0 else "SWIPE_LEFT"
        return None
