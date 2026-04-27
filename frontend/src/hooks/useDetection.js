import { useState, useEffect, useRef, useCallback } from 'react'
import { processFrame } from '../services/api.js'

// ─── Constants ────────────────────────────────────────────────────────────────

const DEFAULT_CAPTURE_INTERVAL_MS = 300   // ~6-7 FPS effective (safe for most backends)
const MAX_LOG_ENTRIES = 200               // Session history limit
const JPEG_QUALITY = 0.82                 // Canvas toBlob quality (0–1)

// ─── Initial State ────────────────────────────────────────────────────────────

const initialStats = {
  captureFps: 0,
  responseFps: 0,
  avgLatencyMs: 0,
  totalFrames: 0,
  totalDetections: 0,
  totalViolations: 0,
  droppedFrames: 0,
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useDetection() {

  // ── Refs (mutable, no re-render) ─────────────────────────────────────────
  const videoRef = useRef(null)    // <video> DOM element
  const canvasRef = useRef(null)    // Off-screen <canvas> for frame capture
  const streamRef = useRef(null)    // MediaStream
  const intervalRef = useRef(null)    // setInterval handle
  const abortRef = useRef(null)    // AbortController for current request
  const isBusyRef = useRef(false)   // True while a request is in-flight
  const latencyBuf = useRef([])      // Rolling latency samples
  const captureTimesRef = useRef([])      // For capture FPS calculation
  const responseTimesRef = useRef([])     // For response FPS calculation

  // ── State (triggers re-render) ────────────────────────────────────────────
  const [isRunning, setIsRunning] = useState(false)
  const [isLoading, setIsLoading] = useState(false)   // Initializing camera
  const [isProcessing, setIsProcessing] = useState(false)   // Request in-flight
  const [cameraError, setCameraError] = useState(null)
  const [backendError, setBackendError] = useState(null)

  const [detectionResult, setDetectionResult] = useState(null)
  const [processedFrame, setProcessedFrame] = useState(null)
  const [stats, setStats] = useState(initialStats)
  const [sessionLog, setSessionLog] = useState([])

  const [mode, setMode] = useState("live")
  // "live" | "upload" | "rtsp"

  const [uploadedFile, setUploadedFile] = useState(null)

  const handleFileUpload = useCallback((file) => {
    if (!file) return

    setUploadedFile(file)
    setMode("upload")   // 🔥 AUTO SWITCH
  }, [])

  // ── Processing options (controlled by UI toggles) ─────────────────────────
  const [options, setOptions] = useState({
    enableVehicleDetection: true,
    enableOCR: true,
    captureIntervalMs: DEFAULT_CAPTURE_INTERVAL_MS,
  })

  // ── Capture interval reactive to options ─────────────────────────────────
  useEffect(() => {
    if (isRunning) {
      restartInterval()
    }
  }, [options.captureIntervalMs]) // eslint-disable-line

  // ─── Camera Initialization ─────────────────────────────────────────────────

  const startCamera = useCallback(async () => {
    if (mode !== "live") return   // prevent wrong mode
    setIsLoading(true)
    setCameraError(null)
    setBackendError(null)

    try {
      const constraints = {
        video: {
          width: { ideal: 1280, max: 1920 },
          height: { ideal: 720, max: 1080 },
          frameRate: { ideal: 30, max: 60 },
          facingMode: 'environment',   // Prefer rear camera on mobile
        },
        audio: false,
      }

      const stream = await navigator.mediaDevices.getUserMedia(constraints)
      streamRef.current = stream

      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }

      // Create off-screen canvas sized to video track
      const track = stream.getVideoTracks()[0]
      const { width = 1280, height = 720 } = track.getSettings()

      if (!canvasRef.current) {
        canvasRef.current = document.createElement('canvas')
      }
      canvasRef.current.width = width
      canvasRef.current.height = height

      setIsRunning(true)
      setIsLoading(false)
      startInterval()

    } catch (err) {
      setIsLoading(false)
      if (err.name === 'NotAllowedError') {
        setCameraError('Camera permission denied. Please allow camera access and refresh.')
      } else if (err.name === 'NotFoundError') {
        setCameraError('No camera found. Please connect a webcam.')
      } else if (err.name === 'NotReadableError') {
        setCameraError('Camera is in use by another application.')
      } else {
        setCameraError(`Camera error: ${err.message}`)
      }
    }
  }, [mode]) // eslint-disable-line


  // ─── Stop Camera + Cleanup ─────────────────────────────────────────────────

  const stopCamera = useCallback(() => {
    // Stop interval
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }

    // Abort any in-flight request
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }

    // Stop media stream tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null
    }

    isBusyRef.current = false
    setIsRunning(false)
    setIsProcessing(false)
    setProcessedFrame(null)
  }, [])

  useEffect(() => {
    if (mode !== "live" && isRunning) {
      stopCamera()
    }
  }, [mode, isRunning, stopCamera])

  // Cleanup on unmount
  useEffect(() => () => stopCamera(), [stopCamera])

  // ─── Frame Capture Interval ────────────────────────────────────────────────

  function startInterval() {
    if (intervalRef.current) clearInterval(intervalRef.current)
    intervalRef.current = setInterval(captureAndSend, options.captureIntervalMs)
  }

  function restartInterval() {
    if (intervalRef.current) clearInterval(intervalRef.current)
    if (isRunning) {
      intervalRef.current = setInterval(captureAndSend, options.captureIntervalMs)
    }
  }

  // ─── Core: Capture Frame → Send to Backend ─────────────────────────────────

  const captureAndSend = useCallback(async () => {
    // Skip if: video not ready, busy, not running
    if (
      !videoRef.current ||
      !canvasRef.current ||
      videoRef.current.readyState < 2 ||
      isBusyRef.current
    ) {
      setStats((prev) => ({ ...prev, droppedFrames: prev.droppedFrames + 1 }))
      return
    }

    // Record capture time for FPS calculation
    const captureTs = performance.now()
    captureTimesRef.current.push(captureTs)
    if (captureTimesRef.current.length > 30) captureTimesRef.current.shift()

    // Draw current video frame to canvas
    const ctx = canvasRef.current.getContext('2d')
    ctx.drawImage(
      videoRef.current,
      0, 0,
      canvasRef.current.width,
      canvasRef.current.height,
    )

    // Convert canvas to JPEG Blob (async, non-blocking)
    let frameBlob
    try {
      frameBlob = await canvasToBlob(canvasRef.current, JPEG_QUALITY)
    } catch {
      return  // Canvas not ready
    }

    // Abort previous in-flight request
    if (abortRef.current) abortRef.current.abort()
    abortRef.current = new AbortController()

    isBusyRef.current = true
    setIsProcessing(true)

    const requestStart = performance.now()

    try {
      const result = await processFrame(
        frameBlob,
        { enableVehicleDetection: options.enableVehicleDetection, enableOCR: options.enableOCR },
        abortRef.current.signal,
      )

      const latency = performance.now() - requestStart

      // Update response FPS buffer
      responseTimesRef.current.push(performance.now())
      if (responseTimesRef.current.length > 30) responseTimesRef.current.shift()

      // Rolling latency average (last 20 samples)
      latencyBuf.current.push(latency)
      if (latencyBuf.current.length > 20) latencyBuf.current.shift()
      const avgLatency = latencyBuf.current.reduce((a, b) => a + b, 0) / latencyBuf.current.length

      // Update processed frame
      if (result.annotatedFrame) {
        setProcessedFrame(result.annotatedFrame)
      }

      // Update detection result
      setDetectionResult(result)
      setBackendError(null)

      // Append to session log if there are detections or violations
      const hasEvent = result.speedSigns.length > 0 || result.violation.status === 'VIOLATION'
      if (hasEvent) {
        const logEntry = {
          id: Date.now(),
          timestamp: new Date().toISOString(),
          frameId: result.frameId,
          speedLimit: result.currentSpeedLimit,
          vehicleCount: result.vehicles.length,
          signCount: result.speedSigns.length,
          status: result.violation.status,
          vehicleSpeed: result.violation.speed,
          latencyMs: Math.round(latency),
        }
        setSessionLog((prev) => [logEntry, ...prev].slice(0, MAX_LOG_ENTRIES))
      }

      // Update aggregate stats
      setStats((prev) => {
        const captureFps = calculateFps(captureTimesRef.current)
        const responseFps = calculateFps(responseTimesRef.current)
        return {
          captureFps: Math.round(captureFps * 10) / 10,
          responseFps: Math.round(responseFps * 10) / 10,
          avgLatencyMs: Math.round(avgLatency),
          totalFrames: prev.totalFrames + 1,
          totalDetections: prev.totalDetections + result.speedSigns.length,
          totalViolations: result.violation.status === 'VIOLATION'
            ? prev.totalViolations + 1
            : prev.totalViolations,
          droppedFrames: prev.droppedFrames,
        }
      })

    } catch (err) {
      if (err.isAbort) return   // Intentional cancel — not an error
      setBackendError(
        err.isTimeout ? 'Backend timeout — request took too long'
          : err.isNetwork ? 'Backend unreachable — check FastAPI server'
            : `Backend error: ${err.message || err.detail || 'Unknown'}`
      )
    } finally {
      isBusyRef.current = false
      setIsProcessing(false)
    }
  }, [options]) // eslint-disable-line

  // ─── Option Updater ────────────────────────────────────────────────────────

  const updateOption = useCallback((key, value) => {
    setOptions((prev) => ({ ...prev, [key]: value }))
  }, [])

  // ─── Session Log Controls ──────────────────────────────────────────────────

  const clearLog = useCallback(() => setSessionLog([]), [])

  // ─── Public API ────────────────────────────────────────────────────────────

  return {
    // Refs (pass to DOM elements)
    videoRef,

    // State
    isRunning,
    isLoading,
    isProcessing,
    cameraError,
    backendError,
    detectionResult,
    processedFrame,
    stats,
    sessionLog,
    options,

    // Actions
    startCamera,
    stopCamera,
    updateOption,
    clearLog,
    mode,
    setMode,
    handleFileUpload,
  }
}

// ─── Utilities ─────────────────────────────────────────────────────────────────

/** Convert canvas to JPEG Blob via Promise */
function canvasToBlob(canvas, quality = 0.85) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => blob ? resolve(blob) : reject(new Error('Canvas toBlob failed')),
      'image/jpeg',
      quality,
    )
  })
}

/** Calculate FPS from an array of timestamps (ms) */
function calculateFps(timestamps) {
  if (timestamps.length < 2) return 0
  const span = timestamps[timestamps.length - 1] - timestamps[0]
  return span > 0 ? ((timestamps.length - 1) / span) * 1000 : 0
}
