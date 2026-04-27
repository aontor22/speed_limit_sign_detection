/**
 * App.jsx
 * =======
 * Root component. Composes all panels into the dashboard layout.
 *
 * Layout (desktop):
 * ┌─ Header ───────────────────────────────────────────────────┐
 * ├─────────────────────────────────────────────────────────────┤
 * │  Left Column (60%)          │  Right Column (40%)           │
 * │  ┌──────────────────────┐   │  ┌─────────────────────────┐  │
 * │  │  Live Camera Feed    │   │  │  Violation Alert        │  │
 * │  └──────────────────────┘   │  └─────────────────────────┘  │
 * │  ┌──────────────────────┐   │  ┌─────────────────────────┐  │
 * │  │  Processed Output    │   │  │  Detection Stats        │  │
 * │  └──────────────────────┘   │  └─────────────────────────┘  │
 * │                             │  ┌─────────────────────────┐  │
 * │                             │  │  Controls               │  │
 * │                             │  └─────────────────────────┘  │
 * ├─────────────────────────────────────────────────────────────┤
 * │  Session Log (full width)                                   │
 * └─────────────────────────────────────────────────────────────┘
 *
 * Layout (mobile):
 *  Single column, stacked vertically.
 */

import React from 'react'
import { useDetection } from './hooks/useDetection.js'
import Header from './components/Dashboard/Header.jsx'
import CameraFeed from './components/Camera/CameraFeed.jsx'
import ProcessedFeed from './components/Camera/ProcessedFeed.jsx'
import ViolationAlert from './components/Detection/ViolationAlert.jsx'
import DetectionStats from './components/Detection/DetectionStats.jsx'
import ControlPanel from './components/Controls/ControlPanel.jsx'
import SessionLog from './components/Logs/SessionLog.jsx'
import MediaUploadPanel from './components/MediaUpload/MediaUploadPanel.jsx'
import { useNavigate, useLocation } from 'react-router-dom'
import { useEffect } from 'react'

export default function App() {
  const {
    videoRef,
    isRunning,
    isLoading,
    isProcessing,
    cameraError,
    backendError,
    detectionResult,
    processedFrame,
    stats,
    sessionLog,
    options,
    startCamera,
    stopCamera,
    updateOption,
    clearLog,
    mode,
    setMode,
    handleFileUpload,
  } = useDetection()

  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    const path = location.pathname.replace('/', '')

    if (path === 'live') setMode('live')
    else if (path === 'rtsp') setMode('rtsp')
    else if (path === 'image' || path === 'video' || path === 'media')
      setMode('upload')

  }, [location.pathname])

  useEffect(() => {
    if (mode === 'live') navigate('/live')
    else if (mode === 'rtsp') navigate('/rtsp')
    else if (mode === 'upload') navigate('/media')
  }, [mode])

  return (
    <div className="min-h-screen bg-slate-950 bg-grid-pattern bg-grid-sm flex flex-col font-ui">

      {/* Global background gradient */}
      <div className="fixed inset-0 bg-gradient-to-br from-slate-950 via-slate-950 to-cyan-950/20 pointer-events-none" />

      {/* ── Header ────────────────────────────────────────────────────────── */}
      <Header
        isRunning={isRunning}
        isProcessing={isProcessing}
        stats={stats}
      />

      {/* ── Main Content ──────────────────────────────────────────────────── */}
      <main className="relative flex-1 flex flex-col gap-4 p-4 md:p-5 max-w-[1600px] w-full mx-auto">

        {/* Two-column layout */}
        <div className="flex flex-col lg:flex-row gap-4 flex-1 min-h-0">

          {/* ── Left Column: Video Feeds ───────────────────────────────────── */}
          <div className="flex flex-col gap-4 lg:flex-[3] min-h-0">

            {/* Camera Feeds Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4" style={{ minHeight: 260 }}>
              <CameraFeed
                videoRef={videoRef}
                isRunning={isRunning}
                isLoading={isLoading}
                cameraError={cameraError}
              />
              <ProcessedFeed
                processedFrame={processedFrame}
                isProcessing={isProcessing}
                isRunning={isRunning}
                stats={stats}
              />
            </div>

            {/* Session Log (below video on left column) */}
            <div className="flex-1">
              <SessionLog sessionLog={sessionLog} onClear={clearLog} />
            </div>
          </div>

          {/* ── Right Column: Stats + Controls ────────────────────────────── */}
          <div className="flex flex-col gap-4 lg:w-80 xl:w-96 flex-shrink-0">

            {/* Violation Alert — most important, top */}
            <ViolationAlert
              violation={detectionResult?.violation}
              speedLimit={detectionResult?.currentSpeedLimit}
            />

            {/* Detection Stats */}
            <DetectionStats
              stats={stats}
              detectionResult={detectionResult}
            />

            {/* Upload Panel (NEW - TOP CONTROL INPUT) */}
            <MediaUploadPanel
              mode={mode}
              setMode={setMode}
              handleFileUpload={handleFileUpload}
              isRunning={isRunning}
            />

            {/* Controls at bottom */}
            <ControlPanel
              isRunning={isRunning}
              isLoading={isLoading}
              backendError={backendError}
              options={options}
              onStart={startCamera}
              onStop={stopCamera}
              onOptionChange={updateOption}
            />

            {/* Footer credits */}
            <div className="mt-auto pt-2 border-t border-slate-800/50">
              <p className="font-mono text-xs text-slate-700 text-center">
                YOLOv8 · DeepSORT · Tesseract OCR · FastAPI
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
