import pytest
from backend.gestures.recognizer import GestureRecognizer
from backend.tests.hand_factory import pose, make_hand

NAMES = ["INDEX_POINT", "PINCH", "FIST", "THUMBS_UP", "THUMBS_DOWN", "SCREENSHOT", "PEACE", "OPEN_PALM"]


def classify(name_or_points, rec=None):
    rec = rec or GestureRecognizer()
    pts = pose(name_or_points) if isinstance(name_or_points, str) else name_or_points
    g, c, _ = rec.recognize(pts, now=1.0)
    return g, c


@pytest.mark.parametrize("name", NAMES)
def test_every_pose_is_recognised_confidently(name):
    g, c = classify(name)
    assert g == name, (g, c, GestureRecognizer().debug)
    assert c >= 0.85


def test_thumbs_up_is_not_screenshot_and_not_pinch():
    g, _ = classify("THUMBS_UP")
    assert g == "THUMBS_UP" and g not in ("SCREENSHOT", "PINCH")


def test_screenshot_is_ily_not_thumbs_up():
    g, _ = classify("SCREENSHOT")
    assert g == "SCREENSHOT" and g != "THUMBS_UP"


def test_pinch_is_not_thumbs_up():
    g, _ = classify("PINCH")
    assert g == "PINCH" and g != "THUMBS_UP"


def test_fist_is_not_pinch_even_with_thumb_wrapped_near_index():
    rec = GestureRecognizer()
    g, _ = classify("FIST", rec)
    assert g == "FIST"
    assert rec.debug["pinch_d"] < 0.40      # tips genuinely close, yet it must stay a FIST


def test_thumbs_up_vs_thumbs_down_direction():
    assert classify("THUMBS_UP")[0] == "THUMBS_UP"
    assert classify("THUMBS_DOWN")[0] == "THUMBS_DOWN"


def test_ily_needs_both_middle_and_ring_folded():
    # ILY with the ring finger half raised must not fire screenshot
    pts = make_hand({"middle": 1, "ring": 0.3}, "side")
    assert classify(pts)[0] != "SCREENSHOT"


def test_thumb_sideways_fist_is_unknown_not_forced():
    pts = make_hand({"index": 1, "middle": 1, "ring": 1, "pinky": 1}, "sideways_fist")
    assert classify(pts)[0] == "UNKNOWN"


def test_ambiguous_finger_gives_unknown():
    # index half-curled: neither clearly extended nor folded
    pts = make_hand({"index": 0.3, "middle": 1, "ring": 1, "pinky": 1}, "fold")
    assert classify(pts)[0] == "UNKNOWN"


def test_no_hand_is_none():
    assert GestureRecognizer().recognize([], now=1.0)[0] == "NONE"


def test_pinch_hysteresis_holds_slightly_loose_pinch():
    rec = GestureRecognizer()
    assert rec.recognize(pose("PINCH"), now=1.0)[0] == "PINCH"
    # loosen: thumb tip drifts a little away from the index tip but stays under the release limit
    pts = pose("PINCH")
    pts[4] = [pts[8][0] - 0.05 * 0.2 * 1.0, pts[8][1] + 0.04, 0.0]
    d = rec.recognize(pts, now=1.03)
    assert d[0] == "PINCH"


def test_pinch_threshold_is_configurable():
    pts = pose("PINCH")
    pts[4] = [pts[8][0] - 0.05, pts[8][1] + 0.05, 0.0]       # ~0.35 palm apart
    assert GestureRecognizer({"pinch_threshold": 0.20, "pinch_release": 0.22}).recognize(pts, now=1)[0] != "PINCH"
    assert GestureRecognizer({"pinch_threshold": 0.45, "pinch_release": 0.5}).recognize(pts, now=1)[0] == "PINCH"


def test_low_confidence_returns_unknown():
    rec = GestureRecognizer({"min_confidence": 0.999})
    assert rec.recognize(pose("OPEN_PALM"), now=1)[0] == "UNKNOWN"


def test_aspect_ratio_correction_keeps_poses_stable():
    # same hand drawn in a 16:9 frame: x coords are squeezed by 1/aspect in normalised space
    aspect = 16 / 9
    pts = [[(x - 0.5) / aspect + 0.5, y, z] for x, y, z in pose("THUMBS_UP")]
    assert GestureRecognizer(aspect=aspect).recognize(pts, now=1)[0] == "THUMBS_UP"


# ----------------------------------------------------------------- motion
def run_motion(poses_fn, xs, ys=None, dt=0.04):
    rec = GestureRecognizer()
    events, gestures = [], []
    t = 1.0
    for i, x in enumerate(xs):
        y = ys[i] if ys else 0.75
        g, c, m = rec.recognize(poses_fn(cx=x, cy=y), now=t)
        gestures.append(g)
        if m["swipe_event"]:
            events.append(m["swipe_event"])
        t += dt
    return events, gestures


def test_open_palm_swipe_right_and_left():
    xs = [0.2 + 0.05 * i for i in range(10)]
    assert run_motion(lambda **k: pose("OPEN_PALM", **k), xs)[0] == ["SWIPE_RIGHT"]
    assert run_motion(lambda **k: pose("OPEN_PALM", **k), xs[::-1])[0] == ["SWIPE_LEFT"]


def test_static_hand_never_swipes():
    assert run_motion(lambda **k: pose("OPEN_PALM", **k), [0.5] * 30)[0] == []


def test_swipe_never_fires_from_pinch_fist_thumbs_or_screenshot():
    xs = [0.2 + 0.06 * i for i in range(10)]
    for n in ("PINCH", "FIST", "THUMBS_UP", "THUMBS_DOWN", "SCREENSHOT", "PEACE"):
        ev, g = run_motion(lambda n=n, **k: pose(n, **k), xs)
        assert ev == [], n


def test_vertical_index_motion_becomes_scroll():
    ys = [0.4 + 0.03 * i for i in range(12)]
    ev, g = run_motion(lambda **k: pose("INDEX_POINT", **k), [0.5] * 12, ys)
    assert "VERTICAL_SCROLL" in g and ev == []


def test_slow_index_motion_stays_cursor_control():
    ys = [0.4 + 0.004 * i for i in range(12)]
    ev, g = run_motion(lambda **k: pose("INDEX_POINT", **k), [0.5] * 12, ys)
    assert set(g) == {"INDEX_POINT"}


def test_switching_into_index_pose_does_not_trigger_scroll():
    """Extending the index finger moves the fingertip fast; that must not count as scrolling."""
    rec = GestureRecognizer()
    t, seen = 1.0, []
    for name in ["FIST"] * 6 + ["INDEX_POINT"] * 10:
        g, c, m = rec.recognize(pose(name), now=t); seen.append(g); t += 0.033
    assert "VERTICAL_SCROLL" not in seen
