"""Robust, pinch-free Sketch gesture recognition.

The Sketch recognizer is intentionally separate from Desktop/Browser gestures.
It uses palm-normalised finger geometry, adaptive landmark smoothing and a short
majority vote.  Ambiguous frames become OTHER instead of being forced into an
action.  Pose commands (PALM_LEFT, thumbs, fist) require more stability than
continuous drawing/erase poses.
"""
from collections import deque
import math
import numpy as np

FINGER_CHAINS = ((5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16), (17, 18, 19, 20))


def _angle(a, b, c):
    u = np.asarray(a, dtype=np.float32)[:2] - np.asarray(b, dtype=np.float32)[:2]
    v = np.asarray(c, dtype=np.float32)[:2] - np.asarray(b, dtype=np.float32)[:2]
    nu = max(float(np.linalg.norm(u)), 1e-6)
    nv = max(float(np.linalg.norm(v)), 1e-6)
    return float(np.degrees(np.arccos(np.clip(float(np.dot(u, v) / (nu * nv)), -1.0, 1.0))))


def _clip(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, float(v)))


def _distance(a, b, aspect=1.0):
    d = (np.asarray(a, dtype=np.float32)[:2] - np.asarray(b, dtype=np.float32)[:2]).copy()
    d[0] *= float(aspect or 1.0)
    return float(np.linalg.norm(d))


def _finger_evidence(hand, chain, aspect=1.0):
    mcp, pip, dip, tip = chain
    pip_angle = _angle(hand[mcp], hand[pip], hand[dip])
    dip_angle = _angle(hand[pip], hand[dip], hand[tip])
    wrist = hand[0, :2]
    tip_wrist = _distance(hand[tip], wrist, aspect)
    pip_wrist = max(_distance(hand[pip], wrist, aspect), 1e-6)
    reach = tip_wrist / pip_wrist

    angle_score = min((pip_angle - 128.0) / 27.0, (dip_angle - 122.0) / 28.0)
    reach_score = (reach - 1.04) / 0.18
    score = 0.62 * angle_score + 0.38 * reach_score
    if score >= 0.48:
        state = "E"
    elif score <= 0.12:
        state = "F"
    else:
        state = None
    return state, max(0.0, min(1.0, score)), pip_angle, dip_angle, reach


def finger_states(hand, aspect=1.0):
    hand = np.asarray(hand, dtype=np.float32)
    if hand.shape != (21, 3):
        return np.zeros(4, dtype=bool)
    return np.asarray([_finger_evidence(hand, c, aspect)[0] == "E" for c in FINGER_CHAINS], dtype=bool)


def _thumb_direction(hand, aspect=1.0):
    a, b = hand[2, :2], hand[4, :2]
    v = (b - a).astype(np.float32)
    v[0] *= float(aspect or 1.0)
    n = max(float(np.linalg.norm(v)), 1e-6)
    return float(v[0] / n), float(-v[1] / n)


def _palm_direction(hand, aspect=1.0):
    """Average wrist->fingertip direction; less sensitive to one bad landmark."""
    wrist = hand[0, :2]
    vecs = []
    for idx in (8, 12, 16, 20):
        v = (hand[idx, :2] - wrist).astype(np.float32)
        v[0] *= float(aspect or 1.0)
        n = float(np.linalg.norm(v))
        if n > 1e-5:
            vecs.append(v / n)
    if not vecs:
        return 0.0, 0.0
    v = np.mean(vecs, axis=0)
    n = max(float(np.linalg.norm(v)), 1e-6)
    return float(v[0] / n), float(-v[1] / n)


def _confidence(values):
    values = [float(v) for v in values if v is not None]
    return _clip(np.mean(values) if values else 0.0)


def _finger_geometry(hand, chain, aspect=1.0):
    """Return palm-normalised geometry useful for diagnostics/tuning.

    These measurements are deliberately separate from the existing classifier
    thresholds in V14. They let us observe extension and bend quality without
    changing the established 126-test gesture behavior.
    """
    mcp, pip, dip, tip = chain
    wrist = hand[0]
    palm = max(_distance(wrist, hand[9], aspect), 1e-6)

    mcp_reach = _distance(hand[mcp], wrist, aspect) / palm
    tip_reach = _distance(hand[tip], wrist, aspect) / palm
    pip_reach = _distance(hand[pip], wrist, aspect) / palm

    pip_angle = _angle(hand[mcp], hand[pip], hand[dip])
    dip_angle = _angle(hand[pip], hand[dip], hand[tip])

    # 0 = strongly folded, 1 = strongly extended.  This is intentionally a
    # diagnostic feature for V14; it is not yet a hard classification gate.
    extension = _clip((tip_reach - pip_reach) / 0.55)
    bend = _clip(((pip_angle - 90.0) / 90.0 + (dip_angle - 90.0) / 90.0) * 0.5)

    return {
        "mcp_reach": round(float(mcp_reach), 3),
        "pip_reach": round(float(pip_reach), 3),
        "tip_reach": round(float(tip_reach), 3),
        "extension": round(float(extension), 3),
        "bend": round(float(bend), 3),
        "pip_angle": round(float(pip_angle), 1),
        "dip_angle": round(float(dip_angle), 1),
    }


