import { useCallback, useEffect, useRef, useState } from 'react'
import type { FrameEntry } from '../types'
import { findLastFrameIndexAtOrBefore } from '../lib/frameSync'
import { BboxOverlay } from './BboxOverlay'

type Props = {
  videoSrc: string | null
  videoWidth: number
  videoHeight: number
  /** Video FPS from metadata (shown next to the timer). */
  fps?: number
  frames: FrameEntry[]
  frameIndex: number
  onFrameIndexChange: (index: number) => void
  selectedId: string | null
  onSelect: (id: string) => void
}

function formatTimecode(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return '0:00.000'
  const totalMs = Math.round(sec * 1000)
  const ms = totalMs % 1000
  const totalS = Math.floor(totalMs / 1000)
  const s = totalS % 60
  const m = Math.floor(totalS / 60) % 60
  const h = Math.floor(totalS / 3600)
  const pad = (n: number, w: number) => String(n).padStart(w, '0')
  const core =
    h > 0
      ? `${h}:${pad(m, 2)}:${pad(s, 2)}`
      : `${m}:${pad(s, 2)}`
  return `${core}.${pad(ms, 3)}`
}

export function VideoDetectionPlayer({
  videoSrc,
  videoWidth,
  videoHeight,
  fps,
  frames,
  frameIndex,
  onFrameIndexChange,
  selectedId,
  onSelect,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const frameIndexRef = useRef(frameIndex)
  frameIndexRef.current = frameIndex

  const framesRef = useRef(frames)
  framesRef.current = frames

  const onFrameIndexChangeRef = useRef(onFrameIndexChange)
  onFrameIndexChangeRef.current = onFrameIndexChange

  /** Next frameIndex change came from matching playback time (do not seek the video). */
  const indexFromPlayback = useRef(false)
  /** Skip one sync while setting currentTime programmatically. */
  const skipTimeSync = useRef(false)

  const lastTimerStepRef = useRef<number | null>(null)

  const [videoError, setVideoError] = useState<string | null>(null)
  const [duration, setDuration] = useState(0)
  /** High-resolution playback clock for the UI (updated from the rAF loop). */
  const [displayTime, setDisplayTime] = useState(0)

  const current =
    frameIndex >= 0 && frames[frameIndex] ? frames[frameIndex] : undefined

  const syncFrameFromVideo = useCallback(() => {
    const el = videoRef.current
    const fr = framesRef.current
    if (!el || fr.length === 0 || skipTimeSync.current) return
    const t = el.currentTime
    const idx = findLastFrameIndexAtOrBefore(fr, t)
    if (idx !== frameIndexRef.current) {
      indexFromPlayback.current = true
      onFrameIndexChangeRef.current(idx)
    }
  }, [])

  /** rAF loop while playing: sync detections + timer at display refresh rate. */
  useEffect(() => {
    const el = videoRef.current
    if (!el || !videoSrc) return

    let rafId = 0
    let running = false

    const tick = () => {
      if (!running) return
      const v = videoRef.current
      if (!v) return

      const t = v.currentTime
      syncFrameFromVideo()

      const step = Math.floor(t * 100)
      if (lastTimerStepRef.current !== step) {
        lastTimerStepRef.current = step
        setDisplayTime(t)
      }

      rafId = requestAnimationFrame(tick)
    }

    const start = () => {
      running = true
      cancelAnimationFrame(rafId)
      rafId = requestAnimationFrame(tick)
    }

    const stop = () => {
      running = false
      cancelAnimationFrame(rafId)
    }

    const onSeeked = () => {
      skipTimeSync.current = false
      const v = videoRef.current
      if (v) {
        lastTimerStepRef.current = Math.floor(v.currentTime * 100)
        setDisplayTime(v.currentTime)
      }
      syncFrameFromVideo()
    }

    el.addEventListener('playing', start)
    el.addEventListener('pause', stop)
    el.addEventListener('seeked', onSeeked)

    if (!el.paused) start()

    return () => {
      stop()
      el.removeEventListener('playing', start)
      el.removeEventListener('pause', stop)
      el.removeEventListener('seeked', onSeeked)
    }
  }, [videoSrc, syncFrameFromVideo])

  useEffect(() => {
    const el = videoRef.current
    if (!el || frameIndex < 0 || !frames[frameIndex]) return

    if (indexFromPlayback.current) {
      indexFromPlayback.current = false
      return
    }

    const target = frames[frameIndex].timestamp
    if (Math.abs(el.currentTime - target) > 0.05) {
      skipTimeSync.current = true
      el.currentTime = target
    }
  }, [frameIndex, frames])

  const onLoadedMetadata = useCallback(() => {
    const el = videoRef.current
    if (el) {
      setDuration(el.duration || 0)
      const t = el.currentTime
      lastTimerStepRef.current = Math.floor(t * 100)
      setDisplayTime(t)
    }
    setVideoError(null)
    queueMicrotask(() => syncFrameFromVideo())
  }, [syncFrameFromVideo])

  const onVideoError = useCallback(() => {
    setVideoError(
      'Could not load this video (network, CORS, or format). Try “Load video file” with a local copy.',
    )
  }, [])

  if (!videoSrc) {
    return (
      <div className="video-player video-player--empty">
        <p className="muted">
          No video URL. Metadata may be missing a source, or load a local file
          with <strong>Load video</strong>.
        </p>
      </div>
    )
  }

  return (
    <div className="video-player">
      {videoError ? (
        <div className="banner banner--error">{videoError}</div>
      ) : null}
      <div
        className="video-bbox"
        style={{
          aspectRatio: `${videoWidth} / ${videoHeight}`,
        }}
      >
        {/* biome-ignore lint/a11y/useMediaCaption: source footage has no caption track */}
        <video
          ref={videoRef}
          className="video-bbox__el"
          src={videoSrc}
          controls
          playsInline
          preload="metadata"
          crossOrigin="anonymous"
          onLoadedMetadata={onLoadedMetadata}
          onError={onVideoError}
          aria-label="Video with detection overlay"
        />
        <div className="video-bbox__overlay">
          {current ? (
            <BboxOverlay
              videoWidth={videoWidth}
              videoHeight={videoHeight}
              objects={current.objects}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          ) : null}
        </div>
      </div>
      <div className="video-player__meta">
        <div
          className="video-player__timer mono"
          role="timer"
          aria-live="polite"
          aria-label="Playback position"
        >
          <span>{formatTimecode(displayTime)}</span>
          {duration > 0 ? (
            <>
              <span className="video-player__sep"> / </span>
              <span>{formatTimecode(duration)}</span>
            </>
          ) : null}
          {fps != null && Number.isFinite(fps) ? (
            <span className="video-player__fps"> · {fps} fps</span>
          ) : null}
        </div>
        <p className="video-player__meta-detail">
          {current
            ? `Detection @ ${current.timestamp.toFixed(2)}s · frame_idx ${current.frame_idx}`
            : 'No detection for this time'}
        </p>
      </div>
    </div>
  )
}
