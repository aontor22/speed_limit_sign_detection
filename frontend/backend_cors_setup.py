"""
backend_cors_setup.py
======================
Add this CORS configuration to your existing FastAPI app.
Paste into your main.py / app.py BEFORE any route definitions.

This allows the React dev server (localhost:3000) to call your API.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Speed Limit Detection API")

# ── CORS ──────────────────────────────────────────────────────────────────────
# In development: allow React dev server
# In production: replace with your actual frontend domain

ALLOWED_ORIGINS = [
    "http://localhost:3000",       # Vite dev server
    "http://127.0.0.1:3000",
    "http://localhost:5173",       # Vite alternative port
    # "https://your-production-domain.com",  # Add in production
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ── Expected /api/process-frame endpoint shape ────────────────────────────────
# Your endpoint should accept multipart/form-data with a 'frame' file field.
# Query params: enable_vehicles (bool), enable_ocr (bool)
#
# Example minimal endpoint (adapt to your existing code):
#
# from fastapi import File, UploadFile, Query
# import base64, cv2, numpy as np
#
# @app.post("/api/process-frame")
# async def process_frame(
#     frame: UploadFile = File(...),
#     enable_vehicles: bool = Query(True),
#     enable_ocr: bool = Query(True),
# ):
#     contents = await frame.read()
#     nparr = np.frombuffer(contents, np.uint8)
#     img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
#
#     # Run your existing pipeline here...
#     # result = your_pipeline.process(img, enable_vehicles, enable_ocr)
#
#     # Encode annotated frame
#     _, buffer = cv2.imencode('.jpg', annotated_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
#     frame_b64 = base64.b64encode(buffer).decode('utf-8')
#
#     return {
#         "annotated_frame": frame_b64,          # base64 string (no data: prefix needed)
#         "vehicles": [
#             {
#                 "id": 1,
#                 "bbox": [x1, y1, x2, y2],
#                 "class_name": "Car",
#                 "confidence": 0.92,
#                 "speed": 67.3                  # simulated or real
#             }
#         ],
#         "speed_signs": [
#             {
#                 "bbox": [x1, y1, x2, y2],
#                 "confidence": 0.88,
#                 "ocr_text": "60",
#                 "speed_limit": 60
#             }
#         ],
#         "current_speed_limit": 60,
#         "violation": {
#             "status": "SAFE",                  # "SAFE" | "WARNING" | "VIOLATION"
#             "vehicle_id": 1,
#             "speed": 67.3,
#             "limit": 60,
#             "excess_speed": 7.3,
#             "severity": "MINOR"
#         },
#         "processing_time_ms": 45,
#         "frame_id": 1023
#     }
#
# @app.get("/api/health")
# async def health():
#     return {"status": "ok", "model": "loaded"}
