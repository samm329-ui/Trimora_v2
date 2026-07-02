export type JobStatus =
  | "uploaded"
  | "queued"
  | "extracting_audio"
  | "chunking"
  | "transcribing"
  | "merging"
  | "segmenting"
  | "analyzing"
  | "scoring"
  | "preview_ready"
  | "export_ready"
  | "complete"
  | "cancelled"
  | "failed";

export interface JobRecord {
  job_id: string;
  status: JobStatus;
  progress: number;
  created_at?: string;
  updated_at?: string;
  error?: string | null;
  preview_count?: number;
  export_count?: number;
  stats?: Record<string, unknown>;
}

export interface PreviewClip {
  id: string;
  title: string;
  hook_start: number;
  hook_end: number;
  body_start: number;
  body_end: number;
  ending_start: number;
  ending_end: number;
  duration: number;
  total_score: number;
  status: string;
  transcript_snippet?: string;
}

export interface PreviewManifest {
  job_id: string;
  clips: PreviewClip[];
}
