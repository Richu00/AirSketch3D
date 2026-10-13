from backend.modes.manager import ModeManager
from backend.sketch.recognition import SketchGestureRecognizer
from backend.tests.hand_factory import pose
from backend.tests.test_modes import FakeActions, APPS


def sketch():
    a = FakeActions(); m = ModeManager(a, lambda: APPS); m.set_mode("SKETCH")
    return m, a


def test_tap_of_thumbs_up_does_not_toggle():
    m, _ = sketch()
    assert m.handle_event("THUMBS_UP") == ""
    assert m.tick("THUMBS_UP", 10.0) == "" and m.tick("THUMBS_UP", 10.3) == ""
    assert m.sketch_control_mode == "DRAW"


def test_held_thumbs_up_toggles_once_each_way():
    m, _ = sketch()
    m.tick("THUMBS_UP", 10.0)
    assert m.tick("THUMBS_UP", 11.1) == "Sketch Mouse Control" and m.sketch_control_mode == "MOUSE"
    assert m.tick("THUMBS_UP", 12.5) == ""                      # still held: no second toggle
    m.tick("NONE", 13.0)
    m.tick("THUMBS_UP", 14.0)
    assert m.tick("THUMBS_UP", 15.1) == "Sketch Draw Control" and m.sketch_control_mode == "DRAW"


def test_pinch_clicks_only_in_mouse_control():
    m, a = sketch()
    assert m.handle_event("PINCH") == "" and not a.calls
    m.sketch_control_mode = "MOUSE"
    assert m.handle_event("PINCH") == "Mouse Click" and a.calls == [("click",)]


def test_leaving_sketch_resets_control_mode():
    m, _ = sketch(); m.sketch_control_mode = "MOUSE"
    assert m.handle_event("THUMBS_DOWN") == "Sketch Mode Exited" and m.mode == "DESKTOP"
    m.set_mode("SKETCH")
    assert m.sketch_control_mode == "DRAW"


def test_one_noisy_frame_does_not_become_a_draw_point():
    r = SketchGestureRecognizer(aspect=1.0)
    seen = [r.classify(pose(n))[0] for n in ["FIST"] * 6 + ["INDEX_POINT"] + ["FIST"] * 3]
    assert "DRAW" not in seen[6:]


def test_pipeline_thumbs_up_hold_switches_to_mouse_and_blocks_drawing():
    from backend.main import state
    state.modes.paused = False; state.modes.set_mode("SKETCH"); state.apply_settings(); state.sketch.clear()
    state.recognizer.aspect = 1.0; state.sketch.configure(aspect=1.0)
    moves = []
    state.actions.move_cursor = lambda *a, **k: moves.append(1)
    state.actions.click = lambda: None
    t = 500.0
    for _ in range(50):                                          # ~1.6 s of thumbs-up
        state.process(pose("THUMBS_UP"), t); t += 0.033
    assert state.modes.sketch_control_mode == "MOUSE"
    n = state.sketch.point_count
    for _ in range(20):
        state.process(pose("INDEX_POINT"), t); t += 0.033
    assert state.sketch.point_count == n and moves               # cursor moves, nothing is drawn
    state.modes.set_mode("DESKTOP"); state.sketch.clear()


def _rotated_open_palm(direction=1):
    import numpy as np
    from backend.tests.hand_factory import pose
    hand = np.asarray(pose('OPEN_PALM'), dtype=float)
    wrist = hand[0, :2].copy()
    v = hand[:, :2] - wrist
    rot = np.array([[0.0, -1.0], [1.0, 0.0]]) if direction > 0 else np.array([[0.0, 1.0], [-1.0, 0.0]])
    hand[:, :2] = wrist + v @ rot.T
    return hand.tolist()


def test_sideways_open_palm_is_the_sketch_inspect_command():
    r = SketchGestureRecognizer(aspect=1.0)
    r.classify(_rotated_open_palm(-1))
    assert r.classify(_rotated_open_palm(-1))[0] == 'PALM_LEFT'


