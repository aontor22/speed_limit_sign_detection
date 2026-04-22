/**
 * components/Detection/ViolationAlert.jsx
 * =========================================
 * The centrepiece status display. Shows the violation state with:
 *  - SAFE   → green calm indicator
 *  - WARNING → amber pulsing badge
 *  - VIOLATION → red flashing alert with speed delta
 *
 * Also shows the large speed limit sign replica.
 */

import React, { useEffect, useRef } from 'react'

const STATUS_CONFIG = {
  SAFE: {
    label:       'ALL CLEAR',
    color:       'text-safe',
    borderColor: 'border-safe/40',
    bgColor:     'bg-safe/5',
    glowColor:   'shadow-safe/20',
    badgeClass:  'badge-safe',
    icon:        '✓',
    iconBg:      'bg-safe/10',
  },
  WARNING: {
    label:       'WARNING',
    color:       'text-warn',
    borderColor: 'border-warn/50',
    bgColor:     'bg-warn/5',
    glowColor:   'shadow-warn/30',
    badgeClass:  'badge-warn',
    icon:        '⚠',
    iconBg:      'bg-warn/10',
  },
  VIOLATION: {
    label:       'SPEED VIOLATION',
    color:       'text-danger',
    borderColor: 'border-danger',
    bgColor:     'bg-danger/5',
    glowColor:   'shadow-danger/30',
    badgeClass:  'badge-danger',
    icon:        '✕',
    iconBg:      'bg-danger/10',
  },
  UNKNOWN: {
    label:       'NO DATA',
    color:       'text-slate-500',
    borderColor: 'border-slate-700',
    bgColor:     'bg-slate-900',
    glowColor:   '',
    badgeClass:  'badge-neutral',
    icon:        '—',
    iconBg:      'bg-slate-800',
  },
}

export default function ViolationAlert({ violation, speedLimit }) {
  const status = violation?.status || 'UNKNOWN'
  const cfg    = STATUS_CONFIG[status] || STATUS_CONFIG.UNKNOWN

  const isViolation = status === 'VIOLATION'
  const isWarning   = status === 'WARNING'
  const hasSpeed    = violation?.speed != null
  const hasLimit    = violation?.limit != null || speedLimit != null
  const limit       = violation?.limit ?? speedLimit

  return (
    <div className={`
      panel p-4 flex flex-col gap-4 transition-all duration-300
      ${cfg.borderColor} border
      ${isViolation ? 'violation-flash animate-pulse-danger' : ''}
    `}>

      {/* Status Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-8 h-8 rounded-full ${cfg.iconBg} ${cfg.borderColor} border flex items-center justify-center`}>
            <span className={`${cfg.color} text-sm font-bold`}>{cfg.icon}</span>
          </div>
          <div>
            <p className="font-mono text-xs text-slate-500 uppercase tracking-widest">Violation Status</p>
            <p className={`font-display text-lg font-bold uppercase tracking-wide ${cfg.color} ${
              isViolation ? 'text-glow-danger' : isWarning ? 'text-glow-warn' : ''
            }`}>
              {cfg.label}
            </p>
          </div>
        </div>
        <span className={cfg.badgeClass}>{status}</span>
      </div>

      {/* Speed / Limit Row */}
      <div className="grid grid-cols-2 gap-3">

        {/* Speed Sign Badge */}
        <div className="flex flex-col items-center justify-center gap-2">
          <p className="font-mono text-xs text-slate-500 uppercase tracking-widest">Speed Limit</p>
          <SpeedSignBadge limit={limit} />
        </div>

        {/* Vehicle Speed */}
        <div className="flex flex-col items-center justify-center gap-1">
          <p className="font-mono text-xs text-slate-500 uppercase tracking-widest">Vehicle Speed</p>
          {hasSpeed ? (
            <div className="text-center">
              <span className={`font-display text-5xl font-bold leading-none ${
                isViolation ? 'text-danger text-glow-danger'
                : isWarning  ? 'text-warn text-glow-warn'
                : 'text-slate-200'
              }`}>
                {Math.round(violation.speed)}
              </span>
              <span className="font-mono text-sm text-slate-500 ml-1">km/h</span>
            </div>
          ) : (
            <span className="font-mono text-2xl text-slate-700">—</span>
          )}
          {isViolation && violation.excess != null && (
            <div className="mt-1 flex items-center gap-1 bg-danger/10 border border-danger/30 rounded px-2 py-0.5">
              <span className="font-mono text-xs text-danger font-bold">
                +{Math.round(violation.excess)} km/h over
              </span>
            </div>
          )}
        </div>
      </div>

    </div>
  )
}

// Traffic-sign-style badge
function SpeedSignBadge({ limit }) {
  return (
    <div className="relative flex items-center justify-center" style={{ width: 72, height: 72 }}>
      {/* Outer red ring */}
      <div className="absolute inset-0 rounded-full bg-white/95 border-[4px] border-red-600 shadow-lg" />
      {/* Number */}
      <span className={`relative z-10 font-display text-center font-black text-slate-900 leading-none select-none ${
        limit != null ? (limit >= 100 ? 'text-xl' : 'text-2xl') : 'text-3xl'
      }`}>
        {limit != null ? limit : '?'}
      </span>
    </div>
  )
}
