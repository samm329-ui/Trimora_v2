# Trimora Backend Scaffold

This backend is organized to match the technical requirement document:
- `app/` owns FastAPI startup and lifespan
- `api/` owns public endpoints and middleware
- `pipelines/` owns job orchestration, analytics, and learning
- `workers/` owns bounded execution wrappers
- `services/` owns audio, transcription, segmentation, feature, graph, scoring, rendering, and preview logic
- `models/` owns typed job/transcript/segment/clip/feature/graph/learning schemas
- `storage/` owns local filesystem persistence
- `config/` owns runtime configuration
- `utils/` owns reusable helpers

Lifecycle:
`uploaded → queued → extracting_audio → chunking → transcribing → merging → segmenting → analyzing → scoring → preview_ready → export_ready → complete`

Endpoints:
- `POST /api/process`
- `GET /api/status/{job_id}`
- `GET /api/preview/{job_id}`
- `GET /api/result/{job_id}`
- `POST /api/retry/{job_id}`
- `POST /api/cancel/{job_id}`

The code is intentionally modular so a database adapter or queue system can replace the local storage and in-process orchestration later without changing the API contract.