def test_sideways_thumbs_are_sketch_undo_redo_commands():
    import numpy as np
    from backend.sketch.recognition import classify_pose
    from backend.tests.hand_factory import pose
    for sign, expected in ((1, 'THUMBS_RIGHT'), (-1, 'THUMBS_LEFT')):
        hand = np.asarray(pose('FIST'), dtype=float)
        base = hand[1, :2].copy()
        tip = base + np.array([sign * 0.16, -0.01])
        for idx, t in ((2, .4), (3, .7), (4, 1.0)):
            hand[idx, :2] = base + (tip - base) * t
        assert classify_pose(hand) == expected


def test_engine_undo_redo_round_trip():
    from backend.sketch.engine import SketchEngine
    e = SketchEngine(aspect=1.0, params={'smooth_tip': False})
    for p in ((.1, .1), (.2, .1), (.3, .1)):
        e.update('DRAW', p, 0.0)
    e.update('PAUSE', None, 1.0)
    for p in ((.5, .5), (.6, .5)):
        e.update('DRAW', p, 2.0)
    assert e.point_count == 5
    assert e.undo_stroke() and e.point_count == 3
    assert e.redo_stroke() and e.point_count == 5


def test_screen_left_palm_is_inspect_command_and_right_is_not():
    import numpy as np
    from backend.sketch.recognition import classify_pose
    hand_left = np.asarray(_rotated_open_palm(-1), dtype=float)
    hand_right = np.asarray(_rotated_open_palm(1), dtype=float)
    assert classify_pose(hand_left) == 'PALM_LEFT'
    assert classify_pose(hand_right) != 'PALM_LEFT'


def test_pipeline_palm_left_enters_and_exits_3d_inspect_directly():
    import numpy as np
    from backend.main import state

    state.modes.paused = False
    state.modes.set_mode("SKETCH")
    state.apply_settings()
    state.sketch.clear()
    state.sketch.model = {"id": 999, "outline": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]], "height": 0.6}
    state.sketch_inspector.reset()
    state._palm_left_frames = 0
    state._palm_left_latched = False

    hand = _rotated_open_palm(-1)
    t = 900.0

    actions = []
    for _ in range(4):
        *_, event_name, action = state.process(hand, t)
        t += 0.033
        if action:
            actions.append((event_name, action))

    assert state.sketch_inspector.inspecting is True
    assert ("PALM_LEFT", "3D Inspect Mode") in actions

    # Release the pose before trying it again; the latch must clear.
    for _ in range(3):
        state.process(pose("INDEX_POINT"), t)
        t += 0.033

    actions = []
    for _ in range(4):
        *_, event_name, action = state.process(hand, t)
        t += 0.033
        if action:
            actions.append((event_name, action))

    assert state.sketch_inspector.inspecting is False
    assert ("PALM_LEFT", "Returned to Sketch") in actions
    state.modes.set_mode("DESKTOP")
    state.sketch.clear()
    state.sketch_inspector.reset()


def test_inspect_mode_blocks_pause_and_preserves_model_on_return():
    from backend.main import state
    state.modes.paused = False
    state.modes.set_mode("SKETCH")
    state.apply_settings()
    state.sketch.clear()
    state.sketch.model = {"id": 1001, "outline": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]], "height": 0.6}
    state.sketch_inspector.reset()
    state._palm_left_frames = 0
    state._palm_left_latched = False
    state._inspect_transition_until = 0.0

    left = _rotated_open_palm(-1)
    t = 1200.0
    for _ in range(4):
        state.process(left, t); t += 0.033
    assert state.sketch_inspector.inspecting is True
    assert state.paused is False
    model_id = state.sketch.model["id"]

    # Ordinary open palm must not pause the application while inspecting.
    from backend.tests.hand_factory import pose
    for _ in range(4):
        state.process(pose("OPEN_PALM"), t); t += 0.033
    assert state.sketch_inspector.inspecting is True
    assert state.paused is False
    assert state.sketch.model["id"] == model_id

    # Release and toggle out with PALM_LEFT again.
    for _ in range(4):
        state.process(pose("INDEX_POINT"), t); t += 0.033
    for _ in range(4):
        state.process(left, t); t += 0.033
    assert state.sketch_inspector.inspecting is False
    assert state.sketch.model is not None
    assert state.sketch.model["id"] == model_id

    state.modes.set_mode("DESKTOP")
    state.sketch.clear()
    state.sketch_inspector.reset()

# ---------------------------------------------------------------------------
# V14 recognition diagnostics / geometry regressions

