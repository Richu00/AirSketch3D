import math

import numpy as np

from backend.sketch.engine import SketchEngine
from backend.sketch.geometry import build_3d_shape
from backend.sketch.inspector import SketchInspector
from backend.sketch.recognition import SketchGestureRecognizer
from backend.tests.hand_factory import pose


def circle(cx, cy, r, n=60):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def test_multiple_closed_strokes_become_multiple_components():
    e = SketchEngine(aspect=1.0)
    t = 0.0
    for p in circle(0.3, 0.5, 0.15):
        e.update('DRAW', p, t); t += 0.01
    e.update('PAUSE', None, t); t += 0.01
    for p in circle(0.7, 0.5, 0.10):
        e.update('DRAW', p, t); t += 0.01
    ok, msg = e.generate()
    assert ok, msg
    assert len(e.model['outlines']) == 2
    assert e.model['outline'] == e.model['outlines'][0]


def test_open_stroke_is_rejected():
    e = SketchEngine(aspect=1.0)
    t = 0.0
    for i in range(30):
        e.update('DRAW', (0.2 + i * 0.01, 0.5), t); t += 0.01
    ok, msg = e.generate()
    assert not ok
    assert 'Close your outline' in msg


def test_sketch_has_no_pinch_command():
    # There is intentionally no PINCH label/branch in Sketch mode. A pinch-like
    # pose is simply interpreted by the ordinary finger geometry, never as a command.
    r = SketchGestureRecognizer(aspect=1.0)
    for _ in range(6):
        g, _ = r.classify(pose('PINCH'))
    assert g in {'DRAW', 'OTHER'}


def test_sketch_classifier_recognizes_core_poses():
    r = SketchGestureRecognizer(aspect=1.0)
    for name, expected in [('INDEX_POINT', 'DRAW'), ('PEACE', 'ERASE'), ('OPEN_PALM', 'PAUSE'), ('FIST', 'FIST')]:
        r.reset()
        seen = []
        for _ in range(6):
            g, _ = r.classify(pose(name))
            seen.append(g)
        assert seen[-1] == expected, (name, seen)


def test_inspector_one_hand_rotation_and_two_hand_controls():
    i = SketchInspector(); i.enter()
    h1 = np.asarray(pose('INDEX_POINT'))
    i.update([h1])
    moved = h1.copy(); moved[:, 0] += 0.05; moved[:, 1] += 0.02
    i.update([moved])
    assert i.rotation[0] != 0 or i.rotation[1] != 0

    h2 = np.asarray(pose('INDEX_POINT', cx=0.75))
    i.update([h1, h2])
    moved2 = h2.copy(); moved2[:, 0] += 0.08
    i.update([moved, moved2])
    assert i.pan[0] != 0 or i.zoom != 1 or i.rotation[2] != 0


def test_nearly_closed_outline_is_auto_snapped_for_generation():
    e = SketchEngine(aspect=1.0, params={"close_snap_distance": 0.035})
    t = 0.0
    pts = circle(0.5, 0.5, 0.2, 80)
    # Leave the final point visibly short of the starting point.
    pts[-1] = (pts[0][0] + 0.065, pts[0][1] + 0.01)
    for p in pts:
        e.update("DRAW", p, t); t += 0.01
    ok, msg = e.generate()
    assert ok, msg
    assert e.model is not None

