from __future__ import annotations
import cv2
import numpy as np
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ultralytics import YOLO

from utils.logger import setup_logger

log = setup_logger("Detector")


# ──────────────────────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Detection:
    """
    Represents a single object detection result.

    Attributes:
        x1, y1, x2, y2 : Bounding box corners (pixels, absolute)
        confidence      : YOLO confidence score (0–1)
        class_id        : Integer class index
        class_name      : Human-readable class label
        track_id        : DeepSORT track ID (–1 if not tracked)
    """
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float
    class_id: int
    class_name: str
    track_id: int = -1

    # ── Computed Properties ───────────────────────────────────────────────────

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x1, self.y1, self.x2, self.y2)

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> tuple[int, int]:
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)

    def iou(self, other: "Detection") -> float:
        """Compute Intersection-over-Union with another Detection."""
        ix1 = max(self.x1, other.x1)
        iy1 = max(self.y1, other.y1)
        ix2 = min(self.x2, other.x2)
        iy2 = min(self.y2, other.y2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        union = self.area + other.area - inter
        return inter / union if union > 0 else 0.0


# ──────────────────────────────────────────────────────────────────────────────
# SpeedSignDetector
# ──────────────────────────────────────────────────────────────────────────────

class SpeedSignDetector:
    """
    Detects speed-limit signs in a BGR frame using YOLOv8.

    The model should be trained exclusively on speed-limit sign images.
    Class 0 is assumed to be the speed-limit sign class (adjust if needed).

    Args:
        weights_path       : Path to trained .pt weights file
        confidence_threshold: Minimum confidence to accept detection (0–1)
        iou_threshold      : NMS IoU threshold (0–1)
        device             : Inference device — "cpu", "cuda", "mps"
        imgsz              : Inference image size (must match training size)
    """

    SIGN_CLASS_ID = 0   # Update if your model uses a different class index

    def __init__(self,
                 weights_path: str,
                 confidence_threshold: float = 0.50,
                 iou_threshold: float = 0.45,
                 device: str = "cpu",
                 imgsz: int = 640):

        self.conf = confidence_threshold
        self.iou = iou_threshold
        self.device = device
        self.imgsz = imgsz
        self._model: Optional[YOLO] = None

        self._load_model(weights_path)

    # ── Public API ────────────────────────────────────────────────────────────

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """
        Run speed-sign detection on a single BGR frame.

        Args:
            frame: OpenCV BGR image (H×W×3 uint8)

        Returns:
            List of Detection objects for all signs found in the frame.
            Empty list if model not loaded or no detections above threshold.
        """
        if self._model is None:
            log.warning("Speed-sign model not loaded — skipping detection.")
            return []

        results = self._model.predict(
            source=frame,
            conf=self.conf,
            iou=self.iou,
            imgsz=self.imgsz,
            device=self.device,
            verbose=False,          # Suppress per-frame YOLO console output
        )

        detections: list[Detection] = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0])
                cls  = int(box.cls[0])
                name = self._model.names.get(cls, f"class_{cls}")
                detections.append(Detection(
                    x1=x1, y1=y1, x2=x2, y2=y2,
                    confidence=conf,
                    class_id=cls,
                    class_name=name,
                ))

        log.debug(f"Speed signs detected: {len(detections)}")
        return detections

    def is_loaded(self) -> bool:
        """Return True if the model weights were loaded successfully."""
        return self._model is not None

    # ── Private ───────────────────────────────────────────────────────────────

    def _load_model(self, weights_path: str) -> None:
        """Load YOLO weights; log a warning (not crash) if file missing."""
        path = Path(weights_path)
        if not path.exists():
            log.warning(
                f"Speed-sign weights not found at '{weights_path}'. "
                "Detection will be skipped until the file is placed there. "
                "Expected: models/speed_limit_model.pt"
            )
            return
        try:
            self._model = YOLO(str(path))
            self._model.to(self.device)
            log.info(f"Speed-sign model loaded from '{weights_path}' on {self.device}")
        except Exception as e:
            log.error(f"Failed to load speed-sign model: {e}")
            self._model = None


# ──────────────────────────────────────────────────────────────────────────────
# VehicleDetector
# ──────────────────────────────────────────────────────────────────────────────

class VehicleDetector:
    """
    Detects vehicles (car, motorcycle, bus, truck) in a BGR frame using
    a pretrained YOLOv8 COCO model.

    COCO vehicle class IDs:
        2  → car
        3  → motorcycle
        5  → bus
        7  → truck

    Args:
        weights_path       : Path or name of pretrained model (e.g. "yolov8n.pt")
        confidence_threshold: Minimum detection confidence
        iou_threshold      : NMS IoU threshold
        device             : Inference device
        vehicle_class_ids  : List of COCO class IDs to keep
    """

    DEFAULT_VEHICLE_CLASSES = {2: "Car", 3: "Motorcycle", 5: "Bus", 7: "Truck"}

    def __init__(self,
                 weights_path: str = "yolov8n.pt",
                 confidence_threshold: float = 0.40,
                 iou_threshold: float = 0.45,
                 device: str = "cpu",
                 vehicle_class_ids: Optional[list[int]] = None):

        self.conf = confidence_threshold
        self.iou = iou_threshold
        self.device = device
        self.vehicle_ids = vehicle_class_ids or list(self.DEFAULT_VEHICLE_CLASSES.keys())
        self._model: Optional[YOLO] = None

        self._load_model(weights_path)

    # ── Public API ────────────────────────────────────────────────────────────

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """
        Run vehicle detection on a single BGR frame.

        Returns:
            List of Detection objects for all vehicles found.
        """
        if self._model is None:
            return []

        results = self._model.predict(
            source=frame,
            conf=self.conf,
            iou=self.iou,
            classes=self.vehicle_ids,   # Only detect the classes we care about
            device=self.device,
            verbose=False,
        )

        detections: list[Detection] = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls = int(box.cls[0])
                if cls not in self.vehicle_ids:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0])
                name = self.DEFAULT_VEHICLE_CLASSES.get(cls, f"vehicle_{cls}")
                detections.append(Detection(
                    x1=x1, y1=y1, x2=x2, y2=y2,
                    confidence=conf,
                    class_id=cls,
                    class_name=name,
                ))

        log.debug(f"Vehicles detected: {len(detections)}")
        return detections

    def is_loaded(self) -> bool:
        return self._model is not None

    # ── Private ───────────────────────────────────────────────────────────────

    def _load_model(self, weights_path: str) -> None:
        """
        Load the YOLO model. If the .pt file doesn't exist locally,
        Ultralytics will automatically download it from the internet.
        """
        try:
            self._model = YOLO(weights_path)
            self._model.to(self.device)
            log.info(f"Vehicle model loaded: '{weights_path}' on {self.device}")
        except Exception as e:
            log.error(f"Failed to load vehicle model '{weights_path}': {e}")
            self._model = None