def classify_pose_confidence(hand, aspect=1.0):
    if len(hand) != 21:
        return "NONE", 0.0
    hand = np.asarray(hand, dtype=np.float32)
    ev = [_finger_evidence(hand, c, aspect) for c in FINGER_CHAINS]
    states = [x[0] for x in ev]
    scores = [x[1] for x in ev]
    index, middle, ring, pinky = states
    palm = max(_distance(hand[0], hand[9], aspect), 1e-6)
    thumb_ratio = _distance(hand[4], hand[17], aspect) / palm
    tx, ty = _thumb_direction(hand, aspect)
    px, py = _palm_direction(hand, aspect)

    if all(s == "F" for s in states):
        if abs(tx) >= 0.78 and abs(tx) >= abs(ty) * 1.15:
            return ("THUMBS_RIGHT" if tx > 0 else "THUMBS_LEFT"), _confidence([abs(tx), 1.0 - abs(ty)])
        # A thumb must also be visibly separated from the palm before its
        # vertical direction is treated as a command.  This prevents a curled
        # thumb on a normal fist from becoming THUMBS_UP.
        if thumb_ratio >= 0.90 and ty >= 0.72:
            return "THUMBS_UP", _confidence([ty, _clip((thumb_ratio - .90) / .5), *[1 - s for s in scores]])
        if thumb_ratio >= 0.90 and ty <= -0.72:
            return "THUMBS_DOWN", _confidence([-ty, _clip((thumb_ratio - .90) / .5), *[1 - s for s in scores]])
        return "FIST", _confidence([1.0 - abs(tx) * .35, 1.0 - abs(ty) * .35, *[1 - s for s in scores]])

    if sum(s == "E" for s in states) >= 3:
        # Dedicated sideways open-palm command.  The aggregate axis makes it
        # much harder for one fingertip to create a false PALM_LEFT.
        if px <= -0.78 and -px >= abs(py) * 1.25:
            return "PALM_LEFT", _confidence([abs(px), 1.0 - abs(py), *scores])
        return "PAUSE", _confidence([*scores, _clip((thumb_ratio - .55) / .45)])

    if index == "E" and middle == "E" and ring == "F" and pinky == "F":
        return "ERASE", _confidence([scores[0], scores[1], 1 - scores[2], 1 - scores[3]])
    if index == "E" and middle == "F" and ring == "F" and pinky == "F":
        return "DRAW", _confidence([scores[0], 1 - scores[1], 1 - scores[2], 1 - scores[3]])
    return "OTHER", 0.0


def classify_pose(hand, aspect=1.0):
    """Backwards-compatible pose-only API returning just the gesture name."""
    return classify_pose_confidence(hand, aspect)[0]


def is_fist(hand, aspect=1.0):
    return classify_pose(hand, aspect) == "FIST"


