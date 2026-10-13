"""Optional ML gesture classifier (SVM / MLP trained with ml/train_gesture.py).

If models/gesture_model.joblib exists, Sketch mode uses it to recognise
DRAW / ERASE / PAUSE / FIST / OTHER. If it is missing (or scikit-learn is not
installed) the rule-based recogniser is used instead - nothing else changes.
"""
import warnings
from collections import Counter, deque
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", message="X does not have valid feature names")

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "models" / "gesture_model.joblib"
VALID_LABELS = {"DRAW", "ERASE", "PAUSE", "FIST", "OTHER"}


def landmarks_to_features(points):
    """21 landmarks -> 63 numbers, independent of hand position and size."""
    pts = np.array([[p[0], p[1], p[2] if len(p) > 2 else 0.0] for p in points], dtype=float)
    pts -= pts[0]                                       # wrist becomes the origin
    scale = np.linalg.norm(pts[:, :2], axis=1).max()
    pts /= scale if scale > 0 else 1.0                  # hand size becomes 1
    return pts.flatten()


class MLGestureClassifier:
    """Predicts a sketch gesture and smooths it with majority voting (debouncing)."""

    def __init__(self, model, window=7, min_votes=5):
        self.model = model
        self.history = deque(maxlen=window)
        self.min_votes = min_votes
        self.stable = "OTHER"

    @classmethod
    def load(cls, path=MODEL_PATH, window=7, min_votes=5):
        """Return a classifier, or None if there is no usable model."""
        path = Path(path)
        if not path.exists():
            return None
        try:
            import joblib
            model = joblib.load(path)
            if not set(model.classes_) <= VALID_LABELS:
                print("[AIRCONTROL] models/gesture_model.joblib has old labels - retrain it. Using rule-based sketch gestures.")
                return None
            print("[AIRCONTROL] Loaded ML gesture model for Sketch mode.")
            return cls(model, window, min_votes)
        except Exception as exc:                        # missing sklearn, corrupt file, ...
            print(f"[AIRCONTROL] Could not load ML gesture model ({exc}). Using rule-based sketch gestures.")
            return None

    def predict(self, points):
        raw = self.model.predict(landmarks_to_features(points).reshape(1, -1))[0]
        self.history.append(str(raw))
        label, votes = Counter(self.history).most_common(1)[0]
        if votes >= self.min_votes:
            self.stable = label
        return self.stable

    def reset(self):
        self.history.clear()
        self.stable = "OTHER"
