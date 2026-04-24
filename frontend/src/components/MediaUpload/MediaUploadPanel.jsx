/**
 * components/MediaUpload/MediaUploadPanel.jsx
 * =============================================
 * Drag-and-drop / file-picker UI for the POST /api/process-media endpoint.
 * Accepts images and video files, shows results inline.
 *
 * Can be dropped into App.jsx alongside the live camera panels as a tab or
 * separate panel — it has no shared state dependencies.
 */

import React, { useState, useRef, useCallback } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

const ACCEPT_TYPES = [
  'image/jpeg', 'image/png', 'image/bmp', 'image/webp',
  'video/mp4', 'video/x-msvideo', 'video/quicktime',
  'video/x-matroska', 'video/webm',
].join(',')

// ─── Status badge ─────────────────────────────────────────────────────────────

function AlertBadge({ status }) {
  if (status === 'VIOLATION') return <span className="badge-danger">VIOLATION</span>
  if (status === 'SAFE')      return <span className="badge-safe">SAFE</span>
  return <span className="badge-neutral">{status || 'NONE'}</span>
}

// ─── Main component ────────────────────────────────────────────────────────────

export default function MediaUploadPanel() {
  const fileInputRef  = useRef(null)
  const [isDragging,  setIsDragging]  = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [progress,    setProgress]    = useState('')
  const [error,       setError]       = useState(null)
  const [result,      setResult]      = useState(null)   // ProcessMediaResponse

  // Options
  const [frameSkip,      setFrameSkip]      = useState(2)
  const [includeFrames,  setIncludeFrames]  = useState(false)
  const [maxFrames,      setMaxFrames]      = useState(500)

  // ── Upload handler ──────────────────────────────────────────────────────────

  const uploadFile = useCallback(async (file) => {
    if (!file) return
    setIsUploading(true)
    setError(null)
    setResult(null)
    setProgress(`Uploading ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)…`)

    const formData = new FormData()
    formData.append('file', file)

    const params = new URLSearchParams({
      frame_skip:     frameSkip,
      include_frames: includeFrames,
      max_frames:     maxFrames,
    })

    try {
      const resp = await fetch(
        `${API_BASE}/api/process-media?${params}`,
        { method: 'POST', body: formData }
      )

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
  }, [frameSkip, includeFrames, maxFrames])

  // ── Drag-and-drop ────────────────────────────────────────────────────────────

  const onDragOver = useCallback((e) => { e.preventDefault(); setIsDragging(true)  }, [])
  const onDragLeave = useCallback(()  => setIsDragging(false), [])
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

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="panel flex flex-col gap-0">
      <div className="panel-header">
        <span className="font-display text-sm font-semibold tracking-widest uppercase text-slate-300">
          Media Upload
        </span>
        <span className="badge-neutral">Image / Video</span>
      </div>

      <div className="p-4 flex flex-col gap-4">

        {/* Options row */}
        <div className="grid grid-cols-3 gap-2">
          <label className="flex flex-col gap-1">
            <span className="font-mono text-xs text-slate-500 uppercase tracking-wider">Frame Skip</span>
            <input
              type="number" min={1} max={30} value={frameSkip}
              onChange={e => setFrameSkip(Number(e.target.value))}
              className="bg-slate-800 border border-slate-700 rounded px-2 py-1 font-mono text-xs text-slate-300 focus:outline-none focus:border-cyan/50"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-mono text-xs text-slate-500 uppercase tracking-wider">Max Frames</span>
            <input
              type="number" min={1} max={5000} value={maxFrames}
              onChange={e => setMaxFrames(Number(e.target.value))}
              className="bg-slate-800 border border-slate-700 rounded px-2 py-1 font-mono text-xs text-slate-300 focus:outline-none focus:border-cyan/50"
            />
          </label>
          <label className="flex flex-col gap-1 justify-end">
            <span className="font-mono text-xs text-slate-500 uppercase tracking-wider">Include Frames</span>
            <button
              onClick={() => setIncludeFrames(v => !v)}
              className={`py-1 px-3 rounded text-xs font-mono border transition-colors ${
                includeFrames
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
          className={`
            relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer
            transition-all duration-200
            ${isDragging
              ? 'border-cyan bg-cyan/5'
              : 'border-slate-700 hover:border-slate-600 hover:bg-slate-800/30'
            }
          `}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPT_TYPES}
            className="hidden"
            onChange={onFileChange}
          />
          {isUploading ? (
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-2 border-t-cyan border-slate-700 rounded-full animate-spin" />
              <p className="font-mono text-xs text-cyan animate-pulse">{progress}</p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <span className="text-3xl text-slate-600">↑</span>
              <p className="font-ui text-sm text-slate-400">
                Drop an image or video here, or click to select
              </p>
              <p className="font-mono text-xs text-slate-600">
                JPG · PNG · MP4 · AVI · MOV · MKV · WEBM
              </p>
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="bg-danger/5 border border-danger/30 rounded-lg px-3 py-2.5">
            <p className="font-mono text-xs text-danger">{error}</p>
          </div>
        )}

        {/* Results */}
        {result && <MediaResult result={result} />}
      </div>
    </div>
  )
}

// ─── Result display ────────────────────────────────────────────────────────────

function MediaResult({ result }) {
  const { type, results, summary } = result
  const firstFrame = results?.[0]

  return (
    <div className="flex flex-col gap-4 animate-fade-in">

      {/* Summary */}
      <div className="panel p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="font-display text-sm font-bold text-slate-200 uppercase tracking-wider">
            {type === 'image' ? 'Image Result' : 'Video Summary'}
          </span>
          <span className="badge-cyan">{type.toUpperCase()}</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <SummaryTile label="Frames"     value={summary.total_frames_processed} />
          <SummaryTile label="Violations" value={summary.total_violations}
            valueClass={summary.total_violations > 0 ? 'text-danger' : 'text-safe'} />
          <SummaryTile label="Avg FPS"    value={summary.avg_fps} />
          <SummaryTile label="Avg Latency" value={`${summary.avg_processing_ms}ms`} />
        </div>
        {summary.unique_speed_limits.length > 0 && (
          <div className="mt-3 flex items-center gap-2">
            <span className="font-mono text-xs text-slate-500 uppercase tracking-wider">Limits detected:</span>
            {summary.unique_speed_limits.map(l => (
              <span key={l} className="font-display text-sm font-bold text-white bg-slate-800 border border-slate-700 rounded px-2 py-0.5">
                {l} km/h
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Annotated image (image type or include_frames=true) */}
      {firstFrame?.annotated_frame && (
        <div className="panel overflow-hidden">
          <div className="panel-header">
            <span className="font-mono text-xs text-slate-400 uppercase tracking-widest">Annotated Output</span>
            <AlertBadge status={firstFrame.violation?.status} />
          </div>
          <img
            src={`data:image/jpeg;base64,${firstFrame.annotated_frame}`}
            alt="Annotated detection output"
            className="w-full object-contain max-h-80"
          />
        </div>
      )}

      {/* Per-frame violations table (video type) */}
      {type === 'video' && (
        <div className="panel">
          <div className="panel-header">
            <span className="font-mono text-xs text-slate-400 uppercase tracking-widest">
              Frame Results
            </span>
            <span className="font-mono text-xs text-slate-600">{results.length} frames</span>
          </div>
          <div className="overflow-y-auto" style={{ maxHeight: 240 }}>
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-slate-900">
                <tr className="border-b border-slate-800">
                  {['Frame', 'Limit', 'Vehicles', 'Alert', 'ms'].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-mono text-slate-600 uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {results.map(r => (
                  <tr key={r.frame_id} className={`border-b border-slate-800/50 ${
                    r.violation?.status === 'VIOLATION' ? 'bg-danger/5' : ''
                  }`}>
                    <td className="px-3 py-1.5 font-mono text-slate-500">#{r.frame_id}</td>
                    <td className="px-3 py-1.5 font-display font-bold text-white">
                      {r.current_speed_limit ?? '—'}
                    </td>
                    <td className="px-3 py-1.5 font-mono text-slate-400">{r.vehicles?.length ?? 0}</td>
                    <td className="px-3 py-1.5"><AlertBadge status={r.violation?.status} /></td>
                    <td className="px-3 py-1.5 font-mono text-slate-600">
                      {r.processing_time_ms?.toFixed(0) ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Download results */}
      <button
        onClick={() => downloadJSON(result)}
        className="w-full py-2 font-mono text-xs text-cyan border border-cyan/20 hover:border-cyan/50 rounded-lg transition-colors"
      >
        ↓ Download Full Results (JSON)
      </button>
    </div>
  )
}

function SummaryTile({ label, value, valueClass = 'text-slate-200' }) {
  return (
    <div className="bg-slate-800/50 rounded-lg p-3 flex flex-col gap-1 items-center">
      <span className={`font-display text-xl font-bold leading-none ${valueClass}`}>{value}</span>
      <span className="font-mono text-xs text-slate-600 uppercase tracking-widest">{label}</span>
    </div>
  )
}

function downloadJSON(data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `speedvision_media_${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
}
