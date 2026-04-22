import cv2
import time
import random
import numpy as np
from collections import deque
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# FPS Counter
# ──────────────────────────────────────────────────────────────────────────────

class FPSCounter:
    def __init__(self, window_size: int = 30):
        self._times = deque(maxlen=window_size)
        self._last = time.perf_counter()

    def update(self) -> float:
        """Call once per processed frame. Returns current average FPS."""
        now = time.perf_counter()
        self._times.append(now - self._last)
        self._last = now
        if len(self._times) == 0:
            return 0.0
        return 1.0 / (sum(self._times) / len(self._times))

    @property
    def fps(self) -> float:
        if not self._times:
            return 0.0
        return 1.0 / (sum(self._times) / len(self._times))


# ──────────────────────────────────────────────────────────────────────────────
# Frame Utilities
# ──────────────────────────────────────────────────────────────────────────────

def resize_frame(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    """
    Resize a frame to exact (width, height).
    Fastest path — no aspect-ratio preservation (use letterbox for that).
    """
    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_LINEAR)


def letterbox_frame(frame: np.ndarray,
                    target_size: int = 640) -> tuple[np.ndarray, float, tuple]:
    """
    Resize keeping aspect ratio, pad to square with gray border.
    Standard YOLOv8 pre-processing.

    Returns:
        (padded_frame, scale, (pad_w, pad_h))
    """
    h, w = frame.shape[:2]
    scale = target_size / max(h, w)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    pad_w = (target_size - new_w) // 2
    pad_h = (target_size - new_h) // 2

    padded = cv2.copyMakeBorder(
        resized, pad_h, pad_h, pad_w, pad_w,
        cv2.BORDER_CONSTANT, value=(114, 114, 114)
    )
    return padded, scale, (pad_w, pad_h)


def crop_with_padding(frame: np.ndarray,
                      x1: int, y1: int, x2: int, y2: int,
                      pad: int = 10) -> np.ndarray:
    """
    Crop a bounding-box region from frame with optional padding.
    Clamps to frame boundaries automatically.
    """
    h, w = frame.shape[:2]
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(w, x2 + pad)
    y2 = min(h, y2 + pad)
    return frame[y1:y2, x1:x2]


# ──────────────────────────────────────────────────────────────────────────────
# Drawing / UI Overlay
# ──────────────────────────────────────────────────────────────────────────────

def draw_bounding_box(frame: np.ndarray,
                      x1: int, y1: int, x2: int, y2: int,
                      label: str,
                      color: tuple = (0, 255, 0),
                      thickness: int = 2,
                      font_scale: float = 0.6) -> None:
    """
    Draw a labelled bounding box on the frame (in-place).

    Args:
        frame     : BGR image array (modified in-place)
        x1,y1,x2,y2 : Bounding box corners in pixels
        label     : Text to display above the box
        color     : BGR tuple for box and label background
        thickness : Line thickness in pixels
        font_scale: OpenCV font scale for label text
    """
    # Box
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

    # Label background
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), baseline = cv2.getTextSize(label, font, font_scale, 1)
    bg_y1 = max(y1 - th - baseline - 4, 0)
    cv2.rectangle(frame, (x1, bg_y1), (x1 + tw + 4, y1), color, cv2.FILLED)

    # Label text
    cv2.putText(frame, label, (x1 + 2, y1 - baseline - 2),
                font, font_scale, (0, 0, 0), 1, cv2.LINE_AA)


