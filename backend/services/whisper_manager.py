from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    import torch

    _HAVE_TORCH = True
except ImportError:
    _HAVE_TORCH = False

try:
    from faster_whisper import WhisperModel

    _HAVE_FASTER_WHISPER = True
except ImportError:
    _HAVE_FASTER_WHISPER = False


@dataclass
class WhisperRuntimeInfo:
    provider: str
    model: str
    device: str
    compute_type: str
    workers: int
    cpu_cores: int = 0


class WhisperManager:
    """Process-wide singleton. Loads the Faster-Whisper model once and owns its lifetime."""

    _instance: WhisperManager | None = None
    _class_lock = threading.Lock()

    def __new__(cls) -> WhisperManager:
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._model: WhisperModel | None = None
        self._device: str = "cpu"
        self._model_size: str = "small"
        self._compute_type: str = "int8"
        self._workers: int = 1
        self._load_lock = threading.Lock()
        self._job_language: dict[str, str] = {}
        self._language_lock = threading.Lock()
        self._configure()

    def _configure(self) -> None:
        """Detect hardware and select model/compute/workers."""
        from backend.config.settings import settings

        model_override = os.getenv("WHISPER_MODEL_SIZE", "")
        device_override = os.getenv("WHISPER_DEVICE", "")
        compute_override = os.getenv("WHISPER_COMPUTE_TYPE", "")

        if device_override and device_override != "auto":
            self._device = device_override
        elif _HAVE_TORCH and torch.cuda.is_available():
            self._device = "cuda"
        else:
            self._device = "cpu"

        # If device is set to cuda but CUDA is not available, fail fast
        if self._device == "cuda" and not (_HAVE_TORCH and torch.cuda.is_available()):
            raise RuntimeError(
                "CUDA requested but not available. "
                "Ensure PyTorch with CUDA support is installed and a GPU is accessible. "
                "Set WHISPER_DEVICE=cpu to use CPU mode instead."
            )

        total_vram_gb = self._get_total_vram_gb()

        if self._device == "cuda" and total_vram_gb > 0:
            usable_vram = total_vram_gb * 0.80
            self._model_size, self._compute_type, model_mem = self._select_model_gpu(
                usable_vram, model_override, compute_override
            )
            self._workers = max(1, int(usable_vram / (model_mem + 0.5)))
        else:
            self._model_size = (
                model_override
                if model_override and model_override != "auto"
                else getattr(settings, "whisper_model_size", "small")
                if getattr(settings, "whisper_model_size", "auto") != "auto"
                else "small"
            )
            self._compute_type = (
                compute_override
                if compute_override and compute_override != "auto"
                else getattr(settings, "whisper_compute_type", "int8")
                if getattr(settings, "whisper_compute_type", "auto") != "auto"
                else "int8"
            )
            self._workers = 1

        logger.info(
            "WhisperManager: model=%s device=%s compute_type=%s workers=%d (vram=%.1fGB)",
            self._model_size,
            self._device,
            self._compute_type,
            self._workers,
            total_vram_gb,
        )

    def _get_total_vram_gb(self) -> float:
        if not (_HAVE_TORCH and torch.cuda.is_available()):
            return 0.0
        try:
            props = torch.cuda.get_device_properties(0)
            return props.total_mem / (1024**3)
        except Exception:
            return 0.0

    def _select_model_gpu(
        self, usable_vram_gb: float, model_override: str, compute_override: str
    ) -> tuple[str, str, float]:
        if model_override and model_override != "auto":
            compute = (
                compute_override
                if compute_override and compute_override != "auto"
                else "float16"
            )
            mem_map = {
                "tiny": 0.15,
                "base": 0.3,
                "small": 0.6,
                "medium": 1.6,
                "large-v2": 3.0,
                "large-v3": 3.0,
                "large-v3-turbo": 1.7,
            }
            return model_override, compute, mem_map.get(model_override, 1.6)

        candidates = [
            ("large-v3", "float16", 3.0),
            ("large-v3-turbo", "float16", 1.7),
            ("medium", "float16", 1.6),
            ("small", "int8", 0.6),
            ("base", "int8", 0.3),
            ("tiny", "int8", 0.15),
        ]
        for model, compute, mem in candidates:
            if mem <= usable_vram_gb:
                return model, compute, mem
        return "tiny", "int8", 0.15

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            if not _HAVE_FASTER_WHISPER:
                raise RuntimeError(
                    "faster-whisper is not installed. Run: pip install faster-whisper"
                )
            logger.info(
                "Loading Faster-Whisper model: %s on %s (%s)",
                self._model_size,
                self._device,
                self._compute_type,
            )
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
            self._warmup()
            logger.info("Faster-Whisper model loaded successfully.")

    def _warmup(self) -> None:
        if self._model is None:
            return
        try:
            import numpy as np

            dummy = np.zeros(8000, dtype=np.float32)
            list(self._model.transcribe(dummy, beam_size=1, language="en"))
            logger.debug("Warm-up pass completed.")
        except Exception as e:
            logger.debug("Warm-up pass skipped: %s", e)

    def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
        vad_filter: bool = True,
        job_id: str | None = None,
    ) -> list[dict]:
        """Transcribe an audio file. Returns list of {"start", "end", "text"} dicts."""
        self._ensure_loaded()
        assert self._model is not None

        from backend.config.settings import settings

        effective_language = language
        if effective_language is None and job_id and job_id in self._job_language:
            effective_language = self._job_language[job_id]
            logger.debug("Using cached language '%s' for job %s", effective_language, job_id)

        segments, info = self._model.transcribe(
            audio_path,
            beam_size=settings.whisper_beam_size,
            language=effective_language,
            vad_filter=vad_filter,
            vad_parameters=dict(
                min_silence_duration_ms=settings.whisper_vad_min_silence_ms,
                min_speech_duration_ms=250,
            ),
        )

        if info.language and job_id and job_id not in self._job_language:
            with self._language_lock:
                if job_id not in self._job_language:
                    self._job_language[job_id] = info.language
                    logger.info(
                        "Language detected: %s (caching for job %s)", info.language, job_id
                    )

        results = []
        for seg in segments:
            results.append(
                {
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text.strip(),
                    "avg_logprob": getattr(seg, "avg_logprob", 0.0),
                    "no_speech_prob": getattr(seg, "no_speech_prob", 0.0),
                }
            )

        return results

    def clear_job_language(self, job_id: str) -> None:
        """Clear cached language for a completed job."""
        with self._language_lock:
            self._job_language.pop(job_id, None)

    def info(self) -> WhisperRuntimeInfo:
        self._ensure_loaded()
        return WhisperRuntimeInfo(
            provider="faster-whisper",
            model=self._model_size,
            device=self._device,
            compute_type=self._compute_type,
            workers=self._workers,
            cpu_cores=os.cpu_count() or 1,
        )

    @property
    def worker_count(self) -> int:
        self._ensure_loaded()
        return self._workers

    @property
    def model_size(self) -> str:
        return self._model_size

    @property
    def device(self) -> str:
        return self._device
