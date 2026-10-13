"""AirSketch3D drawing engine integrated into AIRCONTROL.

The engine is deliberately independent of camera/MediaPipe/UI code.  It owns
strokes, closure detection, erasing, validation, resampling and 3D model data.
Desktop/BROWSER pinch remains untouched; SKETCH mode never consumes pinch.
"""
from __future__ import annotations

import copy
import numpy as np

from backend.sketch.geometry import build_3d_shape, build_3d_shape_ex, _path_length

DEFAULTS = {
    "extrude_height": 0.6,
    "fist_hold_ms": 700,
    "erase_radius": 0.06,
    "min_points": 15,
    "resample_points": 96,
    "min_step": 0.004,
    "close_snap_distance": 0.05,
    "min_component_area": 0.0015,
    # --- forgiving drawing (air drawing is never perfectly closed) ---
    "live_close_distance": 0.08,     # live snap radius around the stroke start (fraction of frame height)
    "auto_close_ratio": 0.45,        # on build, close a stroke whose gap is <= 45% of its length
    "repair_crossings": True,        # trim overshoot tails / small loops instead of rejecting
    "snap_shapes": True,             # clean triangle / rectangle / circle recognition
    # --- fingertip smoothing (One Euro filter) ---
    "smooth_tip": True,
    "smooth_min_cutoff": 1.0,        # lower = smoother when moving slowly
    "smooth_beta": 2.8,              # moderate responsiveness without fingertip chatter
    "hand_loss_grace_ms": 350,       # a tracking drop shorter than this does not lift the pen
}

SKETCH_GESTURES = ("DRAW", "ERASE", "PAUSE", "FIST", "OTHER", "NONE")


class _Fragment(list):
    """A piece of a stroke left behind by the eraser. Never auto-closed into a shape."""


class OneEuroFilter:
    """Adaptive low-pass filter: smooth when the finger is slow, responsive when it is fast."""

    def __init__(self, min_cutoff=1.6, beta=6.0, d_cutoff=1.0):
        self.min_cutoff, self.beta, self.d_cutoff = float(min_cutoff), float(beta), float(d_cutoff)
        self.reset()

    def reset(self):
        self._x = None
        self._dx = None
        self._t = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2.0 * np.pi * max(cutoff, 1e-6))
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, value, t):
        value = np.asarray(value, dtype=float)
        if self._x is None or self._t is None:
            self._x, self._dx, self._t = value.copy(), np.zeros_like(value), t
            return value
        dt = max(float(t - self._t), 1e-3)
        self._t = t
        raw_speed = (value - self._x) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self._dx = a_d * raw_speed + (1.0 - a_d) * self._dx
        cutoff = self.min_cutoff + self.beta * float(np.linalg.norm(self._dx))
        a = self._alpha(cutoff, dt)
        self._x = a * value + (1.0 - a) * self._x
        return self._x.copy()


def build_outline(points, n=96, aspect=1.0):
    """Backward-compatible single-outline helper used by older tests/tools."""
    outlines, problems = build_3d_shape([points], resample_points=n, aspect=aspect)
    if not outlines:
        return None
    return np.asarray(outlines[0], dtype=np.float32)


