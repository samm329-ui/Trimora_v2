import { useEffect, useRef, useState } from "react";
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
  const pollingRef = useRef(true);

  async function refresh(currentJobId = jobId): Promise<boolean> {
    if (!currentJobId) return false;
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
      return true;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load job";
      setError(msg);
      return !msg.includes("404");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!jobId) return;
    pollingRef.current = true;
    refresh(jobId);
    const timer = window.setInterval(async () => {
      if (!pollingRef.current) return;
      const ok = await refresh(jobId);
      if (!ok) pollingRef.current = false;
    }, 2500);
    return () => {
      pollingRef.current = false;
      window.clearInterval(timer);
    };
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
