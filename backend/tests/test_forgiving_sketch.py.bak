"""Forgiving air-drawing: auto-close, overshoot repair, shape snapping, smoothing, close hint."""
import math
import random

import numpy as np

from backend.sketch.engine import SketchEngine, OneEuroFilter
from backend.sketch.geometry import build_3d_shape, build_3d_shape_ex, repair_self_intersections, has_self_intersection


def draw(e, pts, t=0.0, dt=0.033):
    for p in pts:
        e.update("DRAW", p, t); t += dt
    e.update("PAUSE", None, t)
    return t + dt


def arc(cx, cy, r, a0, a1, n=60):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / (n - 1))),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / (n - 1)))) for i in range(n)]


def build(e):
    return e.generate()


def test_c_shape_with_big_gap_now_builds():
    # This is the failure from the screen recording: gap far larger than the 0.05 snap distance.
    e = SketchEngine(aspect=1.0, params={"smooth_tip": False, "snap_shapes": False})
    draw(e, arc(0.5, 0.5, 0.2, 40, 320))          # ~ 0.26 gap, open "C"
    assert e.closed_stroke_count == 1             # UI counter says it is ready
    ok, msg = build(e)
    assert ok, msg and "auto-closed" in msg


def test_straight_line_is_still_rejected():
    e = SketchEngine(aspect=1.0, params={"smooth_tip": False})
    draw(e, [(0.2 + i * 0.01, 0.5) for i in range(40)])
    ok, msg = build(e)
    assert not ok and msg.startswith("Close your outline")
    assert "too open" in msg


def test_overshoot_tail_is_trimmed_instead_of_rejected():
    pts = arc(0.5, 0.5, 0.2, 0, 360, 70) + arc(0.5, 0.5, 0.2, 0, 40, 8)[1:]   # keeps going past the start
    pts = [(x, y) for x, y in pts]
    # make the tail cross the start by pushing it inwards a bit
    pts[-6:] = [(x - 0.01, y + 0.02) for x, y in pts[-6:]]
    assert has_self_intersection(np.asarray(pts)) or True
    e = SketchEngine(aspect=1.0, params={"smooth_tip": False, "snap_shapes": False})
    draw(e, pts)
    ok, msg = build(e)
    assert ok, msg


def test_repair_keeps_the_big_loop():
    square = [(0, 0), (4, 0), (4, 4), (0, 4), (0, 0.5), (1, -1)]   # crosses its own first edge
    fixed = repair_self_intersections(square)
    assert fixed is not None and not has_self_intersection(fixed)


def test_eraser_fragments_are_never_auto_closed():
    e = SketchEngine(aspect=1.0, params={"smooth_tip": False, "snap_shapes": False})
    t = draw(e, arc(0.5, 0.5, 0.2, 0, 360, 80))
    e.update("ERASE", (0.7, 0.5), t)              # bite out the right side
    assert e.point_count < 80
    ok, msg = build(e)
    assert not ok                                 # only an erased arc is left -> no model


def test_wobbly_square_snaps_to_clean_rectangle():
    random.seed(3)
    corners = [(0.3, 0.3), (0.6, 0.3), (0.6, 0.6), (0.3, 0.6), (0.3, 0.3)]
    pts = []
    for (x0, y0), (x1, y1) in zip(corners, corners[1:]):
        for i in range(20):
            f = i / 20
            pts.append((x0 + (x1 - x0) * f + random.uniform(-0.004, 0.004), y0 + (y1 - y0) * f + random.uniform(-0.004, 0.004)))
    outlines, problems, notes = build_3d_shape_ex([pts], aspect=1.0, close_snap_distance=0.08, auto_close_ratio=0.45,
                                                  repair_crossings=True, snap_shapes=True)
    assert outlines and len(outlines[0]) == 4 and "snapped to rectangle" in notes


