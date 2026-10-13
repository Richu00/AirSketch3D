"""Hand-loss grace, tracker throttling, inspector reset/clamp, camera exposure option."""
import numpy as np
import pytest

from backend.sketch.engine import SketchEngine
from backend.sketch.inspector import SketchInspector


def _line(e, pts, t, dt=0.033):
    for p in pts:
        e.update("DRAW", p, t); t += dt
    return t


def test_short_hand_loss_does_not_split_the_stroke():
    e = SketchEngine(aspect=1.0, params={"smooth_tip": False, "hand_loss_grace_ms": 350})
    t = _line(e, [(0.2 + i * 0.01, 0.3) for i in range(10)], 0.0)
    for _ in range(4):                                  # ~130 ms with no hand
        e.update("NONE", None, t); t += 0.033
    t = _line(e, [(0.4 + i * 0.01, 0.3) for i in range(10)], t)
    assert len([s for s in e.strokes if s]) == 1        # still ONE stroke


def test_long_hand_loss_still_lifts_the_pen():
    e = SketchEngine(aspect=1.0, params={"smooth_tip": False, "hand_loss_grace_ms": 350})
    t = _line(e, [(0.2 + i * 0.01, 0.3) for i in range(10)], 0.0)
    for _ in range(20):                                 # ~660 ms
        e.update("NONE", None, t); t += 0.033
    _line(e, [(0.6 + i * 0.01, 0.6) for i in range(10)], t)
    assert len([s for s in e.strokes if s]) == 2


def test_grace_can_be_switched_off():
    e = SketchEngine(aspect=1.0, params={"smooth_tip": False, "hand_loss_grace_ms": 0})
    t = _line(e, [(0.2 + i * 0.01, 0.3) for i in range(10)], 0.0)
    e.update("NONE", None, t); t += 0.033
    _line(e, [(0.4 + i * 0.01, 0.3) for i in range(10)], t)
    assert len([s for s in e.strokes if s]) == 2


def test_deliberate_pause_is_not_bridged():
    e = SketchEngine(aspect=1.0, params={"smooth_tip": False, "hand_loss_grace_ms": 350})
    t = _line(e, [(0.2 + i * 0.01, 0.3) for i in range(10)], 0.0)
    e.update("PAUSE", None, t); t += 0.033             # open palm = pen up, immediately
    _line(e, [(0.4 + i * 0.01, 0.3) for i in range(10)], t)
    assert len([s for s in e.strokes if s]) == 2


def test_glitch_pen_down_does_not_add_an_empty_undo_step():
    e = SketchEngine(aspect=1.0, params={"smooth_tip": False, "hand_loss_grace_ms": 0})
    t = _line(e, [(0.2 + i * 0.02, 0.3) for i in range(10)], 0.0)
    e.update("PAUSE", None, t); t += 0.5
    e.update("PAUSE", None, t); t += 0.5
    before = len(e._undo_stack)
    e.update("OTHER", None, t); t += 0.1
    e.update("OTHER", None, t)
    assert len(e._undo_stack) == before


def test_inspector_reset_view_and_pan_clamp():
    i = SketchInspector(); i.enter()
    h1 = np.zeros((21, 3)); h2 = np.zeros((21, 3))
    h1[[0, 5, 9, 13, 17], 0] = 0.3; h2[[0, 5, 9, 13, 17], 0] = 0.7
    for k in range(200):                                 # keep dragging both hands the same way
        h1[:, 0] += 0.01; h2[:, 0] += 0.01
        i.update([h1.copy(), h2.copy()])
    assert abs(i.pan[0]) <= 1.6 + 1e-6
    i.rotation = [1.0, 2.0, 3.0]; i.zoom = 2.0
    s = i.reset_view()
    assert s["rotation"] == [0, 0, 0] and s["pan"] == [0, 0] and s["zoom"] == 1.0 and i.inspecting


def test_camera_exposure_is_optional():
    from backend.vision.camera import Camera
    assert Camera().exposure is None
    assert Camera(exposure=-6).exposure == -6


