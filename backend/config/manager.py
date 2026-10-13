import copy
import json
from pathlib import Path
from threading import RLock

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"

# Defaults keep older settings.json files (and older frontends that POST a
# smaller settings object) working: missing sections/keys are filled in.
DEFAULT_SETTINGS = {
    "gesture": {"confidence_threshold": 0.85, "stabilization_frames": 6, "cooldown_ms": 800, "sensitivity": 1.0},
    "cursor": {"sensitivity": 1.5, "smoothing": 0.72, "invert_x": False, "invert_y": False},
    "camera": {"camera_index": 0, "width": 960, "height": 540, "mirror": True, "show_landmarks": True, "show_fps": True, "exposure": None},
    "recognition": {"pinch_threshold": 0.30, "pinch_release": 0.42, "finger_extended_ratio": 1.20,
                    "finger_folded_ratio": 1.00, "thumb_extended_ratio": 0.90, "thumb_folded_ratio": 0.72,
                    "swipe_min_distance": 0.28, "swipe_cooldown_ms": 700, "scroll_min_speed": 0.55},
    "media": {"volume_steps": 5, "exit_hold_ms": 1500},
    "launcher": {"columns": 3},
    "sketch": {"extrude_height": 0.6, "fist_hold_ms": 700, "erase_radius": 0.06, "min_points": 15,
               "resample_points": 96, "gesture_history": 5, "gesture_hold_frames": 2,
               "close_snap_distance": 0.05, "min_component_area": 0.0015, "use_ml": False,
               "live_close_distance": 0.08, "auto_close_ratio": 0.45, "repair_crossings": True,
               "snap_shapes": True, "smooth_tip": True, "smooth_min_cutoff": 1.0, "smooth_beta": 2.8, "hand_loss_grace_ms": 350},
    "actions": {"gesture_mappings": {}},
}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class ConfigManager:
    def __init__(self): self.lock=RLock()
    def _load(self, name):
        with self.lock:
            return json.loads((CONFIG_DIR/name).read_text(encoding="utf-8"))
    def _save(self, name, data):
        with self.lock:
            (CONFIG_DIR/name).write_text(json.dumps(data, indent=2), encoding="utf-8")
    def settings(self):
        try:
            return _merge(DEFAULT_SETTINGS, self._load("settings.json"))
        except (OSError, ValueError):
            return copy.deepcopy(DEFAULT_SETTINGS)
    def save_settings(self, data):
        merged = _merge(self.settings(), data)
        self._save("settings.json", merged)
        return merged
    def applications(self): return self._load("applications.json")
    def websites(self): return self._load("websites.json")
    def gestures(self): return self._load("gestures.json")