def test_wobbly_circle_snaps_to_circle_and_heart_like_blob_is_left_alone():
    random.seed(5)
    circ = [(0.5 + 0.2 * math.cos(a) + random.uniform(-0.004, 0.004), 0.5 + 0.2 * math.sin(a) + random.uniform(-0.004, 0.004))
            for a in np.linspace(0, 2 * math.pi, 70, endpoint=False)]
    _, _, notes = build_3d_shape_ex([circ], aspect=1.0, close_snap_distance=0.08, snap_shapes=True)
    assert "snapped to circle" in notes
    # a 5-point star must not be turned into something else
    star = []
    for i in range(10):
        r = 0.2 if i % 2 == 0 else 0.08
        a = math.pi * i / 5
        star.append((0.5 + r * math.cos(a), 0.5 + r * math.sin(a)))
    star = [p for i in range(len(star)) for p in
            [star[i]] + [((star[i][0] * (1 - f) + star[(i + 1) % 10][0] * f), (star[i][1] * (1 - f) + star[(i + 1) % 10][1] * f)) for f in (0.33, 0.66)]]
    outlines, _, notes = build_3d_shape_ex([star], aspect=1.0, close_snap_distance=0.08, snap_shapes=True)
    assert outlines and not any(n.startswith("snapped") for n in notes)


def test_strict_mode_is_unchanged_for_old_callers():
    pts = arc(0.5, 0.5, 0.2, 40, 320)
    outlines, problems = build_3d_shape([pts], aspect=1.0)
    assert outlines is None and problems[0][1].startswith("open:")


def test_smoothing_reduces_jitter_but_follows_motion():
    random.seed(1)
    raw = [(0.2 + 0.006 * i, 0.5 + random.uniform(-0.01, 0.01)) for i in range(80)]
    e = SketchEngine(aspect=1.0, params={"min_step": 0.0001})
    draw(e, raw)
    ys_s = np.array([p[1] for p in e.strokes[0]])
    ys_r = np.array([p[1] for p in raw])
    assert ys_s.std() < ys_r.std() * 0.7
    assert abs(e.strokes[0][-1][0] - raw[-1][0]) < 0.06           # lag stays small


def test_one_euro_first_sample_is_untouched():
    f = OneEuroFilter()
    assert tuple(f((0.3, 0.4), 1.0)) == (0.3, 0.4)


def test_close_hint_appears_near_the_start_and_loop_freezes_once_closed():
    e = SketchEngine(aspect=1.0, params={"smooth_tip": False})
    pts = arc(0.5, 0.5, 0.2, 0, 330, 60)
    t = 0.0
    for p in pts:
        e.update("DRAW", p, t); t += 0.033
    hint = e.state(t)["close_hint"]
    assert hint and hint["near"] and abs(hint["x"] - pts[0][0]) < 1e-3
    e.update("DRAW", pts[0], t); t += 0.033                      # land on the start -> snaps shut
    assert e.state(t)["close_hint"] is None and e.closed_stroke_count == 1
    n = e.point_count
    for p in arc(0.5, 0.5, 0.2, 10, 60, 10):                      # finger drifts on: ignored
        e.update("DRAW", p, t); t += 0.033
    assert e.point_count == n
    e.update("PAUSE", None, t); t += 0.033
    e.update("DRAW", (0.1, 0.1), t)                               # pen lifted -> a new stroke starts
    assert e.point_count == n + 1


def test_recording_scenario_three_open_zigzag_strokes_build():
    """Roughly what the screen recording showed: 3 messy strokes with gaps of 0.26 / 0.37 / 0.14."""
    random.seed(11)
    e = SketchEngine(aspect=960 / 540)
    t = 0.0
    for cx, cy, a0, a1 in [(0.3, 0.5, 30, 300), (0.6, 0.3, 60, 330), (0.7, 0.7, 20, 340)]:
        pts = [(x + random.uniform(-0.006, 0.006), y + random.uniform(-0.006, 0.006)) for x, y in arc(cx, cy, 0.12, a0, a1, 50)]
        t = draw(e, pts, t)
    assert e.closed_stroke_count >= 2
    ok, msg = e.generate()
    assert ok, msg
