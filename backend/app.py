import argparse
import sys
import os
import cv2
import time
import numpy as np
from fastapi import  UploadFile, File, FastAPI
import base64
from system import build_system

# ── Project imports ───────────────────────────────────────────────────────────
from utils.config_loader import load_config
from utils.logger import setup_logger, DetectionLogger
from utils.helpers import (
    FPSCounter, resize_frame,
    draw_bounding_box, draw_speed_badge, draw_fps_overlay,
    draw_violation_alert, draw_info_panel,
    VehicleSpeedSimulator,
)
from modules.detector import SpeedSignDetector, VehicleDetector
from modules.ocr import SpeedOCR
from modules.tracker import VehicleTracker, SimpleTracker, HAS_DEEPSORT
from modules.violation_checker import ViolationChecker

app = FastAPI()

@app.on_event("startup")
def startup():
    global cfg, components

    args = parse_args()
    cfg = load_config(args.config)
    components = build_system(cfg, args)

cfg = None
components = None
state = {
    "frame_id": 0,
    "last_speed_limit": None,
    "speed_limit_frame": 0,
    "total_sign_detections": 0,
    "total_violations": 0,
    "fps": 0.0,
}


# ──────────────────────────────────────────────────────────────────────────────
# CLI Argument Parsing
# ──────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Intelligent Real-Time Speed Limit Sign Detection System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--source", type=str, default=None,
        help="Video source: 0 (webcam), camera index, or path to video file"
    )
    parser.add_argument(
        "--config", type=str, default="config.yaml",
        help="Path to YAML config file (default: config.yaml)"
    )
    parser.add_argument(
        "--save-video", action="store_true",
        help="Save annotated output video to output/ directory"
    )
    parser.add_argument(
        "--no-display", action="store_true",
        help="Disable real-time window display (for headless/server use)"
    )
    parser.add_argument(
        "--no-vehicles", action="store_true",
        help="Disable vehicle detection (speed signs only)"
    )
    parser.add_argument(
        "--no-tracking", action="store_true",
        help="Disable DeepSORT tracking"
    )
    return parser.parse_args()


# ──────────────────────────────────────────────────────────────────────────────
# System Initialisation
# ──────────────────────────────────────────────────────────────────────────────

