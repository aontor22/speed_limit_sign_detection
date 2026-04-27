import React, { useState, useRef, useCallback } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

const ACCEPT_TYPES = [
  'image/jpeg', 'image/png', 'image/bmp', 'image/webp',
  'video/mp4', 'video/x-msvideo', 'video/quicktime',
  'video/x-matroska', 'video/webm',
].join(',')

// ─── Status badge ─────────────────────────────────────────────
function AlertBadge({ status }) {
  if (status === 'VIOLATION') return <span className="badge-danger">VIOLATION</span>
  if (status === 'SAFE') return <span className="badge-safe">SAFE</span>
  return <span className="badge-neutral">{status || 'NONE'}</span>
}

// ─── Main component ────────────────────────────────────────────
export default function MediaUploadPanel({
  mode,
  setMode,
  handleFileUpload,
  isRunning,
}) {
  const fileInputRef = useRef(null)

  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [progress, setProgress] = useState('')
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [preview, setPreview] = useState(null)

  // Options
  const [frameSkip, setFrameSkip] = useState(2)
  const [includeFrames, setIncludeFrames] = useState(false)
  const [maxFrames, setMaxFrames] = useState(500)

  // ── Upload handler ──────────────────────────────────────────
  const uploadFile = useCallback(async (file) => {
    if (!file) return

    // 🔥 NEW: preview + hook sync
    const url = URL.createObjectURL(file)
    setPreview(url)
    handleFileUpload?.(file)

    setIsUploading(true)
    setError(null)
    setResult(null)
    setProgress(`Uploading ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)…`)

    const formData = new FormData()
    formData.append('file', file)

    const params = new URLSearchParams({
      frame_skip: frameSkip,
      include_frames: includeFrames,
      max_frames: maxFrames,
    })

    try {
      const resp = await fetch(`${API_BASE}/api/process-media?${params}`, {
        method: 'POST',
        body: formData,
      })

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }))
        throw new Error(err.detail || `HTTP ${resp.status}`)
      }

      setProgress('Parsing results…')
      const data = await resp.json()
      setResult(data)
      setProgress('')
    } catch (err) {
      setError(err.message)
      setProgress('')
    } finally {
      setIsUploading(false)
    }
  }, [frameSkip, includeFrames, maxFrames, handleFileUpload])

  // ── Drag-and-drop ────────────────────────────────────────────
  const onDragOver = useCallback((e) => { e.preventDefault(); setIsDragging(true) }, [])
  const onDragLeave = useCallback(() => setIsDragging(false), [])
  const onDrop = useCallback((e) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) uploadFile(file)
  }, [uploadFile])

  const onFileChange = useCallback((e) => {
    const file = e.target.files[0]
    if (file) uploadFile(file)
    e.target.value = ''
  }, [uploadFile])

  // ── Render ────────────────────────────────────────────────
  return (
    <div className="panel flex flex-col gap-0">

      {/* 🔥 MODE TOGGLE */}
      <div className="flex gap-2 p-2 border-b border-slate-800">
        {["live", "upload", "rtsp"].map(m => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`flex-1 py-1 text-xs rounded ${mode === m
                ? "bg-cyan text-black font-semibold"
                : "bg-slate-800 text-slate-400"
              }`}
          >
            {m.toUpperCase()}
          </button>
        ))}
      </div>

      <div className="panel-header">
        <span className="font-display text-sm font-semibold tracking-widest uppercase text-slate-300">
          Media Upload
        </span>
        <span className="badge-neutral">Image / Video</span>
      </div>

      <div className="p-4 flex flex-col gap-4">

        {/* LIVE MODE */}
        {mode === "live" && (
          <div className="text-xs text-slate-400 text-center">
            {isRunning ? "🟢 Camera Running" : "🔴 Camera Stopped"}
          </div>
        )}

        {/* RTSP MODE */}
        {mode === "rtsp" && (
          <input
            type="text"
            placeholder="rtsp://camera-stream-url"
            className="w-full bg-slate-800 text-xs p-2 rounded-md"
          />
        )}

        {/* UPLOAD MODE */}
        {mode === "upload" && (
          <>
            {/* Options row */}
            <div className="grid grid-cols-3 gap-2">
              <label className="flex flex-col gap-1">
                <span className="font-mono text-xs text-slate-500 uppercase tracking-wider">Frame Skip</span>
                <input
                  type="number" min={1} max={30} value={frameSkip}
                  onChange={e => setFrameSkip(Number(e.target.value))}
                  className="bg-slate-800 border border-slate-700 rounded px-2 py-1 font-mono text-xs text-slate-300"
                />
              </label>

              <label className="flex flex-col gap-1">
                <span className="font-mono text-xs text-slate-500 uppercase tracking-wider">Max Frames</span>
                <input
                  type="number" min={1} max={5000} value={maxFrames}
                  onChange={e => setMaxFrames(Number(e.target.value))}
                  className="bg-slate-800 border border-slate-700 rounded px-2 py-1 font-mono text-xs text-slate-300"
                />
              </label>

              <label className="flex flex-col gap-1 justify-end">
                <span className="font-mono text-xs text-slate-500 uppercase tracking-wider">Include Frames</span>
                <button
                  onClick={() => setIncludeFrames(v => !v)}
                  className={`py-1 px-3 rounded text-xs border ${includeFrames
                      ? 'bg-cyan/15 text-cyan border-cyan/40'
                      : 'bg-slate-800 text-slate-500 border-slate-700'
                    }`}
                >
                  {includeFrames ? 'ON' : 'OFF'}
                </button>
              </label>
            </div>

            {/* Drop zone */}
            <div
              onClick={() => fileInputRef.current?.click()}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
              className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer ${isDragging
                  ? 'border-cyan bg-cyan/5'
                  : 'border-slate-700 hover:border-slate-600'
                }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPT_TYPES}
                className="hidden"
                onChange={onFileChange}
              />

              {isUploading ? (
                <p className="text-xs text-cyan">{progress}</p>
              ) : (
                <p className="text-sm text-slate-400">
                  Drop an image or video here, or click to select
                </p>
              )}
            </div>

            {/* 🔥 Preview */}
            {preview && (
              <video
                src={preview}
                controls
                className="w-full rounded border border-slate-700"
              />
            )}
          </>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 p-2 rounded text-xs text-red-400">
            {error}
          </div>
        )}

        {/* Results */}
        {result && <MediaResult result={result} />}
      </div>
    </div>
  )
}

function MediaResult({ result }) {
  const { type, results, summary } = result
  const firstFrame = results?.[0]

  return (
    <div className="flex flex-col gap-4">

      {/* Summary */}
      <div className="panel p-3">
        <p className="text-xs text-slate-400">
          Frames: {summary?.total_frames_processed}
        </p>
        <p className="text-xs text-slate-400">
          Violations: {summary?.total_violations}
        </p>
      </div>

      {/* Preview image */}
      {firstFrame?.annotated_frame && (
        <img
          src={`data:image/jpeg;base64,${firstFrame.annotated_frame}`}
          className="w-full rounded"
        />
      )}

    </div>
  )
}