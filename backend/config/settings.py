# backend/config/settings.py

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PipelineSettings:
    """All pipeline configuration in one place."""
    # Pipeline
    pipeline_version: str = "v10.1.0"
    max_concurrency: int = 10
    total_budget_ms: float = 5000.0

    # Window splitter
    min_window_duration: float = 15.0
    max_window_duration: float = 120.0
    preferred_min_duration: float = 45.0
    preferred_max_duration: float = 90.0

    # Strategies
    enabled_strategies: list = field(default_factory=lambda: [
        "story", "hook", "reveal", "reaction", "opinion"
    ])

    # Objectives
    enabled_objectives: list = field(default_factory=lambda: [
        "hook_delivery", "standalone", "ending", "dead_time",
        "narrative_coherence", "information_density", "temporal_flow",
        "emotional_arc", "creator_fit", "visual_quality"
    ])

    # Portfolio
    top_k: int = 20
    diversity_policy: str = "balanced"  # balanced, quality, diversity, similar

    # Evaluation
    evaluation_storage_path: str = "evaluations"
    snapshot_storage_path: str = "snapshots"

    # Deduplication
    similarity_threshold: float = 0.5
    similarity_provider: str = "jaccard"  # jaccard, semantic (future)

    # Feature flags
    feature_flags: dict = field(default_factory=lambda: {
        "enable_vision": False,
        "enable_audio_analysis": False,
        "enable_semantic_dedup": False,
        "enable_ground_truth_learning": False,
    })


DEFAULT_SETTINGS = PipelineSettings()
