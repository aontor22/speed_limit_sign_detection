from __future__ import annotations

import argparse
import asyncio
import base64
import mimetypes
import os
import tempfile
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import (
    FastAPI, File, HTTPException, Query, UploadFile,
    WebSocket, WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ── Import existing pipeline — DO NOT MODIFY THESE IMPORTS ───────────────────
from app import build_system, process_frame
from utils.config_loader import load_config
from utils.logger import setup_logger
from utils.helpers import FPSCounter, resize_frame

# ──────────────────────────────────────────────────────────────────────────────
# Configuration & Logging
# ──────────────────────────────────────────────────────────────────────────────

log = setup_logger("FastAPI", level="INFO")

_CFG_PATH = os.getenv("CONFIG_PATH", "config.yaml")
try:
    CFG = load_config(_CFG_PATH)
except FileNotFoundError:
    log.warning(f"Config not found at '{_CFG_PATH}'. Using defaults.")
    CFG = None

# ──────────────────────────────────────────────────────────────────────────────
# Media validation constants
# ──────────────────────────────────────────────────────────────────────────────

_IMAGE_MIME_TYPES: frozenset[str] = frozenset({
    "image/jpeg", "image/png", "image/bmp",
    "image/tiff", "image/webp", "image/x-bmp",
})
_VIDEO_MIME_TYPES: frozenset[str] = frozenset({
    "video/mp4", "video/x-msvideo", "video/quicktime",
    "video/x-matroska", "video/webm", "video/mpeg",
    "video/x-ms-wmv", "video/3gpp",
})
_IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp",
})
_VIDEO_EXTENSIONS: frozenset[str] = frozenset({
    ".mp4", ".avi", ".mov", ".mkv", ".webm", ".mpg", ".mpeg",
    ".wmv", ".3gp", ".ts",
})

# Safety limits — all overridable via environment variables
MAX_VIDEO_FRAMES    = int(os.getenv("MAX_VIDEO_FRAMES",    "500"))
MAX_VIDEO_DURATION  = float(os.getenv("MAX_VIDEO_DURATION_S", "120.0"))
MAX_FILE_SIZE_MB    = float(os.getenv("MAX_FILE_SIZE_MB",   "500"))
FRAME_SKIP_DEFAULT  = int(os.getenv("VIDEO_FRAME_SKIP",    "2"))

# WebSocket throttle — minimum milliseconds between processed frames per connection.
# Prevents a fast sender from overloading a slow backend.
WS_MIN_FRAME_INTERVAL_MS = int(os.getenv("WS_MIN_FRAME_INTERVAL_MS", "80"))  # ~12 FPS max

# ──────────────────────────────────────────────────────────────────────────────
# Application lifespan — load ML models once, share across all requests & sockets
# ──────────────────────────────────────────────────────────────────────────────

