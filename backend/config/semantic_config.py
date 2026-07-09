from __future__ import annotations

from enum import Enum


class ComposerDebugLevel(Enum):
    """Debug output levels for the Deterministic Story Composer."""
    OFF = "off"         # No reasoning artifact
    SUMMARY = "summary" # Statistics + report only
    FULL = "full"       # Every decision + traces


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

# --- Deterministic Story Composer ---
COMPOSER_BEAM_WIDTH = 3
COMPOSER_MAX_SEGMENTS = 8
COMPOSER_MIN_SCORE = 0.3
COMPOSER_TARGET_DURATION = 60.0
COMPOSER_MIN_DURATION = 30.0
COMPOSER_MAX_DURATION = 90.0
COMPOSER_QUALITY_THRESHOLD = -0.3
COMPOSER_MIN_IMPROVEMENT = 0.1

# Candidate generation
COMPOSER_MIN_CONFIDENCE = 0.3
COMPOSER_MIN_IMPORTANCE = 0.3

# Story quality thresholds
COMPOSER_MAX_REPEATED_ENTITIES = 2
COMPOSER_MONOTONE_EMOTION_COUNT = 3
COMPOSER_MIN_PROMISE_SUPPORT = 0.2

# Debug
COMPOSER_DEBUG_LEVEL = ComposerDebugLevel.SUMMARY
