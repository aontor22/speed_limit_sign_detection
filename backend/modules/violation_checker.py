from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from modules.detector import Detection
from utils.logger import setup_logger

log = setup_logger("ViolationChecker")


# ──────────────────────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ViolationEvent:
    """
    Represents a single speed violation event.

    Attributes:
        track_id     : Tracker ID of the offending vehicle
        vehicle_speed: Measured / simulated speed in km/h
        speed_limit  : The posted speed limit in km/h
        excess_speed : How much over the limit (speed - limit)
        class_name   : Vehicle type (car, bus, etc.)
        timestamp    : Unix timestamp of the event
        bbox         : (x1,y1,x2,y2) of the vehicle in the frame
    """
    track_id: int
    vehicle_speed: float
    speed_limit: int
    excess_speed: float
    class_name: str
    timestamp: float = field(default_factory=time.time)
    bbox: tuple = field(default_factory=tuple)

    @property
    def severity(self) -> str:
        """Classify the severity of the violation."""
        if self.excess_speed < 10:
            return "MINOR"
        elif self.excess_speed < 25:
            return "MODERATE"
        else:
            return "SEVERE"


# ──────────────────────────────────────────────────────────────────────────────
# ViolationChecker
# ──────────────────────────────────────────────────────────────────────────────

class ViolationChecker:
    """
    Checks whether each tracked vehicle is exceeding the current speed limit.

    Args:
        speed_tolerance     : km/h buffer before flagging (default 5)
        cooldown_frames     : Frames between repeated violation alerts per track
    """

    def __init__(self,
                 speed_tolerance: float = 5.0,
                 cooldown_frames: int = 30):
        self.tolerance = speed_tolerance
        self.cooldown = cooldown_frames

        # Track last violation frame per track ID to prevent alert spam
        self._last_violation_frame: dict[int, int] = {}
        self._violation_history: list[ViolationEvent] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def check(self,
              vehicle_detections: list[Detection],
              vehicle_speeds: dict[int, float],
              speed_limit: Optional[int],
              frame_id: int
              ) -> list[ViolationEvent]:
        """
        Evaluate all tracked vehicles against the current speed limit.

        Args:
            vehicle_detections : Tracked vehicle Detection objects
            vehicle_speeds     : Dict mapping track_id → speed (km/h)
            speed_limit        : Current road speed limit (from OCR), or None
            frame_id           : Current frame number (for cooldown logic)

        Returns:
            List of ViolationEvent objects for violations in this frame.
            May be empty if no violations or speed_limit is unknown.
        """
        if speed_limit is None:
            return []

        violations: list[ViolationEvent] = []

        for det in vehicle_detections:
            tid = det.track_id
            speed = vehicle_speeds.get(tid)
            if speed is None:
                continue

            # Check cooldown to avoid flooding with alerts
            last_frame = self._last_violation_frame.get(tid, -self.cooldown)
            if frame_id - last_frame < self.cooldown:
                continue

            # Is this vehicle over the limit?
            if speed > speed_limit + self.tolerance:
                excess = speed - speed_limit
                event = ViolationEvent(
                    track_id=tid,
                    vehicle_speed=speed,
                    speed_limit=speed_limit,
                    excess_speed=excess,
                    class_name=det.class_name,
                    bbox=det.bbox,
                )
                violations.append(event)
                self._violation_history.append(event)
                self._last_violation_frame[tid] = frame_id

                log.warning(
                    f"VIOLATION | Track {tid} ({det.class_name}) "
                    f"@ {speed:.1f} km/h (limit {speed_limit}) "
                    f"[{event.severity}]"
                )

        return violations

    def get_history(self) -> list[ViolationEvent]:
        """Return all violation events recorded this session."""
        return list(self._violation_history)

    def get_stats(self) -> dict:
        """Return summary statistics of violations."""
        total = len(self._violation_history)
        if total == 0:
            return {"total": 0}
        severities = {"MINOR": 0, "MODERATE": 0, "SEVERE": 0}
        speeds = []
        for v in self._violation_history:
            severities[v.severity] += 1
            speeds.append(v.vehicle_speed)
        return {
            "total": total,
            "severities": severities,
            "avg_excess_speed": sum(v.excess_speed for v in self._violation_history) / total,
            "max_speed_recorded": max(speeds),
        }

    def reset_cooldown(self, track_id: int) -> None:
        """Reset the violation cooldown for a specific track (e.g., new track ID)."""
        self._last_violation_frame.pop(track_id, None)
