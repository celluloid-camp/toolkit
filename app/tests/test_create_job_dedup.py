import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.api.routes import create_job
from app.models.result_models import CreateJobRequest
from app.models.schemas import JobStatus

TEST_VIDEO_URL = "https://example.com/video.mp4"
PROJECT_ID = "project-123"
ACTIVE_SCENE_JOB_ID = "scene-job-id"


@pytest.fixture
def mock_job_manager():
    active_scene_job = JobStatus(
        job_id=ACTIVE_SCENE_JOB_ID,
        external_id=PROJECT_ID,
        video_url=TEST_VIDEO_URL,
        job_type="scene_detect",
    )
    active_scene_job.status = "processing"
    active_scene_job.start_time = datetime.now()

    manager = MagicMock()
    manager.get_all_jobs.return_value = [active_scene_job]
    manager.enqueue_job.return_value = None
    return manager


def _create_job_request(job_type: str) -> CreateJobRequest:
    return CreateJobRequest(
        job_type=job_type,
        external_id=PROJECT_ID,
        video_url=TEST_VIDEO_URL,
    )


def test_create_job_dedupes_same_job_type(mock_job_manager):
    with patch("app.api.routes.job_manager", mock_job_manager):
        response = asyncio.run(
            create_job(_create_job_request("scene_detect"), key="test-key")
        )

    assert response["job_id"] == ACTIVE_SCENE_JOB_ID
    assert "already has an active job" in response["message"]
    mock_job_manager.enqueue_job.assert_not_called()


def test_create_job_allows_different_job_type_for_same_project(mock_job_manager):
    with patch("app.api.routes.job_manager", mock_job_manager):
        response = asyncio.run(
            create_job(_create_job_request("object_detect"), key="test-key")
        )

    assert response["job_id"] != ACTIVE_SCENE_JOB_ID
    assert response["job_type"] == "object_detect"
    assert "job added to queue" in response["message"]
    mock_job_manager.enqueue_job.assert_called_once()