_COMPONENTS: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Load all ML models (YOLO, OCR, DeepSORT) once at server startup.
    Shared safely across HTTP and WebSocket handlers via module-level _COMPONENTS.
    """
    global _COMPONENTS

    if CFG is None:
        log.error("Cannot start: config.yaml not found.")
        yield
        return

    fake_args = argparse.Namespace(no_vehicles=False, no_tracking=False)
    log.info("Loading ML pipeline components…")
    try:
        _COMPONENTS = build_system(CFG, fake_args)
        log.info("ML pipeline ready.")
    except Exception as exc:
        log.error(f"Pipeline failed to load: {exc}", exc_info=True)

    yield  # Server runs here

    if _COMPONENTS.get("detection_logger"):
        _COMPONENTS["detection_logger"].close()
    log.info("FastAPI server shut down.")


# ──────────────────────────────────────────────────────────────────────────────
# FastAPI App
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Speed Limit Detection API",
    version="3.0.0",
    description=(
        "Real-time speed limit sign detection via YOLOv8 + OCR + DeepSORT. "
        "Exposes HTTP batch endpoints and a WebSocket streaming endpoint."
    ),
    lifespan=lifespan,
)

_CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic Response Models
# ──────────────────────────────────────────────────────────────────────────────

class BoundingBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int


class SignResult(BaseModel):
    bbox:        BoundingBox
    confidence:  float
    ocr_text:    str
    speed_limit: int | None


class VehicleResult(BaseModel):
    id:         int
    bbox:       BoundingBox
    class_name: str
    confidence: float
    speed:      float | None


class ViolationInfo(BaseModel):
    status:       str               # "SAFE" | "WARNING" | "VIOLATION" | "NONE"
    vehicle_id:   int   | None = None
    speed:        float | None = None
    limit:        int   | None = None
    excess_speed: float | None = None
    severity:     str   | None = None


class FrameResult(BaseModel):
    frame_id:            int
    annotated_frame:     str | None = None   # base64 JPEG
    speed_signs:         list[SignResult]    = Field(default_factory=list)
    vehicles:            list[VehicleResult] = Field(default_factory=list)
    current_speed_limit: int | None = None
    violation:           ViolationInfo
    processing_time_ms:  float | None = None


class MediaSummary(BaseModel):
    total_frames_processed: int
    total_sign_detections:  int
    total_violations:       int
    unique_speed_limits:    list[int]
    avg_processing_ms:      float
    avg_fps:                float
    duration_seconds:       float
    violation_rate_pct:     float


class ProcessMediaResponse(BaseModel):
    type:    str                 # "image" | "video"
    results: list[FrameResult]
    summary: MediaSummary


# ──────────────────────────────────────────────────────────────────────────────
# Shared pipeline helpers
# (used by /api/process-frame, /api/process-media, and /ws/live-stream)
# ──────────────────────────────────────────────────────────────────────────────

def _fresh_state() -> dict:
    """
    Return a clean per-request state dict that exactly mirrors the state
    structure used in app.py's main() loop. This must stay in sync with
    app.py if that state dict ever changes.
    """
    return {
        "frame_id":              0,
        "last_speed_limit":      None,
        "speed_limit_frame":     0,
        "total_sign_detections": 0,
        "total_violations":      0,
        "fps":                   0.0,
    }


def _encode_frame_b64(frame: np.ndarray, jpeg_quality: int = 85) -> str:
    """
    Encode a BGR numpy array to a base64 JPEG string.
    Returns the raw base64 string without a 'data:' prefix.
    """
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    if not ok:
        raise RuntimeError("cv2.imencode failed — frame may be empty or corrupt.")
    return base64.b64encode(buf).decode("utf-8")


def _decode_b64_to_frame(b64_string: str) -> np.ndarray:
    """
    Decode a base64 JPEG string (with or without data: prefix) to a BGR
    numpy array suitable for the detection pipeline.

    Raises ValueError if the string cannot be decoded to a valid image.
    """
    # Strip optional data URI prefix  (data:image/jpeg;base64,<data>)
    if "," in b64_string:
        b64_string = b64_string.split(",", 1)[1]

    try:
        raw = base64.b64decode(b64_string)
    except Exception as exc:
        raise ValueError(f"Invalid base64 payload: {exc}") from exc

    arr = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None or frame.size == 0:
        raise ValueError("base64 payload decoded but could not be parsed as an image.")
    return frame


def _detect_media_kind(filename: str, content_type: str) -> str:
    """
    Determine whether an uploaded file is 'image' or 'video'.
    Checks file extension first, then MIME type. Raises HTTP 415 on failure.
    """
    suffix = Path(filename).suffix.lower()
    if suffix in _IMAGE_EXTENSIONS:
        return "image"
    if suffix in _VIDEO_EXTENSIONS:
        return "video"

    mime = (content_type or "").split(";")[0].strip().lower()
    if not mime:
        mime = mimetypes.guess_type(filename)[0] or ""
    if mime in _IMAGE_MIME_TYPES:
        return "image"
    if mime in _VIDEO_MIME_TYPES:
        return "video"

    raise HTTPException(
        status_code=415,
        detail=(
            f"Unsupported file type: extension='{suffix}', mime='{mime}'. "
            f"Accepted images: {sorted(_IMAGE_EXTENSIONS)}. "
            f"Accepted videos: {sorted(_VIDEO_EXTENSIONS)}."
        ),
    )


def _run_pipeline_on_frame(
    frame: np.ndarray,
    frame_id: int,
    state: dict,
    components: dict,
    cfg,
    fps_counter: FPSCounter,
) -> tuple[np.ndarray, dict, list, list, dict, list, int | None, float]:
    """
    Central pipeline execution wrapper — called by every code path that needs
    to run detect → track → OCR → violation on a single BGR frame.

    This is the single integration point between the HTTP/WS layer and the
    existing process_frame() function. It calls process_frame() exactly once
    per frame, then re-runs only the lightweight sub-detectors (no OCR) to
    obtain structured detection lists for serialization.

    Args:
        frame       : BGR numpy array
        frame_id    : Sequential frame counter
        state       : Pipeline state dict (mutated in-place by process_frame)
        components  : ML pipeline components from build_system()
        cfg         : System configuration DotDict
        fps_counter : FPSCounter instance (updated here)

    Returns:
        (annotated, state, sign_detections, tracked_vehicles,
         vehicle_speeds, active_violations, current_speed_limit, proc_ms)
    """
    state["frame_id"] = frame_id
    t0 = time.perf_counter()

    # ── THE ONE CALL TO THE EXISTING PIPELINE ─────────────────────────────────
    annotated, state = process_frame(
        frame=frame.copy(),
        frame_id=frame_id,
        components=components,
        cfg=cfg,
        state=state,
    )
    # ─────────────────────────────────────────────────────────────────────────

    proc_ms = (time.perf_counter() - t0) * 1000
    state["fps"] = fps_counter.update()

    # Re-derive structured detection lists.
    # process_frame() returns (annotated_frame, state) only — internal
    # detection lists are local variables inside it.  We re-run the fast
    # sub-detectors on the resized frame so serialization has typed data.
    # OCR is NOT repeated — its result is already in state["last_speed_limit"].
    resized = resize_frame(frame, cfg.video.resize_width, cfg.video.resize_height)

    sign_detections  = components["sign_detector"].detect(resized)
    vehicle_dets     = (
        components["vehicle_detector"].detect(resized)
        if components.get("vehicle_detector") else []
    )
    tracked_vehicles = (
        components["tracker"].update(vehicle_dets, resized)
        if (components.get("tracker") and vehicle_dets) else vehicle_dets
    )

    current_speed_limit = state.get("last_speed_limit")
    vehicle_speeds: dict[int, float] = {
        (v.track_id if v.track_id != -1 else id(v)):
        components["speed_sim"].get_speed(v.track_id if v.track_id != -1 else id(v))
        for v in tracked_vehicles
    }
    active_violations = (
        components["violation_checker"].check(
            tracked_vehicles, vehicle_speeds, current_speed_limit, frame_id
        )
        if current_speed_limit and cfg.violation.enabled
        else []
    )

    return (
        annotated, state, sign_detections, tracked_vehicles,
        vehicle_speeds, active_violations, current_speed_limit, proc_ms,
    )


def _serialise_frame_result(
    frame_id: int,
    annotated: np.ndarray | None,
    state: dict,
    sign_detections: list,
    tracked_vehicles: list,
    vehicle_speeds: dict,
    active_violations: list,
    current_speed_limit: int | None,
    proc_ms: float,
    include_frame: bool = True,
) -> FrameResult:
    """
    Convert raw pipeline outputs into a typed FrameResult Pydantic model.
    Single serialization point — no other location constructs FrameResult manually.
    """
    signs_out: list[SignResult] = [
        SignResult(
            bbox=BoundingBox(x1=s.x1, y1=s.y1, x2=s.x2, y2=s.y2),
            confidence=round(s.confidence, 4),
            ocr_text=str(current_speed_limit) if current_speed_limit else "",
            speed_limit=current_speed_limit,
        )
        for s in sign_detections
    ]

    vehicles_out: list[VehicleResult] = [
        VehicleResult(
            id=int(v.track_id if v.track_id != -1 else id(v)),
            bbox=BoundingBox(x1=v.x1, y1=v.y1, x2=v.x2, y2=v.y2),
            class_name=v.class_name,
            confidence=round(v.confidence, 4),
            speed=round(vehicle_speeds.get(
                v.track_id if v.track_id != -1 else id(v), 0.0
            ), 1),
        )
        for v in tracked_vehicles
    ]

    if active_violations:
        worst = max(active_violations, key=lambda ev: ev.excess_speed)
        violation = ViolationInfo(
            status="VIOLATION",
            vehicle_id=worst.track_id,
            speed=round(worst.vehicle_speed, 1),
            limit=worst.speed_limit,
            excess_speed=round(worst.excess_speed, 1),
            severity=worst.severity,
        )
    elif current_speed_limit and tracked_vehicles:
        violation = ViolationInfo(status="SAFE", limit=current_speed_limit)
    else:
        violation = ViolationInfo(status="NONE")

    frame_b64: str | None = None
    if include_frame and annotated is not None:
        try:
            frame_b64 = _encode_frame_b64(annotated)
        except RuntimeError as exc:
            log.warning(f"Frame {frame_id} encoding failed: {exc}")

    return FrameResult(
        frame_id=frame_id,
        annotated_frame=frame_b64,
        speed_signs=signs_out,
        vehicles=vehicles_out,
        current_speed_limit=current_speed_limit,
        violation=violation,
        processing_time_ms=round(proc_ms, 2),
    )


def _build_summary(
    frame_results: list[FrameResult],
    total_elapsed_s: float,
) -> MediaSummary:
    """Aggregate per-frame results into a session-level MediaSummary."""
    n = len(frame_results)
    violations  = sum(1 for r in frame_results if r.violation.status == "VIOLATION")
    sign_hits   = sum(len(r.speed_signs) for r in frame_results)
    speed_limits = sorted({
        r.current_speed_limit
        for r in frame_results
        if r.current_speed_limit is not None
    })
    proc_times = [r.processing_time_ms for r in frame_results if r.processing_time_ms]
    avg_proc   = sum(proc_times) / len(proc_times) if proc_times else 0.0
    avg_fps    = n / total_elapsed_s if total_elapsed_s > 0 else 0.0
    viol_rate  = (violations / n * 100) if n > 0 else 0.0

    return MediaSummary(
        total_frames_processed=n,
        total_sign_detections=sign_hits,
        total_violations=violations,
        unique_speed_limits=speed_limits,
        avg_processing_ms=round(avg_proc, 2),
        avg_fps=round(avg_fps, 2),
        duration_seconds=round(total_elapsed_s, 3),
        violation_rate_pct=round(viol_rate, 2),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Image / Video processing helpers (sync — run in thread pool)
# ──────────────────────────────────────────────────────────────────────────────

def _process_image_bytes(
    image_bytes: bytes,
    components: dict,
    cfg,
    include_frame: bool = True,
) -> tuple[FrameResult, float]:
    """
    Decode raw image bytes and run the full pipeline on the single frame.
    Returns (FrameResult, elapsed_seconds).
    """
    nparr = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None or frame.size == 0:
        raise HTTPException(
            status_code=422,
            detail="Image could not be decoded. File may be corrupt or in an unsupported format.",
        )

    state       = _fresh_state()
    fps_counter = FPSCounter(window_size=10)
    wall_start  = time.perf_counter()

    (annotated, state, sign_detections, tracked_vehicles,
     vehicle_speeds, active_violations, current_speed_limit, proc_ms) = \
        _run_pipeline_on_frame(frame, 1, state, components, cfg, fps_counter)

    elapsed_s = time.perf_counter() - wall_start
    result = _serialise_frame_result(
        frame_id=1,
        annotated=annotated,
        state=state,
        sign_detections=sign_detections,
        tracked_vehicles=tracked_vehicles,
        vehicle_speeds=vehicle_speeds,
        active_violations=active_violations,
        current_speed_limit=current_speed_limit,
        proc_ms=proc_ms,
        include_frame=include_frame,
    )
    return result, elapsed_s


def _process_video_file(
    video_path: str,
    components: dict,
    cfg,
    frame_skip: int = FRAME_SKIP_DEFAULT,
    include_frames: bool = False,
    max_frames: int = MAX_VIDEO_FRAMES,
    max_duration_s: float = MAX_VIDEO_DURATION,
) -> tuple[list[FrameResult], float]:
    """
    Process a video file frame-by-frame using the existing pipeline.

    Memory-safe: sequential processing, hard limits on frames and wall time,
    base64 frames omitted by default for long videos.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(
            status_code=422,
            detail="Video file could not be opened. It may be corrupt or use an unsupported codec.",
        )

    source_fps       = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_vid_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    vid_duration_s   = total_vid_frames / source_fps if source_fps > 0 else 0.0
    log.info(
        f"Video probe: {total_vid_frames} frames @ {source_fps:.1f}fps "
        f"= {vid_duration_s:.1f}s  frame_skip={frame_skip}"
    )
    if vid_duration_s > max_duration_s:
        log.warning(
            f"Video {vid_duration_s:.1f}s > limit {max_duration_s}s. Will stop early."
        )

    state           = _fresh_state()
    fps_counter     = FPSCounter(window_size=30)
    frame_results: list[FrameResult] = []
    frames_processed = 0
    raw_frame_idx    = 0
    wall_start       = time.perf_counter()

    try:
        while True:
            ret, raw_frame = cap.read()
            if not ret:
                break

            raw_frame_idx += 1
            if raw_frame_idx % frame_skip != 0:
                continue
            if frames_processed >= max_frames:
                log.warning(f"max_frames={max_frames} reached. Stopping.")
                break
            if time.perf_counter() - wall_start >= max_duration_s:
                log.warning(f"max_duration_s={max_duration_s:.0f}s reached. Stopping.")
                break

            (annotated, state, sign_detections, tracked_vehicles,
             vehicle_speeds, active_violations, current_speed_limit, proc_ms) = \
                _run_pipeline_on_frame(
                    raw_frame, raw_frame_idx, state, components, cfg, fps_counter
                )
            frames_processed += 1

            frame_results.append(_serialise_frame_result(
                frame_id=raw_frame_idx,
                annotated=annotated if include_frames else None,
                state=state,
                sign_detections=sign_detections,
                tracked_vehicles=tracked_vehicles,
                vehicle_speeds=vehicle_speeds,
                active_violations=active_violations,
                current_speed_limit=current_speed_limit,
                proc_ms=proc_ms,
                include_frame=include_frames,
            ))

            log.debug(
                f"vid frame {raw_frame_idx} ({frames_processed} processed) "
                f"{proc_ms:.1f}ms limit={current_speed_limit} "
                f"signs={len(sign_detections)} veh={len(tracked_vehicles)}"
            )
    finally:
        cap.release()

    total_elapsed = time.perf_counter() - wall_start
    log.info(
        f"Video done: {frames_processed} frames in {total_elapsed:.2f}s "
        f"({frames_processed / max(total_elapsed, 0.001):.1f} eff-fps)"
    )
    return frame_results, total_elapsed


