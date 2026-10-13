import math

from backend.modes.manager import ModeManager
from backend.sketch.engine import SketchEngine, build_outline
from backend.tests.hand_factory import pose
from backend.tests.test_modes import FakeActions, APPS


def circle(n=60, r=0.2, cx=0.5, cy=0.5):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def draw(eng, pts, t=0.0, dt=0.033):
    for p in pts:
        eng.update("DRAW", p, t); t += dt
    return t


# ------------------------------------------------------------------ drawing
def test_draw_adds_points_and_pause_lifts_the_pen():
    e = SketchEngine(aspect=1.0)
    t = draw(e, [(0.1, 0.1), (0.2, 0.1), (0.3, 0.1)])
    e.update("PAUSE", (0.9, 0.9), t); t += 0.033             # pen lifted: nothing is drawn
    t = draw(e, [(0.5, 0.5), (0.6, 0.5)], t)
    assert e.point_count == 5
    assert len([s for s in e.strokes if s]) == 2             # two separate strokes


def test_tiny_jitter_is_ignored():
    e = SketchEngine(aspect=1.0)
    draw(e, [(0.5, 0.5), (0.5005, 0.5), (0.5, 0.5005)])
    assert e.point_count == 1


# ------------------------------------------------------------------ erasing
def test_erase_removes_points_near_the_fingertip_only_and_splits_strokes():
    e = SketchEngine(aspect=1.0, params={"erase_radius": 0.05})
    draw(e, [(0.1 + 0.02 * i, 0.5) for i in range(30)])      # a horizontal line from x=0.1 to 0.68
    before = e.point_count
    e.update("ERASE", (0.4, 0.5), 5.0)
    assert 0 < e.point_count < before
    strokes = [s for s in e.strokes if s]
    assert len(strokes) == 2                                  # the line was cut in two
    assert all(abs(x - 0.4) >= 0.05 for s in strokes for x, _ in s)


def test_erase_far_away_changes_nothing():
    e = SketchEngine(aspect=1.0)
    draw(e, circle())
    v, n = e.version, e.point_count
    e.update("ERASE", (0.95, 0.95), 5.0)
    assert e.version == v and e.point_count == n


# --------------------------------------------------------------- generation
def test_fist_hold_generates_model_once():
    e = SketchEngine(aspect=1.0)
    t = draw(e, circle())
    events = []
    for _ in range(40):                                       # ~1.3 s of fist
        events.append(e.update("FIST", None, t)); t += 0.033
    assert sum(1 for x in events if x.startswith("3D model generated")) == 1
    assert e.model and e.model["id"] == 1 and len(e.model["outline"]) == 96
    xs = [p[0] for p in e.model["outline"]]; ys = [p[1] for p in e.model["outline"]]
    assert max(abs(v) for v in xs + ys) <= 1.0001             # normalised into [-1, 1]


def test_short_fist_does_not_generate_and_progress_reports():
    e = SketchEngine(aspect=1.0)
    t = draw(e, circle())
    for _ in range(5): e.update("FIST", None, t); t += 0.033
    assert e.model is None and 0 < e.fist_progress(t) < 1
    e.update("PAUSE", None, t)
    assert e.fist_progress(t) == 0


def test_fist_with_too_few_points_warns_once_and_makes_no_model():
    e = SketchEngine(aspect=1.0)
    draw(e, [(0.1, 0.1), (0.2, 0.2), (0.3, 0.1)])
    t, events = 10.0, []
    for _ in range(60): events.append(e.update("FIST", None, t)); t += 0.033
    assert e.model is None
    assert len([x for x in events if x]) == 1 and "Draw more" in [x for x in events if x][0]


def test_regenerating_after_releasing_the_fist_makes_a_new_model():
    e = SketchEngine(aspect=1.0)
    t = draw(e, circle())
    for _ in range(40): e.update("FIST", None, t); t += 0.033
    e.update("PAUSE", None, t); t += 0.033
    for _ in range(40): e.update("FIST", None, t); t += 0.033
    assert e.model["id"] == 2


def test_circle_stays_round_on_a_wide_frame():
    aspect = 16 / 9
    pts = [(0.5 + 0.2 * math.cos(a) / aspect, 0.5 + 0.2 * math.sin(a)) for a in [2 * math.pi * i / 60 for i in range(60)]]
    out = build_outline(pts, 80, aspect)
    w = out[:, 0].max() - out[:, 0].min(); h = out[:, 1].max() - out[:, 1].min()
    assert abs(w - h) < 0.05


def test_short_none_dropout_does_not_split_drawing_stroke():
    e = SketchEngine(aspect=1.0, params={"hand_loss_grace_ms": 350})
    t = draw(e, [(0.1 + 0.02 * i, 0.5) for i in range(20)])
    strokes_before = len([s for s in e.strokes if s])
    e.update("NONE", None, t); t += 0.033
    e.update("NONE", None, t); t += 0.033
    draw(e, [(0.6 + 0.02 * i, 0.5) for i in range(10)], t)
    assert len([s for s in e.strokes if s]) == strokes_before


def test_short_other_dropout_does_not_split_drawing_stroke():
    e = SketchEngine(aspect=1.0, params={"hand_loss_grace_ms": 350})
    t = draw(e, [(0.1 + 0.02 * i, 0.5) for i in range(20)])
    strokes_before = len([s for s in e.strokes if s])
    e.update("OTHER", None, t); t += 0.033
    e.update("OTHER", None, t); t += 0.033
    draw(e, [(0.6 + 0.02 * i, 0.5) for i in range(10)], t)
    assert len([s for s in e.strokes if s]) == strokes_before


