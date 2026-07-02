from __future__ import annotations

import itertools
import re
import subprocess
from pathlib import Path

from backend.models.segment import AtomicSegment
from backend.models.transcript import TranscriptChunk
from backend.utils.text_utils import split_sentences


HOOK_PATTERNS = [
    re.compile(r"^(what|how|why|when|where|who)\s"),
    re.compile(r"^did you know"),
    re.compile(r"^have you ever"),
    re.compile(r"^imagine"),
    re.compile(r"^here's the thing"),
    re.compile(r"^let me tell you"),
    re.compile(r"^the secret is"),
    re.compile(r"^nobody talks about"),
    re.compile(r"^question:"),
    re.compile(r"^challenge:"),
    re.compile(r"^problem:"),
    re.compile(r"^you need to know"),
    re.compile(r"^listen to this"),
]

ENDING_PATTERNS = [
    re.compile(r"(so that's|therefore|in summary|that's why|the takeaway is)"),
    re.compile(r"(subscribe|follow|like this|comment below|share this)"),
    re.compile(r"(next time|see you|thanks for watching|until next time)"),
]


class SegmentationService:
    def detect_pauses(self, audio_path: Path, min_pause_seconds: float = 0.5) -> list[float]:
        """Detect pause timestamps in audio using FFmpeg silencedetect."""
        cmd = [
            "ffmpeg", "-i", str(audio_path),
            "-af", f"silencedetect=noise=-30dB:d={min_pause_seconds}",
            "-f", "null", "-",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            return []

        pauses = []
        for line in result.stderr.split("\n"):
            if "silence_end" in line:
                try:
                    time_str = line.split("silence_end:")[1].split()[0]
                    pauses.append(float(time_str))
                except (IndexError, ValueError):
                    continue

        return sorted(pauses)

    def build_atomic_segments(
        self,
        chunks: list[TranscriptChunk],
        pauses: list[float] | None = None,
    ) -> list[AtomicSegment]:
        segments: list[AtomicSegment] = []
        counter = 0
        for chunk in chunks:
            sentences = split_sentences(chunk.text) or [chunk.text.strip()]
            if not sentences:
                continue
            span = max(chunk.end - chunk.start, 0.1)
            step = span / max(len(sentences), 1)
            for i, sentence in enumerate(sentences):
                seg_start = chunk.start + i * step
                seg_end = min(chunk.end, seg_start + step)
                kind = self._kind_for_text(sentence, i, len(sentences))
                segments.append(
                    AtomicSegment(
                        id=f"seg_{chunk.chunk_id}_{i}",
                        start=round(seg_start, 3),
                        end=round(seg_end, 3),
                        text=sentence,
                        kind=kind,
                        order=counter,
                    )
                )
                counter += 1

        segments = self._merge_small_segments(segments)
        return segments

    def _merge_small_segments(self, segments: list[AtomicSegment], min_duration: float = 1.2) -> list[AtomicSegment]:
        """Merge segments that are too short with their neighbor."""
        if not segments:
            return segments
        merged = []
        for seg in segments:
            duration = seg.end - seg.start
            if duration < min_duration and merged:
                prev = merged[-1]
                merged[-1] = AtomicSegment(
                    id=prev.id,
                    start=prev.start,
                    end=seg.end,
                    text=prev.text + " " + seg.text,
                    kind=prev.kind,
                    order=prev.order,
                    score=prev.score,
                    features=prev.features,
                )
            elif duration < min_duration and not merged and len(segments) > 1:
                next_seg = segments[1]
                next_seg.start = seg.start
                next_seg.text = seg.text + " " + next_seg.text
            else:
                merged.append(seg)
        return merged

    def _kind_for_text(self, text: str, idx: int, total: int) -> str:
        lower = text.lower()
        if idx == 0:
            for pattern in HOOK_PATTERNS:
                if pattern.search(lower):
                    return "hook"
            if any(word in lower for word in ["what", "how", "why", "imagine"]):
                return "hook"
        if idx == total - 1:
            for pattern in ENDING_PATTERNS:
                if pattern.search(lower):
                    return "ending"
            if any(word in lower for word in ["so", "therefore", "that is why", "in summary"]):
                return "ending"
        return "body"
