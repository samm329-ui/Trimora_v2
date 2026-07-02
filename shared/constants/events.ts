export const PIPELINE_EVENTS = [
  "job_created",
  "audio_extracted",
  "chunk_plan_ready",
  "transcription_completed",
  "segments_built",
  "features_computed",
  "candidates_ranked",
  "preview_ready",
  "export_ready",
  "job_failed"
] as const;
