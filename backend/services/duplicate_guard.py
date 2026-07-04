from __future__ import annotations

import hashlib
import logging

from backend.models.story_blueprint import StoryBlueprint
from backend.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class DuplicateGuard:
    def __init__(self, embedder: EmbeddingService):
        self.embedder = embedder
        self.seen_blueprints: list[StoryBlueprint] = []
        self.seen_embeddings: list = []
        self.seen_signatures: set[str] = set()

    def _blueprint_signature(self, blueprint: StoryBlueprint) -> str:
        segment_str = "|".join(blueprint.segment_ids)
        return f"{blueprint.story_id}:{hashlib.md5(segment_str.encode()).hexdigest()[:12]}"

    def is_duplicate(self, blueprint: StoryBlueprint, existing: list[StoryBlueprint] | None = None) -> tuple[bool, str, str]:
        check_list = existing or self.seen_blueprints

        # Composite key: story_id + segment sequence
        sig = self._blueprint_signature(blueprint)
        if sig in self.seen_signatures:
            return True, "exact_duplicate", "Identical segment sequence already exists"

        new_segments = set(blueprint.segment_ids)
        new_emb = self.embedder.embed(f"{blueprint.story_name} {blueprint.validated_story_summary}")

        for i, bp in enumerate(check_list):
            # Segment overlap (threshold: 0.95 to allow legitimate alternative cuts)
            existing_segments = set(bp.segment_ids)
            overlap = len(new_segments & existing_segments) / max(len(new_segments | existing_segments), 1)
            if overlap >= 0.95:
                return True, "near_duplicate", f"{overlap:.0%} overlap with {bp.blueprint_id}"

            # Semantic similarity (threshold: 0.90)
            if i < len(self.seen_embeddings):
                sim = self.embedder.cosine_similarity(new_emb, self.seen_embeddings[i])
                if sim >= 0.90:
                    return True, "narrative_duplicate", f"Similarity {sim:.2f} with {bp.blueprint_id}"

        # Not duplicate, register
        self.seen_signatures.add(sig)
        self.seen_blueprints.append(blueprint)
        self.seen_embeddings.append(new_emb)
        return False, "", ""
