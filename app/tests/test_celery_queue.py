"""Unit tests for CeleryJobManager status resolution."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from app.core.celery_queue import CeleryJobManager
from app.core.tasks import _processing_meta


def test_processing_meta_includes_job_type():
    job_data = {
        "job_id": "job-1",
        "external_id": "ext-1",
        "video_url": "https://example.com/video.mp4",
        "job_type": "transcribe",
        "callback_url": "https://example.com/callback",
    }
    meta = _processing_meta(job_data, "2026-06-10T12:00:00", 65.6)
    assert meta["job_type"] == "transcribe"
    assert meta["progress"] == 65.6
    assert meta["video_url"] == job_data["video_url"]


@patch("app.core.celery_queue.celery_app")
@patch("app.core.celery_queue.AsyncResult")
def test_get_job_from_celery_enriches_partial_processing_meta(
    mock_async_result, _mock_app
):
    manager = CeleryJobManager()
    manager._redis = MagicMock()
    manager._redis.hgetall.return_value = {
        "job_id": "job-1",
        "external_id": "test",
        "video_url": "https://example.com/video.mp4",
        "job_type": "transcribe",
        "callback_url": "",
        "params": "{}",
        "status": "queued",
        "start_time": datetime.now().isoformat(),
    }

    result = MagicMock()
    result.state = "PROCESSING"
    result.info = {
        "job_id": "job-1",
        "external_id": "test",
        "status": "processing",
        "progress": 65.6,
        "start_time": "2026-06-10T12:08:38.822587",
    }
    mock_async_result.return_value = result

    job = manager.get_job_from_celery("job-1")

    assert job is not None
    assert job.job_type == "transcribe"
    assert job.status == "processing"
    assert job.progress == 65.6


@patch("app.core.celery_queue.celery_app")
@patch("app.core.celery_queue.AsyncResult")
def test_get_job_from_celery_success_returns_completed(mock_async_result, _mock_app):
    manager = CeleryJobManager()

    result = MagicMock()
    result.state = "SUCCESS"
    result.result = {
        "job_id": "job-1",
        "external_id": "test",
        "video_url": "https://example.com/video.mp4",
        "job_type": "transcribe",
        "status": "completed",
        "result_path": "outputs/test/transcript_job-1.json",
        "start_time": "2026-06-10T12:08:38.822587",
        "end_time": "2026-06-10T12:10:35.909000",
        "metadata": {},
    }
    mock_async_result.return_value = result

    job = manager.get_job_from_celery("job-1")

    assert job is not None
    assert job.job_type == "transcribe"
    assert job.status == "completed"
    assert job.progress == 100.0
