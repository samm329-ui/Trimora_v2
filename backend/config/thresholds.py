from __future__ import annotations

# Segment thresholds
MIN_SEGMENT_SECONDS: float = 1.2
MAX_SEGMENT_SECONDS: float = 30.0

# Candidate scoring
MIN_CANDIDATE_SCORE: float = 0.35
PREVIEW_TOP_K: int = 20

# Hook/Ending detection
HOOK_MIN_WORDS: int = 5
ENDING_MIN_WORDS: int = 5

# Duration preferences (in seconds)
IDEAL_MIN_DURATION: int = 30
IDEAL_MAX_DURATION: int = 60
TOO_SHORT_THRESHOLD: int = 15
TOO_LONG_THRESHOLD: int = 90

# Scoring weights
SCORING_WEIGHTS = {
    "hook": 0.35,
    "body": 0.25,
    "ending": 0.20,
    "flow": 0.20,
}
