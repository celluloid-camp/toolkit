import { useCallback, useEffect, useMemo, useState } from 'react'
import './App.css'
import type { DetectionFile } from './types'
import { parseDetectionJsonText } from './lib/parseDetectionJson'
import { resolveSpriteUrl, resolveVideoSource } from './lib/resolveAssets'
import { parseSpriteFragment } from './lib/parseThumbnail'
import { BboxFrame } from './components/BboxFrame'
import { SpriteCrop } from './components/SpriteCrop'
import { VideoDetectionPlayer } from './components/VideoDetectionPlayer'

export default function App() {
  const [data, setData] = useState<DetectionFile | null>(null)
  const [parseError, setParseError] = useState<string | null>(null)
  /** Manual sprite file (blob URL); overrides metadata sprite URL. */
  const [spriteBlobUrl, setSpriteBlobUrl] = useState<string | null>(null)
  const [videoFileUrl, setVideoFileUrl] = useState<string | null>(null)
  const [frameIndex, setFrameIndex] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const frames = data?.frames ?? []
  const current =
    frameIndex >= 0 && frames[frameIndex] ? frames[frameIndex] : undefined

  const effectiveVideoSrc = useMemo(() => {
    if (!data) return null
    if (videoFileUrl) return videoFileUrl
    return resolveVideoSource(data.metadata.video)
  }, [data, videoFileUrl])

  useEffect(() => {
    if (!effectiveVideoSrc && frameIndex < 0) {
      setFrameIndex(0)
    }
  }, [effectiveVideoSrc, frameIndex])

  useEffect(() => {
    if (!current?.objects.length) {
      setSelectedId(null)
      return
    }
    setSelectedId((prev) => {
      if (prev && current.objects.some((o) => o.id === prev)) return prev
      return current.objects[0]?.id ?? null
    })
  }, [current])

  const onJsonFile = useCallback((file: File) => {
    setParseError(null)
    const reader = new FileReader()
    reader.onerror = () => {
      setParseError('Could not read the file from disk.')
      setData(null)
    }
    reader.onload = () => {
      const buf = reader.result
      if (!(buf instanceof ArrayBuffer)) {
        setParseError('Could not read the file as binary data.')
        setData(null)
        return
      }
      const text = new TextDecoder('utf-8', { fatal: false }).decode(buf)
      const result = parseDetectionJsonText(text)
      if (!result.ok) {
        setParseError(result.message)
        setData(null)
        return
      }
      const d = result.data
      setData(d)
      const fr = d.frames
      const hasVideo = Boolean(resolveVideoSource(d.metadata.video))
      if (hasVideo && fr.length > 0 && fr[0].timestamp > 0.001) {
        setFrameIndex(-1)
      } else {
        setFrameIndex(0)
      }
      setSelectedId(null)
      setVideoFileUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev)
        return null
      })
      setSpriteBlobUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev)
        return null
      })
    }
    reader.readAsArrayBuffer(file)
  }, [])

  const onSpriteFile = useCallback((file: File) => {
    setSpriteBlobUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return URL.createObjectURL(file)
    })
  }, [])

  useEffect(() => {
    return () => {
      if (spriteBlobUrl) URL.revokeObjectURL(spriteBlobUrl)
    }
  }, [spriteBlobUrl])

  useEffect(() => {
    return () => {
      if (videoFileUrl) URL.revokeObjectURL(videoFileUrl)
    }
  }, [videoFileUrl])

  const onVideoFile = useCallback((file: File) => {
    setVideoFileUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return URL.createObjectURL(file)
    })
  }, [])

  const spriteFromMetadata = useMemo(() => {
    if (!data) return null
    return resolveSpriteUrl(data.metadata.sprite)
  }, [data])

  const effectiveSpriteUrl = spriteBlobUrl ?? spriteFromMetadata

  const selectedObject = useMemo(() => {
    if (!current) return null
    return current.objects.find((o) => o.id === selectedId) ?? null
  }, [current, selectedId])

  const thumbFragment = selectedObject
    ? parseSpriteFragment(selectedObject.thumbnail)
    : null

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1 className="header__title">Detection viewer</h1>
          <p className="header__sub">
            Load a detection JSON — sprite and video URLs from the file are
            used automatically when present; use Load sprite / Load video to
            override.
          </p>
        </div>
        <div className="header__actions">
          <label className="btn">
            <input
              type="file"
              accept="application/json,.json"
              className="sr-only"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) onJsonFile(f)
                e.target.value = ''
              }}
            />
            Load JSON
          </label>
          <label className="btn btn--secondary">
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
              className="sr-only"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) onSpriteFile(f)
                e.target.value = ''
              }}
            />
            Load sprite
          </label>
          <label className="btn btn--secondary">
            <input
              type="file"
              accept="video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov"
              className="sr-only"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) onVideoFile(f)
                e.target.value = ''
              }}
            />
            Load video
          </label>
        </div>
      </header>

      {parseError ? (
        <div className="banner banner--error" role="alert">
          {parseError}
        </div>
      ) : null}

      {!data ? (
        <p className="empty">
          Open a detection export with <strong>Load JSON</strong>. If the file
          includes video and sprite URLs under metadata, they load
          automatically.
        </p>
      ) : (
        <>
          <section className="viewer">
            <div className="viewer__controls">
              <label className="scrub">
                <span className="scrub__label">
                  {frameIndex < 0
                    ? `Before first detection · ${frames.length} keyframes`
                    : `Frame ${frameIndex + 1} / ${frames.length}${
                        current
                          ? ` · idx ${current.frame_idx} · ${current.timestamp.toFixed(2)}s`
                          : ''
                      }`}
                </span>
                <input
                  type="range"
                  min={effectiveVideoSrc ? -1 : 0}
                  max={Math.max(0, frames.length - 1)}
                  value={frameIndex < -1 ? -1 : frameIndex}
                  onChange={(e) =>
                    setFrameIndex(Number(e.target.value))
                  }
                  className="scrub__input"
                />
              </label>
            </div>

            <div className="viewer__main">
              <div className="viewer__bbox">
                <h3 className="subhead">
                  {effectiveVideoSrc ? 'Video + detections' : 'Frame preview'}
                </h3>
                {effectiveVideoSrc ? (
                  <VideoDetectionPlayer
                    videoSrc={effectiveVideoSrc}
                    videoWidth={data.metadata.video.width}
                    videoHeight={data.metadata.video.height}
                    fps={data.metadata.video.fps}
                    frames={frames}
                    frameIndex={frameIndex}
                    onFrameIndexChange={setFrameIndex}
                    selectedId={selectedId}
                    onSelect={setSelectedId}
                  />
                ) : null}
                {!effectiveVideoSrc && current ? (
                  <BboxFrame
                    videoWidth={data.metadata.video.width}
                    videoHeight={data.metadata.video.height}
                    objects={current.objects}
                    selectedId={selectedId}
                    onSelect={setSelectedId}
                  />
                ) : null}
                {!effectiveVideoSrc && !current ? (
                  <p>No frames in file.</p>
                ) : null}
              </div>

              <div className="viewer__side">
                <h3 className="subhead">Objects ({current?.objects.length ?? 0})</h3>
                <ul className="obj-list">
                  {current?.objects.map((o) => (
                    <li key={o.id}>
                      <button
                        type="button"
                        className={
                          o.id === selectedId ? 'obj-list__btn is-on' : 'obj-list__btn'
                        }
                        onClick={() => setSelectedId(o.id)}
                      >
                        <span className="mono">{o.id}</span>
                        <span className="muted">{o.class_name}</span>
                        <span>{(o.confidence * 100).toFixed(1)}%</span>
                      </button>
                    </li>
                  ))}
                </ul>

                {selectedObject && thumbFragment ? (
                  <div className="thumb-block">
                    <h3 className="subhead">Sprite crop</h3>
                    <SpriteCrop
                      imageUrl={effectiveSpriteUrl}
                      fragment={thumbFragment}
                      label={selectedObject.thumbnail}
                    />
                    <dl className="kv kv--tight">
                      <dt>Bbox</dt>
                      <dd className="mono">
                        {selectedObject.bbox.x},{selectedObject.bbox.y}{' '}
                        {selectedObject.bbox.width}×{selectedObject.bbox.height}
                      </dd>
                    </dl>
                  </div>
                ) : null}
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
