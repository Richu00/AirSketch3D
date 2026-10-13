# AIRCONTROL architecture

AIRCONTROL remains the top-level application. AirSketch3D is an integrated subsystem, not a second application.

```text
Webcam
  │
  ▼
backend/vision/hand_tracker.py
  │  one detector pass; primary hand + up to two hands exposed
  ▼
backend/gestures/recognizer.py ── desktop/browser/apps/media gestures
  │
  ├── backend/actions/ ───────── computer control
  │
  └── SKETCH mode
        │
        ├── backend/sketch/recognition.py   pinch-free Sketch poses
        ├── backend/sketch/engine.py        strokes / erase / closure / build
        ├── backend/sketch/geometry.py      validation / resampling / extrusion
        └── backend/sketch/inspector.py     one/two-hand 3D inspection
                    │
                    ▼
            FastAPI WebSocket
                    │
                    ▼
frontend/src/components/sketch/SketchViewer.tsx
```

## Gesture boundary

Pinch remains part of AIRCONTROL's normal desktop/browser interaction. It is intentionally **not consumed by Sketch
mode**. Sketch has its own recognizer for DRAW, ERASE, PAUSE and FIST; screenshot and thumbs-down remain global utility
commands. This separation prevents changes to Sketch from changing desktop click/drag behavior.

## Drawing lifecycle

1. Index finger draws a smoothed fingertip path.
2. Short ambiguous detector glitches are tolerated.
3. Returning near the first point closes the component.
4. Erasing may split a stroke; invalid fragments are ignored if another valid closed component exists.
5. Fist hold validates every substantial component independently.
6. Valid components are resampled, smoothed and normalized together.
7. The frontend renders all components and can export STL/OBJ.

## Inspection lifecycle

After a model exists, a left swipe enters inspection. One-hand movement rotates; two hands pan, zoom and twist. A fist
switches the preview to solid. A right swipe returns to drawing. Existing mouse OrbitControls remain available.
