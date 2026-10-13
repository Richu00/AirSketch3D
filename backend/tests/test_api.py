from fastapi.testclient import TestClient
from backend.main import app, state
from backend.tests.hand_factory import pose


def test_health_and_config_roundtrip():
    c = TestClient(app)
    assert c.get("/health").json() == {"ok": True, "service": "AIRCONTROL"}
    cfg = c.get("/config").json()
    assert cfg["gesture"]["confidence_threshold"] > 0 and "recognition" in cfg


def test_mode_endpoint_opens_launcher_state():
    c = TestClient(app)
    assert c.post("/mode", json={"mode": "apps"}).json()["mode"] == "APPS"
    assert state.modes.launcher_state()["open"] and len(state.modes.launcher_state()["items"]) >= 1
    assert c.post("/mode", json={"mode": "nonsense"}).json()["mode"] == "DESKTOP"


def test_old_frontend_settings_payload_does_not_drop_new_keys(tmp_path, monkeypatch):
    import backend.config.manager as cm
    monkeypatch.setattr(cm, "CONFIG_DIR", tmp_path)
    for n in ("settings.json",):
        (tmp_path / n).write_text("{}")
    mgr = cm.ConfigManager()
    out = mgr.save_settings({"gesture": {"confidence_threshold": 0.9}})
    assert out["gesture"]["confidence_threshold"] == 0.9 and out["recognition"]["pinch_threshold"] == 0.30


def test_full_pipeline_pose_sequence_end_to_end():
    """Feed synthetic landmark frames through AppState.process (recognizer+stabilizer+modes)."""
    state.modes.paused = False; state.modes.set_mode("DESKTOP"); state.apply_settings()
    state.recognizer.aspect = 1.0          # synthetic hands are drawn in a square frame
    state.actions.click = lambda: clicks.append(1)
    state.actions.screenshot = lambda: "shot.png"
    state.actions.move_cursor = lambda *a, **k: None
    clicks, actions, t = [], [], 100.0

    def feed(name, n):
        nonlocal t
        for _ in range(n):
            g, conf, m, st, ev, act = state.process(pose(name), t); t += 0.033
            if act: actions.append((name, act))
    feed("INDEX_POINT", 8)
    feed("PINCH", 40)                      # one long pinch -> exactly one click
    feed("INDEX_POINT", 6)
    feed("THUMBS_UP", 30)                  # opens launcher, launches nothing
    assert state.modes.mode == "APPS"
    feed("THUMBS_DOWN", 30)                # cancel (held past the 800 ms global cooldown)
    assert state.modes.mode == "DESKTOP" and not state.paused
    feed("INDEX_POINT", 6)
    feed("SCREENSHOT", 30)
    assert clicks == [1]
    acts = [a for _, a in actions]
    assert acts == ["Left Click", "Application Launcher", "Launcher Closed", "Screenshot: shot.png"]


def test_sketch_endpoints():
    c = TestClient(app)
    state.sketch.clear()
    assert c.post("/mode", json={"mode": "sketch"}).json()["mode"] == "SKETCH"
    assert c.get("/sketch").json()["points"] == 0
    r = c.post("/sketch/generate")
    assert r.status_code == 400 and not r.json()["success"]          # nothing drawn yet
    import math
    for i in range(40):
        state.sketch.update("DRAW", (0.5 + 0.2 * math.cos(i / 6.4), 0.5 + 0.2 * math.sin(i / 6.4)), i * 0.05)
    r = c.post("/sketch/generate")
    assert r.status_code == 200 and r.json()["model"]["id"] >= 1
    assert c.get("/status").json()["sketch_model"] is not None
    assert c.post("/sketch/undo").json()["success"]
    assert c.post("/sketch/clear").json()["success"] and c.get("/sketch").json()["points"] == 0
    c.post("/mode", json={"mode": "DESKTOP"})