def _run_video_via_tempfile(
    file_bytes: bytes,
    suffix: str,
    components: dict,
    cfg,
    frame_skip: int,
    include_frames: bool,
    max_frames: int,
) -> tuple[list[FrameResult], float]:
    """
    Write video bytes to a NamedTemporaryFile (OpenCV requires a seekable
    file path) and call _process_video_file. Guarantees cleanup on exit.
    """
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=suffix, delete=False, dir=tempfile.gettempdir()
        ) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        return _process_video_file(
            video_path=tmp_path,
            components=components,
            cfg=cfg,
            frame_skip=frame_skip,
            include_frames=include_frames,
            max_frames=max_frames,
            max_duration_s=MAX_VIDEO_DURATION,
        )
    finally:
        if tmp_path and Path(tmp_path).exists():
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ──────────────────────────────────────────────────────────────────────────────
# WebSocket session state
# ──────────────────────────────────────────────────────────────────────────────

class _WebSocketSession:
    """
    Encapsulates all mutable state for a single /ws/live-stream connection.

    Each WebSocket connection gets its own independent instance so that
    per-client tracking state (speed limits, violation counts, FPS) does not
    bleed between sessions.

    Attributes:
        state           : Pipeline state dict (mirrors app.py main() loop)
        fps_counter     : Rolling FPS tracker
        total_violations: Cumulative violation count for this session
        frame_count     : Total frames processed this session
        last_proc_ts    : Timestamp of last processed frame (for throttling)
    """

    __slots__ = (
        "state", "fps_counter", "total_violations",
        "frame_count", "last_proc_ts",
    )

    def __init__(self) -> None:
        self.state:            dict      = _fresh_state()
        self.fps_counter:      FPSCounter = FPSCounter(window_size=30)
        self.total_violations: int       = 0
        self.frame_count:      int       = 0
        self.last_proc_ts:     float     = 0.0   # perf_counter timestamp


