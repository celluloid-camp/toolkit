"""Unit tests for the transcription merge / alignment logic.

These tests exercise the pure-Python helpers in ``app.detection.transcribe``
without requiring any ML models or audio files.
"""

import importlib.util
import os
import sys

import pytest

# ---------------------------------------------------------------------------
# Load app.detection.transcribe directly to avoid triggering the heavy
# app.detection.__init__.py which requires cv2 / mediapipe etc.
# ---------------------------------------------------------------------------
_TRANSCRIBE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "detection", "transcribe.py"
)
_spec = importlib.util.spec_from_file_location("transcribe_module", _TRANSCRIBE_PATH)
_transcribe_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("transcribe_module", _transcribe_mod)
_spec.loader.exec_module(_transcribe_mod)

_overlap = _transcribe_mod._overlap
merge_transcript_with_speakers = _transcribe_mod.merge_transcript_with_speakers
aggregate_speakers = _transcribe_mod.aggregate_speakers


# ---------------------------------------------------------------------------
# _overlap helper
# ---------------------------------------------------------------------------


class TestOverlap:
    def test_no_overlap_before(self):
        assert _overlap(0.0, 1.0, 2.0, 3.0) == 0.0

    def test_no_overlap_after(self):
        assert _overlap(2.0, 3.0, 0.0, 1.0) == 0.0

    def test_touching_at_boundary(self):
        # Segments share a single point – zero-duration overlap
        assert _overlap(0.0, 1.0, 1.0, 2.0) == 0.0

    def test_partial_overlap(self):
        assert _overlap(0.0, 2.0, 1.0, 3.0) == pytest.approx(1.0)

    def test_full_containment(self):
        # b is fully inside a
        assert _overlap(0.0, 4.0, 1.0, 3.0) == pytest.approx(2.0)

    def test_identical_intervals(self):
        assert _overlap(1.5, 3.5, 1.5, 3.5) == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# merge_transcript_with_speakers
# ---------------------------------------------------------------------------


class TestMergeTranscriptWithSpeakers:
    def _seg(self, id, start, end, text="hello"):
        return {
            "id": id,
            "start": start,
            "end": end,
            "text": text,
            "confidence": 0.9,
            "words": None,
        }

    def _diar(self, start, end, speaker):
        return {"start": start, "end": end, "speaker": speaker}

    def test_empty_inputs(self):
        result = merge_transcript_with_speakers([], [])
        assert result == []

    def test_no_diarization_segments(self):
        asr = [self._seg(0, 0.0, 2.0)]
        result = merge_transcript_with_speakers(asr, [])
        assert len(result) == 1
        assert result[0]["speaker"] is None

    def test_exact_match(self):
        asr = [self._seg(0, 0.5, 3.0)]
        diar = [self._diar(0.5, 3.0, "SPEAKER_00")]
        result = merge_transcript_with_speakers(asr, diar)
        assert result[0]["speaker"] == "SPEAKER_00"

    def test_best_overlap_wins(self):
        asr = [self._seg(0, 0.0, 4.0)]
        diar = [
            self._diar(0.0, 1.0, "SPEAKER_00"),  # 1 s overlap
            self._diar(1.0, 4.0, "SPEAKER_01"),  # 3 s overlap – should win
        ]
        result = merge_transcript_with_speakers(asr, diar)
        assert result[0]["speaker"] == "SPEAKER_01"

    def test_gap_between_segments(self):
        # ASR segment falls in a gap between diarization segments
        asr = [self._seg(0, 2.0, 3.0)]
        diar = [
            self._diar(0.0, 1.5, "SPEAKER_00"),
            self._diar(3.5, 5.0, "SPEAKER_01"),
        ]
        result = merge_transcript_with_speakers(asr, diar)
        assert result[0]["speaker"] is None

    def test_crossing_boundaries(self):
        """ASR segment spans across a speaker change; best-overlap speaker wins."""
        asr = [self._seg(0, 0.0, 6.0)]
        diar = [
            self._diar(0.0, 4.0, "SPEAKER_00"),  # 4 s overlap
            self._diar(4.0, 8.0, "SPEAKER_01"),  # 2 s overlap
        ]
        result = merge_transcript_with_speakers(asr, diar)
        assert result[0]["speaker"] == "SPEAKER_00"

    def test_original_segment_not_mutated(self):
        asr = [self._seg(0, 0.0, 2.0)]
        original_keys = set(asr[0].keys())
        merge_transcript_with_speakers(asr, [self._diar(0.0, 2.0, "SPEAKER_00")])
        # Original dict must not gain the 'speaker' key
        assert set(asr[0].keys()) == original_keys

    def test_multiple_segments_multiple_speakers(self):
        asr = [
            self._seg(0, 0.0, 2.0, "Hello"),
            self._seg(1, 3.0, 5.0, "World"),
        ]
        diar = [
            self._diar(0.0, 2.5, "SPEAKER_00"),
            self._diar(2.5, 6.0, "SPEAKER_01"),
        ]
        result = merge_transcript_with_speakers(asr, diar)
        assert result[0]["speaker"] == "SPEAKER_00"
        assert result[1]["speaker"] == "SPEAKER_01"

    def test_preserves_all_original_fields(self):
        asr = [self._seg(0, 1.0, 3.0, "test")]
        diar = [self._diar(1.0, 3.0, "SPEAKER_00")]
        result = merge_transcript_with_speakers(asr, diar)
        seg = result[0]
        assert seg["id"] == 0
        assert seg["start"] == 1.0
        assert seg["end"] == 3.0
        assert seg["text"] == "test"
        assert seg["confidence"] == 0.9
        assert seg["words"] is None


# ---------------------------------------------------------------------------
# aggregate_speakers
# ---------------------------------------------------------------------------


class TestAggregateSpeakers:
    def test_empty_input(self):
        assert aggregate_speakers([]) == []

    def test_no_speaker_labels(self):
        segs = [{"start": 0.0, "end": 2.0, "text": "x", "speaker": None}]
        assert aggregate_speakers(segs) == []

    def test_single_speaker(self):
        segs = [
            {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"},
            {"start": 3.0, "end": 5.0, "speaker": "SPEAKER_00"},
        ]
        result = aggregate_speakers(segs)
        assert len(result) == 1
        assert result[0]["label"] == "SPEAKER_00"
        assert result[0]["total_speaking_time_sec"] == pytest.approx(4.0)

    def test_two_speakers(self):
        segs = [
            {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"},
            {"start": 3.5, "end": 5.5, "speaker": "SPEAKER_01"},
            {"start": 6.0, "end": 7.0, "speaker": "SPEAKER_00"},
        ]
        result = aggregate_speakers(segs)
        totals = {s["label"]: s["total_speaking_time_sec"] for s in result}
        assert totals["SPEAKER_00"] == pytest.approx(4.0)
        assert totals["SPEAKER_01"] == pytest.approx(2.0)

    def test_output_sorted_by_label(self):
        segs = [
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_02"},
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_00"},
            {"start": 2.0, "end": 3.0, "speaker": "SPEAKER_01"},
        ]
        result = aggregate_speakers(segs)
        labels = [s["label"] for s in result]
        assert labels == sorted(labels)

    def test_missing_speaker_key_skipped(self):
        """Segments without a 'speaker' key are tolerated and skipped."""
        segs = [
            {"start": 0.0, "end": 2.0},  # no speaker key
            {"start": 2.0, "end": 4.0, "speaker": "SPEAKER_00"},
        ]
        result = aggregate_speakers(segs)
        assert len(result) == 1
        assert result[0]["label"] == "SPEAKER_00"
