from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
import base64

from app import process_frame
from system import build_system
from utils.config_loader import load_config


# ─────────────────────────────────────────────────────────────
# Fake Args class (for API mode)
# ─────────────────────────────────────────────────────────────
class Args:
    def __init__(self):
        self.no_vehicles = False
        self.no_tracking = False
        self.config = "config.yaml"


# ─────────────────────────────────────────────────────────────
# Global state
# ─────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────
app = FastAPI()


# 🔥 CORS (ALLOW EVERYTHING FOR DEBUG — no frontend issues)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # ← important fix
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────
@app.get("/")
def home():
    return {"status": "Speed Limit Detection API running"}


# ─────────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    global cfg, components

    args = Args()
    cfg = load_config(args.config)
    components = build_system(cfg, args)


# ─────────────────────────────────────────────────────────────
# Main API
# ─────────────────────────────────────────────────────────────
@app.post("/api/process-frame")
async def process_frame_api(file: UploadFile = File(...)):
    global state, components, cfg

    try:
        contents = await file.read()
        npimg = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

        # Safety check
        if frame is None:
            return {"error": "Invalid image received"}

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
            "stats": {
                "fps": state.get("fps", 0),
                "violations": state.get("total_violations", 0)
            },
            "alert": "VIOLATION" if state.get("total_violations", 0) > 0 else "SAFE"
        }

    except Exception as e:
        return {"error": str(e)}