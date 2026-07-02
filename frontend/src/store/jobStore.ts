import { useEffect, useMemo, useState } from "react";
import type { JobRecord, PreviewManifest } from "../types/job";
import { getJobStatus, getJobResult } from "../services/jobService";
import { getPreview } from "../services/previewService";

export function useJobState(initialJobId?: string) {
  const [jobId, setJobId] = useState<string | undefined>(initialJobId);
  const [job, setJob] = useState<JobRecord | null>(null);
  const [preview, setPreview] = useState<PreviewManifest | null>(null);
  const [resultPath, setResultPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh(currentJobId = jobId) {
    if (!currentJobId) return;
    setLoading(true);
    setError(null);
    try {
      const status = await getJobStatus(currentJobId);
      setJob(status);
      if (status.status === "preview_ready" || status.status === "export_ready" || status.status === "complete") {
        try {
          const prev = await getPreview(currentJobId);
          setPreview(prev);
        } catch {
          setPreview(null);
        }
      }
      if (status.status === "export_ready" || status.status === "complete") {
        const result = await getJobResult(currentJobId);
        if (typeof result.export_path === "string") {
          setResultPath(result.export_path);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load job");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!jobId) return;
    refresh(jobId);
    const timer = window.setInterval(() => {
      refresh(jobId);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [jobId]);

  return {
    jobId,
    setJobId,
    job,
    preview,
    resultPath,
    loading,
    error,
    refresh
  };
}
