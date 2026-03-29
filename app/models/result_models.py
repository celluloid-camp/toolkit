import ipaddress
import os
from enum import Enum
from typing import Annotated, Literal, Optional, Union
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    Discriminator,
    Field,
    Tag,
    field_validator,
    model_validator,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class JobType(str, Enum):
    object_detect = "object_detect"
    scene_detect = "scene_detect"
    transcribe = "transcribe"


def _validate_video_url(v: str) -> str:
    result = urlparse(v)
    if (result.scheme in ("http", "https") and result.netloc) or os.path.exists(v):
        return v
    raise ValueError("video_url must be a valid URL or an existing file path")


def _validate_callback_url(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    result = urlparse(v)
    if result.scheme not in ("http", "https"):
        raise ValueError("callback_url must use http or https scheme")
    if not result.netloc:
        raise ValueError("callback_url must have a valid host")
    hostname = result.hostname
    if hostname is None:
        raise ValueError("callback_url must have a valid host")
    if hostname.lower() == "localhost":
        raise ValueError("callback_url must not point to a private or loopback address")
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
        ):
            raise ValueError(
                "callback_url must not point to a private or loopback address"
            )
    return v


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class JobStats(BaseModel):
    queued: int
    processing: int
    completed: int
    failed: int


class HealthResponse(BaseModel):
    version: str
    status: str
    timestamp: str
    job_stats: Optional[JobStats] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Job-type-specific parameter models
# ---------------------------------------------------------------------------


class ObjectDetectParams(BaseModel):
    similarity_threshold: float = Field(
        0.5, ge=0, le=1, description="Similarity threshold for object tracking"
    )
    analysis_fps: float = Field(
        1.0, gt=0, le=60, description="Frames per second to analyse (default 1)"
    )


class SceneDetectParams(BaseModel):
    threshold: float = Field(
        30.0, gt=0, description="Content detection sensitivity threshold"
    )


class TranscribeParams(BaseModel):
    model_size: str = Field(
        "small", description="Whisper model size (tiny, base, small, medium, large-v2, large-v3)"
    )
    device: str = Field("cpu", description="Inference device (cpu or cuda)")
    compute_type: str = Field(
        "int8", description="Quantisation type (int8, float16, float32)"
    )
    language: Optional[str] = Field(
        None, description="ISO-639-1 language code, or null for auto-detection"
    )
    diarization_enabled: bool = Field(
        True, description="Whether to run speaker diarization"
    )
    num_speakers: Optional[int] = Field(
        None, ge=1, description="Exact number of speakers (overrides min/max)"
    )
    min_speakers: Optional[int] = Field(
        None, ge=1, description="Minimum number of speakers hint"
    )
    max_speakers: Optional[int] = Field(
        None, ge=1, description="Maximum number of speakers hint"
    )


# ---------------------------------------------------------------------------
# Create-job request (single model, params validated by job_type)
# ---------------------------------------------------------------------------


class CreateJobRequest(BaseModel):
    job_type: JobType
    external_id: str = Field(..., description="Project identifier")
    video_url: str = Field(..., description="URL or path to video file")
    callback_url: Optional[str] = Field(
        None, description="Callback URL for job completion notifications"
    )
    params: Union[ObjectDetectParams, SceneDetectParams, TranscribeParams] = Field(
        default_factory=ObjectDetectParams
    )

    _validate_video_url = field_validator("video_url")(_validate_video_url)
    _validate_callback_url = field_validator("callback_url")(_validate_callback_url)

    @model_validator(mode="before")
    @classmethod
    def coerce_params_by_job_type(cls, data):
        """Parse params dict into the correct model based on job_type."""
        if not isinstance(data, dict):
            return data
        job_type = data.get("job_type")
        raw_params = data.get("params")
        if raw_params is None:
            raw_params = {}
        if isinstance(raw_params, dict):
            if job_type == "scene_detect":
                data["params"] = SceneDetectParams(**raw_params)
            elif job_type == "transcribe":
                data["params"] = TranscribeParams(**raw_params)
            else:
                data["params"] = ObjectDetectParams(**raw_params)
        return data


# ---------------------------------------------------------------------------
# Create-job response
# ---------------------------------------------------------------------------