def draw_speed_badge(frame: np.ndarray,
                     x1: int, y1: int, x2: int, y2: int,
                     speed_limit: int) -> None:
    """
    Draw a circular speed-limit badge overlay at the bottom-right of the box.
    Mimics a real traffic sign appearance.
    """
    cx = (x1 + x2) // 2
    cy = y2 + 30
    radius = 28

    # White circle background
    cv2.circle(frame, (cx, cy), radius, (255, 255, 255), cv2.FILLED)
    # Red border (standard speed sign style)
    cv2.circle(frame, (cx, cy), radius, (0, 0, 200), 3)

    text = str(speed_limit)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.7 if speed_limit < 100 else 0.55
    (tw, th), _ = cv2.getTextSize(text, font, scale, 2)
    cv2.putText(frame, text,
                (cx - tw // 2, cy + th // 2),
                font, scale, (0, 0, 0), 2, cv2.LINE_AA)


def draw_fps_overlay(frame: np.ndarray, fps: float,
                     color: tuple = (0, 255, 255)) -> None:
    """Render FPS counter in the top-left corner."""
    label = f"FPS: {fps:.1f}"
    cv2.putText(frame, label, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)


def draw_violation_alert(frame: np.ndarray,
                         vehicle_speed: float,
                         speed_limit: int) -> None:
    """
    Draw a large red VIOLATION banner at the top-center of the frame.
    Called when vehicle_speed > speed_limit.
    """
    h, w = frame.shape[:2]
    msg = f"⚠ VIOLATION! Vehicle: {vehicle_speed:.0f} km/h | Limit: {speed_limit} km/h"
    font = cv2.FONT_HERSHEY_DUPLEX
    scale = 0.75
    thickness = 2
    (tw, th), _ = cv2.getTextSize(msg, font, scale, thickness)

    # Semi-transparent red banner
    overlay = frame.copy()
    banner_h = th + 20
    cv2.rectangle(overlay, (0, 0), (w, banner_h + 10), (0, 0, 200), cv2.FILLED)
    alpha = 0.75
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

    # White text centred
    x = (w - tw) // 2
    cv2.putText(frame, msg, (x, banner_h - 8),
                font, scale, (255, 255, 255), thickness, cv2.LINE_AA)


def draw_info_panel(frame: np.ndarray,
                    frame_id: int,
                    total_detections: int,
                    total_violations: int) -> None:
    """
    Draw a stats panel in the bottom-left corner of the frame.
    Shows frame number, total detections and violations this session.
    """
    h, w = frame.shape[:2]
    lines = [
        f"Frame : {frame_id}",
        f"Signs : {total_detections}",
        f"Violations: {total_violations}",
    ]
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.5
    padding = 8
    line_h = 20
    panel_h = len(lines) * line_h + padding * 2
    panel_w = 180

    # Semi-transparent dark background
    overlay = frame.copy()
    cv2.rectangle(overlay, (5, h - panel_h - 5), (5 + panel_w, h - 5),
                  (30, 30, 30), cv2.FILLED)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    for i, line in enumerate(lines):
        y = h - panel_h - 5 + padding + (i + 1) * line_h
        cv2.putText(frame, line, (12, y),
                    font, scale, (200, 200, 200), 1, cv2.LINE_AA)


# ──────────────────────────────────────────────────────────────────────────────
# OCR Image Pre-processing
# ──────────────────────────────────────────────────────────────────────────────

def preprocess_for_ocr(crop: np.ndarray,
                       upscale_factor: float = 2.5) -> np.ndarray:
    """
    Apply a series of image processing steps to maximise Tesseract accuracy.

    Pipeline:
        1. Upscale  — larger text is easier for OCR
        2. Grayscale conversion
        3. CLAHE    — adaptive contrast enhancement
        4. Gaussian blur — reduce noise
        5. Otsu binarisation — clean black/white text
        6. Morphological closing — fill character gaps

    Args:
        crop          : BGR cropped region containing the speed sign
        upscale_factor: How much to enlarge before OCR (2–4 recommended)

    Returns:
        Binary (thresholded) grayscale image ready for Tesseract.
    """
    if crop is None or crop.size == 0:
        return crop

    # 1. Upscale
    h, w = crop.shape[:2]
    crop = cv2.resize(crop,
                      (int(w * upscale_factor), int(h * upscale_factor)),
                      interpolation=cv2.INTER_CUBIC)

    # 2. Grayscale
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # 3. CLAHE (Contrast Limited Adaptive Histogram Equalisation)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # 4. Slight Gaussian blur to reduce sensor noise
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    # 5. Otsu's binarisation
    _, binary = cv2.threshold(gray, 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 6. Morphological closing to connect broken character strokes
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    return binary


# ──────────────────────────────────────────────────────────────────────────────
# Speed Simulation (for demo / university project)
# ──────────────────────────────────────────────────────────────────────────────

class VehicleSpeedSimulator:
    """
    Simulates realistic vehicle speeds for demonstration purposes.

    In a real deployment, speed would come from:
        - Radar / lidar sensors
        - Optical flow estimation between frames
        - GPS data from connected vehicles (V2I)

    For this project, we assign a random initial speed per vehicle track ID
    and add slight Gaussian noise each frame to mimic realistic measurement.
    """
    def __init__(self, min_speed: float = 20.0, max_speed: float = 120.0):
        self._min = min_speed
        self._max = max_speed
        self._speeds: dict[int, float] = {}   # track_id → speed

    def get_speed(self, track_id: int) -> float:
        """
        Return the simulated speed for a tracked vehicle.
        Speed is initialised once and slightly jittered each call.
        """
        if track_id not in self._speeds:
            # Assign a random base speed on first encounter
            self._speeds[track_id] = random.uniform(self._min, self._max)
        # Add small Gaussian noise (±3 km/h) to simulate sensor fluctuation
        noise = random.gauss(0, 3.0)
        speed = self._speeds[track_id] + noise
        return max(self._min, min(self._max, speed))

    def reset(self, track_id: int) -> None:
        """Remove speed record for a lost track."""
        self._speeds.pop(track_id, None)
