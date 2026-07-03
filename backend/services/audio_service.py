from __future__ import annotations

import json
import math
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from backend.config.settings import settings
from backend.utils.audio_utils import build_chunk_plan


class AudioService:
    def pre_check_audio(self, video_path: Path) -> dict:
        """Analyze audio before processing."""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "stream=codec_name,sample_rate,channels",
            "-show_entries", "format=duration,size",
            "-of", "json",
            str(video_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            return {"has_audio": False, "duration": 0.0}

        audio_stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "audio"),
            None
        )

        return {
            "duration": float(data.get("format", {}).get("duration", 0)),
            "sample_rate": int(audio_stream.get("sample_rate", 0)) if audio_stream else 0,
            "channels": int(audio_stream.get("channels", 0)) if audio_stream else 0,
            "has_audio": audio_stream is not None,
        }

    def detect_silence_ratio(self, audio_path: Path, silence_threshold: float = -30) -> float:
        """Detect ratio of silence in audio file (0.0 = no silence, 1.0 = all silence)."""
        cmd = [
            "ffmpeg", "-i", str(audio_path),
            "-af", f"silencedetect=noise={silence_threshold}dB:d=0.5",
            "-f", "null", "-",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError:
            return 0.0

        total_silence = 0.0
        duration = 0.0
        for line in result.stderr.split("\n"):
            if "silence_duration" in line:
                try:
                    total_silence += float(line.split("silence_duration:")[1].split()[0])
                except (IndexError, ValueError):
                    continue
            elif "Duration" in line and "start" in line:
                parts = line.strip().split(",")
                for p in parts:
                    if "Duration" in p:
                        time_str = p.split("Duration:")[1].strip()
                        h, m, s = time_str.split(":")
                        duration = int(h) * 3600 + int(m) * 60 + float(s)

        if duration <= 0:
            return 0.0
        return min(1.0, total_silence / duration)

    def check_ffmpeg_available(self) -> bool:
        """Check if ffmpeg and ffprobe are available on the system."""
        for binary in ("ffmpeg", "ffprobe"):
            try:
                subprocess.run(
                    [binary, "-version"],
                    capture_output=True,
                    check=True,
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                return False
        return True

    def extract_audio(self, video_path: Path, audio_path: Path) -> Path:
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-c:a", "libopus",
            "-b:a", "64k",
            "-f", "ogg",
            str(audio_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return audio_path
        except FileNotFoundError:
            raise RuntimeError(
                "ffmpeg is not installed or not in PATH. "
                "Install ffmpeg and ensure it is accessible from the command line."
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Audio extraction failed: {e.stderr.decode()}") from e

    def probe_duration(self, video_path: Path) -> float:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(video_path),
        ]
        try:
            out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()
            return float(out)
        except FileNotFoundError:
            raise RuntimeError(
                "ffprobe is not installed or not in PATH. "
                "Install ffmpeg (includes ffprobe) and ensure it is accessible from the command line."
            )
        except (subprocess.CalledProcessError, ValueError) as e:
            raise RuntimeError(f"Audio probing failed: {e}") from e

    def plan_chunks(self, duration_seconds: float, speech_density: float = 0.5):
        return build_chunk_plan(duration_seconds, speech_density)

    def _validate_chunk(self, chunk_path: Path, expected_duration: float, tolerance: float = 0.5) -> bool:
        """Verify a chunk file is valid audio with correct duration."""
        if not chunk_path.exists() or chunk_path.stat().st_size == 0:
            return False
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(chunk_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration = float(result.stdout.strip())
            return abs(duration - expected_duration) < tolerance
        except (subprocess.CalledProcessError, ValueError):
            return False

    def _cleanup_stale_lock(self, lock_path: Path, stale_seconds: float = 30.0) -> None:
        """Remove a lock file if it is older than stale_seconds.

        Portable approach: relies on timestamp only, no os.kill().
        If the lock file is older than stale_seconds, it is assumed stale
        regardless of PID — the owning process is either dead or irrelevant.
        """
        if not lock_path.exists():
            return
        try:
            content = lock_path.read_text(encoding="utf-8").strip()
            parts = content.split(":")
            timestamp = float(parts[1])
            if time.monotonic() - timestamp > stale_seconds:
                lock_path.unlink(missing_ok=True)
        except (ValueError, IndexError, OSError):
            lock_path.unlink(missing_ok=True)

    def _acquire_lock(self, lock_path: Path, stale_seconds: float = 30.0) -> bool:
        """Atomically try to acquire a lock file. Cleans up stale locks from crashed processes."""
        self._cleanup_stale_lock(lock_path, stale_seconds)
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}:{time.monotonic()}".encode())
            os.close(fd)
            return True
        except FileExistsError:
            return False

    def _wait_for_chunk(self, output_path: Path, expected_duration: float, timeout: float = 5.0) -> Path:
        """Wait for another worker to finish creating this chunk.

        Raises TimeoutError if the chunk is not created within the timeout.
        Never returns an invalid or missing chunk.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._validate_chunk(output_path, expected_duration):
                return output_path
            time.sleep(0.1)

        raise TimeoutError(
            f"Timed out waiting for chunk creation: {output_path} "
            f"(expected duration={expected_duration:.1f}s, timeout={timeout}s)"
        )

    def split_chunk(self, audio_path: Path, output_path: Path, start: float, end: float, bitrate: str = "64k") -> Path:
        """Extract a segment from audio into a physical chunk file.

        Concurrency-safe: uses atomic lock files with stale-lock detection.
        Idempotent: reuses validated existing chunks on retry.
        """
        if start < 0:
            raise ValueError(f"start must be >= 0, got {start}")
        if end <= start:
            raise ValueError(f"end must be > start, got end={end} <= start={start}")

        expected_duration = max(0.0, end - start)

        if self._validate_chunk(output_path, expected_duration):
            return output_path

        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = output_path.with_suffix(".tmp")
        lock_path = output_path.with_suffix(".lock")

        if not self._acquire_lock(lock_path):
            return self._wait_for_chunk(output_path, expected_duration)

        try:
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-i", str(audio_path),
                "-t", str(expected_duration),
                "-c:a", "libopus",
                "-b:a", bitrate,
                "-f", "ogg",
                str(tmp_path),
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True)
            except FileNotFoundError:
                raise RuntimeError(
                    "ffmpeg is not installed or not in PATH. "
                    "Install ffmpeg and ensure it is accessible from the command line."
                )
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Chunk splitting failed: {e.stderr.decode()}") from e

            if not self._validate_chunk(tmp_path, expected_duration):
                tmp_path.unlink(missing_ok=True)
                raise RuntimeError(f"Chunk validation failed after split: {tmp_path}")

            tmp_path.replace(output_path)
            return output_path
        finally:
            lock_path.unlink(missing_ok=True)
