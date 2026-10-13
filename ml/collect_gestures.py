"""
Collect gesture training data for the Sketch-mode ML classifier.

Run from the project root (AirControl backend must NOT be running - it owns the webcam):
    python -m ml.collect_gestures --person nilesh

Keys (press once to start recording that label, press again to stop):
  d -> DRAW  (index finger only)      e -> ERASE (index + middle finger)
  p -> PAUSE (open palm, 5 fingers)   f -> FIST
  n -> OTHER (any other hand shape: half open, pointing, pinching...)
  x -> stop recording                 q -> quit

Tip: vary distance, angle and lighting. Aim for 500+ samples per label per person.
Samples are appended to ml/data/gesture_data.csv (63 landmark features + label + person).
"""
import argparse
import csv
from pathlib import Path

import cv2

from backend.gestures.ml_classifier import landmarks_to_features
from backend.vision.hand_tracker import HandTracker

CSV_PATH = Path(__file__).resolve().parent / "data" / "gesture_data.csv"
KEY_TO_LABEL = {ord("d"): "DRAW", ord("e"): "ERASE", ord("p"): "PAUSE", ord("f"): "FIST", ord("n"): "OTHER"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--person", required=True, help="your name (lets train_gesture.py test on a teammate)")
    parser.add_argument("--camera", type=int, default=0)
    args = parser.parse_args()

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_file = not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0     # also repairs an empty file from a crash
    f = open(CSV_PATH, "a", newline="")
    writer = csv.writer(f)
    if new_file:
        writer.writerow(["label", "person"] + [f"f{i}" for i in range(63)])

    counts = {k: 0 for k in ("DRAW", "ERASE", "PAUSE", "FIST", "OTHER")}
    recording = None
    cap = cv2.VideoCapture(args.camera)
    tracker = HandTracker()

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        points, _ = tracker.process(frame, draw=True)
        if points and recording:
            writer.writerow([recording, args.person] + list(landmarks_to_features(points)))
            counts[recording] += 1

        cv2.putText(frame, f"Recording: {recording}" if recording else "Not recording", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255) if recording else (0, 255, 255), 2)
        cv2.putText(frame, " | ".join(f"{k} {v}" for k, v in counts.items()), (10, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, "d=draw e=erase p=pause f=fist n=other x=stop q=quit", (10, frame.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        cv2.imshow("Collect gestures", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("x"):
            recording = None
        elif key in KEY_TO_LABEL:
            new = KEY_TO_LABEL[key]
            recording = None if recording == new else new

    f.close()
    cap.release()
    tracker.close()
    cv2.destroyAllWindows()
    print("Saved to", CSV_PATH, "| samples this session:", counts)


if __name__ == "__main__":
    main()
