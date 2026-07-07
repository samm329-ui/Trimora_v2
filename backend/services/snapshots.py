# backend/services/snapshots.py

from dataclasses import dataclass, field
import json
import time
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class SnapshotV1:
    version: int = 1
    stage: str = ""
    timestamp: float = 0.0
    job_id: str = ""
    data: dict = field(default_factory=dict)
    config_snapshot: dict = field(default_factory=dict)
    git_commit: str = ""
    model_versions: dict = field(default_factory=dict)
    feature_flags: dict = field(default_factory=dict)


class PipelineSnapshotService:
    def __init__(self, job_dir: Path):
        self.job_dir = job_dir
        self.snapshots_dir = job_dir / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, snapshot: SnapshotV1) -> Path:
        filename = f"{snapshot.stage}_v{snapshot.version}_{snapshot.job_id}.json"
        file_path = self.snapshots_dir / filename
        with open(file_path, "w") as f:
            json.dump(self._to_dict(snapshot), f, indent=2, default=str)
        self._generate_summary(snapshot)
        return file_path

    def _generate_summary(self, snapshot: SnapshotV1):
        lines = [
            f"# Pipeline Snapshot: {snapshot.stage}",
            f"",
            f"- **Job ID:** {snapshot.job_id}",
            f"- **Stage:** {snapshot.stage}",
            f"- **Version:** {snapshot.version}",
            f"- **Timestamp:** {snapshot.timestamp}",
            f"- **Git Commit:** {snapshot.git_commit}",
            f"",
            f"## Model Versions",
            f"```json",
            json.dumps(snapshot.model_versions, indent=2, default=str)[:2000],
            f"```",
            f"",
            f"## Feature Flags",
            f"```json",
            json.dumps(snapshot.feature_flags, indent=2, default=str)[:2000],
            f"```",
            f"",
            f"## Configuration",
            f"```json",
            json.dumps(snapshot.config_snapshot, indent=2, default=str)[:2000],
            f"```",
        ]
        summary_path = self.snapshots_dir / f"{snapshot.stage}_v{snapshot.version}_summary.md"
        with open(summary_path, "w") as f:
            f.write("\n".join(lines))

    def save_trace(self, trace: list, job_id: str, latency_stats: dict,
                   config: dict = None, git_commit: str = "",
                   model_versions: dict = None, feature_flags: dict = None):
        trace_data = {
            "job_id": job_id,
            "pipeline_version": "v10.1.0",
            "created_at": time.time(),
            "git_commit": git_commit,
            "model_versions": model_versions or {},
            "feature_flags": feature_flags or {},
            "config_snapshot": config or {},
            "stages": trace,
            "latency_stats": latency_stats,
            "total_ms": sum(s.get("elapsed_ms", 0) for s in trace),
        }
        trace_path = self.job_dir / "trace.json"
        with open(trace_path, "w") as f:
            json.dump(trace_data, f, indent=2)

    def _to_dict(self, snapshot: SnapshotV1) -> dict:
        return {
            "version": snapshot.version,
            "stage": snapshot.stage,
            "timestamp": snapshot.timestamp,
            "job_id": snapshot.job_id,
            "data": snapshot.data,
            "config_snapshot": snapshot.config_snapshot,
            "git_commit": snapshot.git_commit,
            "model_versions": snapshot.model_versions,
            "feature_flags": snapshot.feature_flags,
        }

    @staticmethod
    def get_git_commit() -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:
            return "unknown"
