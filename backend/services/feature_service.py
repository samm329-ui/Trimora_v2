from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from backend.models.feature import SegmentFeatures
from backend.models.segment import AtomicSegment



class FeatureService:

    @staticmethod
    def extract_audio_energy(audio_path: Path, start: float, end: float) -> Optional[float]:
        """Extract RMS audio energy for a segment using ffprobe."""
        cmd = [
            "ffprobe", "-v", "error",
            "-ss", str(start),
            "-to", str(end),
            "-i", str(audio_path),
            "-af", "astats=metadata=1:reset=1",
            "-f", "null", "-",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            return None

        for line in result.stderr.split("\n"):
            if "Overall RMS" in line or "RMS_level" in line:
                try:
                    db_val = float(line.split("=")[1].strip().replace(" dB", ""))
                    return max(0.0, min(1.0, (db_val + 60) / 60))
                except (IndexError, ValueError):
                    continue
        return None

    def compute_features(
        self,
        segment: AtomicSegment,
        audio_path: Optional[Path] = None,
    ) -> SegmentFeatures:
        text = segment.text.strip()
        words = text.split()
        duration = max(segment.end - segment.start, 0.1)

        audio_intensity: float
        audio_energy: Optional[float] = None
        audio_energy_source: str = "text_heuristic"

        if audio_path and audio_path.exists():
            energy = self.extract_audio_energy(audio_path, segment.start, segment.end)
            if energy is not None:
                audio_energy = energy
                audio_energy_source = "real"
                audio_intensity = round(energy, 4)
            else:
                audio_intensity = round(min(1.0, max(0.05, len(text) / 200)), 4)
        else:
            audio_intensity = round(min(1.0, max(0.05, len(text) / 200)), 4)

        words_per_second = len(words) / duration
        text_density = round(min(1.0, max(0.05, words_per_second / 3.0)), 4)

        seg_duration = segment.end - segment.start
        if segment.kind == "hook":
            if seg_duration <= 5:
                structure_score = 0.9
            elif seg_duration <= 10:
                structure_score = 0.7
            else:
                structure_score = 0.5
        elif segment.kind == "ending":
            if seg_duration <= 8:
                structure_score = 0.85
            elif seg_duration <= 15:
                structure_score = 0.7
            else:
                structure_score = 0.5
        else:
            if 10 <= seg_duration <= 45:
                structure_score = 0.7
            elif 5 <= seg_duration <= 60:
                structure_score = 0.5
            else:
                structure_score = 0.3

        unique_ratio = len(set(words)) / max(len(words), 1)
        bonus = 0.0
        if "?" in text:
            bonus += 0.1
        if any(c.isdigit() for c in text):
            bonus += 0.05
        if len(words) <= 10:
            bonus += 0.05
        pattern_score = round(min(1.0, max(0.1, 0.4 + (unique_ratio * 0.5) + bonus)), 4)

        total_score = round(
            (audio_intensity + text_density + structure_score + pattern_score) / 4.0, 4
        )

        return SegmentFeatures(
            segment_id=segment.id,
            audio_intensity=audio_intensity,
            text_density=text_density,
            structure_score=round(structure_score, 4),
            pattern_score=pattern_score,
            total_score=total_score,
            audio_energy=audio_energy,
            audio_energy_source=audio_energy_source,
            extras={
                "word_count": float(len(words)),
                "duration_seconds": round(duration, 4),
            },
        )
