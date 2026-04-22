import os
import cv2
import numpy as np
from pathlib import Path

from utils.config_loader import load_config
from utils.logger import setup_logger

from modules.detector import SpeedSignDetector, VehicleDetector
from modules.ocr import SpeedOCR
from modules.tracker import VehicleTracker, SimpleTracker, HAS_DEEPSORT
from modules.violation_checker import ViolationChecker
from utils.helpers import VehicleSpeedSimulator 
from utils.logger import DetectionLogger



def build_system(cfg, args):
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
