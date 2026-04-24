import { useState, useEffect, useRef, useCallback } from 'react'

// ─── Constants ────────────────────────────────────────────────────────────────

const DEFAULT_CAPTURE_INTERVAL_MS = 100    // ~10 FPS target
const JPEG_QUALITY = 0.82
const WS_RECONNECT_DELAY_MS = 2000         // Wait before reconnecting after error
const MAX_RECONNECT_ATTEMPTS = 5

// ─── WebSocket URL builder ─────────────────────────────────────────────────────

function buildWsUrl(path = '/ws/live-stream') {
  const base = import.meta.env.VITE_API_BASE_URL || ''
  if (base) {
    // Convert http(s):// to ws(s)://
    return base.replace(/^http/, 'ws') + path
  }
  // Same-host relative WebSocket
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}${path}`
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useWebSocketStream() {

  // ── Refs ──────────────────────────────────────────────────────────────────
  const videoRef       = useRef(null)
  const canvasElRef      = useRef(null)
  const streamRef      = useRef(null)
  const wsRef          = useRef(null)          // WebSocket instance
  const intervalRef    = useRef(null)          // Capture interval
  const reconnectCount = useRef(0)
  const isClosingRef   = useRef(false)         // Intentional close flag

  // ── State ─────────────────────────────────────────────────────────────────
  const [isRunning,    setIsRunning]    = useState(false)
  const [isLoading,    setIsLoading]    = useState(false)
  const [wsStatus,     setWsStatus]     = useState('disconnected')  // connecting|open|closed|error
  const [cameraError,  setCameraError]  = useState(null)
  const [wsError,      setWsError]      = useState(null)

  const [detectionResult, setDetectionResult] = useState(null)
  const [processedFrame,  setProcessedFrame]  = useState(null)
  const [stats, setStats] = useState({
    fps: 0, violations: 0, speedLimit: null,
    totalFrames: 0, throttledFrames: 0,
  })
  const [sessionLog, setSessionLog] = useState([])

  const [options, setOptions] = useState({
    captureIntervalMs: DEFAULT_CAPTURE_INTERVAL_MS,
  })

  // ── WebSocket lifecycle ────────────────────────────────────────────────────

  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    if (isClosingRef.current) return

    const url = buildWsUrl('/ws/live-stream')
    setWsStatus('connecting')
    setWsError(null)

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setWsStatus('open')
      reconnectCount.current = 0
      setWsError(null)
    }

    ws.onmessage = (event) => {
      let msg
      try {
        msg = JSON.parse(event.data)
      } catch {
        return
      }

      // Throttled ack — server dropped the frame, update counter only
      if (msg.throttled) {
        setStats(prev => ({ ...prev, throttledFrames: prev.throttledFrames + 1 }))
        return
      }

      // Error from server
      if (msg.error) {
        setWsError(msg.error)
        return
      }

      // Normal result frame
      if (msg.frame) {
        setProcessedFrame(`data:image/jpeg;base64,${msg.frame}`)
      }

      setDetectionResult(msg)
      setStats(prev => ({
        fps:             msg.fps ?? prev.fps,
        violations:      msg.violations ?? prev.violations,
        speedLimit:      msg.speed_limit ?? prev.speedLimit,
        totalFrames:     msg.frame_id ?? prev.totalFrames,
        throttledFrames: prev.throttledFrames,
      }))

      // Append to session log on violation events
      if (msg.alert === 'VIOLATION') {
        setSessionLog(prev => [{
          id:          Date.now(),
          timestamp:   new Date().toISOString(),
          frameId:     msg.frame_id,
          speedLimit:  msg.speed_limit,
          status:      msg.alert,
          procMs:      msg.proc_ms,
        }, ...prev].slice(0, 200))
      }
    }

    ws.onerror = () => {
      setWsStatus('error')
      setWsError('WebSocket connection error. Is the backend running?')
    }

    ws.onclose = (event) => {
      setWsStatus('disconnected')
      wsRef.current = null

      if (isClosingRef.current) return  // Intentional stop

      // Auto-reconnect with backoff
      if (reconnectCount.current < MAX_RECONNECT_ATTEMPTS && isRunning) {
        reconnectCount.current++
        const delay = WS_RECONNECT_DELAY_MS * reconnectCount.current
        setTimeout(connectWebSocket, delay)
      } else {
        setWsError(`WebSocket closed (code ${event.code}). Max reconnects reached.`)
      }
    }
  }, [isRunning])

  // ── Camera initialization ──────────────────────────────────────────────────

  const startCamera = useCallback(async () => {
    setIsLoading(true)
    setCameraError(null)
    isClosingRef.current = false

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } },
        audio: false,
      })
      streamRef.current = stream

      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }

      const track = stream.getVideoTracks()[0]
      const { width = 1280, height = 720 } = track.getSettings()
      if (!canvasElRef.current) {
        canvasElRef.current = document.createElement('canvas')
      }
      canvasElRef.current.width  = width
      canvasElRef.current.height = height

      setIsRunning(true)
      setIsLoading(false)

      // Connect WebSocket and start capture interval
      connectWebSocket()
      intervalRef.current = setInterval(captureAndSend, options.captureIntervalMs)

    } catch (err) {
      setIsLoading(false)
      setCameraError(
        err.name === 'NotAllowedError' ? 'Camera permission denied.'
        : err.name === 'NotFoundError' ? 'No camera found.'
        : `Camera error: ${err.message}`
      )
    }
  }, [options.captureIntervalMs, connectWebSocket])

  // ── Stop ──────────────────────────────────────────────────────────────────

  const stopCamera = useCallback(() => {
    isClosingRef.current = true

    clearInterval(intervalRef.current)
    intervalRef.current = null

    if (wsRef.current) {
      wsRef.current.close(1000, 'Client stopped session')
      wsRef.current = null
    }

    streamRef.current?.getTracks().forEach(t => t.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null

    setIsRunning(false)
    setWsStatus('disconnected')
    setProcessedFrame(null)
  }, [])

  useEffect(() => () => stopCamera(), [stopCamera])

  // ── Frame capture and send ─────────────────────────────────────────────────

  const captureAndSend = useCallback(() => {
    if (
      !videoRef.current ||
      !canvasElRef.current ||
      videoRef.current.readyState < 2 ||
      wsRef.current?.readyState !== WebSocket.OPEN
    ) return

    const ctx = canvasElRef.current.getContext('2d')
    ctx.drawImage(videoRef.current, 0, 0, canvasElRef.current.width, canvasElRef.current.height)

    // toBlob → base64 → send as JSON text message
    canvasElRef.current.toBlob((blob) => {
      if (!blob || wsRef.current?.readyState !== WebSocket.OPEN) return
      const reader = new FileReader()
      reader.onloadend = () => {
        if (wsRef.current?.readyState !== WebSocket.OPEN) return
        // reader.result is "data:image/jpeg;base64,<data>"
        const b64 = reader.result.split(',')[1]
        wsRef.current.send(JSON.stringify({ frame: b64 }))
      }
      reader.readAsDataURL(blob)
    }, 'image/jpeg', JPEG_QUALITY)
  }, [])

  // ── Option updater ─────────────────────────────────────────────────────────

  const updateOption = useCallback((key, value) => {
    setOptions(prev => ({ ...prev, [key]: value }))
    if (key === 'captureIntervalMs' && intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = setInterval(captureAndSend, value)
    }
  }, [captureAndSend])

  const clearLog = useCallback(() => setSessionLog([]), [])

  // ── Public API ─────────────────────────────────────────────────────────────

  return {
    videoRef,
    isRunning,
    isLoading,
    wsStatus,
    cameraError,
    wsError,
    detectionResult,
    processedFrame,
    stats,
    sessionLog,
    options,
    startCamera,
    stopCamera,
    updateOption,
    clearLog,
  }
}
