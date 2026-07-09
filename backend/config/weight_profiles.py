from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WeightProfile:
    """Versioned weight profile for the Deterministic Story Composer.
    
    Architecture frozen. Weights tunable.
    """
    
    name: str
    version: str
    
    # Dynamic weights: [narrative, value, resolution]
    weights_beginning: tuple[float, float, float] = (0.55, 0.35, 0.10)
    weights_middle: tuple[float, float, float] = (0.30, 0.50, 0.20)
    weights_ending: tuple[float, float, float] = (0.20, 0.25, 0.55)
    
    # Narrative scoring weights
    narrativePromise: float = 0.5
    narrativeEntity: float = 0.3
    narrativeTopic: float = 0.2
    
    # Value scoring weights
    valueNovelty: float = 0.3
    valueCuriosity: float = 0.3
    valueEmotion: float = 0.2
    valueImportance: float = 0.2
    
    # Resolution scoring weights
    resolutionDuration: float = 0.4
    resolutionEnding: float = 0.3
    resolutionSignal: float = 0.3
    
    def get_dynamic_weights(self, duration_used: float, duration_budget: float) -> tuple[float, float, float]:
        """Return (narrative, value, resolution) weights based on story position."""
        total = duration_used + duration_budget
        progress = duration_used / total if total > 0 else 0
        
        if progress < 0.25:
            return self.weights_beginning
        elif progress < 0.75:
            return self.weights_middle
        else:
            return self.weights_ending


DEFAULT_PROFILE = WeightProfile(
    name="default",
    version="v1",
)

GAMING_PROFILE = WeightProfile(
    name="gaming",
    version="v1",
    weights_beginning=(0.50, 0.40, 0.10),
    weights_middle=(0.25, 0.55, 0.20),
    weights_ending=(0.15, 0.30, 0.55),
    valueCuriosity=0.35,
    valueEmotion=0.25,
)

PODCAST_PROFILE = WeightProfile(
    name="podcast",
    version="v1",
    weights_beginning=(0.60, 0.30, 0.10),
    weights_middle=(0.35, 0.45, 0.20),
    weights_ending=(0.25, 0.20, 0.55),
    narrativePromise=0.55,
    narrativeEntity=0.35,
)

DOCUMENTARY_PROFILE = WeightProfile(
    name="documentary",
    version="v1",
    weights_beginning=(0.55, 0.35, 0.10),
    weights_middle=(0.30, 0.50, 0.20),
    weights_ending=(0.20, 0.25, 0.55),
    valueCuriosity=0.35,
)

COMEDY_PROFILE = WeightProfile(
    name="comedy",
    version="v1",
    weights_beginning=(0.45, 0.45, 0.10),
    weights_middle=(0.20, 0.60, 0.20),
    weights_ending=(0.15, 0.35, 0.50),
    valueEmotion=0.30,
    valueCuriosity=0.25,
)

FINANCE_PROFILE = WeightProfile(
    name="finance",
    version="v1",
    weights_beginning=(0.60, 0.30, 0.10),
    weights_middle=(0.35, 0.45, 0.20),
    weights_ending=(0.25, 0.20, 0.55),
    narrativePromise=0.55,
)

PROFILES = {
    "default": DEFAULT_PROFILE,
    "gaming": GAMING_PROFILE,
    "podcast": PODCAST_PROFILE,
    "documentary": DOCUMENTARY_PROFILE,
    "comedy": COMEDY_PROFILE,
    "finance": FINANCE_PROFILE,
}


def get_profile(name: str = "default") -> WeightProfile:
    """Get a weight profile by name. Returns default if not found."""
    return PROFILES.get(name, DEFAULT_PROFILE)
