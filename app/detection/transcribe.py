"""Transcription and speaker diarization pipeline.

Uses faster-whisper for ASR (CPU INT8) and pyannote.audio for speaker diarization.
Both models run fully self-hosted with no external API calls required.
"""

import logging
import os
import time
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    """Return the duration of overlap between two time intervals."""
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def merge_transcript_with_speakers(
    asr_segments: List[dict],
    diarization_segments: List[dict],
) -> List[dict]:
    """Attach speaker labels to ASR segments using overlap-based matching.

    For each ASR segment the diarization segment with the greatest time overlap
    is selected and its speaker label is used.  If no diarization segment
    overlaps the ASR segment the speaker field is set to ``None``.

    Args:
        asr_segments: List of dicts with keys ``start``, ``end``, ``text``,
            ``confidence`` and optional ``words``.
        diarization_segments: List of dicts with keys ``start``, ``end``,
            ``speaker``.

    Returns:
        A new list of segment dicts that each include a ``speaker`` key.
    """
    merged: List[dict] = []
    for seg in asr_segments:
        best_speaker: Optional[str] = None
        best_overlap = 0.0
        for d_seg in diarization_segments:
            ov = _overlap(seg["start"], seg["end"], d_seg["start"], d_seg["end"])
            if ov > best_overlap:
                best_overlap = ov
                best_speaker = d_seg["speaker"]
        result = dict(seg)
        result["speaker"] = best_speaker
        merged.append(result)
    return merged


def aggregate_speakers(merged_segments: List[dict]) -> List[dict]:
    """Compute total speaking time per speaker from merged segments.

    Args:
        merged_segments: Output of :func:`merge_transcript_with_speakers`.

    Returns:
        List of dicts ``{"label": str, "total_speaking_time_sec": float}``
        sorted by label.
    """
    totals: dict[str, float] = {}
    for seg in merged_segments:
        speaker = seg.get("speaker")
        if speaker is None:
            continue
        duration = seg["end"] - seg["start"]
        totals[speaker] = totals.get(speaker, 0.0) + duration
    return [
        {"label": label, "total_speaking_time_sec": round(total, 3)}
        for label, total in sorted(totals.items())
    ]


# ---------------------------------------------------------------------------
# ASR: faster-whisper
# ---------------------------------------------------------------------------