def _ws_should_throttle(session: _WebSocketSession) -> bool:
    """
    Return True if this frame should be dropped to respect the minimum
    inter-frame interval (WS_MIN_FRAME_INTERVAL_MS).

    This prevents a fast frontend sender from overwhelming a slow backend
    without requiring a message queue or back-pressure protocol.
    """
    now = time.perf_counter()
    elapsed_ms = (now - session.last_proc_ts) * 1000
    return elapsed_ms < WS_MIN_FRAME_INTERVAL_MS


def _ws_build_response(
    annotated: np.ndarray,
    session: _WebSocketSession,
    current_speed_limit: int | None,
    active_violations: list,
    proc_ms: float,
) -> dict:
    """
    Build the WebSocket response dict for one processed frame.

    Matches the documented response shape exactly:
    {
      "frame":       "<base64 annotated JPEG>",
      "fps":         float,
      "violations":  int,    ← cumulative session total
      "speed_limit": int | null,
      "alert":       "SAFE" | "VIOLATION",
      "proc_ms":     float
    }
    """
    alert = "VIOLATION" if active_violations else "SAFE"

    frame_b64: str | None = None
    try:
        frame_b64 = _encode_frame_b64(annotated, jpeg_quality=80)
    except RuntimeError as exc:
        log.warning(f"WS frame encoding failed: {exc}")

    return {
        "frame":       frame_b64,
        "fps":         round(session.state.get("fps", 0.0), 1),
        "violations":  session.total_violations,
        "speed_limit": current_speed_limit,
        "alert":       alert,
        "proc_ms":     round(proc_ms, 1),
        "frame_id":    session.frame_count,
    }


