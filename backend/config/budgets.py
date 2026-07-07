# backend/config/budgets.py

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StageBudget:
    """Budget for a single stage."""
    name: str
    budget_ms: float
    warning_threshold: float = 0.8  # fraction of budget
    max_warnings: int = 3


STAGE_BUDGETS = {
    "adaptive_windows": StageBudget(name="adaptive_windows", budget_ms=100),
    "signal_extraction": StageBudget(name="signal_extraction", budget_ms=200),
    "evidence_compilation": StageBudget(name="evidence_compilation", budget_ms=500),
    "graph_construction": StageBudget(name="graph_construction", budget_ms=300),
    "role_classification": StageBudget(name="role_classification", budget_ms=150),
    "strategy_execution": StageBudget(name="strategy_execution", budget_ms=1000),
    "candidate_deduplication": StageBudget(name="candidate_deduplication", budget_ms=100),
    "objective_scoring": StageBudget(name="objective_scoring", budget_ms=2000),
    "narrative_optimization": StageBudget(name="narrative_optimization", budget_ms=200),
    "portfolio_optimization": StageBudget(name="portfolio_optimization", budget_ms=200),
    "evaluation_recording": StageBudget(name="evaluation_recording", budget_ms=50),
}

TOTAL_BUDGET_MS = 5000.0


def get_budget(stage_name: str) -> StageBudget:
    return STAGE_BUDGETS.get(stage_name, StageBudget(name=stage_name, budget_ms=1000))


def check_budget(stage_name: str, elapsed_ms: float) -> str:
    """Returns 'ok', 'warning', or 'exceeded'."""
    budget = get_budget(stage_name)
    if elapsed_ms > budget.budget_ms:
        return "exceeded"
    if elapsed_ms > budget.budget_ms * budget.warning_threshold:
        return "warning"
    return "ok"
