# Trimora Backend

Python 3.11+ backend with FastAPI, Pydantic v2, and asyncio.

## Architecture

- `app/` - FastAPI startup, lifespan, health endpoint
- `api/routes/` - REST endpoints (process, status, preview, export)
- `api/middleware/` - CORS, error handling, request logging
- `pipelines/` - Production pipeline, orchestrator, analytics, learning, event bus
- `services/` - 25 service modules covering all business logic
- `models/` - 12 Pydantic model files (33 classes)
- `ranking/` - 13-stage ranking engine with MMR optimization
- `storage/` - File-based persistence (JSON)
- `workers/` - Async worker pools with semaphore
- `config/` - Settings, runtime.yaml, thresholds, semantic config
- `utils/` - Text, audio, time utilities
- `tests/` - 21 test files, 150 tests

## Semantic Enrichment Pipeline

Embedding-first architecture for LLM-efficient semantic enrichment:

1. **Embedding Clustering** - sentence-transformers groups segments into topic blocks
2. **Block Synopses** - Deterministic per-block summaries
3. **Priority Queue** - Block scheduling for parallel workers
4. **Structured Summary** - 1 LLM call generates global video summary
5. **Pass 1** - Segment annotation with block boundaries and summary context
6. **Pass 2** - Story boundary detection with block-based prompts

## Services

| Service | Purpose |
|---|---|
| AudioService | FFmpeg audio extraction and chunking |
| WhisperManager | Faster-Whisper singleton (local transcription) |
| TranscriptionService | Multi-provider transcription router (Faster-Whisper/Groq/Gemini) |
| SegmentationService | Atomic segment creation |
| FeatureService | Multi-signal feature extraction |
| EmbeddingService | TF-IDF + sentence-transformers |
| EmbeddingClusterer | Topic block clustering |
| BlockSynopsisGenerator | Deterministic block synopses |
| PriorityRanker | Block priority ranking |
| TranscriptSummarizer | Structured video summary |
| SemanticService | Pass 1: segment annotation |
| StoryReasoner | Pass 2: story boundary detection |
| StoryDetector | Candidate formation and repair |
| StoryValidator | Quality scoring and rejection |
| CoverageAnalyzer | Segment coverage analysis |
| BlueprintGenerator | Story-to-blueprint conversion |
| DuplicateGuard | Composite duplicate detection |
| LLMProvider | Groq/Gemini/Rule-based LLM providers + ProviderRouter |
| ScoringService | Candidate scoring |
| RankingEngine | 13-stage ranking with MMR |
| PreviewService | Preview manifest building |
| RenderingService | FFmpeg clip rendering |

## API Endpoints

- `GET /api/health` - Health check
- `POST /api/process` - Upload video, create job
- `GET /api/status/{job_id}` - Job status
- `GET /api/preview/{job_id}` - Preview manifest
- `GET /api/result/{job_id}` - Job result
- `POST /api/retry/{job_id}` - Retry failed job
- `POST /api/cancel/{job_id}` - Cancel running job
- `POST /api/export/{job_id}` - Trigger export
- `GET /api/download/{job_id}` - Download MP4

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Testing

```bash
python -m pytest backend/tests/ -v
```
