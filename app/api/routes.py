"""API route handlers"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import APIKeyHeader
from app.core.utils import get_version
from app.core.config import API_KEY
from app.core.dependencies import job_manager
from app.models.result_models import (
    CreateJobRequest,
    CreateJobResponse,
    HealthResponse,
    JobResultsResponse,
    JobStatusResponse,
)
from app.models.schemas import JobStatus

logger = logging.getLogger(__name__)

router = APIRouter()

header_scheme = APIKeyHeader(name="x-api-key")


async def verify_api_key(key: Annotated[str, Depends(header_scheme)]) -> str:
    if key != API_KEY:
        logger.error(f"Invalid API key: {key}")
        raise HTTPException(status_code=401, detail=f"Invalid API key: {key}")
    return key


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["health"],
    operation_id="health_check",
)
async def health_check():
    """Health check endpoint"""
    try:
        if not job_manager.ping():
            raise RuntimeError("Celery is not reachable")

        all_jobs = job_manager.get_all_jobs()
        queued_jobs = len([j for j in all_jobs if j.status == "queued"])
        processing_jobs = len([j for j in all_jobs if j.status == "processing"])
        completed_jobs = len([j for j in all_jobs if j.status == "completed"])
        failed_jobs = len([j for j in all_jobs if j.status == "failed"])

        return {
            "version": get_version(),
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "job_stats": {
                "queued": queued_jobs,
                "processing": processing_jobs,
                "completed": completed_jobs,
                "failed": failed_jobs,
            },
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "version": get_version(),
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": "Health check failed",
            "job_stats": {"queued": 0, "processing": 0, "completed": 0, "failed": 0},
        }


@router.post(
    "/job/create",
    response_model=CreateJobResponse,
    status_code=202,
    operation_id="create_job",
    summary="Create a processing job (object_detect or scene_detect)",
    tags=["jobs"],
)
async def create_job(
    body: CreateJobRequest, key: Annotated[str, Depends(verify_api_key)]
):
    """Create a video processing job. The job_type field selects which
    processing pipeline to run, and params holds type-specific options."""

    try:
        all_jobs = job_manager.get_all_jobs()

        existing_jobs = [
            job
            for job in all_jobs
            if job.external_id == body.external_id and job.job_type == body.job_type
        ]

        active_jobs = [
            job for job in existing_jobs if job.status in ["queued", "processing"]
        ]
        if active_jobs:
            existing_job = active_jobs[0]
            logger.info(
                f"Returning existing active job {existing_job.job_id} for project {body.external_id}"
            )
            return {
                "job_id": existing_job.job_id,
                "job_type": existing_job.job_type,
                "status": existing_job.status,
                "queue_position": 1,
                "message": f"Project {body.external_id} already has an active job",
                "callback_url": existing_job.callback_url,
            }

        job_id = str(uuid.uuid4())

        job = JobStatus(
            job_id=job_id,
            external_id=body.external_id,
            video_url=body.video_url,
            job_type=body.job_type,
            callback_url=body.callback_url,
            params=body.params.model_dump(),
        )
        job.status = "queued"
        job.start_time = datetime.now()

        job_manager.enqueue_job(job)

        logger.info(
            f"Started {body.job_type} job {job_id} for project {body.external_id}"
        )
        if body.callback_url:
            logger.info(f"Callback URL configured: {body.callback_url}")

        return {
            "job_id": job_id,
            "job_type": body.job_type,
            "status": "queued",
            "queue_position": 1,
            "message": f"{body.job_type} job added to queue",
            "callback_url": body.callback_url,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating job: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/status/{job_id}",
    operation_id="get_job_status",
    response_model=JobStatusResponse,
    summary="Get the status of a job",
    tags=["status"],
)
async def get_job_status(job_id: str, _key: Annotated[str, Depends(verify_api_key)]):
    """Get the status of a processing job"""
    try:
        job = job_manager.get_job_from_celery(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        queue_position = 0
        estimated_wait_time = "00:00:00"

        if job.status == "queued":
            queued = job_manager.get_queued_jobs()
            match = next((q for q in queued if q["job_id"] == job_id), None)
            if match:
                queue_position = match["queue_position"]
                estimated_wait_time = match["estimated_wait_time"]

        return {
            "job_id": job.job_id,
            "external_id": job.external_id,
            "job_type": job.job_type,
            "status": job.status,
            "progress": job.progress,
            "queue_position": queue_position,
            "estimated_wait_time": estimated_wait_time,
            "start_time": job.start_time.isoformat() if job.start_time else None,
            "end_time": job.end_time.isoformat() if job.end_time else None,
            "error_message": job.error_message,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error getting job status: {str(e)}"
        )


@router.get(
    "/job/{job_id}/results",
    operation_id="get_job_results",
    response_model=JobResultsResponse,
    summary="Get the results of a completed job",
    tags=["results"],
)
async def get_job_results(job_id: str, _key: Annotated[str, Depends(verify_api_key)]):
    try:
        job = job_manager.get_job_from_celery(job_id)
        if not job:
            return {"status": "not-found", "data": None}

        if job.status == "failed":
            return {
                "status": "failed",
                "job_type": job.job_type,
                "data": None,
                "error_message": job.error_message or "Unknown error",
            }

        if job.status in ("queued", "processing"):
            return {"status": job.status, "job_type": job.job_type, "data": None}

        if not job.result_path or not os.path.exists(job.result_path):
            return {"status": "not-found", "data": None}

        with open(job.result_path) as f:
            result_data = json.load(f)

        return {
            "status": "completed",
            "job_type": job.job_type,
            "data": result_data,
        }

    except Exception as e:
        logger.error(f"Error reading results for job {job_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reading results: {str(e)}")
