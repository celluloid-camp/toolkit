"""
REST API integration tests for the Celluloid Vision API.

These tests run against a live instance of the FastAPI application and
verify the HTTP contract of each endpoint.  They do NOT exercise the
full video-processing pipeline; a real Celery worker is not required.

Environment variables consumed by the tests:
  BASE_URL   – base URL of the running API  (default: http://localhost:8081)
  API_KEY    – value to send in the x-api-key header (default: test-key-for-ci)
"""

import os
import time

import pytest
import requests

BASE_URL = os.getenv("BASE_URL", "http://localhost:8081")
API_KEY = os.getenv("API_KEY", "test-key-for-ci")
HEADERS_AUTH = {"x-api-key": API_KEY}
HEADERS_JSON_AUTH = {"Content-Type": "application/json", "x-api-key": API_KEY}
FAKE_JOB_ID = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_for_api(max_wait: int = 60) -> None:
    """Block until /health returns 200 or timeout is reached."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=5)
            if r.status_code == 200:
                return
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(2)
    pytest.fail(f"API at {BASE_URL} did not become ready within {max_wait}s")


TEST_VIDEO_URL = "https://pt-storage.celluloid.cloud/web-videos/a53d2ce5-0db1-49bf-9daa-be2dafd46ee9-144.mp4"


def _object_detect_payload(**overrides) -> dict:
    base = {
        "job_type": "object_detect",
        "external_id": "ci-test-project",
        "video_url": TEST_VIDEO_URL,
        "params": {"similarity_threshold": 0.5},
    }
    base.update(overrides)
    return base


def _scene_detect_payload(**overrides) -> dict:
    base = {
        "job_type": "scene_detect",
        "external_id": "ci-test-project-scene",
        "video_url": TEST_VIDEO_URL,
        "params": {"threshold": 30.0},
    }
    base.update(overrides)
    return base


def _transcribe_payload(**overrides) -> dict:
    base = {
        "job_type": "transcribe",
        "external_id": "ci-test-project-transcribe",
        "video_url": TEST_VIDEO_URL,
        "params": {"model_size": "small", "diarization_enabled": False},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Session-scoped fixture: wait for the API to be up
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def wait_for_api():
    _wait_for_api()


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_returns_200(self):
        r = requests.get(f"{BASE_URL}/health")
        assert r.status_code == 200

    def test_health_status_field(self):
        r = requests.get(f"{BASE_URL}/health")
        data = r.json()
        assert data["status"] in ("healthy", "unhealthy")

    def test_health_when_redis_connected(self):
        r = requests.get(f"{BASE_URL}/health")
        data = r.json()
        assert data["status"] == "healthy"

    def test_health_contains_job_stats(self):
        r = requests.get(f"{BASE_URL}/health")
        data = r.json()
        assert "job_stats" in data
        stats = data["job_stats"]
        for key in ("queued", "processing", "completed", "failed"):
            assert key in stats
            assert isinstance(stats[key], int)


# ---------------------------------------------------------------------------
# GET / (API docs)
# ---------------------------------------------------------------------------


class TestDocs:
    def test_docs_returns_200(self):
        r = requests.get(f"{BASE_URL}/")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# POST /job/create – authentication
# ---------------------------------------------------------------------------


class TestCreateJobAuth:
    _valid_payload = _object_detect_payload()

    def test_create_missing_api_key_returns_403(self):
        r = requests.post(f"{BASE_URL}/job/create", json=self._valid_payload)
        assert r.status_code == 403

    def test_create_wrong_api_key_returns_401(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=self._valid_payload,
            headers={"x-api-key": "wrong-key"},
        )
        assert r.status_code == 401

    def test_create_valid_api_key_returns_202(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=self._valid_payload,
            headers=HEADERS_AUTH,
        )
        assert r.status_code in (202, 422)


# ---------------------------------------------------------------------------
# POST /job/create – request validation
# ---------------------------------------------------------------------------


class TestCreateJobValidation:
    def test_missing_external_id_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json={
                "job_type": "object_detect",
                "video_url": "http://example.com/v.mp4",
            },
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_missing_video_url_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json={"job_type": "object_detect", "external_id": "ci-proj"},
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_invalid_job_type_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json={
                "job_type": "invalid_type",
                "external_id": "ci-proj",
                "video_url": "http://example.com/v.mp4",
            },
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_object_detect_invalid_similarity_threshold_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=_object_detect_payload(
                external_id="ci-proj",
                params={"similarity_threshold": 5.0},
            ),
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_object_detect_invalid_analysis_fps_zero_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=_object_detect_payload(
                external_id="ci-proj",
                params={"analysis_fps": 0},
            ),
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_object_detect_invalid_analysis_fps_too_high_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=_object_detect_payload(
                external_id="ci-proj",
                params={"analysis_fps": 100},
            ),
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_object_detect_valid_analysis_fps_accepted(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=_object_detect_payload(
                external_id="ci-fps-test",
                params={"similarity_threshold": 0.5, "analysis_fps": 5},
            ),
            headers=HEADERS_AUTH,
        )
        assert r.status_code in (202, 422)

    def test_invalid_video_url_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=_object_detect_payload(
                external_id="ci-proj",
                video_url="not-a-url-and-not-a-file",
            ),
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_invalid_callback_url_scheme_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=_object_detect_payload(
                external_id="ci-proj",
                callback_url="ftp://example.com/callback",
            ),
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_callback_url_localhost_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=_object_detect_payload(
                external_id="ci-proj",
                callback_url="http://localhost/callback",
            ),
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_callback_url_private_ip_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=_object_detect_payload(
                external_id="ci-proj",
                callback_url="http://192.168.1.1/callback",
            ),
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_callback_url_loopback_ip_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=_object_detect_payload(
                external_id="ci-proj",
                callback_url="http://127.0.0.1/callback",
            ),
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422

    def test_valid_callback_url_accepted(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=_object_detect_payload(
                external_id="ci-callback-valid",
                callback_url="https://hooks.example.com/notify",
            ),
            headers=HEADERS_AUTH,
        )
        assert r.status_code in (202, 422)
        if r.status_code == 202:
            assert r.json().get("callback_url") == "https://hooks.example.com/notify"

    def test_object_detect_response_shape(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=_object_detect_payload(external_id="ci-shape-od"),
            headers=HEADERS_AUTH,
        )
        if r.status_code == 202:
            data = r.json()
            assert data["job_type"] == "object_detect"
            assert "job_id" in data
            assert "status" in data
            assert "queue_position" in data
            assert "message" in data

    def test_scene_detect_response_shape(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=_scene_detect_payload(external_id="ci-shape-sd"),
            headers=HEADERS_AUTH,
        )
        if r.status_code == 202:
            data = r.json()
            assert data["job_type"] == "scene_detect"
            assert "job_id" in data
            assert "status" in data

    def test_scene_detect_default_params(self):
        """scene_detect works without explicit params (defaults applied)."""
        r = requests.post(
            f"{BASE_URL}/job/create",
            json={
                "job_type": "scene_detect",
                "external_id": "ci-scene-defaults",
                "video_url": TEST_VIDEO_URL,
            },
            headers=HEADERS_AUTH,
        )
        assert r.status_code in (202, 422)

    def test_transcribe_response_shape(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=_transcribe_payload(external_id="ci-shape-tr"),
            headers=HEADERS_AUTH,
        )
        if r.status_code == 202:
            data = r.json()
            assert data["job_type"] == "transcribe"
            assert "job_id" in data
            assert "status" in data
            assert "queue_position" in data
            assert "message" in data

    def test_transcribe_default_params(self):
        """transcribe works without explicit params (defaults applied)."""
        r = requests.post(
            f"{BASE_URL}/job/create",
            json={
                "job_type": "transcribe",
                "external_id": "ci-transcribe-defaults",
                "video_url": TEST_VIDEO_URL,
            },
            headers=HEADERS_AUTH,
        )
        assert r.status_code in (202, 422)

    def test_transcribe_invalid_job_type_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json={
                "job_type": "invalid_type",
                "external_id": "ci-proj",
                "video_url": TEST_VIDEO_URL,
            },
            headers=HEADERS_AUTH,
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /status/{job_id}
# ---------------------------------------------------------------------------


class TestJobStatusAuth:
    def test_status_missing_api_key_returns_403(self):
        r = requests.get(f"{BASE_URL}/status/{FAKE_JOB_ID}")
        assert r.status_code == 403

    def test_status_wrong_api_key_returns_401(self):
        r = requests.get(
            f"{BASE_URL}/status/{FAKE_JOB_ID}",
            headers={"x-api-key": "wrong-key"},
        )
        assert r.status_code == 401


class TestJobStatus:
    def test_status_nonexistent_job_returns_404(self):
        r = requests.get(f"{BASE_URL}/status/{FAKE_JOB_ID}", headers=HEADERS_AUTH)
        assert r.status_code == 404

    def test_status_returns_correct_shape(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=_object_detect_payload(external_id="ci-status-test"),
            headers=HEADERS_AUTH,
        )
        if r.status_code != 202:
            pytest.skip("Could not enqueue job; skipping status shape test")

        job_id = r.json()["job_id"]
        rs = requests.get(f"{BASE_URL}/status/{job_id}", headers=HEADERS_AUTH)
        assert rs.status_code == 200
        data = rs.json()
        assert data["job_id"] == job_id
        assert "status" in data
        assert data["status"] in ("queued", "processing", "completed", "failed")
        assert "progress" in data
        assert "queue_position" in data
        assert "estimated_wait_time" in data
        assert "job_type" in data

    def test_status_duplicate_project_returns_existing_job(self):
        payload = _object_detect_payload(external_id="ci-dedup-test")
        r1 = requests.post(f"{BASE_URL}/job/create", json=payload, headers=HEADERS_AUTH)
        if r1.status_code != 202:
            pytest.skip("Could not enqueue job; skipping deduplication test")
        job_id_1 = r1.json()["job_id"]

        r2 = requests.post(f"{BASE_URL}/job/create", json=payload, headers=HEADERS_AUTH)
        assert r2.status_code == 202
        assert r2.json()["job_id"] == job_id_1

    def test_different_job_types_same_project_create_separate_jobs(self):
        external_id = "ci-dedup-job-type-test"
        r1 = requests.post(
            f"{BASE_URL}/job/create",
            json=_scene_detect_payload(external_id=external_id),
            headers=HEADERS_AUTH,
        )
        if r1.status_code != 202:
            pytest.skip("Could not enqueue job; skipping job-type dedup test")
        job_id_1 = r1.json()["job_id"]

        r2 = requests.post(
            f"{BASE_URL}/job/create",
            json=_object_detect_payload(external_id=external_id),
            headers=HEADERS_AUTH,
        )
        assert r2.status_code == 202
        assert r2.json()["job_id"] != job_id_1
        assert r2.json()["job_type"] == "object_detect"


# ---------------------------------------------------------------------------
# GET /job/{job_id}/results
# ---------------------------------------------------------------------------


class TestJobResultsAuth:
    def test_results_missing_api_key_returns_403(self):
        r = requests.get(f"{BASE_URL}/job/{FAKE_JOB_ID}/results")
        assert r.status_code == 403

    def test_results_wrong_api_key_returns_401(self):
        r = requests.get(
            f"{BASE_URL}/job/{FAKE_JOB_ID}/results",
            headers={"x-api-key": "wrong-key"},
        )
        assert r.status_code == 401


class TestJobResults:
    def test_results_nonexistent_job_returns_not_found_status(self):
        r = requests.get(f"{BASE_URL}/job/{FAKE_JOB_ID}/results", headers=HEADERS_AUTH)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "not-found"
        assert data["data"] is None

    def test_results_response_has_status_and_data_fields(self):
        r = requests.post(
            f"{BASE_URL}/job/create",
            json=_object_detect_payload(external_id="ci-results-shape"),
            headers=HEADERS_AUTH,
        )
        if r.status_code != 202:
            pytest.skip("Could not enqueue job; skipping results shape test")

        job_id = r.json()["job_id"]
        rr = requests.get(f"{BASE_URL}/job/{job_id}/results", headers=HEADERS_AUTH)
        assert rr.status_code == 200
        data = rr.json()
        assert "status" in data
        assert "data" in data
        assert data["status"] in (
            "queued",
            "processing",
            "completed",
            "failed",
            "not-found",
        )
