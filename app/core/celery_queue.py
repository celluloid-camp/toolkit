"""Celery-based job manager relying on Celery APIs only."""

import ast
import logging
from datetime import datetime
from typing import List, Optional

from celery.result import AsyncResult

from app.core.celery_app import CELERY_QUEUE_NAME, celery_app
from app.models.schemas import JobStatus

logger = logging.getLogger(__name__)

ESTIMATED_MINUTES_PER_JOB = 5

TASK_NAME_BY_JOB_TYPE = {
    "object_detect": "app.core.tasks.process_object_detect_task",
    "scene_detect": "app.core.tasks.process_scene_detect_task",
    "transcribe": "app.core.tasks.process_transcribe_task",
}


class CeleryJobManager:
    def __init__(self, queue_name: str = CELERY_QUEUE_NAME):
        """Initialize Celery job manager."""
        self.queue_name = queue_name
        logger.info("Initialized Celery job manager with queue: %s", queue_name)

    def ping(self) -> bool:
        """Test connectivity through Celery control API."""
        try:
            response = celery_app.control.ping(timeout=1.0)
            return bool(response)
        except Exception:
            return False

    def _extract_job_data(self, task: dict) -> dict:
        """Extract first positional arg dict from Celery inspect task payload."""
        args = task.get("args")
        if isinstance(args, (list, tuple)) and args and isinstance(args[0], dict):
            return args[0]
        if isinstance(args, str) and args:
            try:
                parsed = ast.literal_eval(args)
                if (
                    isinstance(parsed, (list, tuple))
                    and parsed
                    and isinstance(parsed[0], dict)
                ):
                    return parsed[0]
            except Exception:
                return {}
        return {}

    def _job_from_payload(
        self, job_id: str, payload: dict, status: str, progress: float = 0.0
    ) -> JobStatus:
        job = JobStatus(
            job_id=job_id,
            external_id=payload.get("external_id", "unknown"),
            video_url=payload.get("video_url", "unknown"),
            job_type=payload.get("job_type", "object_detect"),
            callback_url=payload.get("callback_url"),
            params=payload.get("params"),
        )
        job.status = status
        job.progress = progress
        return job

    def _inspect_tasks(self) -> tuple[list[dict], list[dict], list[dict]]:
        """Return (active, reserved, scheduled) task lists from Celery inspect."""
        inspector = celery_app.control.inspect(timeout=1.0)
        active = [t for tasks in (inspector.active() or {}).values() for t in tasks]
        reserved = [t for tasks in (inspector.reserved() or {}).values() for t in tasks]
        scheduled = [
            t for tasks in (inspector.scheduled() or {}).values() for t in tasks
        ]
        return active, reserved, scheduled

    def get_job_from_celery(self, job_id: str) -> Optional[JobStatus]:
        """Get job status from Celery task state and inspect output."""
        try:
            result = AsyncResult(job_id, app=celery_app)
            celery_state = result.state

            if celery_state in ("STARTED", "PROCESSING"):
                task_info = result.info if isinstance(result.info, dict) else {}
                job = self._job_from_payload(
                    job_id=job_id,
                    payload=task_info,
                    status="processing",
                    progress=float(task_info.get("progress", 0.0)),
                )
                if task_info.get("start_time"):
                    job.start_time = datetime.fromisoformat(task_info["start_time"])
                return job

            if celery_state == "SUCCESS":
                task_result = result.result if isinstance(result.result, dict) else {}
                job = self._job_from_payload(
                    job_id=job_id,
                    payload=task_result,
                    status="completed",
                    progress=100.0,
                )
                job.result_path = task_result.get("result_path")
                job.metadata = task_result.get("metadata", {})
                if task_result.get("start_time"):
                    job.start_time = datetime.fromisoformat(task_result["start_time"])
                if task_result.get("end_time"):
                    job.end_time = datetime.fromisoformat(task_result["end_time"])
                return job

            if celery_state == "FAILURE":
                info = result.info if isinstance(result.info, dict) else {}
                job = self._job_from_payload(
                    job_id=job_id, payload=info, status="failed", progress=0.0
                )
                job.error_message = str(result.result) if result.result else None
                return job

            if celery_state == "REVOKED":
                job = self._job_from_payload(
                    job_id=job_id, payload={}, status="failed", progress=0.0
                )
                job.error_message = "Task revoked"
                return job

            # PENDING can mean queued or unknown; inspect queue/worker tasks to decide.
            active, reserved, scheduled = self._inspect_tasks()
            for task in active:
                if task.get("id") == job_id:
                    payload = self._extract_job_data(task)
                    return self._job_from_payload(job_id, payload, "processing")
            for task in reserved + scheduled:
                if task.get("id") == job_id:
                    payload = self._extract_job_data(task)
                    return self._job_from_payload(job_id, payload, "queued")

            return None
        except Exception as e:
            logger.error("Error getting job %s from Celery: %s", job_id, str(e))
            return None

    def save_job_to_celery(self, job: JobStatus):
        """Compatibility no-op (Celery is source of truth)."""
        logger.debug("save_job_to_celery no-op for job %s", job.job_id)

    def get_all_jobs(self) -> List[JobStatus]:
        """Get all visible queued/processing jobs from Celery inspect APIs."""
        jobs: list[JobStatus] = []
        try:
            active, reserved, scheduled = self._inspect_tasks()

            for task in active:
                payload = self._extract_job_data(task)
                job_id = task.get("id")
                if job_id:
                    jobs.append(self._job_from_payload(job_id, payload, "processing"))

            for task in reserved + scheduled:
                payload = self._extract_job_data(task)
                job_id = task.get("id")
                if job_id:
                    jobs.append(self._job_from_payload(job_id, payload, "queued"))
        except Exception as e:
            logger.error("Error getting all jobs: %s", str(e))
        return jobs

    def cleanup_stale_jobs(self):
        """Compatibility no-op (no Redis job registry)."""
        logger.info("No stale job cleanup required (Celery-only mode).")

    def get_queue_status_info(self):
        """Get current queue status from Celery inspect APIs."""
        try:
            active, reserved, scheduled = self._inspect_tasks()
            current_job_id = active[0]["id"] if active else None
            queue_length = len(reserved) + len(scheduled)
            return {
                "queue_length": queue_length,
                "current_job": current_job_id,
                "failed_count": 0,
                "finished_count": 0,
            }
        except Exception as e:
            logger.error("Error getting queue status: %s", str(e))
            return {
                "queue_length": 0,
                "current_job": None,
                "failed_count": 0,
                "finished_count": 0,
            }

    def enqueue_job(self, job: JobStatus):
        """Enqueue a job to the Celery queue, routing to the correct task."""
        try:
            task_name = TASK_NAME_BY_JOB_TYPE.get(job.job_type)
            if not task_name:
                raise ValueError(f"Unknown job_type: {job.job_type}")

            job_data = {
                "job_id": job.job_id,
                "external_id": job.external_id,
                "video_url": job.video_url,
                "job_type": job.job_type,
                "callback_url": job.callback_url,
                "params": job.params,
            }

            result = celery_app.send_task(
                task_name,
                args=[job_data],
                task_id=job.job_id,
                queue=self.queue_name,
            )

            logger.info(
                "Enqueued %s job %s to Celery queue %s",
                job.job_type,
                job.job_id,
                self.queue_name,
            )
            return result
        except Exception as e:
            logger.error("Error enqueueing job %s: %s", job.job_id, str(e))
            raise

    def delete_job(self, job_id: str):
        """Delete a job from Celery backend."""
        try:
            result = AsyncResult(job_id, app=celery_app)
            result.forget()
            logger.info("Deleted job %s", job_id)
        except Exception as e:
            logger.warning("Could not delete job %s: %s", job_id, str(e))

    def cancel_job(self, job_id: str):
        """Cancel a queued or running job."""
        try:
            result = AsyncResult(job_id, app=celery_app)
            result.revoke(terminate=True)
            logger.info("Cancelled job %s", job_id)
        except Exception as e:
            logger.warning("Could not cancel job %s: %s", job_id, str(e))

    def get_queued_jobs(self):
        """Get list of queued jobs with estimated wait time."""
        queued_jobs = []
        try:
            jobs = self.get_all_jobs()
            queued = [j for j in jobs if j.status == "queued"]

            for i, job in enumerate(queued):
                wait_seconds = (i + 1) * ESTIMATED_MINUTES_PER_JOB * 60
                h = wait_seconds // 3600
                m = (wait_seconds % 3600) // 60
                s = wait_seconds % 60
                queued_jobs.append(
                    {
                        "job_id": job.job_id,
                        "external_id": job.external_id,
                        "queue_position": i + 1,
                        "estimated_wait_time": f"{h:02d}:{m:02d}:{s:02d}",
                    }
                )
        except Exception as e:
            logger.error("Error getting queued jobs: %s", str(e))
        return queued_jobs

    def clean_queue(self):
        """Purge all pending tasks from the Celery queue."""
        try:
            celery_app.control.purge()
            logger.info("Celery queue cleaned.")
        except Exception as e:
            logger.error("Error cleaning Celery queue: %s", str(e))
