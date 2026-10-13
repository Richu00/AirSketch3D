from backend.gestures.stabilizer import Stabilizer

def test_stabilizer_confirms_after_frames():
    s=Stabilizer(frames=3,cooldown_ms=0)
    assert s.update('PINCH',.9,.8)[0] is None
    assert s.update('PINCH',.9,.8)[0] is None
    assert s.update('PINCH',.9,.8)[0]=='PINCH'

def test_low_confidence_ignored():
    s=Stabilizer(frames=2,cooldown_ms=0)
    assert s.update('PINCH',.2,.8)[0] is None


def test_pinch_fires_once_per_pinch_even_when_held():
    s = Stabilizer(frames=3, cooldown_ms=0)
    events = [s.update('PINCH', .95, .85)[0] for _ in range(60)]      # held for 60 frames
    assert events.count('PINCH') == 1


def test_pinch_fires_again_after_release():
    s = Stabilizer(frames=3, cooldown_ms=0)
    ev = []
    for _ in range(10): ev.append(s.update('PINCH', .95, .85)[0])
    for _ in range(4): ev.append(s.update('INDEX_POINT', .95, .85)[0])   # released
    for _ in range(10): ev.append(s.update('PINCH', .95, .85)[0])
    assert ev.count('PINCH') == 2


def test_flicker_during_hold_does_not_refire():
    s = Stabilizer(frames=3, cooldown_ms=0)
    ev = []
    for _ in range(5): ev.append(s.update('PINCH', .95, .85)[0])
    for g in ['UNKNOWN', 'PINCH', 'PINCH', 'UNKNOWN', 'PINCH', 'PINCH', 'PINCH', 'PINCH']:
        ev.append(s.update(g, .95 if g != 'UNKNOWN' else .3, .85)[0])
    assert ev.count('PINCH') == 1


def test_unknown_and_none_never_fire():
    s = Stabilizer(frames=1, cooldown_ms=0)
    assert all(s.update(g, .99, .85)[0] is None for g in ['UNKNOWN', 'NONE'] * 10)


def test_overrides_let_pinch_confirm_faster():
    s = Stabilizer(frames=6, cooldown_ms=0, overrides={'PINCH': 3})
    assert [s.update('PINCH', .95, .85)[0] for _ in range(3)][-1] == 'PINCH'
    s2 = Stabilizer(frames=6, cooldown_ms=0, overrides={'PINCH': 3})
    assert all(s2.update('FIST', .95, .85)[0] is None for _ in range(5))


def test_single_noisy_frame_does_not_trigger():
    s = Stabilizer(frames=4, cooldown_ms=0)
    for g in ['FIST', 'THUMBS_UP', 'FIST', 'THUMBS_UP', 'FIST']:
        assert s.update(g, .95, .85)[0] is None


def test_stable_gesture_tracks_with_hysteresis():
    s = Stabilizer(frames=6, cooldown_ms=0)
    for _ in range(4): s.update('INDEX_POINT', .95, .85)
    assert s.stable == 'INDEX_POINT'
    s.update('UNKNOWN', .3, .85)
    assert s.stable == 'INDEX_POINT'     # one bad frame does not drop control
    for _ in range(3): s.update('UNKNOWN', .3, .85)
    assert s.stable == 'NONE'
