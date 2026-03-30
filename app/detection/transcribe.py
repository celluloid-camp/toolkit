"""Transcription and speaker diarization pipeline.

Uses faster-whisper for ASR (CPU INT8) and pyannote.audio for speaker diarization.
Both models run fully self-hosted with no external API calls required.
"""

import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from inspect import signature
from typing import Callable, List, Optional
from urllib.parse import urlparse

from app.core.utils import download_file, ensure_dir

logger = logging.getLogger(__name__)


def _get_shared_models_root() -> str:
    """Return the shared models root directory.

    Priority:
    1) CELLULOID_MODELS_DIR env var
    2) /app/models (container default)
    3) local fallback next to this module
    """
    env_dir = os.getenv("CELLULOID_MODELS_DIR")
    if env_dir:
        try:
            ensure_dir(env_dir)
            return env_dir
        except Exception as exc:
            logger.warning(
                "Could not use CELLULOID_MODELS_DIR='%s': %s. Falling back.",
                env_dir,
                exc,
            )

    container_models_dir = "/app/models"
    if os.path.isdir(container_models_dir):
        try:
            ensure_dir(container_models_dir)
            return container_models_dir
        except Exception as exc:
            logger.warning(
                "Could not use container models dir '%s': %s. Falling back.",
                container_models_dir,
                exc,
            )

    fallback_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
    ensure_dir(fallback_dir)
    return fallback_dir


def _patch_torchaudio_audio_metadata() -> None:
    """Patch torchaudio API drift for pyannote 3.x compatibility."""
    try:
        import torchaudio  # type: ignore
    except Exception:
        return

    patched = False

    if not hasattr(torchaudio, "AudioMetaData"):

        @dataclass
        class _AudioMetaDataShim:
            sample_rate: int = 0
            num_frames: int = 0
            num_channels: int = 0
            bits_per_sample: int = 0
            encoding: str = ""

        setattr(torchaudio, "AudioMetaData", _AudioMetaDataShim)
        patched = True

    if not hasattr(torchaudio, "list_audio_backends"):

        def _list_audio_backends() -> List[str]:
            return ["soundfile"]

        setattr(torchaudio, "list_audio_backends", _list_audio_backends)
        patched = True

    if not hasattr(torchaudio, "get_audio_backend"):
        setattr(torchaudio, "_compat_audio_backend", "soundfile")

        def _get_audio_backend() -> str:
            return str(getattr(torchaudio, "_compat_audio_backend", "soundfile"))

        setattr(torchaudio, "get_audio_backend", _get_audio_backend)
        patched = True

    if not hasattr(torchaudio, "set_audio_backend"):

        def _set_audio_backend(backend: Optional[str]) -> None:
            if backend in (None, "soundfile", "ffmpeg", "sox"):
                setattr(torchaudio, "_compat_audio_backend", backend or "soundfile")
                return
            raise ValueError(f"Unsupported audio backend: {backend}")

        setattr(torchaudio, "set_audio_backend", _set_audio_backend)
        patched = True

    if not hasattr(torchaudio, "info"):

        def _info(uri, backend: Optional[str] = None):  # type: ignore[no-untyped-def]
            import soundfile as sf  # type: ignore

            details = sf.info(uri)
            return torchaudio.AudioMetaData(
                sample_rate=int(details.samplerate or 0),
                num_frames=int(details.frames or 0),
                num_channels=int(details.channels or 0),
                bits_per_sample=0,
                encoding=str(details.format or ""),
            )

        setattr(torchaudio, "info", _info)
        patched = True

    if patched:
        logger.info("Applied torchaudio compatibility shims for pyannote")


def _patch_huggingface_hub_auth_kwargs() -> None:
    """Map deprecated `use_auth_token` to `token` for new hub versions."""
    try:
        import huggingface_hub as hf  # type: ignore
    except Exception:
        return

    patched = False

    try:
        hf_download_params = signature(hf.hf_hub_download).parameters
        if "use_auth_token" not in hf_download_params:
            original_hf_download = hf.hf_hub_download

            def _hf_hub_download_compat(*args, **kwargs):  # type: ignore[no-untyped-def]
                if "use_auth_token" in kwargs and "token" not in kwargs:
                    kwargs["token"] = kwargs.pop("use_auth_token")
                else:
                    kwargs.pop("use_auth_token", None)
                return original_hf_download(*args, **kwargs)

            hf.hf_hub_download = _hf_hub_download_compat  # type: ignore[assignment]
            patched = True
    except Exception:
        pass

    try:
        snapshot_params = signature(hf.snapshot_download).parameters
        if "use_auth_token" not in snapshot_params:
            original_snapshot = hf.snapshot_download

            def _snapshot_download_compat(*args, **kwargs):  # type: ignore[no-untyped-def]
                if "use_auth_token" in kwargs and "token" not in kwargs:
                    kwargs["token"] = kwargs.pop("use_auth_token")
                else:
                    kwargs.pop("use_auth_token", None)
                return original_snapshot(*args, **kwargs)

            hf.snapshot_download = _snapshot_download_compat  # type: ignore[assignment]
            patched = True
    except Exception:
        pass

    if patched:
        logger.info("Applied huggingface_hub auth kwarg compatibility shims")


def _get_transcription_models_dir() -> str:
    """Return local models directory for transcription backends."""
    models_dir = os.path.join(_get_shared_models_root(), "whisper")
    ensure_dir(models_dir)
    return models_dir


def _get_pyannote_cache_dir() -> str:
    """Return local cache directory for pyannote checkpoints."""
    cache_dir = os.path.join(_get_shared_models_root(), "pyannote")
    ensure_dir(cache_dir)
    return cache_dir


