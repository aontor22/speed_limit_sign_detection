/**
 * components/Detection/DetectionStats.jsx
 * =========================================
 * Displays real-time stats grid:
 *  - Capture FPS / Response FPS
 *  - Avg latency
 *  - Total frames processed
 *  - Signs detected / Violations count
 *  - Detected vehicles list
 *  - OCR result details
 */

import React from 'react'

export default function DetectionStats({ stats, detectionResult }) {
  const vehicles  = detectionResult?.vehicles  || []
  const speedSigns = detectionResult?.speedSigns || []
  const latency   = detectionResult?.processingTimeMs ?? stats?.avgLatencyMs ?? null

  return (
    <div className="flex flex-col gap-3">

      {/* FPS + Latency Row */}
      <div className="grid grid-cols-3 gap-2">
        <MetricCard
          label="Capture FPS"
          value={stats.captureFps}
          unit=""
          valueClass={stats.captureFps >= 8 ? 'text-safe' : stats.captureFps >= 4 ? 'text-warn' : 'text-danger'}
        />
        <MetricCard
          label="Response FPS"
          value={stats.responseFps}
          unit=""
          valueClass={stats.responseFps >= 5 ? 'text-safe' : stats.responseFps >= 2 ? 'text-warn' : 'text-slate-400'}
        />
        <MetricCard
          label="Latency"
          value={stats.avgLatencyMs > 0 ? stats.avgLatencyMs : '—'}
          unit={stats.avgLatencyMs > 0 ? 'ms' : ''}
          valueClass={
            !stats.avgLatencyMs ? 'text-slate-500'
            : stats.avgLatencyMs < 200 ? 'text-safe'
            : stats.avgLatencyMs < 600 ? 'text-warn'
            : 'text-danger'
          }
        />
      </div>

      {/* Totals Row */}
      <div className="grid grid-cols-3 gap-2">
        <MetricCard label="Frames"     value={stats.totalFrames}     valueClass="text-cyan" />
        <MetricCard label="Signs"      value={stats.totalDetections} valueClass="text-slate-300" />
        <MetricCard label="Violations" value={stats.totalViolations}
          valueClass={stats.totalViolations > 0 ? 'text-danger' : 'text-slate-400'}
        />
      </div>

      {/* Current Detections */}
      <div className="panel">
        <div className="panel-header">
          <span className="font-mono text-xs text-slate-400 uppercase tracking-widest">
            Current Frame
          </span>
          <span className="font-mono text-xs text-slate-600">
            {detectionResult?.frameId ? `#${detectionResult.frameId}` : '—'}
          </span>
        </div>
        <div className="p-3 flex flex-col gap-2">

          {/* Speed Signs */}
          <div className="flex items-start justify-between gap-2">
            <span className="font-mono text-xs text-slate-500 uppercase tracking-wider pt-0.5">Signs</span>
            {speedSigns.length === 0 ? (
              <span className="font-mono text-xs text-slate-700">No signs detected</span>
            ) : (
              <div className="flex flex-wrap gap-1.5 justify-end">
                {speedSigns.map((s, i) => (
                  <div key={i} className="flex items-center gap-1.5 bg-slate-800 rounded px-2 py-1 border border-slate-700">
                    <span className="font-display text-sm font-bold text-white">
                      {(s.speedLimit ?? s.ocrText) || '?'}
                    </span>
                    <span className="font-mono text-xs text-slate-500">
                      {(s.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="border-t border-slate-800" />

          {/* Vehicles */}
          <div className="flex items-start justify-between gap-2">
            <span className="font-mono text-xs text-slate-500 uppercase tracking-wider pt-0.5">Vehicles</span>
            {vehicles.length === 0 ? (
              <span className="font-mono text-xs text-slate-700">No vehicles detected</span>
            ) : (
              <div className="flex flex-col gap-1 items-end">
                {vehicles.slice(0, 4).map((v, i) => (
                  <div key={i} className="flex items-center gap-2 bg-slate-800/60 rounded px-2 py-1">
                    <span className="font-mono text-xs text-slate-400">#{v.id}</span>
                    <span className="font-mono text-xs text-slate-300 capitalize">{v.className}</span>
                    {v.speed != null && (
                      <span className="font-mono text-xs text-cyan">{Math.round(v.speed)}km/h</span>
                    )}
                    <span className="font-mono text-xs text-slate-600">
                      {(v.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
                {vehicles.length > 4 && (
                  <span className="font-mono text-xs text-slate-600">+{vehicles.length - 4} more</span>
                )}
              </div>
            )}
          </div>

          {/* Backend processing time */}
          {latency != null && (
            <>
              <div className="border-t border-slate-800" />
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-slate-500 uppercase tracking-wider">Backend</span>
                <span className="font-mono text-xs text-slate-400">{Math.round(latency)}ms</span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function MetricCard({ label, value, unit = '', valueClass = 'text-slate-200' }) {
  return (
    <div className="panel px-3 py-2.5 flex flex-col gap-1 items-center">
      <span className={`font-display text-2xl font-bold leading-none ${valueClass}`}>
        {value ?? '—'}
        {unit && <span className="text-sm font-mono text-slate-500 ml-0.5">{unit}</span>}
      </span>
      <span className="font-mono text-xs text-slate-600 uppercase tracking-widest text-center">{label}</span>
    </div>
  )
}
