from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from backend.services.audio_service import AudioService


def _make_tone(path: Path, frequency: float, duration: float):
    """Generate a single-tone opus file."""
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"sine=frequency={frequency}:duration={duration}",
        "-c:a", "libopus", str(path),
    ], check=True, capture_output=True)


def _decode_to_pcm(path: Path) -> bytes:
    """Decode audio to raw PCM for content comparison."""
    result = subprocess.run([
        "ffmpeg", "-i", str(path),
        "-f", "s16le", "-acodec", "pcm_s16le",
        "-ar", "48000", "-ac", "1",
        "pipe:1",
    ], capture_output=True, check=True)
    return result.stdout


def test_split_chunk_creates_valid_file():
    """split_chunk creates an output file with correct duration."""
    service = AudioService()
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "test.opus"
        output_path = Path(tmpdir) / "chunks" / "chunk_000.opus"

        _make_tone(input_path, 440.0, 3.0)

        result = service.split_chunk(input_path, output_path, 1.0, 2.0)
        assert result.exists()
        assert result.stat().st_size > 0

        probe = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(output_path),
        ], capture_output=True, text=True)
        duration = float(probe.stdout.strip())
        assert abs(duration - 1.0) < 0.1


def test_split_chunk_validates_inputs():
    """split_chunk rejects invalid start/end values."""
    service = AudioService()
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "test.opus"
        output_path = Path(tmpdir) / "chunk.opus"

        _make_tone(input_path, 440.0, 3.0)

        with pytest.raises(ValueError, match="end must be > start"):
            service.split_chunk(input_path, output_path, 2.0, 1.0)
        with pytest.raises(ValueError, match="start must be >= 0"):
            service.split_chunk(input_path, output_path, -1.0, 1.0)


def test_split_chunks_contain_different_audio():
    """Each chunk contains distinct audio content, not a copy of the full file."""
    service = AudioService()
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "test.opus"

        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=2000:duration=1",
            "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1[out]",
            "-map", "[out]", "-c:a", "libopus", str(input_path),
        ], check=True, capture_output=True)

        chunk_a = Path(tmpdir) / "chunk_000.opus"
        chunk_b = Path(tmpdir) / "chunk_001.opus"
        chunk_c = Path(tmpdir) / "chunk_002.opus"

        service.split_chunk(input_path, chunk_a, 0.0, 1.0)
        service.split_chunk(input_path, chunk_b, 1.0, 2.0)
        service.split_chunk(input_path, chunk_c, 2.0, 3.0)

        pcm_a = _decode_to_pcm(chunk_a)
        pcm_b = _decode_to_pcm(chunk_b)
        pcm_c = _decode_to_pcm(chunk_c)

        assert pcm_a != pcm_b, "chunk_000 and chunk_001 should differ"
        assert pcm_b != pcm_c, "chunk_001 and chunk_002 should differ"
        assert pcm_a != pcm_c, "chunk_000 and chunk_002 should differ"


def test_split_chunk_reuses_existing_valid_chunk():
    """If a valid chunk already exists, split_chunk skips re-creation."""
    service = AudioService()
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "test.opus"
        output_path = Path(tmpdir) / "chunk.opus"

        _make_tone(input_path, 440.0, 3.0)

        service.split_chunk(input_path, output_path, 1.0, 2.0)
        original_mtime = output_path.stat().st_mtime_ns

        time.sleep(0.01)

        result = service.split_chunk(input_path, output_path, 1.0, 2.0)
        assert result == output_path
        assert output_path.stat().st_mtime_ns == original_mtime


def test_wait_for_chunk_raises_on_timeout():
    """_wait_for_chunk raises TimeoutError instead of returning an invalid chunk."""
    service = AudioService()
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "nonexistent.opus"

        with pytest.raises(TimeoutError, match="Timed out waiting for chunk creation"):
            service._wait_for_chunk(output_path, expected_duration=30.0, timeout=0.3)


def test_stale_lock_is_cleaned():
    """Lock file from a dead process is treated as stale and removed."""
    service = AudioService()
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "test.lock"

        lock_path.write_text(f"999999999:0.0")

        service._cleanup_stale_lock(lock_path, stale_seconds=0.0)
        assert not lock_path.exists()