def test_long_tracking_dropout_starts_a_new_stroke():
    e = SketchEngine(aspect=1.0, params={"hand_loss_grace_ms": 100})
    t = draw(e, [(0.1 + 0.02 * i, 0.5) for i in range(20)])
    e.update("NONE", None, t); t += 0.05
    e.update("OTHER", None, t); t += 0.06
    e.update("NONE", None, t); t += 0.06
    draw(e, [(0.6 + 0.02 * i, 0.5) for i in range(10)], t)
    assert len([s for s in e.strokes if s]) == 2


def test_pause_still_ends_drawing_session():
    e = SketchEngine(aspect=1.0)
    t = draw(e, [(0.1 + 0.02 * i, 0.5) for i in range(20)])
    e.update("PAUSE", None, t); t += 0.033
    draw(e, [(0.6 + 0.02 * i, 0.5) for i in range(10)], t)
    assert len([s for s in e.strokes if s]) == 2


def test_undo_and_clear():
    e = SketchEngine(aspect=1.0)
    t = draw(e, [(0.1, 0.1), (0.2, 0.1), (0.3, 0.1)])
    e.update("PAUSE", None, t); t += 0.033
    draw(e, [(0.5, 0.5), (0.6, 0.5)], t)
    assert e.undo_stroke() and e.point_count == 3
    e.clear()
    assert e.point_count == 0 and e.model is None


# --------------------------------------------------------------- mode logic
def test_sketch_mode_thumbs_down_exits_and_does_not_pause():
    a = FakeActions(); m = ModeManager(a, lambda: APPS); m.paused = True
    m.set_mode("SKETCH")
    assert not m.paused                                       # entering sketch un-freezes a paused desktop
    for g in ("PINCH", "FIST", "PEACE", "THUMBS_UP", "OPEN_PALM"):
        assert m.handle_event(g) == ""                        # no desktop actions leak into sketch mode
    assert m.handle_swipe("SWIPE_LEFT") == "" and a.calls == []
    assert m.handle_event("SCREENSHOT").startswith("Screenshot")
    assert m.handle_event("THUMBS_DOWN") == "Sketch Mode Exited"
    assert m.mode == "DESKTOP" and not m.paused


# ------------------------------------------------------- full pipeline
def test_full_pipeline_draw_erase_pause_fist_in_sketch_mode():
    from backend.main import state
    state.ml = None                                           # rule-based gestures for this test
    state.modes.paused = False; state.modes.set_mode("SKETCH"); state.apply_settings(); state.sketch.clear()
    # The synthetic poses are built for a square frame, so neutralise the 16:9 aspect for every recogniser
    # (the sketch recogniser is aspect-aware now: a square-frame fist read at 16:9 looks like a thumbs-up).
    state.recognizer.aspect = 1.0; state.sketch_recognizer.aspect = 1.0; state.sketch.configure(aspect=1.0)
    state.actions.click = lambda: (_ for _ in ()).throw(AssertionError("sketch mode must never click"))
    state.actions.move_cursor = lambda *a, **k: (_ for _ in ()).throw(AssertionError("sketch mode must never move the cursor"))
    t, acts = 100.0, []

    def feed(name, n, **kw):
        nonlocal t
        for _ in range(n):
            out = state.process(pose(name, **kw), t); t += 0.033
            if out[5]: acts.append(out[5])

    for i in range(60):                                       # 1 finger = draw a closed loop
        a = 2 * math.pi * i / 60
        feed("INDEX_POINT", 1, cx=0.5 + 0.18 * math.cos(a), cy=0.6 + 0.16 * math.sin(a))
    assert state.sketch.point_count > 10 and state.sketch.gesture == "DRAW"
    feed("OPEN_PALM", 5)                                      # 5 fingers = pause (a few frames of debounce lag first)
    drawn = state.sketch.point_count
    feed("OPEN_PALM", 15)                                     # ...then nothing changes any more
    assert state.sketch.point_count == drawn and state.sketch.gesture == "PAUSE"
    state.sketch.configure({"erase_radius": 0.07})
    feed("PEACE", 15, cx=0.68, cy=0.6)                         # 2 fingers = erase near the right side of the loop
    assert state.sketch.point_count < drawn and state.sketch.gesture == "ERASE"
    # Re-draw a small closed loop after erasing. The synthetic pose's index tip
    # is offset from its wrist, so compensate for that fixed offset.
    base = pose("INDEX_POINT", cx=0.5, cy=0.6)
    ox, oy = base[8][0] - 0.5, base[8][1] - 0.6
    for i in range(50):
        a = 2 * math.pi * i / 50
        tx, ty = 0.5 + 0.12 * math.cos(a), 0.6 + 0.12 * math.sin(a)
        feed("INDEX_POINT", 1, cx=tx - ox, cy=ty - oy)
    feed("FIST", 40)                                          # fist (held) = generate
    assert state.sketch.model is not None and any(a.startswith("3D model generated") for a in acts)
    assert state.modes.mode == "SKETCH"
    feed("THUMBS_DOWN", 40)                                   # thumbs down leaves sketch mode
    assert state.modes.mode == "DESKTOP"
    state.modes.set_mode("DESKTOP"); state.sketch.clear()
