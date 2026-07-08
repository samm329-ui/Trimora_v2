# backend/evaluation/layer.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import json
import time
from pathlib import Path

from backend.models.evaluation import EvaluationRecord, EvaluationLifecycle, RejectionType, GroundTruth
from backend.models.data import PortfolioData
from backend.core.artifact import ArtifactStage, PipelineContractError


class EvaluationLayer:
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)

    async def execute(self, context, artifact) -> dict:
        portfolio = artifact.data
        if not portfolio:
            return {"records": []}

        if not isinstance(portfolio, PortfolioData):
            raise PipelineContractError(
                ArtifactStage.EVALUATION, PortfolioData, type(portfolio),
                getattr(artifact, 'artifact_id', None), getattr(artifact, 'parent_id', None),
            )

        config_snapshot = context.config.to_dict() if context and hasattr(context.config, 'to_dict') else (context.config if context else {})
        records = []
        for clip in portfolio.portfolio.get("clips", []):
            record = EvaluationRecord(
                record_id=f"eval_{clip.get('id', 'unknown')}",
                job_id=context.job_id if context else "",
                clip_id=clip.get("id", ""),
                candidate_id=clip.get("candidate_id", ""),
                selected=True, rank=clip.get("rank", 0),
                portfolio_position=clip.get("rank", 0),
                objective_scores=clip.get("objective_scores", {}),
                overall_score=clip.get("overall_score", 0),
                pipeline_version="v10.1.0",
                artifact_hashes={"portfolio": artifact.compute_hash()},
                config_snapshot=config_snapshot,
                lifecycle=EvaluationLifecycle.GENERATED,
            )
            self._save_record(record)
            rec_dict = {
                "record_id": record.record_id,
                "job_id": record.job_id,
                "clip_id": record.clip_id,
                "candidate_id": record.candidate_id,
                "selected": record.selected,
                "rank": record.rank,
                "portfolio_position": record.portfolio_position,
                "lifecycle": record.lifecycle.value,
                "rejection_type": record.rejection_type.value if record.rejection_type else None,
                "rejection_reason": record.rejection_reason,
                "rejection_stage": record.rejection_stage,
                "rejection_scores": record.rejection_scores,
                "objective_scores": record.objective_scores,
                "overall_score": record.overall_score,
                "pipeline_version": record.pipeline_version,
                "objective_registry_version": record.objective_registry_version,
                "strategy_registry_version": record.strategy_registry_version,
                "artifact_hashes": record.artifact_hashes,
                "config_snapshot": record.config_snapshot,
                "ground_truth": record.ground_truth.__dict__ if record.ground_truth else None,
            }
            records.append(rec_dict)

        return {"records": records}

    def record_ground_truth(self, record_id: str, ground_truth: GroundTruth):
        record = self._load_record(record_id)
        if record:
            updated = EvaluationRecord(
                record_id=record.record_id, job_id=record.job_id,
                clip_id=record.clip_id, candidate_id=record.candidate_id,
                selected=record.selected, rank=record.rank,
                portfolio_position=record.portfolio_position,
                lifecycle=EvaluationLifecycle.EDITED,
                objective_scores=record.objective_scores,
                overall_score=record.overall_score,
                pipeline_version=record.pipeline_version,
                artifact_hashes=record.artifact_hashes,
                config_snapshot=record.config_snapshot,
                ground_truth=ground_truth,
            )
            self._save_record(updated)

    def _save_record(self, record: EvaluationRecord):
        file_path = self.storage_path / f"{record.record_id}.json"
        data = {
            "record_id": record.record_id,
            "job_id": record.job_id,
            "clip_id": record.clip_id,
            "candidate_id": record.candidate_id,
            "selected": record.selected,
            "rank": record.rank,
            "portfolio_position": record.portfolio_position,
            "lifecycle": record.lifecycle.value,
            "rejection_type": record.rejection_type.value if record.rejection_type else None,
            "rejection_reason": record.rejection_reason,
            "rejection_stage": record.rejection_stage,
            "rejection_scores": record.rejection_scores,
            "objective_scores": record.objective_scores,
            "overall_score": record.overall_score,
            "pipeline_version": record.pipeline_version,
            "objective_registry_version": record.objective_registry_version,
            "strategy_registry_version": record.strategy_registry_version,
            "artifact_hashes": record.artifact_hashes,
            "config_snapshot": record.config_snapshot,
            "ground_truth": record.ground_truth.__dict__ if record.ground_truth else None,
        }
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _load_record(self, record_id: str) -> Optional[EvaluationRecord]:
        file_path = self.storage_path / f"{record_id}.json"
        if file_path.exists():
            with open(file_path) as f:
                data = json.load(f)
                if "lifecycle" in data and isinstance(data["lifecycle"], str):
                    data["lifecycle"] = EvaluationLifecycle(data["lifecycle"])
                if "rejection_type" in data and isinstance(data["rejection_type"], str):
                    data["rejection_type"] = RejectionType(data["rejection_type"])
                if "ground_truth" in data and isinstance(data["ground_truth"], dict):
                    data["ground_truth"] = GroundTruth(**data["ground_truth"])
                return EvaluationRecord(**data)
        return None