def build_system(cfg, args):
    """
    Instantiate all system components from config.

    Returns a dict of component instances.
    """
    log = setup_logger("App", cfg.logging.console_level, cfg.logging.log_dir)
    log.info("=" * 60)
    log.info("  Speed Limit Sign Detection System — Starting Up")
    log.info("=" * 60)

    # ── Speed Sign Detector ──────────────────────────────────────────────────
    sign_detector = SpeedSignDetector(
        weights_path=cfg.model.speed_sign_weights,
        confidence_threshold=cfg.model.confidence_threshold,
        iou_threshold=cfg.model.iou_threshold,
        device=cfg.model.device,
        imgsz=cfg.model.imgsz,
    )

    # ── Vehicle Detector ─────────────────────────────────────────────────────
    vehicle_detector = None
    if not args.no_vehicles:
        vehicle_detector = VehicleDetector(
            weights_path=cfg.model.vehicle_weights,
            confidence_threshold=cfg.model.confidence_threshold,
            iou_threshold=cfg.model.iou_threshold,
            device=cfg.model.device,
            vehicle_class_ids=cfg.vehicles.class_ids,
        )

    # ── Tracker ──────────────────────────────────────────────────────────────
    tracker = None
    if not args.no_tracking and cfg.tracking.enabled:
        if HAS_DEEPSORT:
            tracker = VehicleTracker(
                max_age=cfg.tracking.max_age,
                n_init=cfg.tracking.n_init,
                max_cosine_distance=cfg.tracking.max_cosine_distance,
                nn_budget=cfg.tracking.nn_budget,
            )
            log.info("DeepSORT tracker enabled")
        else:
            tracker = SimpleTracker()
            log.info("Simple IoU tracker enabled (install deep-sort-realtime for DeepSORT)")

    # ── OCR ──────────────────────────────────────────────────────────────────
    ocr = SpeedOCR(
        tesseract_config=cfg.ocr.tesseract_config,
        min_confidence=cfg.ocr.min_confidence,
        upscale_factor=cfg.ocr.upscale_factor,
        padding=cfg.ocr.padding,
        preprocess=cfg.ocr.preprocessing,
    )

    # ── Violation Checker ────────────────────────────────────────────────────
    violation_checker = ViolationChecker(
        speed_tolerance=cfg.violation.speed_tolerance,
    )

    # ── Detection Logger ─────────────────────────────────────────────────────
    detection_logger = None
    if cfg.logging.enabled:
        os.makedirs(cfg.logging.log_dir, exist_ok=True)
        detection_logger = DetectionLogger(
            csv_path=cfg.logging.csv_file,
            json_path=cfg.logging.json_file,
            log_interval=cfg.logging.log_interval,
        )

    # ── Speed Simulator ──────────────────────────────────────────────────────
    speed_sim = VehicleSpeedSimulator(
        min_speed=cfg.violation.simulated_speed_min,
        max_speed=cfg.violation.simulated_speed_max,
    )

    return {
        "log": log,
        "sign_detector": sign_detector,
        "vehicle_detector": vehicle_detector,
        "tracker": tracker,
        "ocr": ocr,
        "violation_checker": violation_checker,
        "detection_logger": detection_logger,
        "speed_sim": speed_sim,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Video Writer Setup
# ──────────────────────────────────────────────────────────────────────────────

def create_video_writer(cfg, cap) -> cv2.VideoWriter | None:
    """Create an OpenCV VideoWriter if output saving is enabled."""
    os.makedirs("output", exist_ok=True)
    fps = cap.get(cv2.CAP_PROP_FPS) or cfg.video.target_fps
    w = int(cfg.video.display_width)
    h = int(cfg.video.display_height)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    path = cfg.output.output_path
    writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
    if writer.isOpened():
        return writer
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Per-Frame Processing
# ──────────────────────────────────────────────────────────────────────────────

def process_frame(frame: np.ndarray,
                  frame_id: int,
                  components: dict,
                  cfg,
                  state: dict) -> tuple[np.ndarray, dict]:
    """
    Run the full detection/OCR/violation pipeline on one frame.

    Args:
        frame      : Raw BGR frame from video capture
        frame_id   : Sequential frame counter (0-based)
        components : Dict of system components from build_system()
        cfg        : Loaded configuration (DotDict)
        state      : Mutable session state dict

    Returns:
        (annotated_frame, updated_state)
    """
    # Resize frame for consistent processing
    frame = resize_frame(frame, cfg.video.resize_width, cfg.video.resize_height)

    # ── 1. Speed Sign Detection ───────────────────────────────────────────────
    sign_detections = components["sign_detector"].detect(frame)

    # ── 2. Vehicle Detection ──────────────────────────────────────────────────
    vehicle_detections = []
    if components["vehicle_detector"]:
        vehicle_detections = components["vehicle_detector"].detect(frame)

    # ── 3. Vehicle Tracking ───────────────────────────────────────────────────
    tracked_vehicles = vehicle_detections  # default: no tracking
    if components["tracker"] and vehicle_detections:
        tracked_vehicles = components["tracker"].update(vehicle_detections, frame)

    # ── 4. OCR on Each Detected Sign ──────────────────────────────────────────
    # Cache the most recent confident speed limit to persist between frames
    current_speed_limit = state.get("last_speed_limit")

    for sign in sign_detections:
        speed, raw, conf = components["ocr"].extract_speed(
            frame, sign.x1, sign.y1, sign.x2, sign.y2
        )
        if speed is not None:
            current_speed_limit = speed
            state["last_speed_limit"] = speed
            state["speed_limit_frame"] = frame_id
            state["total_sign_detections"] += 1

        # Log detection event
        if components["detection_logger"]:
            components["detection_logger"].log(
                frame_id=frame_id,
                speed_limit=speed,
                confidence=sign.confidence,
                bbox=sign.bbox,
                ocr_raw=raw,
            )

    # Forget speed limit after N frames with no new sign detection
    # (avoids applying a stale limit to a different road segment)
    frames_since_sign = frame_id - state.get("speed_limit_frame", 0)
    if frames_since_sign > 90:   # ~3 seconds at 30 fps
        current_speed_limit = None

    # ── 5. Simulate Vehicle Speeds & Check Violations ─────────────────────────
    vehicle_speeds: dict[int, float] = {}
    active_violations = []

    for veh in tracked_vehicles:
        tid = veh.track_id if veh.track_id != -1 else id(veh)
        speed = components["speed_sim"].get_speed(tid)
        vehicle_speeds[tid] = speed

    if current_speed_limit and cfg.violation.enabled:
        active_violations = components["violation_checker"].check(
            tracked_vehicles, vehicle_speeds, current_speed_limit, frame_id
        )
        state["total_violations"] += len(active_violations)

        # Log violations
        if components["detection_logger"] and active_violations:
            for ev in active_violations:
                # Find nearest sign detection to log against
                nearest_sign = sign_detections[0] if sign_detections else None
                components["detection_logger"].log(
                    frame_id=frame_id,
                    speed_limit=current_speed_limit,
                    confidence=nearest_sign.confidence if nearest_sign else 0.0,
                    bbox=nearest_sign.bbox if nearest_sign else (0, 0, 0, 0),
                    ocr_raw=str(current_speed_limit),
                    vehicle_id=ev.track_id,
                    vehicle_speed=ev.vehicle_speed,
                    is_violation=True,
                )

    # ── 6. Draw UI Overlay ────────────────────────────────────────────────────
    annotated = _draw_overlay(
        frame, sign_detections, tracked_vehicles, vehicle_speeds,
        current_speed_limit, active_violations, state, cfg
    )

    return annotated, state


def _draw_overlay(frame, sign_detections, tracked_vehicles,
                  vehicle_speeds, speed_limit, violations, state, cfg):
    """Render all UI elements onto the frame."""

    disp = cfg.display

    # ── Speed sign boxes ─────────────────────────────────────────────────────
    for sign in sign_detections:
        label = f"Speed Sign {sign.confidence:.0%}"
        color = tuple(disp.colors.speed_sign)
        draw_bounding_box(frame, sign.x1, sign.y1, sign.x2, sign.y2,
                          label, color=color,
                          font_scale=disp.font_scale,
                          thickness=disp.box_thickness)
        if speed_limit and disp.show_confidence:
            draw_speed_badge(frame, sign.x1, sign.y1, sign.x2, sign.y2, speed_limit)

    # ── Vehicle boxes ─────────────────────────────────────────────────────────
    violating_ids = {v.track_id for v in violations}
    for veh in tracked_vehicles:
        tid = veh.track_id if veh.track_id != -1 else id(veh)
        v_speed = vehicle_speeds.get(tid, 0.0)
        is_viol = tid in violating_ids

        color = tuple(disp.colors.violation) if is_viol else tuple(disp.colors.vehicle)

        label_parts = [veh.class_name]
        if veh.track_id != -1:
            label_parts.append(f"#{veh.track_id}")
        if disp.show_vehicle_speed:
            label_parts.append(f"{v_speed:.0f} km/h")
        if is_viol:
            label_parts.append("VIOLATION!")

        label = " | ".join(label_parts)
        draw_bounding_box(frame, veh.x1, veh.y1, veh.x2, veh.y2,
                          label, color=color,
                          font_scale=disp.font_scale,
                          thickness=disp.box_thickness + (1 if is_viol else 0))

    # ── Violation banner ──────────────────────────────────────────────────────
    if violations and disp.show_violation_alert and speed_limit:
        worst = max(violations, key=lambda v: v.vehicle_speed)
        draw_violation_alert(frame, worst.vehicle_speed, speed_limit)

    # ── Current speed limit indicator (top-right) ─────────────────────────────
    if speed_limit:
        h, w = frame.shape[:2]
        # Circle badge in top-right corner
        cx, cy, r = w - 60, 60, 45
        cv2.circle(frame, (cx, cy), r, (255, 255, 255), cv2.FILLED)
        cv2.circle(frame, (cx, cy), r, (0, 0, 180), 4)
        txt = str(speed_limit)
        import cv2 as _cv2
        font = _cv2.FONT_HERSHEY_SIMPLEX
        sc = 1.0 if speed_limit < 100 else 0.8
        (tw, th), _ = _cv2.getTextSize(txt, font, sc, 2)
        _cv2.putText(frame, txt, (cx - tw // 2, cy + th // 2),
                     font, sc, (0, 0, 0), 2, _cv2.LINE_AA)
        _cv2.putText(frame, "LIMIT", (cx - 22, cy + r + 15),
                     font, 0.4, (255, 255, 255), 1, _cv2.LINE_AA)

    # ── FPS ───────────────────────────────────────────────────────────────────
    if disp.show_fps:
        draw_fps_overlay(frame, state.get("fps", 0), color=tuple(disp.colors.fps_text))

    # ── Info panel ────────────────────────────────────────────────────────────
    draw_info_panel(frame,
                    state.get("frame_id", 0),
                    state.get("total_sign_detections", 0),
                    state.get("total_violations", 0))

    return frame


# ──────────────────────────────────────────────────────────────────────────────
# Main Loop
# ──────────────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Load config
    cfg = load_config(args.config)
    log = setup_logger("App", cfg.logging.console_level, cfg.logging.log_dir)

    # Override source from CLI
    source = args.source if args.source is not None else cfg.video.source
    # Convert numeric string to int for webcam
    try:
        source = int(source)
    except (ValueError, TypeError):
        pass

    # Initialise all components
    components = build_system(cfg, args)
    log = components["log"]

    # ── Open Video Source ─────────────────────────────────────────────────────
    log.info(f"Opening video source: {source}")
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        log.error(f"Cannot open video source: {source}")
        sys.exit(1)

    # Set capture properties
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.video.resize_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.video.resize_height)

    # ── Output Video Writer ───────────────────────────────────────────────────
    writer = None
    if args.save_video or cfg.output.save_video:
        writer = create_video_writer(cfg, cap)
        if writer:
            log.info(f"Saving output to: {cfg.output.output_path}")

    # ── Session State ─────────────────────────────────────────────────────────
    fps_counter = FPSCounter(window_size=30)
    state = {
        "frame_id": 0,
        "last_speed_limit": None,
        "speed_limit_frame": 0,
        "total_sign_detections": 0,
        "total_violations": 0,
        "fps": 0.0,
    }

    frame_skip = max(1, cfg.video.frame_skip)
    log.info(f"Processing every {frame_skip} frame(s). Press 'q' to quit.")

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN PROCESSING LOOP
    # ─────────────────────────────────────────────────────────────────────────
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                log.info("End of video stream.")
                break

            state["frame_id"] += 1
            frame_id = state["frame_id"]

            # Frame skip: process every Nth frame, display all
            if frame_id % frame_skip != 0:
                # Still show last annotated frame for smooth display
                if not args.no_display:
                    cv2.imshow("Speed Limit Detection System", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            # ── Run full pipeline ─────────────────────────────────────────────
            t_start = time.perf_counter()

            annotated, state = process_frame(
                frame, frame_id, components, cfg, state
            )

            # ── Update FPS ────────────────────────────────────────────────────
            state["fps"] = fps_counter.update()

            # ── Write output frame ────────────────────────────────────────────
            if writer:
                out_frame = resize_frame(annotated,
                                        cfg.video.display_width,
                                        cfg.video.display_height)
                writer.write(out_frame)

            # ── Display ───────────────────────────────────────────────────────
            if not args.no_display:
                display_frame = resize_frame(annotated,
                                            cfg.video.display_width,
                                            cfg.video.display_height)
                cv2.imshow("Speed Limit Detection System", display_frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    log.info("Quit key pressed.")
                    break
                elif key == ord("s"):
                    # Screenshot
                    snap_path = f"output/snapshot_{frame_id}.jpg"
                    os.makedirs("output", exist_ok=True)
                    cv2.imwrite(snap_path, display_frame)
                    log.info(f"Snapshot saved: {snap_path}")
                elif key == ord("p"):
                    # Pause
                    log.info("Paused — press any key to resume")
                    cv2.waitKey(0)

            t_end = time.perf_counter()
            log.debug(f"Frame {frame_id} processed in {(t_end-t_start)*1000:.1f} ms")

    except KeyboardInterrupt:
        log.info("Interrupted by user.")

    finally:
        # ── Cleanup ───────────────────────────────────────────────────────────
        cap.release()
        if writer:
            writer.release()
        cv2.destroyAllWindows()

        if components["detection_logger"]:
            components["detection_logger"].close()
            summary = components["detection_logger"].get_summary()
            log.info("─" * 50)
            log.info("SESSION SUMMARY")
            log.info(f"  Total sign detections : {summary['total_detections']}")
            log.info(f"  Total violations      : {summary['total_violations']}")
            log.info(f"  Unique speed limits   : {summary['unique_speed_limits']}")
            log.info("─" * 50)

        vs = components["violation_checker"].get_stats()
        if vs.get("total", 0) > 0:
            log.info(f"  Violation breakdown   : {vs}")

        log.info("System shut down cleanly.")

@app.post("/api/process-frame")
async def process_frame_api(file: UploadFile = File(...)):
    global state

    contents = await file.read()
    npimg = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    state["frame_id"] += 1

    annotated, state = process_frame(
        frame,
        state["frame_id"],
        components,
        cfg,
        state
    )

    _, buffer = cv2.imencode(".jpg", annotated)
    frame_base64 = base64.b64encode(buffer).decode("utf-8")

    return {
        "frame": frame_base64,
        "detections": [],  # optional: extract if needed
        "stats": {
            "fps": state.get("fps", 0),
            "violations": state.get("total_violations", 0)
        },
        "alert": "VIOLATION" if state.get("total_violations", 0) > 0 else "SAFE"
    }

# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
