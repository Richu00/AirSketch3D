import numpy as np


def test_camera_diagnose_reports_grey_dark_and_low_fps():
    from backend.tools.camera_check import diagnose

    text = " ".join(diagnose(10, 54, 12))
    assert "black-and-white" in text
    assert "dark" in text
    assert "FPS" in text


def test_camera_diagnose_reports_healthy_stream():
    from backend.tools.camera_check import diagnose

    assert "healthy" in diagnose(29, 110, 60)[0]


def test_detector_enhancement_preserves_frame_shape_and_channels():
    from backend.vision.hand_tracker import _enhance_for_detection

    frame = np.full((120, 160, 3), 40, dtype=np.uint8)
    out = _enhance_for_detection(frame)

    assert out.shape == frame.shape
    assert out.dtype == frame.dtype
    assert out.ndim == 3
    assert out.shape[2] == 3