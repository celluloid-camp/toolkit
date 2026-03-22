import type { DetectionObject } from '../types'
import { BboxOverlay } from './BboxOverlay'

type Props = {
  videoWidth: number
  videoHeight: number
  objects: DetectionObject[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function BboxFrame({
  videoWidth,
  videoHeight,
  objects,
  selectedId,
  onSelect,
}: Props) {
  const aspect = videoHeight / videoWidth

  return (
    <div style={{ width: '100%' }}>
      <div
        className="bbox-frame"
        style={{
          aspectRatio: `${videoWidth} / ${videoHeight}`,
          maxWidth: 'min(100%, 720px)',
        }}
      >
        <div className="bbox-frame__grid" />
        <BboxOverlay
          videoWidth={videoWidth}
          videoHeight={videoHeight}
          objects={objects}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      </div>
      <p className="bbox-frame__meta">
        {videoWidth}×{videoHeight} · aspect {aspect.toFixed(3)}
      </p>
    </div>
  )
}