# ──────────────────────────────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════════
#
#   ENDPOINT 1 — POST /api/process-frame
#   ORIGINAL — NOT MODIFIED — DO NOT CHANGE
#
# ════════════════════════════════════════════════════════════════════════════════
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Speed Limit Detection API is running"}

@app.post(
    "/api/process-frame",
    summary="Process a single webcam frame (real-time)",
    tags=["Real-Time HTTP"],
)
async def api_process_frame(
    frame: UploadFile = File(..., description="JPEG frame from browser webcam"),
    enable_vehicles: bool = Query(True,  description="Run vehicle detection"),
    enable_ocr:      bool = Query(True,  description="Run Tesseract OCR on detected signs"),
):
    """
    ⚠️  THIS ENDPOINT IS UNTOUCHED — DO NOT MODIFY.

    Accepts a single JPEG frame (multipart/form-data) from the React frontend,
    runs the YOLO + OCR + DeepSORT + violation pipeline, and returns:
      - annotated_frame       : base64 JPEG with bounding boxes
      - vehicles              : list of tracked vehicle detections
      - speed_signs           : speed sign detections + OCR results
      - violation             : current violation status object
      - processing_time_ms    : backend latency in milliseconds
    """
    if not _COMPONENTS:
        raise HTTPException(503, "ML pipeline not initialized. Check server logs.")
    if CFG is None:
        raise HTTPException(503, "Configuration not loaded.")

    image_bytes = await frame.read()
    if not image_bytes:
        raise HTTPException(400, "Empty frame received.")

    loop = asyncio.get_event_loop()
    result, _ = await loop.run_in_executor(
        None, _process_image_bytes, image_bytes, _COMPONENTS, CFG, True,
    )

    return JSONResponse(content={
        "annotated_frame":     result.annotated_frame,
        "vehicles":            [v.model_dump() for v in result.vehicles],
        "speed_signs":         [s.model_dump() for s in result.speed_signs],
        "current_speed_limit": result.current_speed_limit,
        "violation":           result.violation.model_dump(),
        "processing_time_ms":  result.processing_time_ms,
        "frame_id":            result.frame_id,
        "timestamp":           time.time(),
    })