class SketchEngine:
    def __init__(self, aspect=16 / 9, params=None):
        self.p = dict(DEFAULTS)
        self.aspect = float(aspect) if aspect else 1.0
        self.model = None
        self._model_seq = 0
        self._filter = OneEuroFilter(self.p["smooth_min_cutoff"], self.p["smooth_beta"])
        self._tip = None
        self.last_notes = []
        self.configure(params, aspect=aspect)
        self.clear()

    def configure(self, params=None, aspect=None):
        for key, value in (params or {}).items():
            if key in self.p and value is not None:
                self.p[key] = value
        if aspect:
            self.aspect = float(aspect)
        if hasattr(self, "_filter"):
            self._filter.min_cutoff = float(self.p["smooth_min_cutoff"])
            self._filter.beta = float(self.p["smooth_beta"])

    def clear(self, keep_model=False):
        self.strokes: list[list[tuple[float, float]]] = [[]]
        self._undo_stack = []
        self._redo_stack = []
        self.gesture = "NONE"
        self._prev_gesture = "NONE"
        self._fist_since = None
        self._fist_done = False
        self._warned = False
        self._closed_current = False
        self._tip = None
        self._last_draw_t = None
        # Explicit pen lifecycle: transient tracking noise does not end a draw.
        self._draw_state = "IDLE"
        self._dropout_since = None
        if hasattr(self, "_filter"):
            self._filter.reset()
        self.version = getattr(self, "version", 0) + 1
        if not keep_model:
            self.model = None

    @property
    def point_count(self):
        return sum(len(stroke) for stroke in self.strokes)

    def _snap_distance(self):
        """Live snap radius: generous, because a fingertip never lands exactly on the start."""
        return max(float(self.p["close_snap_distance"]), float(self.p["live_close_distance"]))

    @property
    def closed_stroke_count(self):
        """Strokes that will build into a shape (snapped shut, or a gap small enough to auto-close)."""
        return sum(1 for stroke in self.strokes if self._is_closable(stroke))

    def all_points(self):
        return [point for stroke in self.strokes for point in stroke]

    def _gap(self, stroke):
        dx = (stroke[0][0] - stroke[-1][0]) * self.aspect
        dy = stroke[0][1] - stroke[-1][1]
        return (dx * dx + dy * dy) ** 0.5

    def _left_start(self, stroke):
        """True once the pen has moved well away from where the stroke began.

        Without this a slow start (15 points still sitting inside the snap radius)
        would count as an already-closed loop and freeze the stroke.
        """
        arr = np.asarray(stroke, dtype=float)
        far = np.hypot((arr[:, 0] - arr[0, 0]) * self.aspect, arr[:, 1] - arr[0, 1]).max()
        return bool(far >= 1.5 * self._snap_distance())

    def _is_closed(self, stroke):
        if len(stroke) < self.p["min_points"]:
            return False
        return self._gap(stroke) <= self._snap_distance() and self._left_start(stroke)

    def _is_closable(self, stroke):
        if self._is_closed(stroke):
            return True
        if isinstance(stroke, _Fragment):
            return False
        ratio = float(self.p["auto_close_ratio"] or 0.0)
        if ratio <= 0 or len(stroke) < self.p["min_points"]:
            return False
        length = _path_length(stroke, self.aspect)
        return length > 0 and self._gap(stroke) <= ratio * length

    def _maybe_snap_closed(self, stroke):
        if len(stroke) < self.p["min_points"]:
            return False
        if self._is_closed(stroke):
            stroke[-1] = stroke[0]
            return True
        return False

    def close_hint(self):
        """Where the current stroke started, so the UI can show a 'close the loop' ring."""
        if self.gesture != "DRAW" or self._closed_current or self._tip is None or not self.strokes:
            return None
        stroke = self.strokes[-1]
        if len(stroke) < self.p["min_points"]:
            return None
        radius = self._snap_distance()
        dx = (self._tip[0] - stroke[0][0]) * self.aspect
        dy = self._tip[1] - stroke[0][1]
        dist = (dx * dx + dy * dy) ** 0.5
        return {"x": round(float(stroke[0][0]), 4), "y": round(float(stroke[0][1]), 4),
                "r": round(radius, 4), "near": bool(dist <= radius * 2.2)}

    def fist_progress(self, now=None):
        if self._fist_since is None or now is None:
            return 0.0
        return max(0.0, min(1.0, (now - self._fist_since) * 1000.0 / self.p["fist_hold_ms"]))

    def _record_history(self):
        # A pen-down that follows no change (a glitchy one-frame DRAW, or a resume right after undo)
        # must not create an empty undo step.
        if self._undo_stack and self._undo_stack[-1] == self.strokes:
            return
        self._undo_stack.append(copy.deepcopy(self.strokes))
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _restore(self, strokes):
        self.strokes = copy.deepcopy(strokes)
        self._closed_current = False
        self._prev_gesture = "NONE"
        self._draw_state = "IDLE"
        self._dropout_since = None
        self._filter.reset()
        self._tip = None
        self.model = None
        self.version += 1

    def erase_near(self, x, y):
        before = copy.deepcopy(self.strokes)
        radius = float(self.p["erase_radius"])
        radius2 = radius * radius
        changed = False
        rebuilt = []
        for stroke in self.strokes:
            segment = _Fragment()
            for px, py in stroke:
                dx = (px - x) * self.aspect
                dy = py - y
                if dx * dx + dy * dy <= radius2:
                    changed = True
                    if segment:
                        rebuilt.append(segment)
                        segment = _Fragment()
                else:
                    segment.append((px, py))
            if segment:
                rebuilt.append(segment)
        if changed:
            self._undo_stack.append(before)
            if len(self._undo_stack) > 50:
                self._undo_stack.pop(0)
            self._redo_stack.clear()
            self.strokes = rebuilt + [[]]
            self.model = None
            self.version += 1
        return changed

    def undo_stroke(self):
        if not self._undo_stack:
            return False
        self._redo_stack.append(copy.deepcopy(self.strokes))
        self._restore(self._undo_stack.pop())
        return True

    def redo_stroke(self):
        if not self._redo_stack:
            return False
        self._undo_stack.append(copy.deepcopy(self.strokes))
        self._restore(self._redo_stack.pop())
        return True

    def generate(self):
        if self.point_count < self.p["min_points"]:
            return False, f"Draw more first ({self.point_count}/{self.p['min_points']} points)"

        valid_strokes = [stroke for stroke in self.strokes if len(stroke) >= self.p["min_points"]]
        if not valid_strokes:
            return False, "Draw at least one closed outline"

        outlines, problems, notes = build_3d_shape_ex(
            valid_strokes,
            resample_points=int(self.p["resample_points"]),
            aspect=self.aspect,
            min_points=int(self.p["min_points"]),
            close_snap_distance=self._snap_distance(),
            min_component_area=float(self.p["min_component_area"]),
            auto_close_ratio=float(self.p["auto_close_ratio"] or 0.0),
            repair_crossings=bool(self.p["repair_crossings"]),
            snap_shapes=bool(self.p["snap_shapes"]),
            strict_indices={i for i, s in enumerate(valid_strokes) if isinstance(s, _Fragment)},
        )
        self.last_notes = list(dict.fromkeys(notes))
        if not outlines:
            if problems:
                readable = ", ".join(f"stroke {i + 1}: {self._describe(reason)}" for i, reason in problems[:3])
                return False, f"Close your outline before building ({readable})"
            return False, "No valid closed outline found"

        self._model_seq += 1
        payload = [
            [[round(float(x), 5), round(float(y), 5)] for x, y in outline]
            for outline in outlines
        ]
        self.model = {
            "id": self._model_seq,
            "outlines": payload,
            # Backwards compatibility for older frontend/API consumers.
            "outline": payload[0],
            "height": float(self.p["extrude_height"]),
        }
        self.version += 1
        message = "3D model generated" if len(payload) == 1 else f"3D model generated ({len(payload)} components)"
        if self.last_notes:
            message += " - " + ", ".join(self.last_notes)
        return True, message

    @staticmethod
    def _describe(reason):
        if reason.startswith("open:"):
            gap = reason.split(":")[1].split("/")[0]
            return f"too open to close (gap {float(gap) * 100:.0f}% of frame)"
        return {
            "too_short": "too short",
            "self_intersection": "outline crosses itself",
            "degenerate": "shape too small or flat",
            "resample_failed": "could not be processed",
        }.get(reason, reason)

    def update(self, gesture, tip, now):
        gesture = gesture if gesture in SKETCH_GESTURES else "OTHER"
        event = ""
        grace = float(self.p.get("hand_loss_grace_ms", 0) or 0) / 1000.0

        if gesture == "DRAW" and tip is not None:
            # A DRAW after PAUSE/ERASE/FIST or a long tracking loss starts a
            # fresh stroke. Short NONE/OTHER gaps keep the same pen session.
            starting = self._draw_state != "DRAWING"
            self._dropout_since = None
            self._draw_state = "DRAWING"
            self._last_draw_t = now

            if starting:
                self._filter.reset()
                self._closed_current = False
                self._record_history()
                if self.strokes[-1]:
                    self.strokes.append([])

            raw = (float(tip[0]), float(tip[1]))
            if self.p["smooth_tip"]:
                sx, sy = self._filter(raw, now)
                point = (float(sx), float(sy))
            else:
                point = raw
            self._tip = point
            current = self.strokes[-1]
            if self._closed_current:
                pass
            elif not current:
                current.append(point)
                self.version += 1
            else:
                dx = (point[0] - current[-1][0]) * self.aspect
                dy = point[1] - current[-1][1]
                if dx * dx + dy * dy >= float(self.p["min_step"]) ** 2:
                    current.append(point)
                    if self._maybe_snap_closed(current):
                        self._closed_current = True
                    self.version += 1

        elif gesture in ("NONE", "OTHER") and self._draw_state == "DRAWING":
            # Keep the pen down across brief detector/camera dropouts. The
            # grace timer starts when the dropout begins, not at the last DRAW.
            if self._dropout_since is None:
                self._dropout_since = now
            if grace <= 0 or (now - self._dropout_since) > grace:
                self._draw_state = "IDLE"
                self._dropout_since = None
                self._tip = None

        elif gesture == "PAUSE":
            self._draw_state = "PAUSED"
            self._dropout_since = None
            self._tip = None

        elif gesture == "ERASE" and tip is not None:
            self._draw_state = "ERASING"
            self._dropout_since = None
            self._tip = None
            self.erase_near(float(tip[0]), float(tip[1]))

        elif gesture == "FIST":
            # A command gesture ends the active pen session. The FIST hold
            # timer below remains unchanged and owns model generation.
            self._draw_state = "IDLE"
            self._dropout_since = None
            self._tip = None

        else:
            self._tip = None

        if gesture == "FIST":
            if self._fist_since is None:
                self._fist_since = now
                self._fist_done = False
                self._warned = False
            if not self._fist_done and not self._warned and (now - self._fist_since) * 1000.0 >= self.p["fist_hold_ms"]:
                ok, message = self.generate()
                if ok:
                    self._fist_done = True
                else:
                    self._warned = True
                event = message
        else:
            self._fist_since = None
            self._fist_done = False
            self._warned = False

        self.gesture = gesture
        self._prev_gesture = gesture
        return event

    def state(self, now=None):
        return {
            "gesture": self.gesture,
            "points": self.point_count,
            "closed_strokes": self.closed_stroke_count,
            "version": self.version,
            "fist_progress": round(self.fist_progress(now), 3),
            "erase_radius": self.p["erase_radius"],
            "has_model": self.model is not None,
            "model_id": self.model["id"] if self.model else 0,
            "inspecting": False,
            "close_hint": self.close_hint(),
        }

    def strokes_payload(self):
        return [
            [[round(float(x), 4), round(float(y), 4)] for x, y in stroke]
            for stroke in self.strokes
            if stroke
        ]
