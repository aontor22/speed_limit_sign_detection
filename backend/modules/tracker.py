from __future__ import annotations

import numpy as np
from typing import Optional

from utils.logger import setup_logger
from modules.detector import Detection

log = setup_logger("Tracker")


# ──────────────────────────────────────────────────────────────────────────────
# Try to import deep_sort_realtime; gracefully degrade if not installed
# ──────────────────────────────────────────────────────────────────────────────

try:
    from deep_sort_realtime.deepsort_tracker import DeepSort
    HAS_DEEPSORT = True
except ImportError:
    HAS_DEEPSORT = False
    log.warning(
        "deep-sort-realtime not installed. Tracking disabled.\n"
        "Install with: pip install deep-sort-realtime"
    )


class VehicleTracker:
    """
    Wraps DeepSORT to provide stable vehicle track IDs across frames.

    Args:
        max_age              : Max frames to keep a lost track alive
        n_init               : Min frames to confirm a track
        max_cosine_distance  : Re-ID similarity threshold (lower = stricter)
        nn_budget            : Max appearance vectors stored per track
        embedder             : Feature extractor ('mobilenet' | 'clip_RN50' | None)
    """

    def __init__(self,
                 max_age: int = 30,
                 n_init: int = 3,
                 max_cosine_distance: float = 0.4,
                 nn_budget: int = 100,
                 embedder: str = "mobilenet"):

        self._tracker = None
        self._enabled = False

        if not HAS_DEEPSORT:
            log.warning("DeepSORT not available — tracking disabled.")
            return

        try:
            self._tracker = DeepSort(
                max_age=max_age,
                n_init=n_init,
                max_cosine_distance=max_cosine_distance,
                nn_budget=nn_budget,
                embedder=embedder,
                half=False,         # Use full precision
                bgr=True,           # OpenCV frames are BGR
            )
            self._enabled = True
            log.info(
                f"DeepSORT tracker initialised "
                f"(max_age={max_age}, n_init={n_init})"
            )
        except Exception as e:
            log.error(f"Failed to initialise DeepSORT: {e}")

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self,
               detections: list[Detection],
               frame: np.ndarray
               ) -> list[Detection]:
        """
        Update tracker with new detections and return tracked detections.

        Unconfirmed tracks (fewer than n_init frames) are excluded.

        Args:
            detections : List of Detection objects from VehicleDetector
            frame      : Current BGR frame (used for Re-ID embedding)

        Returns:
            List of Detection objects with track_id populated.
            If tracking is disabled, returns input detections unchanged.
        """
        if not self._enabled or self._tracker is None:
            return detections   # Pass-through

        if not detections:
            # Advance tracker with empty list so it can age out lost tracks
            self._tracker.update_tracks([], frame=frame)
            return []

        # Convert Detection objects → DeepSORT input format
        # DeepSORT expects: [([x, y, w, h], confidence, class_name), ...]
        raw_detections = []
        for det in detections:
            w = det.x2 - det.x1
            h = det.y2 - det.y1
            raw_detections.append(
                ([det.x1, det.y1, w, h], det.confidence, det.class_name)
            )

        # Run tracker update
        try:
            tracks = self._tracker.update_tracks(raw_detections, frame=frame)
        except Exception as e:
            log.debug(f"Tracker update error: {e}")
            return detections

        # Build output: only return confirmed tracks
        tracked: list[Detection] = []
        for track in tracks:
            if not track.is_confirmed():
                continue
            tid = track.track_id
            ltrb = track.to_ltrb()          # [x1, y1, x2, y2]
            x1, y1, x2, y2 = map(int, ltrb)

            # Find matching original detection to preserve class info
            matched_det = self._find_matching_detection(detections, x1, y1, x2, y2)

            tracked.append(Detection(
                x1=x1, y1=y1, x2=x2, y2=y2,
                confidence=matched_det.confidence if matched_det else 0.0,
                class_id=matched_det.class_id if matched_det else -1,
                class_name=track.det_class or (matched_det.class_name if matched_det else "vehicle"),
                track_id=tid,
            ))

        return tracked

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    # ── Private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _find_matching_detection(detections: list[Detection],
                                  x1: int, y1: int, x2: int, y2: int,
                                  iou_threshold: float = 0.3
                                  ) -> Optional[Detection]:
        """
        Match a tracker output bbox to the closest original detection by IoU.
        """
        best, best_iou = None, 0.0
        track_area = max(1, (x2 - x1) * (y2 - y1))
        for det in detections:
            ix1 = max(x1, det.x1); iy1 = max(y1, det.y1)
            ix2 = min(x2, det.x2); iy2 = min(y2, det.y2)
            inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
            union = track_area + det.area - inter
            iou = inter / union if union > 0 else 0.0
            if iou > best_iou:
                best_iou = iou
                best = det
        return best if best_iou >= iou_threshold else None


# ──────────────────────────────────────────────────────────────────────────────
# Fallback: Simple IoU-based tracker (no deep features)
# ──────────────────────────────────────────────────────────────────────────────

class SimpleTracker:
    """
    Lightweight centroid + IoU tracker as a fallback when DeepSORT is
    not available.  Assigns integer IDs to tracks based on spatial overlap.

    Not as robust as DeepSORT (no re-ID, no Kalman prediction), but works
    for demos with minimal dependencies.
    """

    def __init__(self, iou_threshold: float = 0.3, max_missing: int = 15):
        self.iou_threshold = iou_threshold
        self.max_missing = max_missing
        self._tracks: dict[int, dict] = {}
        self._next_id = 1

    def update(self, detections: list[Detection], frame=None) -> list[Detection]:
        """Assign track IDs to detections using greedy IoU matching."""
        if not detections:
            # Increment missing counter for all tracks
            dead = [tid for tid, t in self._tracks.items()
                    if t["missing"] >= self.max_missing]
            for tid in dead:
                del self._tracks[tid]
            for t in self._tracks.values():
                t["missing"] += 1
            return []

        # Match detections to existing tracks
        unmatched_dets = list(range(len(detections)))
        for tid, track in list(self._tracks.items()):
            best_det_idx, best_iou = None, self.iou_threshold
            for i in unmatched_dets:
                iou = self._compute_iou(track["bbox"], detections[i].bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_det_idx = i
            if best_det_idx is not None:
                track["bbox"] = detections[best_det_idx].bbox
                track["missing"] = 0
                detections[best_det_idx].track_id = tid
                unmatched_dets.remove(best_det_idx)
            else:
                track["missing"] += 1
                if track["missing"] > self.max_missing:
                    del self._tracks[tid]

        # Create new tracks for unmatched detections
        for i in unmatched_dets:
            self._tracks[self._next_id] = {
                "bbox": detections[i].bbox, "missing": 0
            }
            detections[i].track_id = self._next_id
            self._next_id += 1

        return [d for d in detections if d.track_id != -1]

    @staticmethod
    def _compute_iou(b1, b2) -> float:
        ix1 = max(b1[0], b2[0]); iy1 = max(b1[1], b2[1])
        ix2 = min(b1[2], b2[2]); iy2 = min(b1[3], b2[3])
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        a1 = (b1[2]-b1[0]) * (b1[3]-b1[1])
        a2 = (b2[2]-b2[0]) * (b2[3]-b2[1])
        union = a1 + a2 - inter
        return inter / union if union > 0 else 0.0
