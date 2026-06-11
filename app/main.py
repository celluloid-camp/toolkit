"""Main FastAPI application"""

import json
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from scalar_fastapi import get_scalar_api_reference
from pydantic import BaseModel
from datetime import datetime

from app.api.routes import router
from app.core.dependencies import job_manager
from app.core.utils import get_version, get_log_level

# Set up logging (level from LOG_LEVEL env, default INFO)
logging.basicConfig(level=get_log_level())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    api_key = os.getenv("API_KEY")
    logger.info(
        "Starting up FastAPI web service with Celery... API key configured: %s",
        "Yes" if api_key else "No",
    )

    # Create output directory
    os.makedirs("outputs", exist_ok=True)

    # Test Redis connection
    try:
        job_manager.ping()
        logger.info("Connected to Redis")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        raise

    # Clean up stale jobs
    job_manager.cleanup_stale_jobs()

    # Save OpenAPI schema to file
    openapi_path = os.getenv("OPENAPI_JSON_PATH", "openapi.json")
    try:
        with open(openapi_path, "w") as f:
            json.dump(app.openapi(), f, indent=2)
        logger.info("OpenAPI schema saved to %s", openapi_path)
    except Exception as e:
        logger.warning("Failed to save OpenAPI schema: %s", e)

    yield

    # Shutdown
    logger.info("Shutting down FastAPI web service...")


tags_metadata = [
    {
        "name": "analysis",
        "description": "Operations with video analysis.",
    },
    {
        "name": "health",
        "description": "Health check operations.",
    },
    {
        "name": "status",
        "description": "Status check operations.",
    },
    {
        "name": "results",
        "description": "Results operations.",
    },
    {
        "name": "webhooks",
        "description": "Webhook operations.",
    },
]

# Create FastAPI app
app = FastAPI(
    title="Celluloid Toolkit API",
    version=get_version(),
    lifespan=lifespan,
    openapi_tags=tags_metadata,
    root_path="/",
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)

# Serve the outputs directory as static files
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")


# Webhook model for documentation
class JobCompletedWebhook(BaseModel):
    job_id: str
    external_id: str
    job_type: str
    status: str
    timestamp: datetime


@app.webhooks.post("job-completed", tags=["webhooks"])
def job_completed(body: JobCompletedWebhook):
    """
    When a job is completed, we'll send you a POST request with this
    data to the URL that you register for the event `job-completed` in the dashboard.
    """


@app.get("/", include_in_schema=False)
async def scalar_html():
    """API documentation"""
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )
