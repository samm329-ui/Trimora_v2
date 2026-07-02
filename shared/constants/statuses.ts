export const JOB_STATUSES = [
  "uploaded",
  "queued",
  "extracting_audio",
  "chunking",
  "transcribing",
  "merging",
  "segmenting",
  "analyzing",
  "scoring",
  "preview_ready",
  "export_ready",
  "complete",
  "cancelled",
  "failed"
] as const;
