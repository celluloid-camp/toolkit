"""Celery tasks for video processing"""

import json
import logging
import os
import time
import traceback
from datetime import datetime

import cv2
import requests

from app.core.celery_app import celery_app
from app.core.utils import download_video

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _send_callback_sync(
    job_id, external_id, job_type, callback_url, status, results=None, error=None
):
    """Send callback notification synchronously with retry logic"""
    callback_data = {
        "job_id": job_id,
        "external_id": external_id,
        "job_type": job_type,
        "status": status,
        "timestamp": datetime.now().isoformat(),
    }
    if status == "completed" and results:
        callback_data["results"] = results
    elif status == "failed" and error:
        callback_data["error"] = error

    max_retries = 3
    retry_delay = 30

    for attempt in range(max_retries):
        try:
            response = requests.post(
                callback_url,
                json=callback_data,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            if 200 <= response.status_code < 300:
                logger.info(
                    f"Callback sent successfully to {callback_url} (attempt {attempt + 1})"
                )
                return
            elif 400 <= response.status_code < 500 and response.status_code not in [
                408,
                429,
            ]:
                logger.error(f"Client error {response.status_code}, not retrying")
                break
            else:
                logger.warning(
                    f"Callback attempt {attempt + 1} returned {response.status_code}"
                )
        except Exception as exc:
            logger.warning(f"Callback attempt {attempt + 1} failed: {exc}")

        if attempt < max_retries - 1:
            time.sleep(retry_delay)
            retry_delay *= 2

    logger.error(f"All callback attempts failed for job {job_id} to {callback_url}")


def _download_and_validate_video(video_url: str) -> str:
    """Download (if remote) and validate a video file. Returns local path."""
    if video_url.startswith(("http://", "https://")):
        video_path = download_video(video_url)
    else:
        video_path = video_url

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Video file not valid")
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if frame_count == 0:
        raise ValueError(
            f"Video contains no video stream. It may be audio-only: {video_path}"
        )
    cap.release()
    return video_path


def _cleanup_video(video_url: str, video_path: str) -> None:
    """Remove downloaded video if it was a remote URL."""
    if video_url.startswith(("http://", "https://")):
        try:
            os.remove(video_path)
            logger.info(f"Cleaned up temporary video file: {video_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary video file: {str(e)}")


def _processing_meta(job_data: dict, start_time: str, progress: float = 0.0) -> dict:
    """Build a complete Celery PROCESSING meta payload (replaces prior meta)."""
    return {
        "job_id": job_data["job_id"],
        "external_id": job_data["external_id"],
        "video_url": job_data["video_url"],
        "job_type": job_data["job_type"],
        "callback_url": job_data.get("callback_url"),
        "status": "processing",
        "progress": round(progress, 1),
        "start_time": start_time,
    }


def _make_progress_reporter(task, job_data: dict, start_time: str):
    """Create a throttled progress callback for Celery state updates."""
    last_reported = [0.0]

    def _report(pct: float):
        if pct - last_reported[0] >= 5.0 or pct >= 100.0:
            last_reported[0] = pct
            task.update_state(
                state="PROCESSING",
                meta=_processing_meta(job_data, start_time, pct),
            )

    return _report


# ---------------------------------------------------------------------------
# Object-detect task
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="app.core.tasks.process_object_detect_task")
def process_object_detect_task(self, job_data: dict):
    """Celery task for object detection on a video."""
    job_id = job_data["job_id"]
    external_id = job_data["external_id"]
    video_url = job_data["video_url"]
    params = job_data.get("params", {})
    similarity_threshold = float(params.get("similarity_threshold", 0.5))
    analysis_fps = float(params.get("analysis_fps", 1.0))
    callback_url = job_data.get("callback_url")
    start_time = datetime.now().isoformat()

    self.update_state(
        state="PROCESSING",
        meta=_processing_meta(job_data, start_time, 0.0),
    )

    try:
        output_dir = os.path.join("outputs", external_id)
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"detections_{job_id}_{timestamp}.json"
        output_path = os.path.join(output_dir, output_filename)

        video_path = _download_and_validate_video(video_url)

        from app.detection.object_detect import ObjectDetector

        detector = ObjectDetector(
            min_score=0.8,
            output_path=output_path,
            similarity_threshold=similarity_threshold,
            external_id=external_id,
            analysis_fps=analysis_fps,
        )

        progress_cb = _make_progress_reporter(self, job_data, start_time)
        results = detector.process_video(
            video_path, video_url, progress_callback=progress_cb
        )

        results["result_type"] = "object_detect"

        sprite_meta = results.get("metadata", {}).get("sprite")
        if sprite_meta:
            base_url = os.getenv("BASE_URL", "").rstrip("/")
            sprite_meta["url"] = (
                f"{base_url}/{sprite_meta['url']}" if base_url else sprite_meta["url"]
            )

        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        logger.info(f"Result file saved to: {output_path}")

        processing = results["metadata"]["processing"]
        detection_stats = processing["detection_statistics"]
        metadata = {
            "frames_processed": processing["frames_processed"],
            "frames_with_detections": processing["frames_with_detections"],
            "total_detections": detection_stats["total_detections"],
            "processing_time": processing["duration_seconds"],
        }

        end_time = datetime.now().isoformat()
        logger.info(f"Job {job_id} completed successfully")

        if callback_url:
            _send_callback_sync(
                job_id,
                external_id,
                "object_detect",
                callback_url,
                "completed",
                {"result_path": output_path, "metadata": metadata},
            )

        _cleanup_video(video_url, video_path)

        return {
            "job_id": job_id,
            "external_id": external_id,
            "video_url": video_url,
            "job_type": "object_detect",
            "callback_url": callback_url,
            "status": "completed",
            "result_path": output_path,
            "start_time": start_time,
            "end_time": end_time,
            "metadata": metadata,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Job {job_id} failed: {error_msg}")
        logger.error(traceback.format_exc())

        if callback_url:
            _send_callback_sync(
                job_id,
                external_id,
                "object_detect",
                callback_url,
                "failed",
                error=error_msg,
            )

        raise


# ---------------------------------------------------------------------------
# Scene-detect task
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="app.core.tasks.process_scene_detect_task")
def process_scene_detect_task(self, job_data: dict):
    """Celery task for scene detection on a video."""
    job_id = job_data["job_id"]
    external_id = job_data["external_id"]
    video_url = job_data["video_url"]
    params = job_data.get("params", {})
    threshold = float(params.get("threshold", 30.0))
    callback_url = job_data.get("callback_url")
    start_time = datetime.now().isoformat()

    self.update_state(
        state="PROCESSING",
        meta=_processing_meta(job_data, start_time, 0.0),
    )

    try:
        output_dir = os.path.join("outputs", external_id)
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"scenes_{job_id}_{timestamp}.json"
        output_path = os.path.join(output_dir, output_filename)
        sprite_path = os.path.join(
            output_dir, f"scenes_{job_id}_{timestamp}.sprite.jpg"
        )

        video_path = _download_and_validate_video(video_url)

        self.update_state(
            state="PROCESSING",
            meta=_processing_meta(job_data, start_time, 10.0),
        )

        from app.detection.scene_detect import detect_scenes_from_file

        scene_result = detect_scenes_from_file(
            video_path,
            threshold=threshold,
            export_sprite=True,
            sprite_output_path=sprite_path,
        )

        if scene_result is None:
            raise RuntimeError("Scene detection returned no results")

        self.update_state(
            state="PROCESSING",
            meta=_processing_meta(job_data, start_time, 90.0),
        )

        if scene_result.sprite_url:
            base_url = os.getenv("BASE_URL", "").rstrip("/")
            scene_result.sprite_url = (
                f"{base_url}/{scene_result.sprite_url}"
                if base_url
                else scene_result.sprite_url
            )

        result_data = scene_result.model_dump()
        result_data["result_type"] = "scene_detect"

        with open(output_path, "w") as f:
            json.dump(result_data, f, indent=2)

        logger.info(f"Scene result file saved to: {output_path}")

        metadata = {
            "total_scenes": scene_result.total_scenes,
            "has_sprite": scene_result.sprite_url is not None,
        }

        end_time = datetime.now().isoformat()
        logger.info(f"Job {job_id} completed successfully")

        if callback_url:
            _send_callback_sync(
                job_id,
                external_id,
                "scene_detect",
                callback_url,
                "completed",
                {"result_path": output_path, "metadata": metadata},
            )

        _cleanup_video(video_url, video_path)

        return {
            "job_id": job_id,
            "external_id": external_id,
            "video_url": video_url,
            "job_type": "scene_detect",
            "callback_url": callback_url,
            "status": "completed",
            "result_path": output_path,
            "start_time": start_time,
            "end_time": end_time,
            "metadata": metadata,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Job {job_id} failed: {error_msg}")
        logger.error(traceback.format_exc())

        if callback_url:
            _send_callback_sync(
                job_id,
                external_id,
                "scene_detect",
                callback_url,
                "failed",
                error=error_msg,
            )

        raise


# ---------------------------------------------------------------------------
# Transcribe task
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="app.core.tasks.process_transcribe_task")
def process_transcribe_task(self, job_data: dict):
    """Celery task for audio transcription with optional speaker diarization."""
    job_id = job_data["job_id"]
    external_id = job_data["external_id"]
    video_url = job_data["video_url"]
    params = job_data.get("params", {})
    callback_url = job_data.get("callback_url")
    start_time = datetime.now().isoformat()

    from app.core.config import (
        DIARIZATION_ENABLED,
        PYANNOTE_AUTH_TOKEN,
        PYANNOTE_MODEL,
        WHISPER_COMPUTE_TYPE,
        WHISPER_DEVICE,
        WHISPER_LANGUAGE,
        WHISPER_MODEL_SIZE,
    )

    model_size = params.get("model_size", WHISPER_MODEL_SIZE)
    device = params.get("device", WHISPER_DEVICE)
    compute_type = params.get("compute_type", WHISPER_COMPUTE_TYPE)
    language = params.get("language", WHISPER_LANGUAGE) or None
    diarization_enabled = params.get("diarization_enabled", DIARIZATION_ENABLED)
    num_speakers = params.get("num_speakers")
    min_speakers = params.get("min_speakers")
    max_speakers = params.get("max_speakers")
    auth_token = PYANNOTE_AUTH_TOKEN
    pyannote_model = PYANNOTE_MODEL

    self.update_state(
        state="PROCESSING",
        meta=_processing_meta(job_data, start_time, 0.0),
    )

    try:
        output_dir = os.path.join("outputs", external_id)
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"transcript_{job_id}_{timestamp}.json"
        output_path = os.path.join(output_dir, output_filename)

        # Download remote file; local paths are used directly.
        if video_url.startswith(("http://", "https://")):
            audio_path = download_video(video_url)
        else:
            audio_path = video_url

        progress_cb = _make_progress_reporter(self, job_data, start_time)

        from app.detection.transcribe import run_transcription_pipeline

        result = run_transcription_pipeline(
            audio_path=audio_path,
            model_size=model_size,
            device=device,
            compute_type=compute_type,
            language=language,
            diarization_enabled=diarization_enabled,
            auth_token=auth_token,
            pyannote_model=pyannote_model,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            progress_callback=progress_cb,
        )

        result["result_type"] = "transcribe"

        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)

        logger.info(f"Transcript saved to: {output_path}")

        metadata = {
            "language": result["metadata"]["language"],
            "audio_duration_sec": result["metadata"]["audio_duration_sec"],
            "processing_time_sec": result["metadata"]["processing_time_sec"],
            "segment_count": len(result["segments"]),
            "speaker_count": len(result["speakers"]),
        }

        end_time = datetime.now().isoformat()
        logger.info(f"Transcription job {job_id} completed successfully")

        if callback_url:
            _send_callback_sync(
                job_id,
                external_id,
                "transcribe",
                callback_url,
                "completed",
                {"result_path": output_path, "metadata": metadata},
            )

        # Clean up downloaded file
        if video_url.startswith(("http://", "https://")):
            try:
                os.remove(audio_path)
                logger.info(f"Cleaned up temporary file: {audio_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file: {str(e)}")

        return {
            "job_id": job_id,
            "external_id": external_id,
            "video_url": video_url,
            "job_type": "transcribe",
            "callback_url": callback_url,
            "status": "completed",
            "result_path": output_path,
            "start_time": start_time,
            "end_time": end_time,
            "metadata": metadata,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Transcription job {job_id} failed: {error_msg}")
        logger.error(traceback.format_exc())

        if callback_url:
            _send_callback_sync(
                job_id,
                external_id,
                "transcribe",
                callback_url,
                "failed",
                error=error_msg,
            )

        raise
