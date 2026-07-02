# Event Contracts

## Pipeline Events

| Event Name | Payload | Description |
|------------|---------|-------------|
| job_created | { job_id, filename } | New job created |
| audio_extracted | { job_id, duration } | Audio extracted from video |
| chunk_plan_ready | { job_id, chunks, workers } | Chunk plan calculated |
| transcription_completed | { job_id, chunk_count } | All chunks transcribed |
| segments_built | { job_id, segment_count } | Atomic segments created |
| features_computed | { job_id, feature_count } | Features extracted |
| candidates_ranked | { job_id, candidate_count } | Candidates scored and ranked |
| preview_ready | { job_id, preview_count } | Preview manifest ready |
| export_ready | { job_id, export_path } | Export rendered |
| job_failed | { job_id, error } | Job failed with error |

## Event Bus Usage

Events are published to the EventBus and can be consumed by:
- Learning pipeline (background learning)
- Analytics pipeline (metrics collection)
- Frontend (via WebSocket in future)

## Event Structure

```typescript
interface PipelineEvent {
  job_id: string;
  name: string;
  payload: Record<string, unknown>;
  timestamp: string;
}
```
