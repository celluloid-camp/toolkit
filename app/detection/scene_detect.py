import os
import json
from typing import List, Optional, Tuple

import cv2
from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector, ThresholdDetector
from app.core.utils import download_file, ensure_dir
from app.detection.sprite import SpriteGenerator
from datetime import datetime
from urllib.parse import urlparse
from pydantic import BaseModel


class SceneInfo(BaseModel):
    """Represents a single scene in the video"""

    scene_id: int
    start_time: str
    end_time: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    sprite_fragment: Optional[str] = None  # e.g. "#xywh=0,0,160,90"


class SceneDetection(BaseModel):
    """Type definition for scene detection results"""

    total_scenes: int
    scenes: List[SceneInfo]
    sprite_url: Optional[str] = None
    sprite_fragments: Optional[List[str]] = None  # ordered #xywh per scene


def detect_scenes_from_file(
    video_path: str,
    threshold: float = 30.0,
    save_json: bool = False,
    export_sprite: bool = False,
    sprite_output_path: Optional[str] = None,
    thumbnail_size: Tuple[int, int] = (160, 90),
) -> Optional[SceneDetection]:
    """
    Detect scenes in a video and optionally build a sprite of first-frame thumbnails.

    Uses PySceneDetect SceneManager (ContentDetector + ThresholdDetector). If
    export_sprite is True, the first frame of each detected scene is added to a
    single sprite image and each scene gets a sprite_fragment (#xywh=x,y,width,height).

    Args:
        video_path: Path of the video to process.
        threshold: Content detection threshold (default: 30.0).
        save_json: Whether to save results to JSON file (default: False).
        export_sprite: If True, build a sprite image and set sprite_fragment per scene.
        sprite_output_path: Where to save the sprite image (used only if export_sprite).
        thumbnail_size: (width, height) of each thumbnail in the sprite.

    Returns:
        SceneDetection with scenes and optional sprite_path / sprite_fragments, or None.
    """
    import traceback

    try:
        video = open_video(video_path)
        scene_manager = SceneManager()
        # TODO: add separate threshold and min_scene_len to the content detector and threshold detector
        scene_manager.add_detector(
            ContentDetector(threshold=threshold, min_scene_len=15)
        )
        scene_manager.add_detector(ThresholdDetector(threshold=12.0, min_scene_len=15))

        scene_manager.detect_scenes(video=video)
        scenes = scene_manager.get_scene_list()
        print(f"Detected {len(scenes)} scenes")

        if not scenes:
            return SceneDetection(total_scenes=0, scenes=[])

        sprite_path_out: Optional[str] = None
        sprite_fragments_out: Optional[List[str]] = None

        if export_sprite:
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            generator = SpriteGenerator(thumbnail_size=thumbnail_size)

            for scene_idx, (start_time, _end_time) in enumerate(scenes):
                frame_num = int(start_time.get_seconds() * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if ret and frame is not None:
                    generator.add_thumbnail(frame, f"scene_{scene_idx}", scene_idx)

            cap.release()

            if generator.sprites:
                if sprite_output_path:
                    ensure_dir(
                        os.path.dirname(os.path.abspath(sprite_output_path)) or "."
                    )
                    generator.save_sprite(sprite_output_path)
                    sprite_path_out = sprite_output_path
                else:
                    base = os.path.splitext(video_path)[0]
                    default_sprite = f"{base}_scenes_sprite.jpg"
                    generator.save_sprite(default_sprite)
                    sprite_path_out = default_sprite

                sprite_fragments_out = [s["fragment_id"] for s in generator.sprites]

        scenes_data: List[SceneInfo] = []
        for i, (start_time, end_time) in enumerate(scenes):
            fragment = (
                sprite_fragments_out[i]
                if sprite_fragments_out and i < len(sprite_fragments_out)
                else None
            )
            scenes_data.append(
                SceneInfo(
                    scene_id=i,
                    start_time=str(start_time),
                    end_time=str(end_time),
                    start_seconds=start_time.get_seconds(),
                    end_seconds=end_time.get_seconds(),
                    duration_seconds=(end_time - start_time).get_seconds(),
                    sprite_fragment=fragment,
                )
            )

        return SceneDetection(
            total_scenes=len(scenes),
            scenes=scenes_data,
            sprite_url=sprite_path_out,
            sprite_fragments=sprite_fragments_out,
        )

    except Exception as e:
        traceback.print_exc()
        print(f"Error detecting scenes: {str(e)}")
        return None


def main():
    """CLI entry point for scene detection."""
    import argparse

    parser = argparse.ArgumentParser(description="Detect scenes in a video")
    parser.add_argument("video_url", help="URL or local path to a video file")
    parser.add_argument(
        "--threshold",
        type=float,
        default=30.0,
        help="Content detection threshold (default: 30.0)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: tmp next to this file)",
    )
    args = parser.parse_args()

    video_url = args.video_url
    tmp_dir = args.output_dir or os.path.join(os.getcwd(), "tmp")
    ensure_dir(tmp_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if video_url.startswith(("http://", "https://")):
        filename = os.path.basename(urlparse(video_url).path)
        if not filename or "." not in filename:
            filename = "video.mp4"
        name, ext = os.path.splitext(filename)
        unique_filename = f"{name}_{timestamp}{ext}"
        video_path = os.path.join(tmp_dir, unique_filename)
        print(f"Downloading video to: {video_path}")
        download_file(video_url, video_path)
    else:
        video_path = video_url

    sprite_path = os.path.join(tmp_dir, f"scenes_sprite_{timestamp}.jpg")
    results = detect_scenes_from_file(
        video_path,
        threshold=args.threshold,
        export_sprite=True,
        sprite_output_path=sprite_path,
    )

    output_path = os.path.join(tmp_dir, f"scene_detection_{timestamp}.json")
    with open(output_path, "w") as f:
        json.dump(results.model_dump() if results else None, f, indent=2)

    print(f"Scene detection results saved to: {output_path}")
    return 0


if __name__ == "__main__":
    main()
