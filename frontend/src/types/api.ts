import type { JobRecord, PreviewManifest } from "./job";

export interface ProcessResponse {
  job_id: string;
  status: string;
  progress: number;
}

export interface ResultResponse {
  job: JobRecord;
  preview: PreviewManifest | Record<string, never>;
  export_available: boolean;
  export_path?: string | null;
}
