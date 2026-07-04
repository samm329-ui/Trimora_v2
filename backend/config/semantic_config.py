from __future__ import annotations

# Story quality scoring weights
STORY_QUALITY_WEIGHTS = {
    "completeness": 0.25,
    "coherence": 0.25,
    "hook_quality": 0.15,
    "ending_quality": 0.15,
    "continuity": 0.10,
    "emotional_arc": 0.10,
}

# Rejection thresholds
REJECTION_THRESHOLDS = {
    "quality_too_low": 0.30,
    "incomplete_arc": 0.30,
    "weak_hook": 0.20,
    "weak_ending": 0.20,
}

# Story structure
MIN_STORY_SEGMENTS = 3
MAX_GAP_BETWEEN_SEGMENTS = 5.0
TIMESTAMP_OVERLAP_TOLERANCE = 0.5

# Duplicate detection
DUPLICATE_SIMILARITY_THRESHOLD = 0.90
DUPLICATE_SEGMENT_OVERLAP = 0.95

# Blueprint generation
BLUEPRINT_SHORT_MAX = 90.0
SEGMENT_MAX_USAGE = 3

# Prompt templates (empty placeholders — will be populated with actual prompts)
PASS1_PROMPT_TEMPLATE = ""
PASS2_PROMPT_TEMPLATE = ""
