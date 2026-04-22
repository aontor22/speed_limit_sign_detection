/**
 * components/Camera/CameraFeed.jsx
 * =================================
 * Renders the live webcam video feed with status overlays.
 *
 * Visual language: industrial surveillance — dark borders, cyan corner brackets,
 * subtle scan-line texture, status indicator dot.
 */

import React from 'react'

export default function CameraFeed({ videoRef, isRunning, isLoading, cameraError }) {
  return (
    <div className="panel h-full flex flex-col">
      {/* Header */}
      <div className="panel-header">
        <div className="flex items-center gap-2.5">
          <div className={`w-2 h-2 rounded-full transition-colors duration-500 ${
            isRunning  ? 'bg-safe animate-pulse'
            : isLoading ? 'bg-warn animate-pulse'
            : 'bg-slate-600'
          }`} />
          <span className="font-display text-sm font-semibold tracking-widest uppercase text-slate-300">
            Live Camera Feed
          </span>
        </div>
        <span className="badge-neutral font-mono text-xs">CH-01</span>
      </div>

      {/* Video Area */}
      <div className="relative flex-1 min-h-0 bg-black scanlines corner-brackets">

        {/* Actual video element */}
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          className={`w-full h-full object-cover transition-opacity duration-500 ${
            isRunning ? 'opacity-100' : 'opacity-0'
          }`}
        />

        {/* Idle / Loading state */}
        {!isRunning && !cameraError && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-slate-950">
            {isLoading ? (
              <>
                <div className="relative">
                  <div className="w-12 h-12 rounded-full border-2 border-cyan/20" />
                  <div className="absolute inset-0 w-12 h-12 rounded-full border-2 border-t-cyan border-transparent animate-spin" />
                </div>
                <p className="font-mono text-xs text-cyan tracking-widest animate-pulse">
                  INITIALIZING CAMERA...
                </p>
              </>
            ) : (
              <>
                <CameraIcon className="w-14 h-14 text-slate-700" />
                <p className="font-mono text-xs text-slate-600 tracking-widest uppercase">
                  Camera Offline
                </p>
              </>
            )}
          </div>
        )}

        {/* Camera Error */}
        {cameraError && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-slate-950 px-6">
            <div className="w-10 h-10 rounded-full bg-danger/10 border border-danger/30 flex items-center justify-center">
              <span className="text-danger text-lg">!</span>
            </div>
            <p className="font-mono text-xs text-danger text-center leading-relaxed max-w-xs">
              {cameraError}
            </p>
          </div>
        )}

        {/* LIVE badge */}
        {isRunning && (
          <div className="absolute top-3 left-3 flex items-center gap-1.5 bg-black/60 border border-danger/40 rounded-full px-2.5 py-1 backdrop-blur-sm">
            <span className="w-1.5 h-1.5 rounded-full bg-danger animate-blink" />
            <span className="font-mono text-xs text-danger font-semibold tracking-widest">LIVE</span>
          </div>
        )}

        {/* Bottom gradient fade */}
        <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-black/40 to-transparent pointer-events-none" />
      </div>
    </div>
  )
}

// Inline SVG icon
function CameraIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 10l4.553-2.069A1 1 0 0121 8.868v6.264a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
    </svg>
  )
}
