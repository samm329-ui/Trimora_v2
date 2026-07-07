from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PromptArtifact:
    """Stored prompt with lifecycle metadata."""

    prompt_id: str
    content: str
    token_count: int
    content_hash: str
    created_at: float
    job_id: str
    task_type: str
    reference_count: int = 0


class PromptStore:
    """Reference-based prompt storage with lifecycle management.

    Prevents memory leaks via reference counting and TTL-based expiry.
    """

    def __init__(self, token_counter=None, ttl_seconds: float = 3600.0):
        self._store: dict[str, PromptArtifact] = {}
        self._hash_index: dict[str, str] = {}
        self._ttl = ttl_seconds
        self._counter = token_counter
        self._next_id = 0

    @staticmethod
    def _hash_content(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    def store(self, content: str, job_id: str, task_type: str) -> str:
        """Store prompt, return prompt_id. Deduplicates by content hash."""
        content_hash = self._hash_content(content)

        if content_hash in self._hash_index:
            existing_id = self._hash_index[content_hash]
            self._store[existing_id].reference_count += 1
            return existing_id

        token_count = self._counter.count(content) if self._counter else 0
        prompt_id = f"{job_id}_{task_type}_{self._next_id}"
        self._next_id += 1

        artifact = PromptArtifact(
            prompt_id=prompt_id,
            content=content,
            token_count=token_count,
            content_hash=content_hash,
            created_at=time.monotonic(),
            job_id=job_id,
            task_type=task_type,
            reference_count=1,
        )

        self._store[prompt_id] = artifact
        self._hash_index[content_hash] = prompt_id
        return prompt_id

    def get(self, prompt_id: str) -> str:
        """Retrieve prompt content by ID."""
        artifact = self._store.get(prompt_id)
        if artifact is None:
            raise KeyError(f"Prompt not found: {prompt_id}")
        return artifact.content

    def get_artifact(self, prompt_id: str) -> PromptArtifact | None:
        """Retrieve full artifact by ID."""
        return self._store.get(prompt_id)

    def release(self, prompt_id: str) -> None:
        """Release reference to prompt. Decrement ref count, cleanup if zero."""
        artifact = self._store.get(prompt_id)
        if artifact is None:
            return
        artifact.reference_count -= 1
        if artifact.reference_count <= 0:
            self._cleanup(prompt_id)

    def _cleanup(self, prompt_id: str) -> None:
        """Remove prompt from store."""
        artifact = self._store.pop(prompt_id, None)
        if artifact:
            self._hash_index.pop(artifact.content_hash, None)

    def cleanup_expired(self) -> int:
        """Remove prompts older than TTL. Returns count removed."""
        now = time.monotonic()
        expired = [
            pid
            for pid, a in self._store.items()
            if now - a.created_at > self._ttl
        ]
        for pid in expired:
            self._cleanup(pid)
        return len(expired)

    def size_bytes(self) -> int:
        """Total memory usage in bytes."""
        return sum(len(a.content.encode()) for a in self._store.values())

    def __len__(self) -> int:
        return len(self._store)
