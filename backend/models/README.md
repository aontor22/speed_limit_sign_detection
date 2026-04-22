# 🚦 Intelligent Real-Time Speed Limit Sign Detection & Recognition System

> A production-grade computer vision system for detecting speed limit signs
> and identifying vehicle speed violations in real-time video streams.

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [System Architecture](#system-architecture)
3. [Project Structure](#project-structure)
4. [Setup Instructions](#setup-instructions)
5. [How to Run](#how-to-run)
6. [Configuration Guide](#configuration-guide)
7. [Module Documentation](#module-documentation)
8. [Performance Tips](#performance-tips)
9. [Presentation Key Points](#presentation-key-points)
10. [Troubleshooting](#troubleshooting)

---

## Project Overview

This system combines **YOLOv8 object detection**, **Tesseract OCR**, and
**DeepSORT multi-object tracking** to build a real-time traffic monitoring
system that:

- Detects speed limit signs in video frames
- Reads the numeric speed value via OCR
- Tracks multiple vehicles with persistent IDs
- Compares vehicle speed against the detected limit
- Flags and logs speed violations in real-time

### Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Sign Detection | YOLOv8 (Ultralytics) | Locate speed signs in frame |
| Vehicle Detection | YOLOv8n (COCO pretrained) | Locate cars, buses, trucks |
| OCR | Tesseract + pytesseract | Read speed value from sign |
| Tracking | DeepSORT | Persistent vehicle IDs |
| Video Processing | OpenCV | Frame capture & display |
| Logging | CSV + JSON | Persistent detection records |
| Configuration | YAML | Tunable system parameters |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  VIDEO SOURCE (Webcam / File)             │
└──────────────────────────┬──────────────────────────────┘
                           │ BGR frame
              ┌────────────▼─────────────┐
              │      Frame Resizer        │  (OpenCV)
              └───┬───────────────────┬──┘
                  │                   │
     ┌────────────▼──────┐  ┌─────────▼─────────┐
     │  SpeedSignDetector│  │  VehicleDetector   │
     │  (YOLOv8 custom)  │  │  (YOLOv8 COCO)    │
     └────────────┬──────┘  └─────────┬──────────┘
                  │                   │
     ┌────────────▼──────┐  ┌─────────▼──────────┐
     │    SpeedOCR        │  │   VehicleTracker    │
     │  (Tesseract OCR)   │  │   (DeepSORT)        │
     └────────────┬──────┘  └─────────┬──────────┘
                  │                   │
     ┌────────────▼───────────────────▼──────────┐
     │              ViolationChecker               │
     │     (speed_vehicle > speed_limit + tol?)   │
     └────────────────────┬──────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
    ┌─────▼─────┐  ┌──────▼─────┐  ┌────▼──────┐
    │  UI Overlay│  │  CSV/JSON  │  │ Video Out │
    │  (OpenCV) │  │  Logger    │  │ (optional)│
    └───────────┘  └────────────┘  └───────────┘
```

---

## Project Structure

```
speed_limit_detection/
│
├── app.py                    ← Main entry point
├── config.yaml               ← All tunable parameters
├── requirements.txt          ← Python dependencies
├── test_system.py            ← Dependency verification
├── analyze_logs.py           ← Post-session analytics
│
├── modules/                  ← Core processing modules
│   ├── __init__.py
│   ├── detector.py           ← YOLOv8 sign + vehicle detection
│   ├── ocr.py                ← Tesseract OCR pipeline
│   ├── tracker.py            ← DeepSORT + SimpleTracker fallback
│   └── violation_checker.py  ← Speed vs limit comparison
│
├── utils/                    ← Shared utilities
│   ├── __init__.py
│   ├── config_loader.py      ← YAML config with dot-notation
│   ├── helpers.py            ← Drawing, FPS, preprocessing
│   └── logger.py             ← Console + file logging + CSV/JSON
│
├── models/                   ← YOLOv8 weight files
│   ├── README.md             ← How to get/train models
│   └── speed_limit_model.pt  ← YOUR trained model (place here)
│
├── logs/                     ← Auto-created at runtime
│   ├── detections.csv
│   └── detections.json
│
└── output/                   ← Auto-created at runtime
    ├── result.mp4            ← Saved video (if enabled)
    └── snapshots/            ← Frame captures (press 's')
```

---

## Setup Instructions

### Step 1: Clone / Download Project

```bash
# If using git:
git clone <your-repo-url>
cd speed_limit_detection

# Or unzip the project folder, then:
cd speed_limit_detection
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate it
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

### Step 3: Install Python Dependencies

```bash
pip install -r requirements.txt
```

> **GPU Acceleration (optional):**
> If you have an NVIDIA GPU with CUDA, install the CUDA version of PyTorch:
> ```bash
> pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
> ```
> Then set `device: "cuda"` in `config.yaml`.

### Step 4: Install Tesseract OCR

Tesseract is a **system-level** binary — it must be installed separately:

```bash
# Ubuntu / Debian:
sudo apt update && sudo apt install tesseract-ocr

# macOS (Homebrew):
brew install tesseract

# Windows:
# Download installer from: https://github.com/UB-Mannheim/tesseract/wiki
# Add install path (e.g. C:\Program Files\Tesseract-OCR) to PATH
```

Verify:
```bash
tesseract --version
```

### Step 5: Place Your Trained Model

Copy your trained YOLOv8 `.pt` file:
```bash
cp /path/to/your/best.pt models/speed_limit_model.pt
```

If you don't have a trained model yet, see `models/README.md` for training instructions.
The vehicle detection model (`yolov8n.pt`) is **automatically downloaded** by Ultralytics.

### Step 6: Verify Installation

```bash
python test_system.py
```

Expected output:
```
  [PASS]  OpenCV — 4.9.0
  [PASS]  PyTorch — 2.1.0
  [PASS]  Ultralytics YOLOv8
  [PASS]  Tesseract OCR — 5.3.0
  [PASS]  DeepSORT
  [PASS]  Config loading
  [PASS]  Helper functions
  [PASS]  OCR pipeline
  [PASS]  Detector module
  ✅  All core tests passed!
```

---

## How to Run

### Basic Usage

```bash
# Use webcam (default):
python app.py

# Use a video file:
python app.py --source path/to/traffic_video.mp4

# Use a specific camera index:
python app.py --source 1
```

### Advanced Usage

```bash
# Save annotated output video:
python app.py --source video.mp4 --save-video

# Run headless (no display window, e.g. on a server):
python app.py --source video.mp4 --no-display

# Disable vehicle detection (sign detection only):
python app.py --no-vehicles

# Use a custom config file:
python app.py --config my_config.yaml

# Combine flags:
python app.py --source video.mp4 --save-video --no-display
```

### Keyboard Controls (while running)

| Key | Action |
|-----|--------|
| `q` | Quit the program |
| `s` | Save a screenshot (in output/) |
| `p` | Pause / Resume |

### Analyze Session Logs

After running, analyze what was detected:
```bash
python analyze_logs.py
```

---

## Configuration Guide

Open `config.yaml` to tune the system. Key settings:

```yaml
model:
  confidence_threshold: 0.50   # Lower → more detections (more false positives)
                                 # Higher → fewer but more reliable detections
  device: "cpu"                  # Change to "cuda" for GPU

video:
  source: 0                      # 0 = webcam, or "video.mp4"
  frame_skip: 2                  # 1 = every frame, 2 = every other frame

ocr:
  upscale_factor: 2.5            # Higher = better OCR on small signs (slower)
  min_confidence: 40             # Tesseract confidence threshold

violation:
  speed_tolerance: 5             # km/h buffer before flagging violation
```

---

## Module Documentation

### `modules/detector.py`
- `SpeedSignDetector`: Runs YOLOv8 on each frame, returns `Detection` objects
- `VehicleDetector`: Detects cars/buses/trucks using COCO pretrained YOLOv8
- `Detection`: Dataclass with x1,y1,x2,y2, confidence, class, track_id

### `modules/ocr.py`
- `SpeedOCR`: Takes a frame + bbox, crops + preprocesses + runs Tesseract
- Returns `(speed_int, raw_text, confidence)`
- Applies digit whitelist, CLAHE, Otsu thresholding

### `modules/tracker.py`
- `VehicleTracker`: DeepSORT wrapper with appearance Re-ID
- `SimpleTracker`: Fallback IoU tracker (no deep features)
- Updates track IDs each frame, handles lost tracks

### `modules/violation_checker.py`
- `ViolationChecker`: Compares vehicle speed vs. sign limit + tolerance
- Returns `ViolationEvent` objects with severity classification
- Cooldown prevents alert spam per vehicle

### `utils/logger.py`
- `setup_logger()`: Colored console + rotating file logger
- `DetectionLogger`: Writes CSV + JSON detection records

### `utils/helpers.py`
- Drawing functions: bounding boxes, speed badges, FPS, violation banners
- `FPSCounter`: Rolling average FPS measurement
- `preprocess_for_ocr()`: Full preprocessing pipeline
- `VehicleSpeedSimulator`: Realistic simulated speed for demo

---

## Performance Tips

### Speed Optimization
1. **Frame skipping**: Set `frame_skip: 2` or `3` in config
2. **Smaller model**: Use `yolov8n.pt` (nano) instead of larger variants
3. **GPU**: Set `device: "cuda"` for 5–10× speedup
4. **Resize**: Reduce `resize_width/height` for faster inference
5. **Disable tracking**: Use `--no-tracking` if tracking not needed

### Accuracy Improvement
1. **More training data**: At least 1000+ annotated images per class
2. **Data augmentation**: Random brightness, rotation, blur
3. **Higher model**: Use `yolov8m.pt` or `yolov8l.pt`
4. **OCR upscaling**: Increase `upscale_factor` to 3.0–4.0
5. **Confidence tuning**: Lower threshold for distant/small signs

### OCR Accuracy
1. Ensure good lighting in video
2. Increase `padding` for tight crops
3. Try different Tesseract PSM modes (6, 7, 8)
4. Use `--oem 1` (LSTM only) vs `--oem 3` (combined)

---

## Presentation Key Points

### 1. Why YOLOv8?
> *"YOLOv8 is a single-stage detector that performs bounding box regression
> and class prediction in a single forward pass through the neural network.
> This makes it extremely fast — capable of 30+ FPS on CPU — which is
> essential for real-time traffic monitoring."*

### 2. Why Tesseract for OCR?
> *"Tesseract uses an LSTM neural network to recognise characters. We apply
> a digit-only whitelist to eliminate misreads, and a full preprocessing
> pipeline — CLAHE contrast enhancement, Gaussian blur, and Otsu
> binarisation — to maximise accuracy on varying lighting conditions."*

### 3. Why DeepSORT for Tracking?
> *"DeepSORT extends basic IoU tracking with a deep appearance descriptor —
> a 128-dimensional embedding vector per detection — allowing vehicles to
> be re-identified after partial occlusion. A Kalman filter predicts
> positions between frames, making IDs stable even during brief gaps."*

### 4. Real-World Deployment
> *"In production, vehicle speed would be measured by roadside radar or
> lidar sensors, or estimated via optical flow between frames. Our system
> uses simulated speed values for demonstration, but the violation logic
> and logging infrastructure is production-ready."*

### 5. System Pipeline
> *"Each video frame goes through five stages: detection, OCR, tracking,
> violation checking, and logging — all running in under 33ms at 30 FPS
> on a modern CPU. The modular architecture allows any component to be
> swapped independently."*

### 6. Limitations & Future Work
> *"Current limitations include OCR sensitivity to sign angle and occlusion,
> and simulated rather than real vehicle speeds. Future improvements could
> include fisheye camera correction, nighttime IR imaging support,
> and integration with real radar speed sensors via serial interface."*

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `TesseractNotFoundError` | Install Tesseract system binary (see Step 4) |
| `FileNotFoundError: speed_limit_model.pt` | Place your `.pt` file in `models/` |
| `Cannot open video source: 0` | Check webcam is connected / try `--source 1` |
| Low OCR accuracy | Increase `upscale_factor`, ensure sign is well-lit |
| Slow FPS | Set `frame_skip: 3`, use smaller model, or enable GPU |
| DeepSORT install error | `pip install deep-sort-realtime` or use `--no-tracking` |
| CUDA out of memory | Set `device: "cpu"` or reduce `imgsz` to 320 |

---

## License

This project is built for academic/educational purposes.
YOLOv8 is developed by [Ultralytics](https://ultralytics.com) under AGPL-3.0.
Tesseract OCR is open-source under Apache 2.0.

---

*Built as a university final-year project in Computer Vision & Machine Learning.*
