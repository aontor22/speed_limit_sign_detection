import os
import csv
import json
import logging
import datetime
from pathlib import Path

try:
    import colorlog
    HAS_COLORLOG = True
except ImportError:
    HAS_COLORLOG = False


# ──────────────────────────────────────────────────────────────────────────────
# Console / File Logger
# ──────────────────────────────────────────────────────────────────────────────

def setup_logger(name: str = "SpeedLimitSystem",
                 level: str = "INFO",
                 log_dir: str = "logs") -> logging.Logger:
    """
    Create and return a named logger with:
      - Colourised console output  (if colorlog installed)
      - Plain-text rotating file output  logs/<name>.log

    Args:
        name  : Logger name (shown in every line)
        level : Logging level string — DEBUG | INFO | WARNING | ERROR
        log_dir: Directory to write .log file

    Returns:
        Configured logging.Logger instance
    """
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers when module is re-imported
    if logger.handlers:
        return logger

    # ── Console Handler ──────────────────────────────────────────────────────
    if HAS_COLORLOG:
        fmt = "%(log_color)s%(asctime)s [%(levelname)-8s] %(name)s%(reset)s — %(message)s"
        color_fmt = colorlog.ColoredFormatter(
            fmt,
            datefmt="%H:%M:%S",
            log_colors={
                "DEBUG":    "cyan",
                "INFO":     "green",
                "WARNING":  "yellow",
                "ERROR":    "red",
                "CRITICAL": "bold_red",
            },
        )
        ch = logging.StreamHandler()
        ch.setFormatter(color_fmt)
    else:
        fmt = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))

    logger.addHandler(ch)

    # ── File Handler ─────────────────────────────────────────────────────────
    try:
        from logging.handlers import RotatingFileHandler
        log_file = Path(log_dir) / f"{name}.log"
        fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(fh)
    except Exception as e:
        logger.warning(f"Could not create file handler: {e}")

    return logger


# ──────────────────────────────────────────────────────────────────────────────
# Detection Event Logger  (CSV + JSON)
# ──────────────────────────────────────────────────────────────────────────────

class DetectionLogger:
    """
    Logs every speed-limit detection event to both CSV and JSON files.

    Each record contains:
        timestamp, frame_id, speed_limit, confidence,
        bbox (x1,y1,x2,y2), ocr_text, vehicle_speed, violation

    Args:
        csv_path  : Path to output CSV file
        json_path : Path to output JSON file
        log_interval : Write to disk every N events (buffered for performance)
    """

    CSV_FIELDS = [
        "timestamp", "frame_id", "speed_limit_kmh",
        "confidence", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2",
        "ocr_raw", "vehicle_id", "vehicle_speed_kmh", "is_violation"
    ]

    def __init__(self,
                 csv_path: str = "logs/detections.csv",
                 json_path: str = "logs/detections.json",
                 log_interval: int = 1):

        self.csv_path = Path(csv_path)
        self.json_path = Path(json_path)
        self.log_interval = log_interval
        self._buffer: list[dict] = []
        self._all_records: list[dict] = []
        self._event_count = 0

        # Ensure directories exist
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)

        # Write CSV header if file is new
        if not self.csv_path.exists():
            with open(self.csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_FIELDS)
                writer.writeheader()

        # Load existing JSON if present
        if self.json_path.exists():
            try:
                with open(self.json_path, "r") as f:
                    self._all_records = json.load(f)
            except Exception:
                self._all_records = []

    # ── Public API ────────────────────────────────────────────────────────────

    def log(self,
            frame_id: int,
            speed_limit: int | None,
            confidence: float,
            bbox: tuple[int, int, int, int],
            ocr_raw: str = "",
            vehicle_id: int | None = None,
            vehicle_speed: float | None = None,
            is_violation: bool = False) -> None:
        """
        Record one detection event.

        Args:
            frame_id     : Video frame number
            speed_limit  : Parsed speed value in km/h (None if OCR failed)
            confidence   : YOLO detection confidence (0–1)
            bbox         : Bounding box (x1, y1, x2, y2) in pixels
            ocr_raw      : Raw string returned by Tesseract
            vehicle_id   : Tracker ID of nearest vehicle (optional)
            vehicle_speed: Estimated/simulated vehicle speed (km/h)
            is_violation : True if vehicle speed exceeds speed limit
        """
        record = {
            "timestamp":        datetime.datetime.now().isoformat(),
            "frame_id":         frame_id,
            "speed_limit_kmh":  speed_limit,
            "confidence":       round(confidence, 4),
            "bbox_x1":          bbox[0],
            "bbox_y1":          bbox[1],
            "bbox_x2":          bbox[2],
            "bbox_y2":          bbox[3],
            "ocr_raw":          ocr_raw,
            "vehicle_id":       vehicle_id,
            "vehicle_speed_kmh": round(vehicle_speed, 1) if vehicle_speed else None,
            "is_violation":     is_violation,
        }

        self._buffer.append(record)
        self._all_records.append(record)
        self._event_count += 1

        # Flush buffer to disk periodically
        if self._event_count % self.log_interval == 0:
            self._flush()

    def close(self) -> None:
        """Flush any remaining buffered records and close files."""
        self._flush()

    def get_summary(self) -> dict:
        """Return a summary dict of session statistics."""
        total = len(self._all_records)
        violations = sum(1 for r in self._all_records if r["is_violation"])
        speeds = [r["speed_limit_kmh"] for r in self._all_records
                  if r["speed_limit_kmh"] is not None]
        return {
            "total_detections": total,
            "total_violations": violations,
            "unique_speed_limits": sorted(set(speeds)),
            "session_start": self._all_records[0]["timestamp"] if total > 0 else None,
            "session_end": self._all_records[-1]["timestamp"] if total > 0 else None,
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _flush(self) -> None:
        """Write buffered records to CSV and JSON."""
        if not self._buffer:
            return
        try:
            # CSV — append rows
            with open(self.csv_path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_FIELDS)
                writer.writerows(self._buffer)

            # JSON — rewrite entire array (keeps it valid JSON)
            with open(self.json_path, "w") as f:
                json.dump(self._all_records, f, indent=2, default=str)

        except Exception as e:
            print(f"[DetectionLogger] Flush error: {e}")
        finally:
            self._buffer.clear()