# ──────────────────────────────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════════
#
#   ENDPOINT 2 — POST /api/process-media
#   Added in v2.0  —  Image OR video file batch processing
#
# ════════════════════════════════════════════════════════════════════════════════
# ──────────────────────────────────────────────────────────────────────────────

@app.post(
    "/api/process-media",
    response_model=ProcessMediaResponse,
    summary="Process an image or video file (batch)",
    tags=["Batch Media HTTP"],
)
async def api_process_media(
    file: UploadFile = File(
        ...,
        description="Image (JPEG/PNG/BMP/WEBP) or video (MP4/AVI/MOV/MKV/WEBM)",
    ),
    frame_skip: int = Query(
        default=FRAME_SKIP_DEFAULT, ge=1, le=30,
        description="Video only: process every Nth frame. 1=all, 2=every other (default).",
    ),
    include_frames: bool = Query(
        default=False,
        description=(
            "Video only: embed base64 annotated frames in results. "
            "WARNING: large response for long videos. Default False."
        ),
    ),
    max_frames: int = Query(
        default=MAX_VIDEO_FRAMES, ge=1, le=5000,
        description=f"Video only: max frames to process (default {MAX_VIDEO_FRAMES}).",
    ),
):
    """
    **Batch media endpoint.** Accepts image or video, auto-detects type,
    runs the full YOLO + OCR + DeepSORT + violation pipeline.

    ### Image response shape
    ```json
    {
      "type": "image",
      "results": [{
        "frame_id": 1,
        "annotated_frame": "<base64>",
        "speed_signs": [...],
        "vehicles": [...],
        "current_speed_limit": 60,
        "violation": { "status": "SAFE", ... },
        "processing_time_ms": 84.3
      }],
      "summary": { "total_frames_processed": 1, "total_violations": 0, ... }
    }
    ```

    ### Video response shape
    ```json
    {
      "type": "video",
      "results": [
        { "frame_id": 2, "alert": "SAFE",      ... },
        { "frame_id": 4, "alert": "VIOLATION", ... }
      ],
      "summary": {
        "total_frames_processed": 45,
        "total_violations": 3,
        "avg_fps": 11.2,
        "unique_speed_limits": [60, 80],
        ...
      }
    }
    ```
    """
    if not _COMPONENTS:
        raise HTTPException(503, "ML pipeline not initialized.")
    if CFG is None:
        raise HTTPException(503, "Configuration not loaded.")

    filename     = file.filename or "upload"
    content_type = file.content_type or ""
    media_kind   = _detect_media_kind(filename, content_type)

    log.info(f"process-media: '{filename}' kind={media_kind} skip={frame_skip}")

    max_bytes  = int(MAX_FILE_SIZE_MB * 1024 * 1024)
    file_bytes = await file.read(max_bytes + 1)
    if len(file_bytes) > max_bytes:
        raise HTTPException(413, f"File too large. Max {MAX_FILE_SIZE_MB:.0f} MB.")
    if not file_bytes:
        raise HTTPException(400, "Empty file received.")

    loop = asyncio.get_event_loop()

    if media_kind == "image":
        result, elapsed = await loop.run_in_executor(
            None, _process_image_bytes, file_bytes, _COMPONENTS, CFG, True,
        )
        frame_results = [result]
        total_elapsed = elapsed
    else:
        suffix = Path(filename).suffix.lower() or ".mp4"
        frame_results, total_elapsed = await loop.run_in_executor(
            None,
            _run_video_via_tempfile,
            file_bytes, suffix, _COMPONENTS, CFG,
            frame_skip, include_frames, max_frames,
        )

    return ProcessMediaResponse(
        type=media_kind,
        results=frame_results,
        summary=_build_summary(frame_results, total_elapsed),
    )


