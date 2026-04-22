/**
 * components/Logs/SessionLog.jsx
 * ================================
 * Shows a scrollable table of detection events this session.
 * Each row: timestamp, speed limit, vehicle count, violation status, latency.
 *
 * Features:
 *  - CSV download of full session log
 *  - JSON download of full session log
 *  - Clear log button
 *  - Violation rows highlighted in red
 *  - Auto-scroll to newest entry
 */

import React, { useRef, useEffect } from 'react'
import { format } from 'date-fns'

export default function SessionLog({ sessionLog, onClear }) {
  const scrollRef = useRef(null)

  // Auto-scroll to top (newest is first)
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = 0
    }
  }, [sessionLog.length])

  return (
    <div className="panel flex flex-col" style={{ minHeight: 0 }}>
      <div className="panel-header">
        <div className="flex items-center gap-2.5">
          <span className="font-display text-sm font-semibold tracking-widest uppercase text-slate-300">
            Session Log
          </span>
          <span className="badge-neutral">{sessionLog.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => downloadCSV(sessionLog)}
            disabled={sessionLog.length === 0}
            className="font-mono text-xs text-cyan hover:text-cyan/80 disabled:text-slate-700 disabled:cursor-not-allowed transition-colors px-2 py-1 border border-cyan/20 hover:border-cyan/40 disabled:border-transparent rounded"
          >
            ↓ CSV
          </button>
          <button
            onClick={() => downloadJSON(sessionLog)}
            disabled={sessionLog.length === 0}
            className="font-mono text-xs text-cyan hover:text-cyan/80 disabled:text-slate-700 disabled:cursor-not-allowed transition-colors px-2 py-1 border border-cyan/20 hover:border-cyan/40 disabled:border-transparent rounded"
          >
            ↓ JSON
          </button>
          <button
            onClick={onClear}
            disabled={sessionLog.length === 0}
            className="font-mono text-xs text-slate-500 hover:text-slate-300 disabled:text-slate-700 disabled:cursor-not-allowed transition-colors"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Table */}
      <div ref={scrollRef} className="overflow-y-auto flex-1" style={{ maxHeight: 280 }}>
        {sessionLog.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 gap-2">
            <span className="font-mono text-xs text-slate-700 uppercase tracking-widest">
              No events recorded yet
            </span>
            <span className="font-mono text-xs text-slate-800">
              Events appear when signs are detected
            </span>
          </div>
        ) : (
          <table className="w-full text-xs border-collapse">
            <thead className="sticky top-0 bg-slate-900 z-10">
              <tr className="border-b border-slate-800">
                {['Time', 'Limit', 'Vehicles', 'Status', 'Spd', 'ms'].map((h) => (
                  <th key={h} className="px-3 py-2 text-left font-mono text-slate-600 uppercase tracking-widest font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sessionLog.map((entry) => (
                <LogRow key={entry.id} entry={entry} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ─── Table Row ─────────────────────────────────────────────────────────────────

function LogRow({ entry }) {
  const isViolation = entry.status === 'VIOLATION'
  const isWarning   = entry.status === 'WARNING'

  return (
    <tr className={`
      border-b border-slate-800/50 transition-colors
      ${isViolation ? 'bg-danger/5 hover:bg-danger/8'
       : isWarning  ? 'bg-warn/5 hover:bg-warn/8'
       : 'hover:bg-slate-800/30'
      }
    `}>
      {/* Time */}
      <td className="px-3 py-2 font-mono text-slate-500 whitespace-nowrap">
        {format(new Date(entry.timestamp), 'HH:mm:ss')}
      </td>

      {/* Speed Limit */}
      <td className="px-3 py-2">
        {entry.speedLimit != null ? (
          <span className="font-display text-sm font-bold text-white">
            {entry.speedLimit}
            <span className="font-mono text-xs text-slate-500 ml-0.5">km/h</span>
          </span>
        ) : (
          <span className="text-slate-700">—</span>
        )}
      </td>

      {/* Vehicle Count */}
      <td className="px-3 py-2 font-mono text-slate-400">
        {entry.vehicleCount}
      </td>

      {/* Status */}
      <td className="px-3 py-2">
        <StatusPill status={entry.status} />
      </td>

      {/* Vehicle Speed */}
      <td className="px-3 py-2 font-mono">
        {entry.vehicleSpeed != null ? (
          <span className={isViolation ? 'text-danger' : 'text-slate-400'}>
            {Math.round(entry.vehicleSpeed)}
          </span>
        ) : (
          <span className="text-slate-700">—</span>
        )}
      </td>

      {/* Latency */}
      <td className="px-3 py-2 font-mono text-slate-600">
        {entry.latencyMs ?? '—'}
      </td>
    </tr>
  )
}

function StatusPill({ status }) {
  if (status === 'VIOLATION') return <span className="badge-danger">VIOL</span>
  if (status === 'WARNING')   return <span className="badge-warn">WARN</span>
  if (status === 'SAFE')      return <span className="badge-safe">SAFE</span>
  return <span className="badge-neutral">{status}</span>
}

// ─── Download Helpers ──────────────────────────────────────────────────────────

function downloadCSV(log) {
  const headers = ['timestamp', 'frame_id', 'speed_limit_kmh', 'vehicle_count',
                   'sign_count', 'status', 'vehicle_speed_kmh', 'latency_ms']
  const rows = log.map((e) => [
    e.timestamp, e.frameId ?? '', e.speedLimit ?? '',
    e.vehicleCount, e.signCount, e.status,
    e.vehicleSpeed != null ? Math.round(e.vehicleSpeed) : '',
    e.latencyMs ?? '',
  ])

  const csv = [headers, ...rows].map((r) => r.join(',')).join('\n')
  triggerDownload(csv, `speedvision_session_${Date.now()}.csv`, 'text/csv')
}

function downloadJSON(log) {
  const json = JSON.stringify(log, null, 2)
  triggerDownload(json, `speedvision_session_${Date.now()}.json`, 'application/json')
}

function triggerDownload(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