class CreateJobResponse(BaseModel):
    job_id: str
    job_type: JobType
    status: str
    queue_position: int
    message: str
    callback_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Job status response
# ---------------------------------------------------------------------------


class JobStatusResponse(BaseModel):
    job_id: str
    external_id: str
    job_type: Optional[str] = None
    status: str
    progress: float
    queue_position: int = 0
    estimated_wait_time: str = "00:00:00"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Object-detect result models
# ---------------------------------------------------------------------------


class BoundingBoxModel(BaseModel):
    x: int
    y: int
    width: int
    height: int


class DetectionObjectModel(BaseModel):
    id: str
    class_name: str
    confidence: float
    bbox: BoundingBoxModel
    thumbnail: str


class DetectionFrameModel(BaseModel):
    frame_idx: int
    timestamp: float
    objects: list[DetectionObjectModel]


class VideoMetadataModel(BaseModel):
    fps: float
    frame_count: int
    width: int
    height: int
    source: str


class SpriteMetadataModel(BaseModel):
    url: str
    thumbnail_size: list[int]


class DetectionStatisticsModel(BaseModel):
    total_detections: Optional[int] = None
    person_detections: Optional[int] = None
    person_with_face: Optional[int] = None
    person_without_face: Optional[int] = None
    other_detections: Optional[int] = None
    class_counts: Optional[dict[str, int]] = None


class ProcessingMetadataModel(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    frames_processed: Optional[int] = None
    frames_with_detections: Optional[int] = None
    processing_speed: Optional[float] = None
    detection_statistics: Optional[DetectionStatisticsModel] = None


class ResultsMetadataModel(BaseModel):
    video: VideoMetadataModel
    sprite: SpriteMetadataModel
    processing: ProcessingMetadataModel


class DetectionResultsModel(BaseModel):
    result_type: Literal["object_detect"] = "object_detect"
    version: str
    metadata: ResultsMetadataModel
    frames: list[DetectionFrameModel]


# ---------------------------------------------------------------------------
# Scene-detect result models
# ---------------------------------------------------------------------------


class SceneInfoModel(BaseModel):
    scene_id: int
    start_time: str
    end_time: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    sprite_fragment: Optional[str] = None


class SceneDetectResultsModel(BaseModel):
    result_type: Literal["scene_detect"] = "scene_detect"
    total_scenes: int
    scenes: list[SceneInfoModel]
    sprite_url: Optional[str] = None
    sprite_fragments: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# Transcription result models
# ---------------------------------------------------------------------------


class WordModel(BaseModel):
    word: str
    start: float
    end: float
    probability: float


class TranscriptSegmentModel(BaseModel):
    id: int
    start: float
    end: float
    speaker: Optional[str] = None
    text: str
    confidence: Optional[float] = None
    words: Optional[list[WordModel]] = None


class SpeakerSummaryModel(BaseModel):
    label: str
    total_speaking_time_sec: float


class DiarizationSegmentModel(BaseModel):
    start: float
    end: float
    speaker: str


class TranscriptionMetadataModel(BaseModel):
    engine: str
    asr_backend: str = "faster-whisper"
    diarization_backend: Optional[str] = None
    device: str
    compute_type: str
    asr_model: str
    language: str
    audio_duration_sec: float
    processing_time_sec: float


class TranscribeResultsModel(BaseModel):
    result_type: Literal["transcribe"] = "transcribe"
    metadata: TranscriptionMetadataModel
    segments: list[TranscriptSegmentModel]
    speakers: list[SpeakerSummaryModel]
    diarization: list[DiarizationSegmentModel]


# ---------------------------------------------------------------------------
# Job results response (polymorphic data)
# ---------------------------------------------------------------------------


ResultData = Annotated[
    Union[
        Annotated[DetectionResultsModel, Tag("object_detect")],
        Annotated[SceneDetectResultsModel, Tag("scene_detect")],
        Annotated[TranscribeResultsModel, Tag("transcribe")],
    ],
    Discriminator("result_type"),
]


class JobResultsResponse(BaseModel):
    status: str
    job_type: Optional[str] = None
    data: Optional[ResultData] = None
    error_message: Optional[str] = None
