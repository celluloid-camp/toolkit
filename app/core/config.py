"""Application configuration and settings"""

import os
from dotenv import load_dotenv

load_dotenv()

# API Configuration
API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
API_VERSION = "1.0.1"

# Server Configuration
HOST = "0.0.0.0"
PORT = 8081

# Redis Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Processing Configuration
MAX_WORKERS = 1  # Only 1 worker since we process one job at a time

# Transcription Configuration
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", None)  # None = auto-detect

# Diarization Configuration
DIARIZATION_ENABLED = os.getenv("DIARIZATION_ENABLED", "true").lower() == "true"
PYANNOTE_AUTH_TOKEN = os.getenv("PYANNOTE_AUTH_TOKEN", None)
PYANNOTE_MODEL = os.getenv("PYANNOTE_MODEL", "pyannote/speaker-diarization-3.1")
