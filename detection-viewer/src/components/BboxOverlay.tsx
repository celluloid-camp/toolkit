import type { DetectionObject } from '../types'

const COLORS = [
  '#f0a030',
  '#4ecdc4',
  '#ff6b6b',
  '#a8dadc',
  '#c9b1ff',
  '#95d5b2',
]

function colorForIndex(i: number) {
  return COLORS[i % COLORS.length]
}

type Props = {
  videoWidth: number
  videoHeight: number
  objects: DetectionObject[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function BboxOverlay({
  videoWidth,
  videoHeight,
  objects,
  selectedId,
  onSelect,
}: Props) {
  return (
    <>
      {objects.map((obj, i) => {
        const left = (obj.bbox.x / videoWidth) * 100
        const top = (obj.bbox.y / videoHeight) * 100
        const w = (obj.bbox.width / videoWidth) * 100
        const h = (obj.bbox.height / videoHeight) * 100
        const active = selectedId === obj.id
        const color = colorForIndex(i)
        return (
          <button
            key={`${obj.id}-${obj.bbox.x}-${obj.bbox.y}`}
            type="button"
            className={`bbox-frame__box${active ? ' bbox-frame__box--active' : ''}`}
            style={{
              left: `${left}%`,
              top: `${top}%`,
              width: `${w}%`,
              height: `${h}%`,
              borderColor: color,
              boxShadow: active ? `0 0 0 2px ${color}88` : undefined,
            }}
            onClick={() => onSelect(obj.id)}
            title={`${obj.id} · ${(obj.confidence * 100).toFixed(1)}%`}
          >
            <span className="bbox-frame__label" style={{ background: color }}>
              {obj.id}
            </span>
          </button>
        )
      })}
    </>
  )
}