def _prepare_diarization_input(audio_path: str) -> tuple[str, bool]:
    """Return a diarization-friendly audio path (mono 16k WAV).

    pyannote/torchaudio backends can fail to decode container formats like mp4
    depending on runtime codec support. We normalize to WAV for reliability.

    Returns:
        (path, should_cleanup)
    """
    ext = os.path.splitext(audio_path)[1].lower()
    if ext in {".wav", ".flac", ".ogg"}:
        return audio_path, False

    try:
        import ffmpeg  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "ffmpeg-python is required to convert media to WAV for diarization."
        ) from exc

    with tempfile.NamedTemporaryFile(
        prefix="pyannote_", suffix=".wav", delete=False
    ) as tmp:
        wav_path = tmp.name

    try:
        (
            ffmpeg.input(audio_path)
            .output(wav_path, ac=1, ar=16000, format="wav")
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True, quiet=True)
        )
        return wav_path, True
    except Exception as exc:
        try:
            os.remove(wav_path)
        except OSError:
            pass
        raise RuntimeError(
            f"Failed to prepare diarization audio from '{audio_path}': {exc}"
        )


def _resolve_faster_whisper_model(model_size: str) -> str:
    """Resolve a local faster-whisper model path, downloading once if needed."""
    if os.path.isdir(model_size):
        return model_size

    models_dir = _get_transcription_models_dir()
    local_model_dir = os.path.join(models_dir, f"faster-whisper-{model_size}")

    # Reuse existing local model if present.
    if os.path.isdir(local_model_dir) and os.listdir(local_model_dir):
        return local_model_dir

    try:
        from huggingface_hub import snapshot_download  # type: ignore
    except Exception:
        # Fallback: let faster-whisper handle download/caching.
        return model_size

    repo_id = f"Systran/faster-whisper-{model_size}"
    logger.info("Downloading Whisper model '%s' to %s", repo_id, local_model_dir)
    snapshot_download(repo_id=repo_id, local_dir=local_model_dir)
    return local_model_dir


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
    resolved_model = _resolve_faster_whisper_model(model_size)
    model = WhisperModel(resolved_model, device=device, compute_type=compute_type)

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
                "confidence": (
                    round(float(getattr(seg, "avg_logprob", None) or 0.0), 4)
                    if getattr(seg, "avg_logprob", None) is not None
                    else None
                ),
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
    _patch_torchaudio_audio_metadata()
    _patch_huggingface_hub_auth_kwargs()

    try:
        from pyannote.audio import Pipeline  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "pyannote.audio is required for speaker diarization. "
            "Install it with: pip install pyannote.audio"
        ) from exc

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    token = auth_token or os.getenv("PYANNOTE_AUTH_TOKEN") or os.getenv("HF_TOKEN")

    logger.info("Loading pyannote pipeline '%s'", model_name)
    try:
        from_pretrained_params = signature(Pipeline.from_pretrained).parameters
        load_kwargs: dict = {}

        if "cache_dir" in from_pretrained_params:
            load_kwargs["cache_dir"] = _get_pyannote_cache_dir()

        if token:
            if "token" in from_pretrained_params:
                load_kwargs["token"] = token
            else:
                load_kwargs["use_auth_token"] = token
        pipeline = Pipeline.from_pretrained(model_name, **load_kwargs)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load pyannote pipeline '{model_name}': {exc}. "
            "Make sure PYANNOTE_AUTH_TOKEN (or HF_TOKEN) is set and you have accepted the "
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
    diarization_input, cleanup_input = _prepare_diarization_input(audio_path)
    try:
        diarization = pipeline(diarization_input, **diarize_kwargs)
    finally:
        if cleanup_input:
            try:
                os.remove(diarization_input)
            except OSError:
                logger.warning(
                    "Could not remove temporary diarization file: %s", diarization_input
                )
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

    merged = merge_transcript_with_speakers(
        asr_result["segments"], diarization_segments
    )
    speakers = aggregate_speakers(merged)

    processing_time = round(time.time() - pipeline_start, 3)

    return {
        "metadata": {
            "engine": (
                "faster-whisper+pyannote" if diarization_segments else "faster-whisper"
            ),
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


def main() -> int:
    """CLI entry point for transcription + diarization."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Transcribe audio/video with faster-whisper + pyannote"
    )
    parser.add_argument("audio_url", help="URL or local path to an audio/video file")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: tmp next to this file)",
    )
    parser.add_argument(
        "--model-size",
        default="small",
        help="Whisper model size (default: small)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Force language code (default: auto-detect)",
    )
    parser.add_argument(
        "--disable-diarization",
        action="store_true",
        help="Run transcription without speaker diarization",
    )
    args = parser.parse_args()

    audio_url = args.audio_url
    tmp_dir = args.output_dir or os.path.join(os.getcwd(), "tmp")
    ensure_dir(tmp_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if audio_url.startswith(("http://", "https://")):
        filename = os.path.basename(urlparse(audio_url).path)
        if not filename or "." not in filename:
            filename = "audio.mp4"
        name, ext = os.path.splitext(filename)
        unique_filename = f"{name}_{timestamp}{ext}"
        audio_path = os.path.join(tmp_dir, unique_filename)
        print(f"Downloading media to: {audio_path}")
        download_file(audio_url, audio_path)
    else:
        audio_path = audio_url

    results = run_transcription_pipeline(
        audio_path=audio_path,
        model_size=args.model_size,
        language=args.language,
        diarization_enabled=not args.disable_diarization,
    )

    output_path = os.path.join(tmp_dir, f"transcription_{timestamp}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Transcription results saved to: {output_path}")
    return 0


if __name__ == "__main__":
    main()
