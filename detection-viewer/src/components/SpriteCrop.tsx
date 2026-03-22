import { useState } from 'react'
import type { SpriteFragment } from '../lib/parseThumbnail'

type Props = {
  imageUrl: string | null
  fragment: SpriteFragment
  label?: string
}

export function SpriteCrop({ imageUrl, fragment, label }: Props) {
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null)

  if (!imageUrl) {
    return (
      <div
        className="sprite-crop sprite-crop--placeholder"
        style={{ width: fragment.width, height: fragment.height }}
      >
        Load sprite…
      </div>
    )
  }

  return (
    <figure className="sprite-crop">
      <div
        className="sprite-crop__clip"
        style={{ width: fragment.width, height: fragment.height }}
      >
        <img
          src={imageUrl}
          alt=""
          decoding="async"
          crossOrigin={
            /^https?:\/\//i.test(imageUrl) ? 'anonymous' : undefined
          }
          onLoad={(e) => {
            const im = e.currentTarget
            setNatural({ w: im.naturalWidth, h: im.naturalHeight })
          }}
          className="sprite-crop__img"
          style={
            natural
              ? {
                  width: natural.w,
                  height: natural.h,
                  transform: `translate(${-fragment.x}px, ${-fragment.y}px)`,
                }
              : { visibility: 'hidden' as const }
          }
        />
      </div>
      {label ? <figcaption className="sprite-crop__cap">{label}</figcaption> : null}
    </figure>
  )
}
