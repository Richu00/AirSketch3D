# Models

- `hand_landmarker.task` — MediaPipe Tasks hand model. It is used when the installed MediaPipe runtime exposes the Tasks API.
- `gesture_model.joblib` — optional legacy training artifact. The live AIRCONTROL Sketch mode does **not** depend on it;
  Sketch uses the deterministic pinch-free recognizer in `backend/sketch/recognition.py`. The files under `ml/` remain for
  experimentation/training only.
