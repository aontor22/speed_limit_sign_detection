/**
 * components/Controls/ControlPanel.jsx
 * =======================================
 * Start/Stop button + toggle switches for detection options.
 * Also shows backend connection error if any.
 */

import React from 'react'

const FPS_OPTIONS = [
  { label: '4 FPS',  value: 250 },
  { label: '7 FPS',  value: 150 },
  { label: '10 FPS', value: 100 },
  { label: '15 FPS', value: 67  },
]

export default function ControlPanel({
  isRunning,
  isLoading,
  backendError,
  options,
  onStart,
  onStop,
  onOptionChange,
}) {
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="font-display text-sm font-semibold tracking-widest uppercase text-slate-300">
          System Controls
        </span>
      </div>

      <div className="p-4 flex flex-col gap-5">

        {/* START / STOP Button */}
        <button
          onClick={isRunning ? onStop : onStart}
          disabled={isLoading}
          className={`
            w-full py-3 px-6 rounded-lg font-display text-base font-bold uppercase tracking-widest
            transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-900
            disabled:opacity-50 disabled:cursor-not-allowed
            ${isRunning
              ? 'bg-danger/10 hover:bg-danger/20 text-danger border border-danger/50 hover:border-danger focus:ring-danger/50'
              : 'bg-cyan/10 hover:bg-cyan/20 text-cyan border border-cyan/50 hover:border-cyan focus:ring-cyan/50'
            }
          `}
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-t-transparent border-current rounded-full animate-spin" />
              Initializing...
            </span>
          ) : isRunning ? (
            '⬛ Stop Detection'
          ) : (
            '▶ Start Detection'
          )}
        </button>

        {/* Toggle Switches */}
        <div className="flex flex-col gap-3">
          <p className="font-mono text-xs text-slate-600 uppercase tracking-widest">Processing Options</p>

          <Toggle
            label="Vehicle Detection"
            description="YOLO COCO model"
            enabled={options.enableVehicleDetection}
            onChange={(v) => onOptionChange('enableVehicleDetection', v)}
          />

          <Toggle
            label="OCR Speed Reading"
            description="Tesseract engine"
            enabled={options.enableOCR}
            onChange={(v) => onOptionChange('enableOCR', v)}
          />
        </div>

        {/* FPS Selector */}
        <div className="flex flex-col gap-2">
          <p className="font-mono text-xs text-slate-600 uppercase tracking-widest">Capture Rate</p>
          <div className="grid grid-cols-4 gap-1.5">
            {FPS_OPTIONS.map(({ label, value }) => (
              <button
                key={value}
                onClick={() => onOptionChange('captureIntervalMs', value)}
                className={`
                  py-1.5 px-2 rounded text-xs font-mono font-medium transition-all duration-150
                  ${options.captureIntervalMs === value
                    ? 'bg-cyan/15 text-cyan border border-cyan/40'
                    : 'bg-slate-800 text-slate-500 border border-slate-700 hover:text-slate-300 hover:border-slate-600'
                  }
                `}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Backend Error */}
        {backendError && (
          <div className="bg-danger/5 border border-danger/30 rounded-lg px-3 py-2.5 flex gap-2.5">
            <span className="text-danger text-sm mt-0.5 flex-shrink-0">⚠</span>
            <p className="font-mono text-xs text-danger/80 leading-relaxed">{backendError}</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Toggle Switch ─────────────────────────────────────────────────────────────

function Toggle({ label, description, enabled, onChange }) {
  return (
    <label className="flex items-center justify-between gap-3 cursor-pointer group">
      <div className="flex flex-col gap-0.5">
        <span className="font-ui text-sm text-slate-300 group-hover:text-slate-200 transition-colors">
          {label}
        </span>
        {description && (
          <span className="font-mono text-xs text-slate-600">{description}</span>
        )}
      </div>

      {/* Track */}
      <button
        role="switch"
        aria-checked={enabled}
        onClick={() => onChange(!enabled)}
        className={`
          toggle-track w-10 h-5 flex-shrink-0
          ${enabled ? 'bg-cyan/80' : 'bg-slate-700'}
          focus:outline-none focus:ring-2 focus:ring-cyan/50 focus:ring-offset-2 focus:ring-offset-slate-900
        `}
      >
        <span className={`toggle-thumb ${enabled ? 'translate-x-5' : 'translate-x-0'}`} />
      </button>
    </label>
  )
}