class SketchGestureRecognizer:
    """Stable Sketch pose detector.

    * Continuous poses (DRAW / ERASE / PAUSE / FIST) switch fast: the pen lifts on the FIRST frame that no
      longer looks like DRAW, and a new pose is confirmed after two frames. A slower, vote-style filter on
      these poses made the pen keep drawing for ~4 frames while the hand closed into a fist.
    * Command poses (sideways palm, sideways/up/down thumbs) are stricter: two agreeing frames to lock
      (smoothed AND raw), and two raw non-matching frames to release, so one bad frame cannot flip them.
    """
    STRICT = {"PALM_LEFT", "THUMBS_LEFT", "THUMBS_RIGHT", "THUMBS_UP", "THUMBS_DOWN"}
    SPECIAL = STRICT | {"FIST"}

    def __init__(self, params=None, aspect=1.0, history=7, hold_frames=2):
        self.aspect = float(aspect or 1.0)
        self.history_size = max(5, int(history))
        self.hold_frames = max(1, int(hold_frames))
        self.reset()

    def configure(self, params=None, aspect=None, history=None, hold_frames=None):
        if aspect is not None:
            self.aspect = float(aspect or 1.0)
        if history is not None:
            self.history_size = max(5, int(history))
        if hold_frames is not None:
            self.hold_frames = max(1, int(hold_frames))
        self.reset()

    def reset(self):
        self.history = deque(maxlen=getattr(self, "history_size", 7))
        self.stable = "OTHER"
        self._candidate = None
        self._candidate_frames = 0
        self._bad_frames = 0
        self._release_frames = 0
        self._smoothed = None
        self.debug = {
            "raw": "OTHER", "stable": "OTHER", "confidence": 0.0,
            "candidate": "", "candidate_frames": 0, "required_frames": 0,
            "locked": False, "quality": 0.0, "finger_states": [],
            "finger_scores": [], "finger_geometry": [], "palm_axis": [0.0, 0.0], "history": [],
        }

    def _quality(self, points):
        palm = _distance(points[0], points[9], self.aspect)
        if palm < 1e-4:
            return 0.0
        # A hand whose palm is collapsed to a few pixels is not trustworthy.
        return _clip((palm - 0.018) / 0.055)

    def _publish(self, raw, confidence):
        ev = [_finger_evidence(self._smoothed, c, self.aspect) for c in FINGER_CHAINS]
        px, py = _palm_direction(self._smoothed, self.aspect)
        self.debug = {
            "raw": raw,
            "stable": self.stable,
            "confidence": round(float(confidence), 3),
            "candidate": self._candidate or "",
            "candidate_frames": int(self._candidate_frames),
            "required_frames": 2 if self._candidate else 0,
            "locked": self.stable not in ("OTHER", "NONE"),
            "quality": round(self._quality(self._smoothed), 3),
            "finger_states": [e[0] or "?" for e in ev],
            "finger_scores": [round(float(e[1]), 2) for e in ev],
            "finger_geometry": [
                _finger_geometry(self._smoothed, chain, self.aspect)
                for chain in FINGER_CHAINS
            ],
            "palm_axis": [round(px, 3), round(py, 3)],
            "history": list(self.history),
        }

    def classify(self, points, now=None):
        points = np.asarray(points, dtype=np.float32)
        if points.shape != (21, 3):
            self.reset()
            return "NONE", 0.0

        if self._smoothed is None:
            self._smoothed = points.copy()
        else:
            motion = _distance(points[8], self._smoothed[8], self.aspect)
            palm = max(_distance(points[0], points[9], self.aspect), 1e-5)
            rel = motion / palm
            # Light smoothing only. Heavier smoothing (alpha ~0.5) delays a pose change by a frame,
            # which keeps the pen down while the hand closes. Faster again when the hand really moves.
            alpha = 0.82 if rel > 0.16 else 0.72
            self._smoothed = (1.0 - alpha) * self._smoothed + alpha * points

        raw, confidence = classify_pose_confidence(self._smoothed, self.aspect)
        direct_raw, _ = classify_pose_confidence(points, self.aspect)
        self.history.append(raw)

        # A locked command pose is released only by two non-matching raw frames.
        if self.stable in self.STRICT:
            if direct_raw == self.stable:
                self._release_frames = 0
                self._candidate, self._candidate_frames = None, 0
                self._publish(raw, confidence)
                return self.stable, float(confidence)
            self._release_frames += 1
            if self._release_frames < 2:
                self._publish(raw, confidence)
                return self.stable, float(confidence)
            self.stable, self._release_frames = "OTHER", 0
            self._candidate, self._candidate_frames = None, 0

        if raw == self.stable:
            self._candidate, self._candidate_frames, self._bad_frames = None, 0, 0
            self._publish(raw, confidence)
            return self.stable, float(confidence)

        if raw == "OTHER":
            self._bad_frames += 1
            if self._bad_frames <= max(self.hold_frames, 2):
                self._publish(raw, confidence)
                return self.stable, float(confidence)
            self._candidate, self._candidate_frames = None, 0
            self._publish(raw, confidence)
            return "OTHER", float(confidence)

        self._bad_frames = 0
        if raw == self._candidate:
            self._candidate_frames += 1
        else:
            self._candidate, self._candidate_frames = raw, 1
        agrees = direct_raw == raw if raw in self.STRICT else True
        if self._candidate_frames >= 2 and agrees:
            self.stable = raw
            self._candidate, self._candidate_frames = None, 0
            self._publish(raw, confidence)
            return self.stable, float(confidence)
        self._publish(raw, confidence)
        return "OTHER", float(confidence)           # not confirmed yet: the pen is up

