/**
 * components/Camera/ProcessedFeed.jsx
 * =====================================
 * Displays the annotated frame returned by the backend.
 * Shows bounding boxes, labels, and OCR overlays as drawn by OpenCV.
 *
 * When no processed frame is available, shows a waiting state.
 * A subtle "PROCESSING" badge flashes when a request is in-flight.
 */

import React from 'react'

export default function ProcessedFeed({ processedFrame, isProcessing, isRunning, stats }) {
  return (
    <div className="panel h-full flex flex-col">
      {/* Header */}
      <div className="panel-header">
        <div className="flex items-center gap-2.5">
          <div className={`w-2 h-2 rounded-full transition-colors duration-300 ${
            isProcessing ? 'bg-cyan animate-pulse' : isRunning ? 'bg-safe' : 'bg-slate-600'
          }`} />
          <span className="font-display text-sm font-semibold tracking-widest uppercase text-slate-300">
            Detection Output
          </span>
        </div>
        <div className="flex items-center gap-2">
          {isProcessing && (
            <span className="badge-cyan animate-pulse">Processing</span>
          )}
          {stats && (
            <span className="font-mono text-xs text-slate-500">
              {stats.responseFps} FPS
            </span>
          )}
        </div>
      </div>

      {/* Processed Frame */}
      <div className="relative flex-1 min-h-0 bg-black scanlines corner-brackets">

        {processedFrame ? (
          <img
            src={processedFrame}
            alt="Processed detection output"
            className="w-full h-full object-cover"
            // Use key to force remount and avoid stale frame blinking
            key={processedFrame.slice(-20)}
          />
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-slate-950">
            {isRunning ? (
              <>
                {/* Processing spinner */}
                <div className="relative flex items-center justify-center">
                  <div className="ping-slow absolute w-10 h-10 rounded-full bg-cyan/20" />
                  <div className="relative w-8 h-8 rounded-full border border-cyan/40 border-t-cyan animate-spin" />
                </div>
                <p className="font-mono text-xs text-cyan/60 tracking-widest animate-pulse">
                  AWAITING FIRST FRAME...
                </p>
              </>
            ) : (
              <>
                <GridIcon className="w-14 h-14 text-slate-800" />
                <p className="font-mono text-xs text-slate-700 tracking-widest uppercase">
                  Output Offline
                </p>
              </>
            )}
          </div>
        )}

        {/* Processing overlay pulse */}
        {isProcessing && processedFrame && (
          <div className="absolute inset-0 pointer-events-none">
            <div className="absolute top-0 left-0 right-0 h-[2px] bg-cyan/60 animate-scan-line" />
          </div>
        )}

        {/* PROCESSED badge */}
        {processedFrame && (
          <div className="absolute top-3 right-3 flex items-center gap-1.5 bg-black/60 border border-cyan/30 rounded-full px-2.5 py-1 backdrop-blur-sm">
            <span className="font-mono text-xs text-cyan/80 tracking-widest">AI VISION</span>
          </div>
        )}

        {/* Latency badge */}
        {stats?.avgLatencyMs > 0 && (
          <div className="absolute bottom-3 right-3 bg-black/70 border border-slate-700 rounded-md px-2 py-1 backdrop-blur-sm">
            <span className="font-mono text-xs text-slate-400">
              {stats.avgLatencyMs}ms
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

function GridIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={0.75}>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  )
}