def test_v14_finger_geometry_is_normalised_and_exposed():
    from backend.sketch.recognition import _finger_geometry, FINGER_CHAINS
    import numpy as np

    hand = np.asarray(pose("INDEX_POINT"), dtype=np.float32)
    g = _finger_geometry(hand, FINGER_CHAINS[0], 1.0)

    assert 0.0 <= g["extension"] <= 1.0
    assert 0.0 <= g["bend"] <= 1.0
    assert g["tip_reach"] > g["mcp_reach"]


def test_v14_debug_contains_geometry_for_all_four_fingers():
    r = SketchGestureRecognizer(aspect=1.0)
    r.classify(pose("INDEX_POINT"))

    geometry = r.debug["finger_geometry"]
    assert len(geometry) == 4
    assert all({"extension", "bend", "tip_reach", "pip_angle", "dip_angle"} <= set(g) for g in geometry)


def test_v14_geometry_does_not_change_pose_api():
    from backend.sketch.recognition import classify_pose

    assert classify_pose(pose("INDEX_POINT")) == "DRAW"
    assert classify_pose(pose("PEACE")) == "ERASE"
    assert classify_pose(pose("FIST")) == "FIST"
    assert classify_pose(pose("OPEN_PALM")) == "PAUSE"

# ---------------------------------------------------------------------------
# V7 robust gesture-engine regressions


def test_v7_pose_api_is_string_compatible():
    from backend.sketch.recognition import classify_pose
    assert classify_pose(pose('INDEX_POINT')) == 'DRAW'
    assert classify_pose(pose('FIST')) == 'FIST'


def test_v7_palm_left_is_stable_and_exposes_debug():
    r = SketchGestureRecognizer(aspect=1.0, history=7, hold_frames=3)
    hand = _rotated_open_palm(-1)
    assert r.classify(hand)[0] == 'OTHER'
    assert r.classify(hand)[0] == 'PALM_LEFT'
    assert r.debug['locked'] is True
    assert r.debug['confidence'] > 0.8
    assert r.debug['candidate_frames'] == 0


def test_v7_one_bad_frame_does_not_flip_locked_palm_left():
    r = SketchGestureRecognizer(aspect=1.0)
    hand = _rotated_open_palm(-1)
    for _ in range(3):
        r.classify(hand)
    assert r.stable == 'PALM_LEFT'
    r.classify(pose('INDEX_POINT'))
    assert r.stable == 'PALM_LEFT'


def test_v7_palm_left_releases_after_two_nonmatching_frames():
    r = SketchGestureRecognizer(aspect=1.0)
    hand = _rotated_open_palm(-1)
    for _ in range(3):
        r.classify(hand)
    r.classify(pose('INDEX_POINT'))
    r.classify(pose('INDEX_POINT'))
    assert r.stable != 'PALM_LEFT'


def test_v7_inspector_smooths_single_hand_jitter():
    from backend.sketch.inspector import SketchInspector
    import numpy as np
    i = SketchInspector(); i.enter()
    h = np.asarray(pose('INDEX_POINT'), dtype=float)
    i.update([h.tolist()])
    before = tuple(i.rotation)
    jitter = h.copy(); jitter[:, 0] += .001; jitter[:, 1] -= .001
    i.update([jitter.tolist()])
    after = tuple(i.rotation)
    assert abs(after[0] - before[0]) < .02
    assert abs(after[1] - before[1]) < .02


def test_v7_appstate_palm_left_is_isolated_from_generic_pause():
    from backend.main import AppState
    app = AppState()
    app.modes.set_mode('SKETCH')
    app.modes.paused = False
    app.sketch.model = {'id': 77, 'outline': [[.1, .1], [.2, .1], [.2, .2]], 'height': .6}
    app.sketch_inspector.reset()
    hand = _rotated_open_palm(-1)
    t = 10.0
    events = []
    for _ in range(4):
        result = app.process(hand, t); t += .033
        if result[-1]: events.append(result[-1])
    assert app.sketch_inspector.inspecting
    assert '3D Inspect Mode' in events
    assert not app.paused
    for _ in range(4):
        app.process(pose('OPEN_PALM'), t); t += .033
    assert app.sketch_inspector.inspecting
    assert not app.paused

