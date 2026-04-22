# 🚦 SpeedVision — React Frontend

> Real-time speed limit detection dashboard. Streams webcam frames to a
> FastAPI backend (YOLOv8 + Tesseract + DeepSORT) and visualizes detections,
> violations, and session analytics in a dark tactical UI.

---

## Project Structure

```
speed-limit-ui/
├── index.html
├── vite.config.js            ← Dev server + API proxy config
├── tailwind.config.js        ← Custom colors, fonts, animations
├── postcss.config.js
├── package.json
├── .env.example              ← Copy to .env.local
├── backend_cors_setup.py     ← Paste into your FastAPI app
│
└── src/
    ├── main.jsx              ← React entry point
    ├── App.jsx               ← Root layout + composition
    ├── index.css             ← Tailwind + global styles
    │
    ├── hooks/
    │   └── useDetection.js   ← Core pipeline hook (ALL state here)
    │
    ├── services/
    │   └── api.js            ← Axios client + response normalizer
    │
    ├── components/
    │   ├── Camera/
    │   │   ├── CameraFeed.jsx      ← Live webcam display
    │   │   └── ProcessedFeed.jsx   ← Backend annotated output
    │   ├── Detection/
    │   │   ├── ViolationAlert.jsx  ← SAFE/WARNING/VIOLATION display
    │   │   └── DetectionStats.jsx  ← FPS, latency, vehicle/sign counts
    │   ├── Controls/
    │   │   └── ControlPanel.jsx    ← Start/Stop + toggles + FPS selector
    │   ├── Logs/
    │   │   └── SessionLog.jsx      ← Events table + CSV/JSON download
    │   └── Dashboard/
    │       └── Header.jsx          ← Top bar with system status
    │
    └── utils/
        └── format.js               ← Shared formatting helpers
```

---

## Quick Start

### 1. Install dependencies

```bash
cd speed-limit-ui
npm install
```

### 2. Configure environment

```bash
cp .env.example .env.local
# Edit .env.local if your backend is not on localhost:8000
```

### 3. Configure CORS on your FastAPI backend

Open `backend_cors_setup.py` — copy the `CORSMiddleware` block into your
existing `main.py` / `app.py` before any route definitions.

### 4. Start both servers

**Terminal 1 — FastAPI backend:**
```bash
cd your-backend-folder
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — React frontend:**
```bash
cd speed-limit-ui
npm run dev
```

Open **http://localhost:3000** in your browser.

---

## How It Works

### Frame Pipeline

```
Browser Camera (getUserMedia)
        ↓
  <video> element (live preview)
        ↓
  Off-screen <canvas>  ← drawImage() every N ms
        ↓
  canvas.toBlob()  ← JPEG at 82% quality
        ↓
  FormData POST /api/process-frame
        ↓
  FastAPI (YOLO + OCR + Tracking)
        ↓
  JSON response { annotated_frame, vehicles, speed_signs, violation }
        ↓
  React state update → re-render
```

### Back-pressure / Throttling

The system uses **busy-flag back-pressure** — not a queue:

- `isBusyRef` is set to `true` when a request is in-flight
- The capture interval fires every N ms but **skips** if busy
- This naturally limits throughput to whatever the backend can sustain
- No frame queue → no accumulated lag

Additionally:
- Each new request **aborts the previous** via `AbortController`
- This prevents out-of-order responses overwriting newer data

### FPS Control

Adjustable via the UI (4 / 7 / 10 / 15 FPS target):
- 4 FPS  → 250ms interval — safest for slow backends
- 7 FPS  → 150ms — default (good for CPU-only YOLO)
- 10 FPS → 100ms — needs GPU or fast server
- 15 FPS → 67ms  — requires < 60ms average backend latency

---

## Backend API Contract

The frontend expects your FastAPI endpoint to accept:

**`POST /api/process-frame`**

| Parameter | Type | Description |
|-----------|------|-------------|
| `frame`   | File (multipart) | JPEG image blob |
| `enable_vehicles` | query bool | Whether to run vehicle detection |
| `enable_ocr`      | query bool | Whether to run OCR |

**Response JSON:**

```json
{
  "annotated_frame": "<base64-jpeg-string>",
  "vehicles": [
    { "id": 1, "bbox": [x1,y1,x2,y2], "class_name": "Car",
      "confidence": 0.92, "speed": 67.3 }
  ],
  "speed_signs": [
    { "bbox": [x1,y1,x2,y2], "confidence": 0.88,
      "ocr_text": "60", "speed_limit": 60 }
  ],
  "current_speed_limit": 60,
  "violation": {
    "status": "VIOLATION",
    "vehicle_id": 1,
    "speed": 67.3,
    "limit": 60,
    "excess_speed": 7.3
  },
  "processing_time_ms": 45,
  "frame_id": 1023
}
```

The `api.js` normalizer handles variations in field names (e.g.
`bounding_box` vs `bbox`, `track_id` vs `id`). See `normalizeResponse()`
in `src/services/api.js` to adapt to your exact schema.

---

## Performance Optimization Notes

### Why multipart/form-data instead of base64?
Base64 encoding inflates binary data by ~33%. Sending JPEG as raw binary
via FormData is faster and uses less bandwidth — especially important when
sending 10+ frames per second.

### Why JPEG at 82% quality?
A 1280×720 frame:
- PNG: ~2.5 MB
- JPEG 95%: ~180 KB
- JPEG 82%: ~95 KB  ← our choice
- JPEG 60%: ~45 KB (visible quality loss affecting OCR)

82% hits the sweet spot of small payload without degrading OCR accuracy
on sign text.

### Why AbortController per request?
If the backend takes 300ms but we capture every 150ms, without abort
we'd queue up 2 in-flight requests. The 2nd response might arrive before
the 1st, causing the UI to flash backwards. AbortController ensures
only the latest request's response is applied.

---

## Presentation Key Points

| Topic | What to say |
|-------|-------------|
| **Architecture** | "The frontend uses a unidirectional data flow: camera → canvas → API → state → UI. All state lives in a single custom hook (useDetection) making it easy to test and debug." |
| **Performance** | "We avoid frame queuing by using a busy flag. The interval fires at the target rate, but if the backend hasn't responded yet, we skip that frame. This gives natural back-pressure without lag accumulation." |
| **Abort Controller** | "Every new frame request cancels the previous one. This prevents stale responses from racing and overwriting newer data — a common bug in naive polling implementations." |
| **State management** | "No Redux or Zustand needed. React hooks plus a single custom hook provide all the state management needed for this real-time pipeline." |
| **CORS & Proxy** | "In development, Vite proxies /api requests to localhost:8000, so there are no CORS issues during development. In production, we configure FastAPI's CORS middleware." |
| **Download reports** | "Session logs are accumulated in React state and can be exported as CSV or JSON. This provides an audit trail for the violation monitoring system." |

---

## Production Build

```bash
npm run build
# Output in dist/ — serve with any static file server
# e.g.: npx serve dist
```

For production, set `VITE_API_BASE_URL` to your deployed backend URL
in your hosting environment's environment variables.