def test_low_light_retry_is_throttled():
    pytest.importorskip("mediapipe")
    from backend.vision.hand_tracker import HandTracker
    t = HandTracker.__new__(HandTracker); t._miss_streak = 0
    seq = [t._try_enhanced() for _ in range(9)]
    assert seq == [True, False, False, False, True, False, False, False, True]


def test_enhancement_works_on_a_downscaled_copy():
    pytest.importorskip("mediapipe")
    from backend.vision.hand_tracker import _enhance_for_detection
    out = _enhance_for_detection(np.full((540, 960, 3), 40, dtype=np.uint8))
    assert out.shape == (360, 640, 3)


def test_palm_left_does_not_open_inspect_while_in_mouse_control():
    from backend.main import state
    from backend.tests.test_sketch_mouse_mode import _rotated_open_palm
    state.modes.paused = False; state.modes.set_mode("SKETCH"); state.apply_settings(); state.sketch.clear()
    state.sketch.model = {"id": 7, "outline": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]], "height": 0.6}
    state.sketch_inspector.reset(); state._palm_left_frames = 0; state._palm_left_latched = False
    state.modes.sketch_control_mode = "MOUSE"
    t = 3000.0
    for _ in range(12):
        state.process(_rotated_open_palm(-1), t); t += 0.033
    assert not state.sketch_inspector.inspecting
    state.modes.sketch_control_mode = "DRAW"
    for _ in range(12):
        state.process(_rotated_open_palm(-1), t); t += 0.033
    assert state.sketch_inspector.inspecting
    state.modes.set_mode("DESKTOP"); state.sketch.clear(); state.sketch_inspector.reset()


def test_reset_view_endpoint():
    from fastapi.testclient import TestClient
    from backend.main import app, state
    state.sketch_inspector.enter(); state.sketch_inspector.zoom = 2.2
    with TestClient(app) as c:
        assert c.post("/sketch/inspect/reset-view").json()["success"] is True
    assert state.sketch_inspector.zoom == 1.0 and state.sketch_inspector.inspecting
    state.sketch_inspector.reset()


# ---------------------------------------------------------------- v4: recognizer timing guarantees
def _pen_up_lag(to_pose):
    from backend.sketch.recognition import SketchGestureRecognizer
    from backend.tests.hand_factory import pose
    r = SketchGestureRecognizer(aspect=1.0)
    for _ in range(12):
        r.classify(pose("INDEX_POINT"))
    out = [r.classify(pose(to_pose))[0] for _ in range(8)]
    return next(i for i, g in enumerate(out) if g != "DRAW")


@pytest.mark.parametrize("target", ["FIST", "OPEN_PALM", "PEACE"])
def test_pen_lifts_on_the_first_frame_that_stops_looking_like_draw(target):
    assert _pen_up_lag(target) == 0


def test_pen_down_is_quick():
    from backend.sketch.recognition import SketchGestureRecognizer
    from backend.tests.hand_factory import pose
    r = SketchGestureRecognizer(aspect=1.0)
    for _ in range(12):
        r.classify(pose("FIST"))
    out = [r.classify(pose("INDEX_POINT"))[0] for _ in range(6)]
    assert next(i for i, g in enumerate(out) if g == "DRAW") <= 1


def test_thumbs_up_needs_a_visible_thumb_but_a_plain_fist_stays_a_fist():
    from backend.sketch.recognition import classify_pose
    from backend.tests.hand_factory import pose
    assert classify_pose(pose("FIST")) == "FIST"
    assert classify_pose(pose("THUMBS_UP")) == "THUMBS_UP"
    assert classify_pose(pose("THUMBS_DOWN")) == "THUMBS_DOWN"


def test_inspector_v4_keeps_both_reset_view_and_total_pan_clamp():
    i = SketchInspector(); i.enter()
    h1 = np.zeros((21, 3)); h2 = np.zeros((21, 3))
    h1[[0, 5, 9, 13, 17], 0] = 0.3; h2[[0, 5, 9, 13, 17], 0] = 0.7
    for _ in range(300):
        h1[:, 0] += 0.01; h2[:, 0] += 0.01
        i.update([h1.copy(), h2.copy()])
    assert abs(i.pan[0]) <= 1.6 + 1e-6
    assert i.reset_view()["pan"] == [0, 0]