# ──────────────────────────────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════════
#
#   ENDPOINT 3 — WebSocket /ws/live-stream
#   Added in v3.0  —  Real-time bidirectional streaming pipeline
#
# ════════════════════════════════════════════════════════════════════════════════
#
#  Protocol:
#
#  Client → Server (JSON text message per frame):
#    { "frame": "<base64 JPEG string>" }
#
#  Server → Client (JSON text message per processed frame):
#    {
#      "frame":       "<base64 annotated JPEG>",
#      "fps":         12.4,
#      "violations":  3,          ← cumulative session total
#      "speed_limit": 60,         ← OCR-extracted limit (null if none visible)
#      "alert":       "SAFE",     ← "SAFE" | "VIOLATION"
#      "proc_ms":     74.2,       ← backend processing time for this frame
#      "frame_id":    42          ← sequential count for this session
#    }
#
#  Server → Client (JSON text message, error only):
#    { "error": "<description>" }
#
#  Connection lifecycle:
#    - Client connects  → session created, pipeline state initialised fresh
#    - Client sends frames → each processed independently, response sent back
#    - Client disconnects  → WebSocketDisconnect caught, session cleaned up
#    - Server error       → error message sent, connection closed gracefully
#
#  Throttling:
#    - If the backend is still processing frame N when frame N+1 arrives,
#      frame N+1 is dropped silently and a lightweight "throttled" ack is sent.
#    - This gives natural back-pressure without requiring a frame queue.
#    - Minimum inter-frame interval: WS_MIN_FRAME_INTERVAL_MS (default 80ms ≈ 12fps)
#
# ──────────────────────────────────────────────────────────────────────────────

