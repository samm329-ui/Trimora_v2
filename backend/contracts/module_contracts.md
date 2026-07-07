# Module Contracts (V10.1)

## Core

### Artifact[T]
- **Type:** Generic frozen dataclass
- **Fields:** artifact_id, version, created_at, data, parent_id, parent_hash, status, metadata
- **Invariants:** Immutable, deterministic ID includes output_hash
- **Thread Safety:** safe (frozen)

### ExecutionContext
- **Type:** Composed of PipelineConfig, MetricsCollector, CacheStore, LoggerAdapter
- **Invariants:** Not a God Object — each concern is isolated in its own class
- **Thread Safety:** mutable, single-threaded access

### PipelineContext
- **Type:** Frozen dataclass
- **Invariants:** Immutable during execution — strategies cannot mutate
- **Thread Safety:** safe (frozen)

### DAGExecutor
- **Type:** Async DAG executor with concurrency control
- **Fields:** max_concurrency, semaphore, budget_enforcer
- **Returns:** ExecutionResult (frozen) — artifacts, errors, trace, latency_stats, warnings, total_ms
- **Invariants:** Dependency-aware, priority-scheduled, max concurrency enforced
- **Thread Safety:** safe (async)

### PipelineOrchestrator
- **Type:** Lightweight stage wiring
- **Invariants:** Builds DAG from StageDefinitions, executes via DAGExecutor
- **Thread Safety:** safe (async)

## Services

### AdaptiveWindowSplitter
- **Input:** Artifact[TranscriptData]
- **Output:** Artifact[SignalData]
- **Invariants:** Non-overlapping, ordered, duration within config bounds
- **Latency Budget:** 100ms
- **Cacheable:** yes

### DynamicRoleClassifier
- **Input:** Artifact[SignalData]
- **Output:** Artifact (classified segments with role field)
- **Invariants:** Each segment gets exactly one role
- **Latency Budget:** 150ms
- **Cacheable:** yes

### PipelineSnapshotService
- **Input:** SnapshotV1
- **Output:** File on disk + summary markdown
- **Invariants:** Includes git_commit, model_versions, feature_flags
- **Latency Budget:** 50ms

## Strategies

### ClipStrategy (ABC)
- **Input:** PipelineContext (graph, evidence, embeddings, signals, transcript)
- **Output:** Artifact[CandidatesData]
- **Invariants:** Unique IDs, start < end, duration > 0
- **Thread Safety:** safe

### StoryStrategy
- **Generates:** Hook-body-ending triples from graph events
- **Min events:** 3

### HookStrategy
- **Generates:** Single events with question marks or engagement keywords

## Objectives

### Objective (ABC)
- **Input:** candidate dict, context dict
- **Output:** ObjectiveResult(score, confidence, status, latency_ms, error)
- **Invariants:** Score in [0, 1], confidence in [0, 1]

### ObjectiveRegistry
- **Executes:** Objectives as dependency DAG (topological order)
- **Invariants:** Dependencies resolved before dependent objectives

## Optimization

### CandidateDeduplicationService
- **Input:** Artifact[CandidatesData]
- **Output:** Artifact[CandidatesData] (deduplicated)
- **Invariants:** Uses SimilarityProvider interface (not hardcoded Jaccard)
- **Latency Budget:** 100ms

### PortfolioOptimizer
- **Input:** Artifact[ScoresData]
- **Output:** Artifact[PortfolioData]
- **Invariants:** MMR selection with configurable diversity policy + SimilarityProvider
- **Latency Budget:** 200ms

### NarrativeOptimizer
- **Input:** Artifact[CandidatesData]
- **Output:** Artifact[CandidatesData] (sorted by start time)
- **Latency Budget:** 200ms

## Evaluation

### EvaluationLayer
- **Input:** Artifact[PortfolioData]
- **Output:** EvaluationData (records list)
- **Invariants:** Lifecycle states (Generated->Edited->Uploaded->7d->30d), ground truth tracking
- **Latency Budget:** 50ms
