# Trimora V10.1

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-FFmpeg-orange.svg)](https://ffmpeg.org/)

> AI-powered platform that transforms long-form videos into engaging short-form clips. V10.1 introduces a production-grade pipeline core with deterministic artifacts, immutable data, DAG execution, token-aware LLM scheduling, a deterministic story composer, pluggable strategies/objectives, and explicit pipeline contracts with fail-fast validation.

---

## Quick Navigation

- [Overview](#overview)
- [V10.1 Production Core](#v101-production-core)
- [Deterministic Story Composer](#deterministic-story-composer)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Semantic Enrichment Pipeline](#semantic-enrichment-pipeline)
- [Project Structure](#project-structure)
- [Production Pipeline](#production-pipeline)
- [Job Lifecycle](#job-lifecycle)
- [API Reference](#api-reference)
- [Ranking Engine](#ranking-engine)
- [Frontend](#frontend)
- [Configuration](#configuration)
- [Setup](#setup)
- [Docker](#docker)
- [Storage](#storage)
- [Testing](#testing)
- [License](#license)

---

## Overview

Trimora takes a long video (podcast, lecture, interview) and automatically extracts the best short-form clips. V10.1 rebuilds the pipeline core with production-grade guarantees: deterministic artifact IDs, immutable data types, DAG-based execution, token-aware LLM scheduling with payload validation, a deterministic story composer using beam search, and pluggable strategies and objectives.

**Processing time estimates** (with Faster-Whisper GPU transcription):

| Video Length | Chunks | Transcription | Semantic | Total |
|---|---|---|---|---|
| 8 minutes | 10 | ~10-20s | ~5s | ~25-40s |
| 30 minutes | 40 | ~40-80s | ~8s | ~60-100s |
| 1 hour | 80 | ~80-160s | ~15s | ~2-4 min |

**Processing time estimates** (with cloud transcription fallback):

| Video Length | Chunks | Transcription | Semantic | Total |
|---|---|---|---|---|
| 30 minutes | 40 | ~160s | ~8s | ~3 min |
| 1 hour | 40 | ~160s | ~8s | ~3 min |
| 3 hours | 120 | ~480s | ~20s | ~9 min |

---

## V10.1 Production Core

V10.1 introduces a complete pipeline execution core with production-readiness guarantees. Every component is immutable, deterministic, and budget-enforced.

### Core Modules

```mermaid
flowchart TB
    subgraph Core["Pipeline Core"]
        ART["Artifact - frozen deterministic IDs"]
        CTX["ExecutionContext - split concerns"]
        DAG["DAGExecutor - semaphore budget priority"]
        ORCH["PipelineOrchestrator - wires stages"]
    end

    subgraph Data["Data Models"]
        TD["TranscriptData"]
        SD["SignalData"]
        ED["EvidenceData"]
        GD["GraphData"]
        CD["CandidatesData"]
        SCD["ScoresData"]
        PD["PortfolioData"]
        EVD["EvaluationData"]
        GTD["GroundTruthData"]
    end

    subgraph Config["Configuration"]
        PS["PipelineSettings - frozen"]
        SB["StageBudgets - 11 stages"]
        WC["WindowConfig"]
    end

    subgraph Strategies["Clip Strategies"]
        ST["ClipStrategy ABC"]
        STORY["StoryStrategy"]
        HOOK["HookStrategy"]
        REVEAL["RevealStrategy"]
        REACT["ReactionStrategy"]
        OPINION["OpinionStrategy"]
    end

    subgraph Objectives["Scoring Objectives"]
        OBJ["Objective ABC"]
        HD["HookDelivery"]
        SA["Standalone"]
        EN["Ending"]
        DT["DeadTime"]
        NC["NarrativeCoherence"]
        ID["InformationDensity"]
        TF["TemporalFlow"]
        EA["EmotionalArc"]
        CF["CreatorFit"]
        VQ["VisualQuality"]
    end

    subgraph Optimization["Optimization"]
        NO["NarrativeOptimizer"]
        PO["PortfolioOptimizer - MMR"]
        CDS["CandidateDeduplication"]
    end

    ORCH --> DAG
    DAG --> ART
    CTX --> PS
    ST --> STORY & HOOK & REVEAL & REACT & OPINION
    OBJ --> HD & SA & EN & DT & NC & ID & TF & EA & CF & VQ
    NO --> CD
    PO --> CD
    CDS --> CD
```

### 13 Production Guarantees

| # | Guarantee | Implementation |
|---|---|---|
| 1 | **Immutable data types** | All 9 data models use `frozen=True` |
| 2 | **Deterministic artifact IDs** | `create_artifact()` factory with `output_hash` parameter |
| 3 | **ExecutionContext not a God Object** | Split into `PipelineConfig`, `MetricsCollector`, `CacheStore`, `LoggerAdapter` |
| 4 | **Immutable PipelineContext** | `PipelineContext` is frozen, read-only |
| 5 | **DAG returns ExecutionResult** | Not `dict` - immutable result with trace, errors, latency stats |
| 6 | **Objective dependencies as DAG** | `ObjectiveRegistry` uses topological sort, not simple loop |
| 7 | **SimilarityProvider interface** | Not hardcoded Jaccard - pluggable via ABC |
| 8 | **Evaluation lifecycle states** | `EvaluationLifecycle`: GENERATED, REVIEWED, APPROVED, REJECTED, DEPLOYED |
| 9 | **Snapshots with full context** | `SnapshotV1` includes git commit, model versions, feature flags |
| 10 | **Automatic budget enforcement** | `BudgetEnforcer`: warning, count, disable, fallback |
| 11 | **Explicit pipeline contracts** | Every stage declares `INPUT_TYPE` / `OUTPUT_TYPE` with `PipelineContractError` on mismatch |
| 12 | **Centralized artifact creation** | `create_artifact()` factory - production code never calls `Artifact(...)` directly |
| 13 | **Fail-fast validation** | `PipelineContractError` carries stage, expected, received, artifact_id, parent_id |

### Pipeline Contracts

Every pipeline stage declares its expected input and output types. Contract violations fail immediately with structured errors.

```mermaid
flowchart LR
    G["GraphData"] -->|"strategies"| CD["CandidatesData"]
    CD -->|"dedup"| CD
    CD -->|"scoring"| SD["ScoresData"]
    SD -->|"narrative"| SD
    SD -->|"portfolio"| PD["PortfolioData"]
    PD -->|"evaluation"| ED["dict records"]
```

| Stage | Input Type | Output Type |
|---|---|---|
| Strategies | `PipelineContext` | `Artifact[CandidatesData]` |
| Deduplication | `Artifact[CandidatesData]` | `Artifact[CandidatesData]` |
| Narrative | `Artifact[ScoresData]` | `Artifact[ScoresData]` |
| Portfolio | `Artifact[ScoresData]` | `Artifact[PortfolioData]` |
| Evaluation | `Artifact[PortfolioData]` | `dict` |

---

## Deterministic Story Composer

The Deterministic Story Composer replaces the broken LLM-based Pass 2 story boundary detection with a deterministic editing engine. It uses beam search to generate high-quality candidate story edits from structured semantic outputs.

**Architecture frozen. Weights tunable.**

### How It Works

The composer does not discover knowledge. It reasons over knowledge that has already been extracted by Pass 1. Its responsibility is editing, not understanding.

```mermaid
flowchart TB
    P1["Pass 1: Semantic Analysis"] --> COMP["Deterministic Story Composer"]
    COMP --> SD["StoryDetector"]
    SD --> SV["StoryValidator"]
    SV --> BG["BlueprintGenerator"]
```

### Three-Axis Scoring

Each segment is scored on three axes with dynamic weights that shift based on story position:

| Story Position | Narrative | Value | Resolution |
|---|---|---|---|
| Beginning (0-25%) | 0.55 | 0.35 | 0.10 |
| Middle (25-75%) | 0.30 | 0.50 | 0.20 |
| Ending (75-100%) | 0.20 | 0.25 | 0.55 |

- **Narrative**: Does this segment belong to the same story? (promise entity alignment, topic similarity)
- **Value**: Does this improve the edit? (novelty, curiosity, emotion diversity)
- **Resolution**: Does this move toward a satisfying ending? (duration fitness, ending strength)

### Beam Search

The composer explores multiple story paths simultaneously using beam search with diversity penalties to ensure varied output.

### Deduplication

Stories are deduplicated by clustering overlapping boundaries and selecting the best representative. Does not merge stories - preserves alternative edits.

### Weight Profiles

Domain-specific tuning profiles are available:

| Profile | Focus |
|---|---|
| `default` | Balanced general-purpose |
| `gaming` | Higher curiosity and emotion |
| `podcast` | Stronger narrative promise |
| `documentary` | Higher curiosity weighting |
| `comedy` | Emotion-driven with curiosity |
| `finance` | Strong narrative promise |

### Debug Levels

| Level | Content | Size |
|---|---|---|
| `OFF` | No reasoning artifact | 0 |
| `SUMMARY` | Statistics + report only | ~50 KB |
| `FULL` | Every decision with traces | ~15 MB |

---

## Features

| Feature | Description |
|---|---|
| Audio-First Processing | Extract audio once, process independently of video |
| Local Transcription | Faster-Whisper with auto model selection (tiny to large-v3) |
| Cloud Transcription | Groq/Gemini as fallback option |
| Per-Job Language Caching | Language detected once, reused across all chunks |
| Parallel Transcription | Local Faster-Whisper with rate-limited concurrent processing |
| Adaptive Chunking | Dynamic chunk sizes based on video duration |
| LLM Scheduler | Token-aware scheduling with reservation model, circuit breaker, and payload validation |
| Payload Validation | Validates prompt size against model limits before execution |
| Payload Splitting | Task-specific splitting strategies (Transcript, Reasoning, Summary) |
| Model Registry | Immutable model-to-provider mapping with safe limits |
| ProviderAdapter | Model-aware execution with retry, backoff, and prompt resolution |
| ProviderRouter | Thread-safe round-robin across multiple API keys/providers |
| Embedding Topic Clustering | sentence-transformers for adaptive block boundaries |
| LLM Semantic Enrichment | Pass 1: segment annotation, Pass 2: deterministic story composition |
| Deterministic Story Composer | Beam search with three-axis scoring, deduplication, and weight profiles |
| Structured Summary | Global video summary as root semantic artifact |
| Block Synopses | Deterministic per-block summaries for debugging and reuse |
| Story Detection and Repair | Candidate formation, verification, and repair |
| Blueprint Generation | Story-to-blueprint conversion with cut selection |
| Multi-Stage Ranking | Semantic deduplication with MMR optimization |
| Deterministic Artifacts | Hash-based IDs with output_hash for true determinism |
| Immutable Data Types | All data models are frozen (immutable) |
| DAG Execution | Semaphore-controlled, priority-queued, budget-enforced |
| Pluggable Strategies | 5 built-in strategies (Story, Hook, Reveal, Reaction, Opinion) |
| Pluggable Objectives | 10 built-in scoring objectives with dependency DAG |
| Pipeline Snapshots | Git commit, model versions, feature flags at each stage |
| Evaluation Lifecycle | 5-state lifecycle: Generated, Reviewed, Approved, Rejected, Deployed |
| FFmpeg Rendering | Direct MP4 clip export |
| Performance Monitoring | Per-chunk RTF logging and transcription analytics |
| Dark Theme UI | Modern React frontend with dark mode |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic v2 |
| Pipeline Core | Custom DAG executor, frozen dataclasses, deterministic hashing |
| LLM Scheduling | Token-aware scheduler, circuit breaker, reservation-based budget |
| Story Composition | Deterministic beam search, three-axis scoring, domain weight profiles |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Media Processing | FFmpeg, ffprobe |
| Transcription | Faster-Whisper (local, CPU/GPU), Groq (cloud), Gemini (cloud) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2), TF-IDF fallback |
| LLM (Semantic) | Groq (Llama 3.1), Gemini - for Pass 1 semantic enrichment |
| Concurrency | asyncio worker pools with semaphore |
| Storage | Local JSON files (database-ready architecture) |
| Deployment | Docker Compose, Windows batch launcher |

---

## Architecture

### High-Level System Architecture

```mermaid
flowchart TB
    subgraph Frontend["Frontend"]
        U["User"] --> FE["React SPA"]
    end

    subgraph Backend["Backend"]
        FE -->|"POST /api/process"| API["FastAPI"]
        API --> ORC["Orchestrator"]
        ORC --> PIPE["Production Pipeline"]
    end

    subgraph Ingestion["Ingestion"]
        PIPE --> EXT["Audio Extraction"]
        EXT --> CHUNK["Chunk Planning"]
        CHUNK --> SCHED["Scheduler"]
    end

    subgraph Transcription["Parallel Transcription"]
        SCHED --> WP["Worker Pool"]
        WP --> TRANS["Transcription"]
        TRANS -->|"local"| WM["WhisperManager"]
        TRANS -->|"cloud"| GROQ["Groq API"]
        TRANS -->|"fallback"| GEMINI["Gemini API"]
        TRANS --> MERGE["Transcript Merge"]
    end

    subgraph Analysis["Analysis"]
        MERGE --> SEG["Segmentation"]
        SEG --> FEAT["Feature Extraction"]
    end

    subgraph Semantic["Semantic Enrichment"]
        FEAT --> EMB["Embedding Clustering"]
        EMB --> BLOCKS["Topic Blocks"]
        BLOCKS --> SYN["Block Synopses"]
        SYN --> SUM["Structured Summary"]
        SUM --> P1["Pass 1: Annotation"]
        P1 --> P2["Story Composer"]
        P2 --> SD["Story Detection"]
        SD --> SV["Story Validation"]
        SV --> BG["Blueprint Generation"]
    end

    subgraph V101["V10.1 Pipeline Core"]
        BG --> STRAT["5 Clip Strategies"]
        STRAT --> DEDUP["Candidate Deduplication"]
        DEDUP --> OBJ["10 Scoring Objectives"]
        OBJ --> NARR["Narrative Optimization"]
        NARR --> PORT["Portfolio Optimization"]
        PORT --> EVAL["Evaluation Recording"]
    end

    subgraph Output["Output"]
        EVAL --> RANK["Multi-Stage Ranking"]
        RANK --> PREV["Preview"]
        PREV --> RENDER["FFmpeg Render"]
    end
```

### End-to-End Pipeline Flow

```mermaid
flowchart TB
    IN(["Video Input"]) --> FF{"FFmpeg installed?"}
    FF -->|"No"| ERR1["Error: ffmpeg not found"]
    FF -->|"Yes"| AUDIO["Extract Audio"]
    AUDIO --> PLAN["Plan Chunks"]
    PLAN --> SPLIT["Split into chunk files"]
    SPLIT --> WP["Worker Pool"]

    WP --> LOCAL{"Local Whisper available?"}
    LOCAL -->|"Yes"| WHISPER["Faster-Whisper GPU/CPU"]
    LOCAL -->|"No"| CLOUD{"API keys configured?"}
    CLOUD -->|"Groq"| GROQ2["Groq API"]
    CLOUD -->|"Gemini"| GEMIN2["Gemini API"]
    CLOUD -->|"None"| STUB["Stub Transcription"]

    WHISPER --> MERGE["Merge Transcripts"]
    GROQ2 --> MERGE
    GEMIN2 --> MERGE
    STUB --> MERGE

    MERGE --> SEG["Atomic Segmentation"]
    SEG --> FEAT["Feature Extraction"]
    FEAT --> EMB["Embedding Clustering"]
    EMB --> BLOCKS["Topic Blocks"]
    BLOCKS --> SYN["Block Synopses"]
    SYN --> SUMMARY["Structured Summary"]

    SUMMARY --> P1["Pass 1: Segment Annotation"]
    BLOCKS --> P1
    P1 --> P2["Story Composer: Beam Search"]
    BLOCKS --> P2
    SUMMARY --> P2

    P2 --> DETECT["Story Detection"]
    DETECT --> REPAIR["Story Repair"]
    REPAIR --> VALID["Story Validation"]
    VALID --> BLUE["Blueprint Generation"]

    BLUE --> DEDUP["Strategy Execution + Dedup"]
    DEDUP --> OBJ["Objective Scoring"]
    OBJ --> NARR["Narrative Optimization"]
    NARR --> PORT["Portfolio Optimization"]
    PORT --> EVAL["Evaluation"]

    EVAL --> RANK["Multi-Stage Ranking"]
    RANK --> PREV["Preview Manifest"]
    PREV --> RENDER["FFmpeg Render MP4"]
    RENDER --> DONE(["Complete"])

    AUDIO -->|"Error"| ERR2["Error: extraction failed"]
    WP -->|"Error"| ERR3["Error: transcription failed"]
```

### Data Flow

```mermaid
flowchart LR
    V["Video"] --> A["audio.opus"]
    A --> C["chunks/*.opus"]
    C --> T["transcript.json"]
    T --> S["atomic_segments.json"]
    S --> F["feature_vectors.json"]
    S --> E["segment_annotations.json"]
    E --> B["topic_blocks.json"]
    B --> SYN["block_synopses.json"]
    SYN --> SM["summary.json"]
    SM --> P2["story boundaries"]
    P2 --> BL["story_blueprints.json"]
    BL --> CD["candidates.json"]
    CD --> RK["ranked_clips.json"]
    RK --> PV["preview_manifest.json"]
    PV --> EX["reel_001.mp4"]
```

---

## LLM Scheduler

The LLM Scheduler replaces the old ExecutionEngine/PipelineExecutor architecture with a token-aware, single-responsibility component system that solves both 413 (payload too large) and 429 (rate limit) errors.

### Architecture

```mermaid
flowchart TB
    subgraph Pipeline["Pipeline Layer"]
        PL["ProductionPipeline"]
        PF["PromptFactory"]
        PS2["PromptStore"]
    end

    subgraph Validation["Validation Layer"]
        PV["PayloadValidator"]
        SPL["PayloadSplitter"]
    end

    subgraph Scheduler["LLM Scheduler"]
        LS["LLMScheduler"]
        TB2["TokenBudget"]
        CB["CircuitBreaker"]
        EP["ExecutionPolicy"]
    end

    subgraph Execution["Execution Layer"]
        PA["ProviderAdapter"]
        MR["ModelRegistry"]
        PR["ProviderRouter"]
    end

    PL -->|"creates tasks"| PF
    PF -->|"stores prompts"| PS2
    PF -->|"returns LLMTasks"| PV
    PV -->|"validates size"| LS
    PV -->|"splits if oversized"| SPL
    SPL -->|"child tasks"| LS
    LS -->|"reserves tokens"| TB2
    LS -->|"checks health"| CB
    LS -->|"wraps retry"| EP
    EP -->|"dispatches"| PA
    PA -->|"resolves prompt"| PS2
    PA -->|"calls provider"| MR
    MR --> PR
```

### Key Components

| Component | Location | Purpose |
|---|---|---|
| `LLMScheduler` | `backend/execution/scheduler.py` | Thin queue-and-dispatch with sequence counter |
| `TokenBudget` | `backend/execution/token_budget.py` | Reservation model with reserve/commit/rollback |
| `CircuitBreaker` | `backend/execution/circuit_breaker.py` | CLOSED/OPEN/HALF_OPEN state machine |
| `ExecutionPolicy` | `backend/execution/execution_policy.py` | Retry, backoff, timeout wrapping circuit breaker |
| `ModelRegistry` | `backend/execution/model_registry.py` | Immutable model-to-provider mapping |
| `ProviderAdapter` | `backend/execution/provider_adapter.py` | Model-aware execution with prompt resolution |
| `PayloadValidator` | `backend/services/payload_validator.py` | Validates payloads against model limits |
| `PayloadSplitter` | `backend/services/payload_splitter.py` | Task-specific splitting strategies |
| `PromptStore` | `backend/services/prompt_store.py` | Reference-based prompt storage with TTL |
| `PromptFactory` | `backend/services/prompt_factory.py` | Creates LLMTasks from pipeline context |
| `TokenCounter` | `backend/services/token_counter.py` | tiktoken + heuristic fallback |

### Task Lifecycle

```mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> QUEUED : submit
    QUEUED --> WAITING_FOR_BUDGET : reserve tokens
    WAITING_FOR_BUDGET --> EXECUTING : budget reserved
    EXECUTING --> COMPLETED : success
    EXECUTING --> RETRYING : retryable failure
    RETRYING --> WAITING_FOR_BUDGET : retry
    EXECUTING --> FAILED : non-retryable
    QUEUED --> FAILED : enqueue error
    COMPLETED --> [*]
    FAILED --> [*]
```

### Safe Operating Limits

| Parameter | Value | Rationale |
|---|---|---|
| Safe TPM | 4,800 | 80% of 6,000 limit |
| Safe RPM | 21 | 70% of 30 limit |
| Max input tokens | 126,000 | Model context window minus output reserve |
| Max output tokens | 2,000 | Model max output |
| Circuit breaker threshold | 3 failures | Opens for 60s after 3 consecutive failures |
| Max retries | 3 | With exponential backoff (2s base, 30s max) |

---

## Semantic Enrichment Pipeline

The semantic enrichment layer uses an embedding-first architecture that reduces LLM calls while improving quality.

### Pipeline Flow

```mermaid
flowchart TB
    START(["Segments + Transcript"]) --> EMB["Embedding Clustering"]
    EMB --> BLOCKS["Topic Blocks"]
    BLOCKS --> SYNOPSIS["Deterministic Synopsis per Block"]
    SYNOPSIS --> PRIORITY["Priority Queue"]

    BLOCKS --> SUMMARY["Structured Summary - 1 LLM call"]
    SUMMARY --> PASS1["Pass 1: Segment Annotation"]
    PRIORITY --> PASS1
    BLOCKS --> PASS1
    PASS1 --> ANNOTATIONS["Segment Annotations"]

    ANNOTATIONS --> PASS2["Story Composer: Beam Search"]
    BLOCKS --> PASS2
    SUMMARY --> PASS2
    PASS2 --> BOUNDARIES["Story Boundaries"]

    BOUNDARIES --> DETECT["Story Detection"]
    DETECT --> VALIDATE["Story Validation"]
    VALIDATE --> BLUEPRINTS["Blueprint Generation"]
```

### Token Savings

| Metric | Before | After | Reduction |
|---|---|---|---|
| Pass 1 batches | 98 | 17 | 83% |
| Pass 2 batches | 20 | 5 | 75% |
| Total LLM calls | 118 | 23 | 81% |
| Total tokens | ~145K | ~35K | 76% |

---

## Project Structure

```text
trimora/
├── backend/
│   ├── main.py
│   ├── app/
│   │   ├── app.py
│   │   └── lifespan.py
│   ├── core/                          # V10.1 Pipeline Core
│   │   ├── artifact.py                # Artifact[T], ErrorArtifact
│   │   ├── context.py                 # ExecutionContext, PipelineContext
│   │   ├── dag.py                     # DAGExecutor, ExecutionResult
│   │   ├── orchestrator.py            # PipelineOrchestrator
│   │   └── v101_bridge.py            # Bridge functions for V10.1
│   ├── models/                        # Data Models
│   │   ├── data.py                    # 9 frozen data types
│   │   ├── clip.py                    # ClipCandidate, Portfolio
│   │   ├── reasoning.py               # Event, Evidence
│   │   ├── evaluation.py              # EvaluationRecord
│   │   ├── segment.py                 # AtomicSegment
│   │   ├── semantic.py                # SegmentAnnotation, LLMStoryBoundary
│   │   ├── story.py, story_blueprint.py
│   │   └── transcript.py, topic_block.py
│   ├── config/                        # Configuration
│   │   ├── settings.py                # PipelineSettings (frozen)
│   │   ├── budgets.py                 # StageBudget, STAGE_BUDGETS
│   │   ├── models.py                  # ModelConfig with safe limits
│   │   ├── semantic_config.py         # ComposerDebugLevel, composer constants
│   │   ├── weight_profiles.py         # Domain-specific weight profiles
│   │   └── runtime.yaml
│   ├── services/                      # Services
│   │   ├── deterministic_story_composer.py  # Beam search story composer
│   │   ├── story_detector.py          # Story candidate formation
│   │   ├── story_validator.py         # Story validation
│   │   ├── semantic_service.py        # Pass 1 annotation
│   │   ├── story_reasoner.py          # Legacy LLM Pass 2 (replaced)
│   │   ├── embedding_clusterer.py     # Topic block clustering
│   │   ├── block_synopsis_generator.py
│   │   ├── priority_ranker.py
│   │   ├── transcript_summarizer.py
│   │   ├── blueprint_generator.py
│   │   ├── coverage_analyzer.py
│   │   ├── llm_provider.py            # ProviderRouter, GroqProvider
│   │   ├── prompt_store.py, prompt_factory.py
│   │   ├── payload_validator.py, payload_splitter.py
│   │   ├── token_counter.py
│   │   ├── audio_service.py, whisper_manager.py
│   │   ├── transcription_service.py
│   │   ├── segmentation_service.py
│   │   ├── feature_service.py, graph_service.py
│   │   ├── scoring_service.py, embedding_service.py
│   │   ├── preview_service.py, rendering_service.py
│   │   └── snapshots.py
│   ├── execution/                     # LLM Scheduler
│   │   ├── scheduler.py               # LLMScheduler
│   │   ├── provider_adapter.py        # ProviderAdapter
│   │   ├── model_registry.py          # ModelRegistry
│   │   ├── token_budget.py            # TokenBudget
│   │   ├── circuit_breaker.py         # CircuitBreaker
│   │   ├── execution_policy.py        # ExecutionPolicy
│   │   ├── models.py                  # LLMTask, TaskState
│   │   └── repository.py, profiler.py
│   ├── strategies/                    # V10.1 Clip Strategies
│   │   ├── base.py                    # ClipStrategy ABC
│   │   └── builtin.py                 # Story, Hook, Reveal, Reaction, Opinion
│   ├── objectives/                    # V10.1 Scoring Objectives
│   │   ├── base.py                    # Objective ABC
│   │   ├── registry.py                # ObjectiveRegistry (DAG)
│   │   └── builtin.py                 # 10 built-in objectives
│   ├── optimization/                  # V10.1 Optimization
│   │   ├── narrative.py               # NarrativeOptimizer
│   │   ├── portfolio.py               # PortfolioOptimizer (MMR)
│   │   └── deduplication.py           # CandidateDeduplicationService
│   ├── evaluation/
│   │   └── layer.py                   # EvaluationLayer
│   ├── graph/
│   │   ├── evidence.py                # EvidenceGraph
│   │   └── persistent.py              # PersistentKnowledgeGraph
│   ├── ranking/                       # Multi-stage ranking
│   │   ├── pipeline.py                # RankingEngine
│   │   ├── hard_constraints.py, narrative.py, context.py
│   │   ├── hook_quality.py, density.py, retention.py
│   │   ├── novelty.py, confidence.py
│   │   ├── tie_breaker.py, explanation.py, optimizer.py
│   │   └── models.py
│   ├── pipelines/
│   │   ├── production_pipeline.py     # Main pipeline
│   │   ├── orchestrator.py, event_bus.py
│   │   ├── learning_pipeline.py, analytics_pipeline.py
│   ├── storage/
│   │   ├── file_store.py, job_store.py
│   │   ├── manifest_store.py, state_store.py
│   ├── workers/
│   │   ├── scheduler.py, worker_pool.py
│   │   ├── transcription_worker.py, feature_worker.py
│   │   └── clip_worker.py, learning_worker.py
│   ├── api/routes/                    # API endpoints
│   ├── utils/                         # Utilities
│   └── tests/                         # 274+ tests
│       ├── unit/                      # Unit tests
│       └── integration/               # Integration tests
├── frontend/
│   └── src/
│       ├── app/                       # App, Router
│       ├── pages/                     # Upload, Status, Preview, Results, Settings
│       ├── components/                # UI components
│       ├── hooks/                     # React hooks
│       ├── services/                  # API services
│       ├── store/                     # State management
│       └── types/                     # TypeScript types
├── shared/                            # Shared contracts and schemas
├── docker/                            # Dockerfiles
├── storage/                           # Runtime job data
├── docker-compose.yml
├── start.bat
└── smoke_test.py
```

---

## Production Pipeline

The pipeline processes videos through sequential stages with automatic budget enforcement, deterministic artifact tracking, and the LLM Scheduler for all LLM calls.

```mermaid
flowchart TB
    START(["Start"]) --> CHK{"FFmpeg installed?"}
    CHK -->|"No"| FAIL1["Fail: ffmpeg not found"]
    CHK -->|"Yes"| EXT["Extract Audio"]

    EXT --> PLAN["Plan Chunks"]
    PLAN --> SPLIT["Split Audio Chunks"]

    SPLIT --> TRANS["Parallel Transcription"]
    TRANS --> RATE{"Rate Limit"}
    RATE -->|"Groq"| GROQ_CALL["Groq API"]
    RATE -->|"Fallback"| GEMINI_CALL["Gemini API"]

    GROQ_CALL --> MERGE["Merge Transcripts"]
    GEMINI_CALL --> MERGE

    MERGE --> SEG["Atomic Segmentation"]
    SEG --> FEAT["Feature Extraction"]
    FEAT --> GRAPH["Knowledge Graph"]

    GRAPH --> EMB["Embedding Clustering"]
    EMB --> BLOCKS["Topic Blocks"]
    BLOCKS --> SYN["Block Synopses"]
    SYN --> PQ["Priority Queue"]

    BLOCKS --> LLM_SCHED["LLM Scheduler"]
    PQ --> LLM_SCHED
    LLM_SCHED --> SUM["Structured Summary"]
    SUM --> P1["Pass 1: Segment Annotation"]
    P1 --> P2["Story Composer: Beam Search"]

    P2 --> DET["Story Detection"]
    DET --> REPAIR["Story Repair"]
    REPAIR --> VALID["Story Validation"]
    VALID --> COV["Coverage Analysis"]
    COV --> BLUE["Blueprint Generation"]

    BLUE --> STRAT["Strategy Execution - 5 strategies"]
    STRAT --> DEDUP["Candidate Deduplication"]
    DEDUP --> OBJ["Objective Scoring - 10 objectives"]
    OBJ --> NARR["Narrative Optimization"]
    NARR --> PORT["Portfolio Optimization"]
    PORT --> EVAL["Evaluation Recording"]
    EVAL --> SNAP["Pipeline Snapshot"]

    SNAP --> PREV["Preview Manifest"]
    PREV --> EXPORT["Render MP4"]
    EXPORT --> LEARN["Analytics and Learning"]
    LEARN --> DONE(["Complete"])

    EXT -->|"Error"| FAIL2["Fail: extraction error"]
    TRANS -->|"Error"| FAIL3["Fail: transcription error"]
```

### Pipeline Stages

| # | Stage | Description |
|---|---|---|
| 1 | FFmpeg Check | Verify ffmpeg/ffprobe are installed |
| 2 | Audio Extraction | Extract audio as OGG/Opus via FFmpeg |
| 3 | Chunk Planning | Calculate adaptive chunk sizes |
| 4 | Chunk Splitting | Split audio into chunk files |
| 5 | Transcription | Parallel transcription via Faster-Whisper |
| 6 | Merge | Deduplicate and merge transcripts |
| 7 | Segmentation | Split into atomic segments |
| 8 | Feature Extraction | Compute audio energy, text density, structure |
| 9 | Embedding Clustering | Group segments into topic blocks |
| 10 | Block Synopses | Generate deterministic synopses |
| 11 | Structured Summary | Global video summary via LLM Scheduler |
| 12 | Pass 1 | Segment annotation (parallel batches) |
| 13 | Story Composer | Deterministic beam search story composition |
| 14 | Story Detection | Candidate formation and repair |
| 15 | Story Validation | Quality scoring and rejection |
| 16 | Blueprint Generation | Story-to-blueprint conversion |
| 17 | Strategy Execution | Run 5 clip strategies |
| 18 | Candidate Deduplication | Similarity-based dedup |
| 19 | Objective Scoring | Score with 10 objectives (DAG order) |
| 20 | Narrative Optimization | Sort for narrative flow |
| 21 | Portfolio Optimization | MMR + diversity selection |
| 22 | Evaluation Recording | Save evaluation records |
| 23 | Multi-Stage Ranking | 11-stage ranking engine |
| 24 | Preview | Build preview manifest |
| 25 | Export | Render top clip as MP4 |
| 26 | Learning | Save analytics and learning data |

---

## Job Lifecycle

```mermaid
stateDiagram-v2
    [*] --> uploaded
    uploaded --> queued : POST /api/process
    queued --> extracting_audio : Pipeline start
    extracting_audio --> chunking : Audio extracted
    chunking --> transcribing : Chunks ready
    transcribing --> merging : All chunks transcribed
    merging --> segmenting : Transcript merged
    segmenting --> analyzing : Segments built
    analyzing --> scoring : Semantic enrichment
    scoring --> preview_ready : Clips ranked
    preview_ready --> export_ready : Preview built
    export_ready --> complete : MP4 rendered

    queued --> failed
    analyzing --> failed
    scoring --> failed

    queued --> cancelled
    extracting_audio --> cancelled
    chunking --> cancelled
    transcribing --> cancelled
    cancelled --> [*]

    complete --> [*]
    failed --> queued : POST /api/retry
```

---

## API Reference

### Base URL

```
http://localhost:8000
```

### Endpoints

#### Health Check

```
GET /api/health
```

**Response:**
```json
{
  "status": "ok",
  "service": "trimora-backend"
}
```

---

#### Process Video

```
POST /api/process
Content-Type: multipart/form-data
```

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `file` | File | Yes | Video file (.mp4, .mov, .mkv, .webm, .m4v) |

**Constraints:**
- Max file size: 2 GB
- Allowed formats: `.mp4`, `.mov`, `.mkv`, `.webm`, `.m4v`

**Response:**
```json
{
  "job_id": "b7047bdb-53e4-4306-ae57-a2115316fc0c",
  "status": "uploaded",
  "progress": 0.0
}
```

**Errors:**
- `400` - Invalid file type or empty file
- `413` - File too large (over 2 GB)

---

#### Get Job Status

```
GET /api/status/{job_id}
```

**Parameters:**

| Name | Type | Location | Description |
|---|---|---|---|
| `job_id` | UUID | path | Job identifier |

**Response:**
```json
{
  "job_id": "b7047bdb-53e4-4306-ae57-a2115316fc0c",
  "status": "analyzing",
  "progress": 0.72,
  "created_at": "2026-07-03T12:00:00Z",
  "updated_at": "2026-07-03T12:01:30Z",
  "error": null,
  "preview_count": 0,
  "export_count": 0,
  "stats": null
}
```

**Errors:**
- `404` - Job not found

---

#### Get Preview

```
GET /api/preview/{job_id}
```

**Parameters:**

| Name | Type | Location | Description |
|---|---|---|---|
| `job_id` | UUID | path | Job identifier |

**Response:**
```json
{
  "job_id": "b7047bdb-53e4-4306-ae57-a2115316fc0c",
  "clips": [
    {
      "id": "clip_001",
      "title": "Opening Hook",
      "hook_start": 12.5,
      "hook_end": 18.2,
      "body_start": 18.2,
      "body_end": 45.0,
      "ending_start": 45.0,
      "ending_end": 52.3,
      "duration": 39.8,
      "total_score": 0.82,
      "status": "ready"
    }
  ]
}
```

---

#### Get Result

```
GET /api/result/{job_id}
```

**Response:**
```json
{
  "job": { "...job record..." },
  "preview": { "...preview manifest..." },
  "export_available": true,
  "export_path": "storage/jobs/<id>/exports/reel_001.mp4"
}
```

---

#### Retry Job

```
POST /api/retry/{job_id}
```

Retries a failed or cancelled job from the beginning.

**Response:**
```json
{
  "job_id": "b7047bdb-53e4-4306-ae57-a2115316fc0c",
  "status": "queued"
}
```

---

#### Cancel Job

```
POST /api/cancel/{job_id}
```

Cancels a running job. The pipeline checks for cancellation between each stage.

**Response:**
```json
{
  "job_id": "b7047bdb-53e4-4306-ae57-a2115316fc0c",
  "status": "cancelled"
}
```

---

#### Export / Check Export

```
POST /api/export/{job_id}
```

Triggers or checks export readiness.

**Response:**
```json
{
  "job_id": "b7047bdb-53e4-4306-ae57-a2115316fc0c",
  "export_path": "storage/jobs/<id>/exports/reel_001.mp4"
}
```

---

#### Download Export

```
GET /api/download/{job_id}
```

Downloads the rendered MP4 file.

**Response:** Binary file download (`video/mp4`)

**Filename:** `trimora_reel_001.mp4`

**Errors:**
- `404` - Export not found

---

### API Flow

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant A as FastAPI
    participant O as Orchestrator
    participant P as Pipeline
    participant S as Storage

    U->>F: Select video file
    F->>A: POST /api/process
    A->>S: Create job directory
    A->>O: start_job(job_id)
    A-->>F: job_id status uploaded

    loop Every 2.5s
        F->>A: GET /api/status
        A->>S: Read state.json
        A-->>F: status progress
    end

    O->>P: run(job_id)
    P->>S: Extract audio
    P->>S: Split chunks
    P->>S: Transcribe
    P->>S: Merge transcripts
    P->>S: Build segments
    P->>S: Extract features
    P->>S: Embedding clustering
    P->>S: Generate summary
    P->>S: Pass 1 annotation
    P->>S: Story composer
    P->>S: Story detection
    P->>S: Score candidates
    P->>S: Rank clips
    P->>S: Build preview
    P->>S: Render MP4

    F->>A: GET /api/preview
    A->>S: Read preview_manifest.json
    A-->>F: PreviewManifest

    U->>F: Click download
    F->>A: GET /api/download
    A->>S: Read MP4 file
    A-->>F: File response
```

---

## Fallback Mechanisms

Trimora implements graceful degradation at multiple levels.

### Transcription Provider Fallback

```mermaid
flowchart TD
    START["Transcription Request"] --> PROVIDER{"Provider?"}

    PROVIDER -->|"whisper"| WHISPER{"Model loaded?"}
    WHISPER -->|"Yes"| LOCAL["Local CPU/GPU"]
    WHISPER -->|"No"| LOAD["Load Model"]
    LOAD --> LOCAL

    PROVIDER -->|"groq"| GROQ{"API Key?"}
    GROQ -->|"Yes"| GROQ_CALL["Groq API"]
    GROQ -->|"No"| GEMINI

    PROVIDER -->|"gemini"| GEMINI{"API Key?"}
    GEMINI -->|"Yes"| GEMI_CALL["Gemini API"]
    GEMINI -->|"No"| STUB["Stub"]

    GROQ_CALL -->|"Success"| RESULT["Result"]
    GROQ_CALL -->|"429"| RETRY["Retry"]
    RETRY --> GROQ_CALL

    GEMI_CALL -->|"Success"| RESULT
    GEMI_CALL -->|"Error"| STUB

    LOCAL --> RESULT
    STUB --> RESULT
```

| Priority | Provider | Model | Fallback Trigger |
|---|---|---|---|
| 1 (Primary) | Faster-Whisper | auto (tiny to large-v3) | Model not installed, GPU unavailable |
| 2 (Fallback) | Groq | whisper-large-v3-turbo | API key missing, rate limit exceeded |
| 3 (Fallback) | Gemini | gemini-2.0-flash | API key missing, API error |
| 4 (Stub) | Local | Generated text | No API keys configured |

### Embedding Fallback

| Priority | Method | Model | Fallback Trigger |
|---|---|---|---|
| 1 (Primary) | Sentence-transformers | all-MiniLM-L6-v2 | Library not installed |
| 2 (Fallback) | TF-IDF | Hash-based 384-dim | Always available |

### LLM Provider Fallback (Semantic Enrichment)

| Priority | Provider | Model | Fallback Trigger |
|---|---|---|---|
| 1 (Primary) | Groq | Llama 3.1 | API key missing, rate limit |
| 2 (Fallback) | Gemini | gemini-2.0-flash | API key missing |
| 3 (Rule-based) | Local | Heuristic | No API keys configured |

#### ProviderRouter (Multi-Key Load Balancing)

```mermaid
flowchart LR
    REQ["LLM Request"] --> ROUTER["ProviderRouter"]
    ROUTER --> B1["groq-1"]
    ROUTER --> B2["groq-2"]
    ROUTER --> B3["groq-3"]
    ROUTER --> B4["gemini"]
    B1 --> G1["Groq API"]
    B2 --> G1
    B3 --> G1
    B4 --> G2["Gemini API"]
```

**Configuration** - each key on its own line in `.env`:
```bash
GROQ_API_KEY_1=gsk_abc123...
GROQ_API_KEY_2=gsk_def456...
GROQ_API_KEY_3=gsk_ghi789...
GEMINI_API_KEY=AIza...
```

---

## Ranking Engine

The ranking engine uses multiple stages to score and select the best clips.

```mermaid
flowchart LR
    C["Candidates"] --> HC["Hard Constraints"]
    HC --> NV["Narrative Validation"]
    NV --> CTX["Context Coherence"]
    CTX --> HQ["Hook Quality"]
    HQ --> ID["Information Density"]
    ID --> RP["Retention Prediction"]
    RP --> ND["Novelty/Dedup"]
    ND --> FINAL["Final Score"]
    FINAL --> MMR["MMR Optimization"]
    MMR --> RANKED["Ranked Clips"]
```

### Scoring Formula

```
total_score = hook_score * 0.35 + body_score * 0.25 + ending_score * 0.20 + flow_score * 0.20
```

### Ranking Stages

| Stage | Module | Purpose |
|---|---|---|
| 1 | `hard_constraints.py` | Filter: duration 15-90s, chronological order, max 30s gap |
| 2 | `narrative.py` | Semantic coherence via embedding similarity |
| 3 | `context.py` | Contextual coherence: pronoun consistency, shared nouns |
| 4 | `hook_quality.py` | Hook effectiveness: duration, questions, curiosity words |
| 5 | `density.py` | Information density: words/sec, specificity bonuses |
| 6 | `retention.py` | Viewer retention prediction: CTA, flow, duration |
| 7 | `novelty.py` | Semantic deduplication via cosine similarity (threshold 0.75) |
| 8 | `tie_breaker.py` | Tie-breaking: confidence, hook, duration, position |
| 9 | `confidence.py` | Confidence scoring: audio source, feature completeness |
| 10 | `explanation.py` | Human-readable ranking explanations |
| 11 | `optimizer.py` | MMR optimization: quality (0.7) + diversity (0.3) |

---

## Frontend

The frontend is a React SPA with 5 pages and a dark-themed UI.

```mermaid
flowchart TB
    subgraph Pages["Pages"]
        UP["Upload Page"]
        SP["Status Page"]
        PP["Preview Page"]
        RP["Results Page"]
        SET["Settings Page"]
    end

    subgraph State["State"]
        JS["jobStore"]
        PS["previewStore"]
        UI["uiStore"]
    end

    UP -->|"Upload"| JS
    JS -->|"Poll status"| SP
    JS -->|"Fetch preview"| PP
    PP -->|"Select clips"| PS
    PP -->|"Download"| RP
    SET -->|"Configure"| UI
```

### Pages

| Page | Route | Purpose |
|---|---|---|
| Upload | `/upload` | File picker, drag-and-drop upload |
| Status | `/status` | Progress timeline, job summary, retry/cancel |
| Preview | `/preview` | Clip grid with scores, export button |
| Results | `/results` | Final output, clip list, download |
| Settings | `/settings` | API base URL configuration |

### State Management

| Store | Hook | Purpose |
|---|---|---|
| `jobStore` | `useJobState()` | Job ID, status, preview, polling (2.5s interval) |
| `previewStore` | `usePreviewSelection()` | Clip selection toggle |
| `uiStore` | `useUiState()` | Theme, API base URL |

---

## Configuration

### Environment Variables

```bash
# Storage
TRIMORA_STORAGE_ROOT=./storage
TRIMORA_JOBS_ROOT=./storage/jobs

# Workers
TRIMORA_MAX_TRANSCRIPTION_WORKERS=5
TRIMORA_MAX_FEATURE_WORKERS=15
TRIMORA_MAX_CLIP_WORKERS=8

# Chunking
TRIMORA_MIN_CHUNK_SECONDS=30
TRIMORA_MAX_CHUNK_SECONDS=120
TRIMORA_OVERLAP_SECONDS=2

# Transcription
TRIMORA_TRANSCRIPTION_PROVIDER=faster-whisper
TRIMORA_TRANSCRIPTION_TIMEOUT=600

# Local Transcription (Faster-Whisper)
WHISPER_MODEL_SIZE=auto
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=auto
WHISPER_BEAM_SIZE=5
WHISPER_VAD_FILTER=true
WHISPER_LANGUAGE=null

# CORS
TRIMORA_CORS_ORIGINS=*

# Frontend
VITE_API_BASE_URL=http://localhost:8000

# API Keys (required for cloud transcription)
GROQ_API_KEY_1=gsk_...
GROQ_API_KEY_2=gsk_...
GROQ_API_KEY_3=gsk_...
GEMINI_API_KEY=AIza...
```

### Runtime Configuration

Settings are loaded in order: defaults, `runtime.yaml`, environment variables.

```yaml
# backend/config/runtime.yaml
workers:
  max_transcription_workers: 15
  max_feature_workers: 15
  max_clip_workers: 8

chunking:
  min_seconds: 30
  max_seconds: 120
  overlap_seconds: 2
  bitrate: "64k"
  keep_chunks: true

storage:
  root: ./storage
  jobs_root: ./storage/jobs

job:
  retry_count: 3
  transcription_provider: "faster-whisper"
  transcription_timeout_seconds: 600
  export_timeout_seconds: 600

whisper:
  model_size: "auto"
  device: "cuda"
  compute_type: "auto"
  beam_size: 5
  language: null
  vad_filter: true
  vad_min_silence_ms: 500

thresholds:
  min_segment_seconds: 1.2
  min_candidate_score: 0.35
  preview_top_k: 20

semantic:
  batch_size: 10
  context_overlap: 2
  batch_delay_seconds: 0.0

models:
  groq_llama_8b:
    name: "llama-3.1-8b-instant"
    provider: "groq"
    context_window: 128000
    max_input_tokens: 126000
    max_output_tokens: 2000
    rpm_limit: 30
    tpm_limit: 6000
    rpd_limit: 14400
    chars_per_token: 3.7

scheduler:
  workers: 1
  max_retries: 3
  base_delay: 2.0
  max_delay: 30.0
  request_timeout: 90.0
  circuit_breaker:
    failure_threshold: 3
    open_duration: 60.0
```

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- FFmpeg (in PATH)
- Faster-Whisper (for local transcription, GPU recommended)
- At least one API key (Groq or Gemini) only if using cloud transcription

### Quick Start (Windows)

```bash
git clone https://github.com/yourusername/trimora.git
cd trimora
copy .env.example .env
# Edit .env with your API keys
start.bat
```

### Manual Setup

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd frontend
npm install

# Start backend (port 8000)
cd ../backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Start frontend (port 5173)
cd ../frontend
npm run dev
```

### Transcription Setup

#### Local Transcription (Faster-Whisper)

No API keys required. Faster-Whisper runs locally on your machine with GPU acceleration.

```bash
pip install faster-whisper
TRIMORA_TRANSCRIPTION_PROVIDER=faster-whisper
WHISPER_MODEL_SIZE=auto
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=auto
```

#### Cloud Transcription (Groq/Gemini)

Requires API keys. Faster than local on CPU, but requires internet connection.

```bash
TRIMORA_TRANSCRIPTION_PROVIDER=groq
GROQ_API_KEY_1=gsk_...
GROQ_API_KEY_2=gsk_...
GEMINI_API_KEY=AIza...
```

---

## Docker

### Docker Compose

```bash
docker-compose up --build
```

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`

### Services

| Service | Port | Description |
|---|---|---|
| backend | 8000 | FastAPI + FFmpeg |
| frontend | 3000 | Nginx + React build |

### Dockerfiles

- `docker/Dockerfile.backend` - Python 3.11-slim + FFmpeg
- `docker/Dockerfile.frontend` - Multi-stage: Node 20 build + Nginx serve

---

## Storage

Each job is self-contained in `storage/jobs/{job_id}/`:

```text
storage/jobs/{job_id}/
├── input/
├── audio/
│   ├── audio.opus
│   └── chunks/
├── transcript/
│   ├── transcript.json
│   └── words.json
├── segments/
│   └── atomic_segments.json
├── features/
│   └── feature_vectors.json
├── graph/
│   └── local_graph.json
├── semantic/
│   ├── segment_embeddings.json
│   ├── topic_blocks.json
│   ├── block_synopses.json
│   ├── block_embeddings.json
│   ├── priority_queue.json
│   ├── summary.json
│   ├── segment_annotations.json
│   ├── pass1_raw.json
│   └── pass2_raw.json
├── stories/
│   ├── story_candidates.json
│   ├── validated_stories.json
│   └── story_reasoning.json
├── clips/
│   ├── candidates.json
│   ├── story_blueprints.json
│   ├── ranked_clips.json
│   ├── preview_manifest.json
│   └── generation_state.json
├── evaluations/
│   └── eval_*.json
├── snapshots/
│   └── *.json
├── learning/
├── analytics/
├── exports/
│   └── reel_001.mp4
├── state.json
└── metadata.json
```

---

## Testing

```bash
# Run all tests (274+ tests)
python -m pytest backend/tests/ -v

# Run V10.1 pipeline core tests
python -m pytest backend/tests/test_strategies.py backend/tests/test_objectives.py backend/tests/test_deduplication.py backend/tests/test_evaluation.py backend/tests/test_integration.py -v

# Run pipeline contract tests
python -m pytest backend/tests/test_pipeline_contracts.py -v

# Run deterministic story composer tests
python -m pytest backend/tests/unit/test_deterministic_story_composer.py -v

# Run existing unit tests only
python -m pytest backend/tests/unit/ -v

# Run with coverage
python -m pytest backend/tests/ --cov=backend --cov-report=term-missing
```

### Smoke Test

```bash
# Full pipeline smoke test
python smoke_test.py
```

---

## License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

```
MIT License - Copyright (c) 2026 Trimora
```
