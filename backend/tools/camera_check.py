"""Camera health check for AirControl.

Run with the backend stopped:
    python -m backend.tools.camera_check
    python -m backend.tools.camera_check --index 0 --reset-exposure

This utility does not modify AirControl runtime behaviour. It measures the
actual camera stream using the same Windows DirectShow path and reports
brightness, saturation and measured FPS.
"""
import argparse
import platform
import time

import cv2
import numpy as np


def diagnose(fps, brightness, saturation):
    notes = []
    if saturation < 22:
        notes.append(
            "Picture is almost black-and-white (saturation %.0f). "
            "The camera may be in a manual-exposure, night or IR mode."
            % saturation
        )
    if brightness < 60:
        notes.append(
            "Picture is dark (brightness %.0f/255). "
            "Add light in FRONT of you or restore auto exposure."
            % brightness
        )
    elif brightness > 215:
        notes.append(
            "Picture is over-exposed (brightness %.0f/255)."
            % brightness
        )
    if fps < 18:
        notes.append(
            "Only %.1f FPS from the camera itself. "
            "The tracker cannot be faster than the camera." % fps
        )
    return notes or [
        "Camera looks healthy (%.0f FPS, brightness %.0f, saturation %.0f)."
        % (fps, brightness, saturation)
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--height", type=int, default=540)
    ap.add_argument("--reset-exposure", action="store_true")
    ap.add_argument("--frames", type=int, default=60)
    a = ap.parse_args()

    backend = cv2.CAP_DSHOW if platform.system() == "Windows" else 0
    cap = cv2.VideoCapture(a.index, backend)
    if not cap.isOpened():
        print("Could not open camera %d. Close other apps using the webcam." % a.index)
        return 1

    # Request MJPG for the diagnostic only. This does NOT change AirControl's
    # camera implementation.
    try:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    except Exception:
        pass

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, a.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, a.height)
    cap.set(cv2.CAP_PROP_FPS, 30)

    if a.reset_exposure:
        try:
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
            print("Auto exposure switch requested.")
        except Exception:
            print("Auto exposure control is not supported by this camera/backend.")

    print(
        "backend=DirectShow" if platform.system() == "Windows" else "backend=default"
    )
    print(
        "auto_exposure=%s exposure=%s reported_fps=%s size=%dx%d"
        % (
            cap.get(cv2.CAP_PROP_AUTO_EXPOSURE),
            cap.get(cv2.CAP_PROP_EXPOSURE),
            cap.get(cv2.CAP_PROP_FPS),
            cap.get(cv2.CAP_PROP_FRAME_WIDTH),
            cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
        )
    )

    for _ in range(15):
        cap.read()

    bright, sat, n = [], [], 0
    t0 = time.perf_counter()

    while n < max(1, a.frames):
        ok, frame = cap.read()
        if not ok:
            break
        n += 1
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        bright.append(float(hsv[..., 2].mean()))
        sat.append(float(hsv[..., 1].mean()))

    elapsed = time.perf_counter() - t0
    cap.release()

    if not n:
        print("No frames received.")
        return 1

    fps = n / max(elapsed, 1e-6)
    for line in diagnose(fps, float(np.mean(bright)), float(np.mean(sat))):
        print("-", line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())