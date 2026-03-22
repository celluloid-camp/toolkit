export interface Bbox {
  x: number
  y: number
  width: number
  height: number
}

export interface DetectionObject {
  id: string
  class_name: string
  confidence: number
  bbox: Bbox
  thumbnail: string
}

export interface FrameEntry {
  frame_idx: number
  timestamp: number
  objects: DetectionObject[]
}

export interface DetectionFile {
  version: string
  metadata: {
    video: {
      fps: number
      frame_count: number
      width: number
      height: number
      /** Video URL or path (relative paths resolved at load time). */
      source?: string
    }
    sprite: {
      /** Relative or absolute path (legacy exports). */
      path?: string
      /** Public URL for the sprite sheet (common in API exports). */
      url?: string
      thumbnail_size: [number, number]
    }
    processing: {
      start_time: string
      end_time: string
      duration_seconds: number
      frames_processed: number
      frames_with_detections: number
      processing_speed: number
      detection_statistics: {
        total_detections: number
        person_detections: number
        person_with_face?: number
        person_without_face?: number
        other_detections: number
        class_counts: Record<string, number>
      }
    }
  }
  frames: FrameEntry[]
}
