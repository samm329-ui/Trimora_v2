# backend/services/adaptive_windows.py

from dataclasses import dataclass
from backend.core.artifact import Artifact, ArtifactStage, create_artifact
from backend.core.context import ExecutionContext
from backend.models.data import TranscriptData, SignalData


@dataclass(frozen=True)
class WindowConfig:
    min_duration: float = 15.0
    max_duration: float = 120.0
    preferred_min: float = 45.0
    preferred_max: float = 90.0


class AdaptiveWindowSplitter:
    def __init__(self, config: WindowConfig = None):
        self.config = config or WindowConfig()

    async def execute(self, inputs: dict) -> Artifact[SignalData]:
        artifact = inputs.get("transcript") or inputs.get(list(inputs.keys())[0]) if inputs else None
        if artifact is None:
            raise ValueError("AdaptiveWindowSplitter requires a transcript artifact")
        transcript = artifact.data

        segments = self._split_into_windows(transcript.segments)
        audio_signals = self._extract_audio_signals(segments)
        text_signals = self._extract_text_signals(segments)

        output_data = SignalData(
            segments=segments, audio_signals=audio_signals,
            text_signals=text_signals,
            signal_count=len(segments) + len(audio_signals) + len(text_signals),
        )
        return create_artifact(data=output_data, stage=ArtifactStage.SIGNALS, parent=artifact)

    def _split_into_windows(self, segments: list) -> list:
        windows = []
        current_window = []
        current_duration = 0.0

        for seg in segments:
            seg_duration = seg.get("end", 0) - seg.get("start", 0)
            if current_duration + seg_duration > self.config.max_duration and current_window:
                windows.append({
                    "segments": current_window,
                    "start": current_window[0].get("start", 0),
                    "end": current_window[-1].get("end", 0),
                    "duration": current_duration,
                })
                current_window = []
                current_duration = 0.0
            current_window.append(seg)
            current_duration += seg_duration

        if current_window:
            windows.append({
                "segments": current_window,
                "start": current_window[0].get("start", 0),
                "end": current_window[-1].get("end", 0),
                "duration": current_duration,
            })
        return windows

    def _extract_audio_signals(self, segments: list) -> list:
        return [{"segment_id": s.get("id"), "energy": 0.5, "pace": 2.5} for s in segments]

    def _extract_text_signals(self, segments: list) -> list:
        return [{"segment_id": s.get("id"), "text": s.get("text", ""),
                 "word_count": len(s.get("text", "").split())} for s in segments]
