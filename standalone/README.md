# Standalone compatibility demo

The files in this directory are retained as a backwards-compatible OpenCV/matplotlib demo for users who used the old
standalone AirSketch3D entry point.

The primary AIRCONTROL application now uses the integrated implementation under `backend/sketch/` and the React viewer
under `frontend/src/components/sketch/`. New functionality should be added there rather than duplicated here.