@app.websocket("/ws/live-stream")
async def ws_live_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time speed-limit detection streaming.

    The client sends raw camera frames as base64 JPEG strings; the server
    returns annotated frames with detection results after each one.

    Each connection maintains its own isolated pipeline state — violations,
    speed limit history, and DeepSORT track IDs do not leak between clients.
    """
    if not _COMPONENTS:
        await websocket.close(code=1011, reason="ML pipeline not initialized.")
        return
    if CFG is None:
        await websocket.close(code=1011, reason="Configuration not loaded.")
        return

    await websocket.accept()
    client_host = websocket.client.host if websocket.client else "unknown"
    log.info(f"WS /ws/live-stream  ← connected from {client_host}")

    # Isolated state for this connection
    session  = _WebSocketSession()
    loop     = asyncio.get_event_loop()

    # One lock to guarantee we never start processing frame N+1 while
    # frame N is still running in the thread pool.
    proc_lock = asyncio.Lock()

    try:
        while True:
            # ── Receive one message from the client ───────────────────────────
            try:
                raw_msg = await websocket.receive_json()
            except WebSocketDisconnect:
                raise   # Let outer handler clean up
            except Exception as exc:
                # Malformed message — send error and keep connection alive
                log.warning(f"WS bad message from {client_host}: {exc}")
                await _ws_send_error(websocket, f"Invalid message format: {exc}")
                continue

            # ── Validate message schema ───────────────────────────────────────
            if not isinstance(raw_msg, dict) or "frame" not in raw_msg:
                await _ws_send_error(
                    websocket,
                    'Expected JSON: {"frame": "<base64 JPEG string>"}',
                )
                continue

            b64_payload = raw_msg["frame"]
            if not isinstance(b64_payload, str) or not b64_payload:
                await _ws_send_error(websocket, '"frame" field must be a non-empty string.')
                continue

            # ── Throttle: drop frames arriving faster than the minimum interval
            if _ws_should_throttle(session):
                # Send a lightweight ack so the client knows we're alive
                await websocket.send_json({"throttled": True, "frame_id": session.frame_count})
                continue

            # ── Decode base64 → BGR frame ─────────────────────────────────────
            try:
                frame = _decode_b64_to_frame(b64_payload)
            except ValueError as exc:
                await _ws_send_error(websocket, str(exc))
                continue

            # ── Acquire lock: one pipeline execution at a time ─────────────────
            # try_acquire pattern: if locked, drop this frame (skip don't queue)
            if proc_lock.locked():
                await websocket.send_json({"throttled": True, "frame_id": session.frame_count})
                continue

            async with proc_lock:
                # Mark timestamp BEFORE offloading so throttle calc is accurate
                session.last_proc_ts = time.perf_counter()
                session.frame_count += 1

                # ── Offload CPU-bound pipeline to thread pool ─────────────────
                # run_in_executor keeps the event loop free to receive the
                # next message while processing is in progress.
                try:
                    (annotated, session.state,
                     sign_detections, tracked_vehicles,
                     vehicle_speeds, active_violations,
                     current_speed_limit, proc_ms) = await loop.run_in_executor(
                        None,
                        _run_pipeline_on_frame,
                        frame,
                        session.frame_count,
                        session.state,
                        _COMPONENTS,
                        CFG,
                        session.fps_counter,
                    )
                except Exception as exc:
                    log.error(f"WS pipeline error (frame {session.frame_count}): {exc}", exc_info=True)
                    await _ws_send_error(websocket, f"Pipeline error: {exc}")
                    continue

                # Update cumulative violation counter
                session.total_violations += len(active_violations)

                # ── Build and send response ───────────────────────────────────
                response = _ws_build_response(
                    annotated=annotated,
                    session=session,
                    current_speed_limit=current_speed_limit,
                    active_violations=active_violations,
                    proc_ms=proc_ms,
                )
                await websocket.send_json(response)

                log.debug(
                    f"WS frame {session.frame_count} | {proc_ms:.1f}ms "
                    f"| fps={session.state.get('fps', 0):.1f} "
                    f"| limit={current_speed_limit} alert={response['alert']}"
                )

    except WebSocketDisconnect:
        log.info(
            f"WS /ws/live-stream ← {client_host} disconnected  "
            f"(frames={session.frame_count} violations={session.total_violations})"
        )
    except Exception as exc:
        log.error(f"WS unexpected error for {client_host}: {exc}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Internal server error.")
        except Exception:
            pass


async def _ws_send_error(websocket: WebSocket, detail: str) -> None:
    """Send a structured error message over the WebSocket without closing it."""
    try:
        await websocket.send_json({"error": detail})
    except Exception:
        pass   # Connection may already be gone


# ──────────────────────────────────────────────────────────────────────────────
# Health check
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["System"])
async def health_check():
    """Returns system status, loaded model state, and version."""
    ready = bool(_COMPONENTS)
    return {
        "status":        "ok" if ready else "degraded",
        "pipeline":      "loaded" if ready else "not loaded",
        "sign_model":    "loaded" if (ready and _COMPONENTS.get("sign_detector") and
                                      _COMPONENTS["sign_detector"].is_loaded()) else "not loaded",
        "vehicle_model": "loaded" if (ready and _COMPONENTS.get("vehicle_detector") and
                                      _COMPONENTS["vehicle_detector"].is_loaded()) else "not loaded",
        "config":        _CFG_PATH,
        "version":       "3.0.0",
        "ws_endpoint":   "/ws/live-stream",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Dev runner
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "fastapi_server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,    # reload=True breaks WebSocket connections on hot reload
        log_level="info",
        ws_ping_interval=20,    # Send WS ping every 20s to detect stale connections
        ws_ping_timeout=30,     # Close connection if pong not received in 30s
    )
