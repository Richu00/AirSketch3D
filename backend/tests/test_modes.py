from backend.modes.manager import ModeManager

APPS = [{"name": n} for n in ["Chrome", "VS Code", "Calculator", "Notepad", "File Explorer"]]


class FakeActions:
    def __init__(self): self.calls = []
    def click(self): self.calls.append(("click",))
    def screenshot(self): self.calls.append(("screenshot",)); return "/tmp/x.png"
    def launch_app(self, name): self.calls.append(("launch", name)); return True, f"Launched {name}"
    def media(self, a, presses=1): self.calls.append(("media", a, presses))
    def browser_back(self): self.calls.append(("back",))
    def browser_forward(self): self.calls.append(("forward",))


def mk():
    a = FakeActions()
    return ModeManager(a, lambda: APPS), a


def names(a): return [c[0] if c[0] != "launch" else c for c in a.calls]


# ------------------------------------------------------------- desktop
def test_thumbs_up_opens_launcher_only_and_launches_nothing():
    m, a = mk()
    assert m.handle_event("THUMBS_UP") == "Application Launcher"
    assert m.mode == "APPS" and not [c for c in a.calls if c[0] == "launch"]
    assert m.launcher_state()["items"][0] == "Chrome"


def test_screenshot_is_independent_of_thumbs_up():
    m, a = mk()
    assert m.handle_event("SCREENSHOT").startswith("Screenshot")
    assert m.mode == "DESKTOP" and a.calls == [("screenshot",)]


def test_pinch_and_fist_click_in_desktop():
    m, a = mk()
    assert m.handle_event("PINCH") == "Left Click"
    assert m.handle_event("FIST") == "Left Click"
    assert a.calls == [("click",), ("click",)]


def test_open_palm_resumes_when_paused_and_is_silent_otherwise():
    m, a = mk()
    assert m.handle_event("OPEN_PALM") == ""
    assert m.handle_event("THUMBS_DOWN") == "Gesture Control Paused" and m.paused
    assert m.handle_event("PINCH") == "" and a.calls == []          # nothing acts while paused
    assert m.handle_event("OPEN_PALM") == "Gesture Control Resumed" and not m.paused


# ------------------------------------------------------------- launcher
def test_launcher_hover_follows_finger_and_pinch_confirms():
    m, a = mk()
    m.handle_event("THUMBS_UP")
    for _ in range(20): m.update_hover(0.5, 0.3)          # centre column, top row
    assert m.hover == 1
    for _ in range(40): m.update_hover(0.9, 0.7)          # right column, bottom row -> index 5 doesn't exist (5 items)
    assert m.hover == -1
    for _ in range(40): m.update_hover(0.15, 0.7)         # left column, bottom row
    assert m.hover == 3
    assert m.handle_event("PINCH") == "Launched Notepad"
    assert ("launch", "Notepad") in a.calls and m.mode == "DESKTOP"


def test_launcher_pinch_with_nothing_hovered_does_not_launch():
    m, a = mk()
    m.handle_event("THUMBS_UP")
    assert m.handle_event("PINCH") == "No application selected"
    assert m.mode == "APPS" and not a.calls


def test_launcher_thumbs_down_cancels_without_pausing():
    m, a = mk()
    m.handle_event("THUMBS_UP")
    assert m.handle_event("THUMBS_DOWN") == "Launcher Closed"
    assert m.mode == "DESKTOP" and not m.paused


def test_launcher_ignores_click_fist_peace_and_swipes():
    m, a = mk()
    m.handle_event("THUMBS_UP")
    for g in ("FIST", "PEACE", "THUMBS_UP", "OPEN_PALM"):
        assert m.handle_event(g) == ""
    assert m.handle_swipe("SWIPE_LEFT") == "" and m.mode == "APPS" and a.calls == []


# ------------------------------------------------------------- browser
def test_browser_mode_flow():
    m, a = mk()
    assert m.handle_event("PEACE") == "Browser Mode" and m.mode == "BROWSER"
    assert m.handle_event("PEACE") == ""                              # no re-toggle
    assert m.handle_event("PINCH") == "Left Click"
    assert m.handle_swipe("SWIPE_LEFT") == "Previous" and ("back",) in a.calls
    assert m.handle_swipe("SWIPE_RIGHT") == "Next" and ("forward",) in a.calls
    assert m.handle_event("THUMBS_DOWN") == "Exited Browser Mode"
    assert m.mode == "DESKTOP" and not m.paused


# ------------------------------------------------------------- media
def media_mode():
    m, a = mk(); m.set_mode("MEDIA"); return m, a


def test_media_mapping_does_not_leak_into_normal_mode():
    m, a = media_mode()
    assert m.handle_event("OPEN_PALM") == "Play / Resume"
    assert m.handle_event("FIST") == "Pause"
    assert m.handle_event("THUMBS_UP") == "Volume Up"
    assert m.mode == "MEDIA"                                           # thumbs-up did NOT open the launcher
    assert m.handle_event("PINCH") == "" and m.handle_event("PEACE") == ""
    assert ("click",) not in a.calls
    assert ("media", "play_pause", 1) in a.calls and ("media", "volume_up", 5) in a.calls


def test_media_swipes_change_track():
    m, a = media_mode()
    m.handle_swipe("SWIPE_LEFT"); m.handle_swipe("SWIPE_RIGHT")
    assert [c for c in a.calls if c[0] == "media"] == [("media", "previous", 1), ("media", "next", 1)]


def test_media_thumbs_down_tap_is_volume_down():
    m, a = media_mode()
    assert m.handle_event("THUMBS_DOWN") == ""
    t = 10.0
    for _ in range(5): assert m.tick("THUMBS_DOWN", t) == ""; t += 0.1
    assert m.tick("NONE", t) == "Volume Down"
    assert m.mode == "MEDIA" and ("media", "volume_down", 5) in a.calls


def test_media_thumbs_down_hold_exits_and_does_not_change_volume():
    m, a = media_mode()
    t, out = 10.0, []
    for _ in range(25): out.append(m.tick("THUMBS_DOWN", t)); t += 0.1
    assert "Media Mode Exited" in out and m.mode == "DESKTOP"
    assert m.tick("NONE", t) == "" and not [c for c in a.calls if c[:2] == ("media", "volume_down")]
    assert not m.paused


def test_media_screenshot_still_works():
    m, a = media_mode()
    assert m.handle_event("SCREENSHOT").startswith("Screenshot")
