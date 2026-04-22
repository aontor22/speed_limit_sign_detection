/**
 * components/Dashboard/Header.jsx
 * ==================================
 * Top navigation bar with system title, connection status, and session timer.
 */

import React, { useState, useEffect } from 'react'

export default function Header({ isRunning, isProcessing, stats }) {
  const [elapsed, setElapsed] = useState(0)
  const [startTime] = useState(Date.now())

  useEffect(() => {
    if (!isRunning) { setElapsed(0); return }
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - startTime) / 1000)), 1000)
    return () => clearInterval(t)
  }, [isRunning, startTime])

  const formatElapsed = (s) => {
    const m = Math.floor(s / 60)
    const sec = s % 60
    return `${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`
  }

  return (
    <header className="flex items-center justify-between px-6 py-3 border-b border-slate-800 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-50">

      {/* Logo / Title */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          <div className="w-6 h-6 rounded bg-cyan/10 border border-cyan/30 flex items-center justify-center">
            <span className="text-cyan text-xs font-bold font-mono">SV</span>
          </div>
          <span className="font-display text-xl font-bold tracking-widest uppercase text-white">
            Speed<span className="text-cyan">Vision</span>
          </span>
        </div>
        <div className="hidden md:flex items-center gap-1.5 border-l border-slate-800 pl-3">
          <span className="font-mono text-xs text-slate-600 uppercase tracking-widest">
            AI Traffic Monitoring System
          </span>
        </div>
      </div>

      {/* Status Indicators */}
      <div className="flex items-center gap-4">

        {/* Session Timer */}
        {isRunning && (
          <div className="hidden sm:flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-safe animate-pulse" />
            <span className="font-mono text-xs text-slate-400">
              {formatElapsed(elapsed)}
            </span>
          </div>
        )}

        {/* FPS badge */}
        {isRunning && (
          <div className="hidden md:block">
            <span className="badge-cyan">{stats.responseFps} fps</span>
          </div>
        )}

        {/* System Status */}
        <div className={`flex items-center gap-2 border rounded-lg px-3 py-1.5 transition-all duration-300 ${
          isProcessing
            ? 'border-cyan/30 bg-cyan/5'
            : isRunning
              ? 'border-safe/30 bg-safe/5'
              : 'border-slate-800 bg-slate-900'
        }`}>
          <div className={`w-2 h-2 rounded-full transition-colors duration-300 ${
            isProcessing ? 'bg-cyan animate-pulse'
            : isRunning  ? 'bg-safe'
            : 'bg-slate-600'
          }`} />
          <span className={`font-mono text-xs uppercase tracking-widest transition-colors duration-300 ${
            isProcessing ? 'text-cyan'
            : isRunning  ? 'text-safe'
            : 'text-slate-600'
          }`}>
            {isProcessing ? 'Processing' : isRunning ? 'Active' : 'Standby'}
          </span>
        </div>
      </div>
    </header>
  )
}