def transcribe_audio(
    audio_path: str,
    model_size: str = "small",
    device: str = "cpu",
    compute_type: str = "int8",
    language: Optional[str] = None,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> dict:
    """Transcribe audio using faster-whisper on CPU.

    Args:
        audio_path: Path to the audio/video file to transcribe.
        model_size: Whisper model size (``tiny``, ``base``, ``small``,
            ``medium``, ``large-v2``, …).
        device: Inference device (``"cpu"`` or ``"cuda"``).
        compute_type: Quantisation type (e.g. ``"int8"``, ``"float16"``).
        language: ISO-639-1 language code, or ``None`` for auto-detection.
        progress_callback: Optional callable receiving a progress percentage
            (0–100).

    Returns:
        Dict with keys ``segments`` (list of segment dicts), ``language``
        (detected/forced language string) and ``audio_duration_sec`` (float).

    Raises:
        ImportError: If ``faster-whisper`` is not installed.
        FileNotFoundError: If ``audio_path`` does not exist.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "faster-whisper is required for transcription. "
            "Install it with: pip install faster-whisper"
        ) from exc

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    logger.info(
        "Loading Whisper model '%s' (device=%s, compute_type=%s)",
        model_size,
        device,
        compute_type,
    )
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    transcribe_kwargs: dict = {
        "word_timestamps": True,
    }
    if language:
        transcribe_kwargs["language"] = language

    logger.info("Starting transcription of %s", audio_path)
    t0 = time.time()
    raw_segments, info = model.transcribe(audio_path, **transcribe_kwargs)

    segments: List[dict] = []
    seg_list = list(raw_segments)  # materialise the generator
    total = len(seg_list) or 1
    for idx, seg in enumerate(seg_list):
        words = None
        if seg.words:
            words = [
                {
                    "word": w.word,
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "probability": round(w.probability, 4),
                }
                for w in seg.words
            ]
        segments.append(
            {
                "id": idx,
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip(),
                "confidence": round(float(getattr(seg, "avg_logprob", None) or 0.0), 4) if getattr(seg, "avg_logprob", None) is not None else None,
                "words": words,
            }
        )
        if progress_callback:
            progress_callback(min(95.0, (idx + 1) / total * 95.0))

    elapsed = time.time() - t0
    logger.info(
        "Transcription completed in %.1fs – %d segments, language=%s",
        elapsed,
        len(segments),
        info.language,
    )

    if progress_callback:
        progress_callback(100.0)

    return {
        "segments": segments,
        "language": info.language,
        "audio_duration_sec": round(info.duration or 0.0, 3),
    }


# ---------------------------------------------------------------------------
# Diarization: pyannote.audio
# ---------------------------------------------------------------------------


def diarize_audio(
    audio_path: str,
    auth_token: Optional[str] = None,
    model_name: str = "pyannote/speaker-diarization-3.1",
    num_speakers: Optional[int] = None,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
) -> List[dict]:
    """Run speaker diarization using pyannote.audio.

    Args:
        audio_path: Path to the audio/video file.
        auth_token: HuggingFace access token required to download the
            pyannote model on first use.  If ``None`` the value is read
            from the ``PYANNOTE_AUTH_TOKEN`` environment variable.
        model_name: pyannote pipeline identifier on the HuggingFace Hub.
        num_speakers: Exact number of speakers (overrides min/max).
        min_speakers: Minimum number of speakers hint.
        max_speakers: Maximum number of speakers hint.

    Returns:
        List of dicts with keys ``start``, ``end``, ``speaker``.

    Raises:
        ImportError: If ``pyannote.audio`` is not installed.
        FileNotFoundError: If ``audio_path`` does not exist.
        RuntimeError: If the pipeline cannot be loaded (e.g. missing token).
    """
    try:
        from pyannote.audio import Pipeline  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "pyannote.audio is required for speaker diarization. "
            "Install it with: pip install pyannote.audio"
        ) from exc

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    token = auth_token or os.getenv("PYANNOTE_AUTH_TOKEN")

    logger.info("Loading pyannote pipeline '%s'", model_name)
    try:
        pipeline = Pipeline.from_pretrained(model_name, use_auth_token=token)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load pyannote pipeline '{model_name}': {exc}. "
            "Make sure PYANNOTE_AUTH_TOKEN is set and you have accepted the "
            "model licence on huggingface.co."
        ) from exc

    diarize_kwargs: dict = {}
    if num_speakers is not None:
        diarize_kwargs["num_speakers"] = num_speakers
    else:
        if min_speakers is not None:
            diarize_kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            diarize_kwargs["max_speakers"] = max_speakers

    logger.info("Running speaker diarization on %s", audio_path)
    t0 = time.time()
    diarization = pipeline(audio_path, **diarize_kwargs)
    elapsed = time.time() - t0
    logger.info("Diarization completed in %.1fs", elapsed)

    segments: List[dict] = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append(
            {
                "start": round(turn.start, 3),
                "end": round(turn.end, 3),
                "speaker": speaker,
            }
        )
    return segments


# ---------------------------------------------------------------------------
# Combined pipeline
# ---------------------------------------------------------------------------


def run_transcription_pipeline(
    audio_path: str,
    model_size: str = "small",
    device: str = "cpu",
    compute_type: str = "int8",
    language: Optional[str] = None,
    diarization_enabled: bool = True,
    auth_token: Optional[str] = None,
    pyannote_model: str = "pyannote/speaker-diarization-3.1",
    num_speakers: Optional[int] = None,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> dict:
    """Run the full transcription + diarization pipeline.

    Executes ASR first (reports 0–70 % progress), then optionally diarization
    (70–90 %), then merges and aggregates (90–100 %).

    Args:
        audio_path: Path to the audio/video file.
        model_size: Whisper model size.
        device: Inference device.
        compute_type: Quantisation type.
        language: Forced language code, or ``None`` for auto-detection.
        diarization_enabled: Whether to run speaker diarization.
        auth_token: HuggingFace token for pyannote model.
        pyannote_model: pyannote pipeline identifier.
        num_speakers: Exact speaker count hint.
        min_speakers: Minimum speaker count hint.
        max_speakers: Maximum speaker count hint.
        progress_callback: Optional callable receiving progress 0–100.

    Returns:
        Dict matching the agreed output schema:
        ``{"metadata": {...}, "segments": [...], "speakers": [...],
           "diarization": [...]}``.
    """
    pipeline_start = time.time()

    def asr_progress(pct: float) -> None:
        if progress_callback:
            progress_callback(pct * 0.70)

    asr_result = transcribe_audio(
        audio_path,
        model_size=model_size,
        device=device,
        compute_type=compute_type,
        language=language,
        progress_callback=asr_progress,
    )

    diarization_segments: List[dict] = []
    if diarization_enabled:
        try:
            if progress_callback:
                progress_callback(70.0)
            diarization_segments = diarize_audio(
                audio_path,
                auth_token=auth_token,
                model_name=pyannote_model,
                num_speakers=num_speakers,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
            )
            if progress_callback:
                progress_callback(90.0)
        except Exception as exc:
            logger.warning(
                "Diarization failed – continuing with transcript only. Error: %s", exc
            )

    merged = merge_transcript_with_speakers(asr_result["segments"], diarization_segments)
    speakers = aggregate_speakers(merged)

    processing_time = round(time.time() - pipeline_start, 3)

    return {
        "metadata": {
            "engine": "faster-whisper+pyannote" if diarization_segments else "faster-whisper",
            "asr_backend": "faster-whisper",
            "diarization_backend": "pyannote" if diarization_segments else None,
            "device": device,
            "compute_type": compute_type,
            "asr_model": model_size,
            "language": asr_result["language"],
            "audio_duration_sec": asr_result["audio_duration_sec"],
            "processing_time_sec": processing_time,
        },
        "segments": merged,
        "speakers": speakers,
        "diarization": diarization_segments,
    }
