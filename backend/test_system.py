"""
test_system.py
==============
System verification script. Run this FIRST to confirm all dependencies
are installed and the pipeline works end-to-end on a synthetic test image.

Usage:
    python test_system.py

Expected output on success:
    [PASS] OpenCV
    [PASS] PyTorch
    [PASS] Ultralytics YOLOv8
    [PASS] Tesseract OCR
    [PASS] DeepSORT  (or [WARN] if not installed)
    [PASS] Config loading
    [PASS] OCR pipeline
    [PASS] Helper functions
    ✅  All core tests passed!
"""

import sys
import cv2
import numpy as np


def print_result(name: str, passed: bool, detail: str = "") -> None:
    icon = "[PASS]" if passed else "[FAIL]"
    print(f"  {icon}  {name}" + (f" — {detail}" if detail else ""))


def test_opencv():
    try:
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.rectangle(img, (10, 10), (90, 90), (0, 255, 0), 2)
        print_result("OpenCV", True, cv2.__version__)
        return True
    except Exception as e:
        print_result("OpenCV", False, str(e))
        return False


def test_pytorch():
    try:
        import torch
        t = torch.tensor([1.0, 2.0, 3.0])
        _ = t.mean()
        print_result("PyTorch", True, torch.__version__)
        return True
    except Exception as e:
        print_result("PyTorch", False, str(e))
        return False


def test_ultralytics():
    try:
        from ultralytics import YOLO
        print_result("Ultralytics YOLOv8", True)
        return True
    except Exception as e:
        print_result("Ultralytics YOLOv8", False, str(e))
        return False


def test_tesseract():
    try:
        import pytesseract
        version = pytesseract.get_tesseract_version()
        # Create a white image with black text "60"
        img = np.ones((100, 200, 3), dtype=np.uint8) * 255
        cv2.putText(img, "60", (50, 70), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0,0,0), 3)
        from PIL import Image
        text = pytesseract.image_to_string(
            Image.fromarray(img),
            config="--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789"
        ).strip()
        print_result("Tesseract OCR", True, f"v{version} | test read: '{text}'")
        return True
    except Exception as e:
        print_result("Tesseract OCR", False,
                     f"{e}\nInstall: sudo apt install tesseract-ocr  |  "
                     "Windows: https://github.com/UB-Mannheim/tesseract/wiki")
        return False


def test_deepsort():
    try:
        from deep_sort_realtime.deepsort_tracker import DeepSort
        print_result("DeepSORT", True)
        return True
    except ImportError:
        print_result("DeepSORT", None,  # Warning, not failure
                     "Not installed (optional). pip install deep-sort-realtime")
        return None  # Not a critical failure


def test_config():
    try:
        from backend.utils.config_loader import load_config
        cfg = load_config("config.yaml")
        assert cfg.model.confidence_threshold > 0
        print_result("Config loading", True, f"confidence={cfg.model.confidence_threshold}")
        return True
    except Exception as e:
        print_result("Config loading", False, str(e))
        return False


def test_ocr_pipeline():
    try:
        from backend.modules.ocr import SpeedOCR
        from backend.utils.helpers import preprocess_for_ocr

        # Synthesise a fake speed sign image
        img = np.ones((100, 100, 3), dtype=np.uint8) * 255
        cv2.circle(img, (50, 50), 45, (200, 200, 200), -1)
        cv2.circle(img, (50, 50), 45, (0, 0, 200), 3)
        cv2.putText(img, "80", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)

        processed = preprocess_for_ocr(img, upscale_factor=2.0)
        assert processed is not None and processed.size > 0

        ocr = SpeedOCR()
        speed, raw, conf = ocr.extract_speed_from_crop(img)
        print_result("OCR pipeline", True, f"speed={speed} raw='{raw}' conf={conf:.0f}")
        return True
    except Exception as e:
        print_result("OCR pipeline", False, str(e))
        return False


def test_helpers():
    try:
        from backend.utils.helpers import (
            FPSCounter, resize_frame, draw_bounding_box,
            draw_fps_overlay, VehicleSpeedSimulator
        )
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        resized = resize_frame(frame, 320, 240)
        assert resized.shape == (240, 320, 3)

        draw_bounding_box(frame, 10, 10, 200, 100, "Test 95%")
        draw_fps_overlay(frame, 29.7)

        fps = FPSCounter()
        import time
        time.sleep(0.01)
        f = fps.update()
        assert f > 0

        sim = VehicleSpeedSimulator(20, 120)
        s = sim.get_speed(42)
        assert 20 <= s <= 120

        print_result("Helper functions", True)
        return True
    except Exception as e:
        print_result("Helper functions", False, str(e))
        return False


def test_detectors():
    try:
        from backend.modules.detector import SpeedSignDetector, VehicleDetector, Detection
        # Just test instantiation — model file may not exist
        det = SpeedSignDetector("models/speed_limit_model.pt")
        # Test Detection dataclass
        d = Detection(10, 20, 200, 300, 0.95, 0, "speed_sign")
        assert d.width == 190 and d.height == 280
        print_result("Detector module", True,
                     "model loaded" if det.is_loaded() else "model file missing (OK for test)")
        return True
    except Exception as e:
        print_result("Detector module", False, str(e))
        return False


# ──────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 55)
    print("  Speed Limit Detection System — Dependency Check")
    print("=" * 55 + "\n")

    results = [
        test_opencv(),
        test_pytorch(),
        test_ultralytics(),
        test_tesseract(),
        test_deepsort(),   # returns None (warning) if missing
        test_config(),
        test_helpers(),
        test_ocr_pipeline(),
        test_detectors(),
    ]

    # Filter out None (warnings)
    failures = [r for r in results if r is False]

    print("\n" + "─" * 55)
    if not failures:
        print("  ✅  All core tests passed! Ready to run app.py\n")
    else:
        print(f"  ❌  {len(failures)} test(s) failed. Fix errors above before running.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
