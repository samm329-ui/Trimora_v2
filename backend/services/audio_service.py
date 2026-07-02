from __future__ import annotations

import json
import math
import subprocess
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
    def extract_audio(self, video_path: Path, audio_path: Path) -> Path:
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "copy",
            str(audio_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return audio_path
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
        except (subprocess.CalledProcessError, ValueError) as e:
            raise RuntimeError(f"Audio probing failed: {e}") from e

    def plan_chunks(self, duration_seconds: float, speech_density: float = 0.5):
        return build_chunk_plan(duration_seconds, speech_density)
