"""
AirSketch3D standalone demo (no web UI): an OpenCV window + a rotatable matplotlib 3D window.
It uses the SAME engine, tracker and gestures as Sketch mode in the AirControl dashboard.

Run from the project root:   python -m standalone.airsketch3d
  1 finger = draw | 2 fingers = erase | open palm = pause | fist (hold) = 3D | c = clear | q = quit
"""
import subprocess
import sys
import time
from collections import Counter, deque
from pathlib import Path

import cv2
import numpy as np

from backend.gestures.ml_classifier import MLGestureClassifier
from backend.gestures.recognizer import GestureRecognizer
from backend.sketch.engine import SketchEngine
from backend.vision.hand_tracker import HandTracker

W, H = 960, 540
RULE_MAP = {"INDEX_POINT": "DRAW", "VERTICAL_SCROLL": "DRAW", "PEACE": "ERASE", "OPEN_PALM": "PAUSE", "FIST": "FIST"}


def main():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    tracker, rec, ml = HandTracker(), GestureRecognizer(aspect=W / H), MLGestureClassifier.load()
    engine, votes = SketchEngine(aspect=W / H), deque(maxlen=7)
    stable = "NONE"

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        points, _ = tracker.process(frame, draw=True)
        now = time.perf_counter()

        if points:
            if ml:
                stable = ml.predict(points)
            else:                                           # rule-based, 5-of-7 majority vote
                g, _, _ = rec.recognize(points, now)
                votes.append(RULE_MAP.get(g, "OTHER"))
                label, n = Counter(votes).most_common(1)[0]
                stable = label if n >= 5 else stable
            event = engine.update(stable, (points[8][0], points[8][1]), now)
        else:
            votes.clear(); stable = "NONE"
            event = engine.update("NONE", None, now)
            if ml: ml.reset()

        if event == "3D model generated" and engine.model:
            np.save("shape_outline.npy", np.array(engine.model["outline"]))
            cv2.destroyAllWindows(); cv2.waitKey(1)
            subprocess.run([sys.executable, str(Path(__file__).with_name("view3d.py")), "shape_outline.npy"])
            engine.clear(); votes.clear()
            continue

        for s in engine.strokes:
            for i in range(1, len(s)):
                cv2.line(frame, (int(s[i - 1][0] * w), int(s[i - 1][1] * h)), (int(s[i][0] * w), int(s[i][1] * h)), (255, 120, 0), 4)
        if points and stable == "ERASE":
            cv2.circle(frame, (int(points[8][0] * w), int(points[8][1] * h)), int(engine.p["erase_radius"] * h), (0, 0, 255), 2)
        cv2.putText(frame, f"Gesture: {stable}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
        if event and event != "3D model generated":
            cv2.putText(frame, event, (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
        cv2.putText(frame, "1 finger=draw | 2=erase | palm=pause | fist(hold)=3D | c=clear | q=quit", (10, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.imshow("AirSketch3D", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("c"):
            engine.clear()

    cap.release(); tracker.close(); cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
