/**
 * services/api.js
 * ===============
 * Centralized API service for communicating with the FastAPI backend.
 *
 * Design decisions:
 *  - Uses multipart/form-data (not base64) for frame upload:
 *    → Smaller payload (~30% less data vs base64 string)
 *    → No JSON serialization overhead for binary image data
 *  - Axios instance with timeout + interceptors for clean error handling
 *  - AbortController support so in-flight requests can be cancelled
 *    when a newer frame arrives (prevents out-of-order responses)
 */

import axios from 'axios'

// ─── Axios Instance ──────────────────────────────────────────────────────────

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 20000,        // 20s hard limit per frame request
  headers: {
    Accept: 'application/json',
  },
})

// Response interceptor — normalize error shape
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const normalized = {
      message: error.message || 'Network error',
      status:  error.response?.status || 0,
      detail:  error.response?.data?.detail || null,
      isAbort: axios.isCancel(error),
      isTimeout: error.code === 'ECONNABORTED',
      isNetwork: !error.response,
    }
    return Promise.reject(normalized)
  },
)

// ─── Frame Processing ─────────────────────────────────────────────────────────

/**
 * Send one video frame to the backend for YOLO + OCR + violation processing.
 *
 * @param {Blob}   frameBlob     - JPEG blob of the captured canvas frame
 * @param {Object} options       - Processing flags
 * @param {boolean} options.enableVehicleDetection
 * @param {boolean} options.enableOCR
 * @param {AbortSignal} signal   - AbortController signal to cancel stale requests
 * @returns {Promise<DetectionResult>}
 */
export async function processFrame(frameBlob, options = {}, signal = null) {
  const formData = new FormData()
  formData.append('frame', frameBlob, 'frame.jpg')

  // Pass processing flags as query params (keep body for binary only)
  const params = {
    enable_vehicles: options.enableVehicleDetection ?? true,
    enable_ocr:      options.enableOCR ?? true,
  }

  const response = await apiClient.post('/api/process-frame', formData, {
    params,
    signal,
    headers: { 'Content-Type': 'multipart/form-data' },
  })

  return normalizeResponse(response.data)
}

/**
 * Health check — used to verify backend is reachable before starting session.
 */
export async function checkHealth() {
  try {
    const response = await apiClient.get('/api/health', { timeout: 3000 })
    return { ok: true, data: response.data }
  } catch (err) {
    return { ok: false, error: err }
  }
}

// ─── Response Normalizer ──────────────────────────────────────────────────────

/**
 * Normalize the backend JSON response into a consistent frontend shape.
 * This shields the UI from backend API changes — only update here.
 *
 * Expected backend shape (adjust field names to match your FastAPI schema):
 * {
 *   annotated_frame: "data:image/jpeg;base64,...",  // or just base64 string
 *   vehicles: [ { id, bbox, class_name, confidence, speed } ],
 *   speed_signs: [ { bbox, confidence, ocr_text, speed_limit } ],
 *   violation: { status: "SAFE"|"WARNING"|"VIOLATION", vehicle_id, speed, limit },
 *   processing_time_ms: 45,
 *   frame_id: 1023
 * }
 *
 * @param {Object} raw - Raw backend JSON
 * @returns {DetectionResult}
 */
function normalizeResponse(raw) {
  // Normalize annotated frame to always have the data: prefix
  let annotatedFrame = raw.annotated_frame || raw.frame || null
  if (annotatedFrame && !annotatedFrame.startsWith('data:')) {
    annotatedFrame = `data:image/jpeg;base64,${annotatedFrame}`
  }

  // Normalize violation status
  const violationRaw = raw.violation || raw.violation_status || {}
  const violationStatus = (
    typeof violationRaw === 'string'
      ? violationRaw
      : violationRaw.status || 'UNKNOWN'
  ).toUpperCase()

  return {
    // Processed frame for display
    annotatedFrame,

    // Vehicle detections array
    vehicles: (raw.vehicles || []).map((v) => ({
      id:         v.id ?? v.track_id ?? -1,
      bbox:       normalizeBbox(v.bbox || v.bounding_box),
      className:  v.class_name || v.type || 'vehicle',
      confidence: v.confidence ?? 0,
      speed:      v.speed ?? v.estimated_speed ?? null,
    })),

    // Speed sign detections array
    speedSigns: (raw.speed_signs || raw.signs || []).map((s) => ({
      bbox:       normalizeBbox(s.bbox || s.bounding_box),
      confidence: s.confidence ?? 0,
      ocrText:    s.ocr_text || s.raw_text || '',
      speedLimit: s.speed_limit ?? s.speed ?? null,
    })),

    // Best current speed limit (from most confident sign)
    currentSpeedLimit: raw.current_speed_limit
      ?? raw.speed_signs?.[0]?.speed_limit
      ?? raw.signs?.[0]?.speed_limit
      ?? null,

    // Violation info
    violation: {
      status:     violationStatus,          // 'SAFE' | 'WARNING' | 'VIOLATION' | 'UNKNOWN'
      vehicleId:  violationRaw.vehicle_id   ?? null,
      speed:      violationRaw.speed        ?? violationRaw.vehicle_speed ?? null,
      limit:      violationRaw.limit        ?? violationRaw.speed_limit ?? null,
      excess:     violationRaw.excess_speed ?? null,
      severity:   violationRaw.severity     ?? null,
    },

    // Metadata
    processingTimeMs: raw.processing_time_ms ?? raw.latency_ms ?? null,
    frameId:          raw.frame_id ?? null,
    timestamp:        raw.timestamp ?? Date.now(),
  }
}

/** Normalize various bbox formats to [x1, y1, x2, y2] */
function normalizeBbox(bbox) {
  if (!bbox) return [0, 0, 0, 0]
  if (Array.isArray(bbox)) return bbox
  if (typeof bbox === 'object') {
    return [
      bbox.x1 ?? bbox.x ?? 0,
      bbox.y1 ?? bbox.y ?? 0,
      bbox.x2 ?? (bbox.x + bbox.w) ?? 0,
      bbox.y2 ?? (bbox.y + bbox.h) ?? 0,
    ]
  }
  return [0, 0, 0, 0]
}

export default apiClient
