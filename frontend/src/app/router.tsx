import { useMemo, useState } from "react";
import { UploadPage } from "../pages/UploadPage";
import { JobStatusPage } from "../pages/JobStatusPage";
import { PreviewPage } from "../pages/PreviewPage";
import { ResultsPage } from "../pages/ResultsPage";
import { SettingsPage } from "../pages/SettingsPage";
import { AppShell } from "../components/layout/AppShell";
import { useJobState } from "../store/jobStore";
import { usePreviewSelection } from "../store/previewStore";
import { useUiState } from "../store/uiStore";
import { retryJob, cancelJob } from "../services/jobService";

export function AppRouter() {
  const jobState = useJobState();
  const previewSelection = usePreviewSelection();
  const uiState = useUiState();
  const [page, setPage] = useState<"upload" | "status" | "preview" | "results" | "settings">("upload");

  const [uploading, setUploading] = useState(false);

  async function handleUpload(file: File) {
    setUploading(true);
    try {
      const res = await (await import("../services/uploadService")).uploadVideo(file);
      jobState.setJobId(res.job_id);
      setPage("status");
    } finally {
      setUploading(false);
    }
  }

  const clips = useMemo(() => jobState.preview?.clips ?? [], [jobState.preview]);
  const exportAvailable = jobState.job?.status === "export_ready" || jobState.job?.status === "complete";

  return (
    <AppShell>
      <nav className="mb-6 flex flex-wrap gap-2">
        {(["upload", "status", "preview", "results", "settings"] as const).map((item) => (
          <button
            key={item}
            onClick={() => setPage(item)}
            className={`rounded-full border px-4 py-2 text-sm ${
              page === item
                ? "border-slate-100 bg-slate-100 text-slate-950"
                : "border-slate-700 bg-slate-900/70 text-slate-300"
            }`}
          >
            {item}
          </button>
        ))}
      </nav>

      {page === "upload" ? <UploadPage onUpload={handleUpload} uploading={uploading} /> : null}
      {page === "status" ? (
        <JobStatusPage
          job={jobState.job}
          onRefresh={() => jobState.refresh()}
          onRetry={async () => {
            if (jobState.jobId) await retryJob(jobState.jobId);
            await jobState.refresh();
          }}
          onCancel={async () => {
            if (jobState.jobId) await cancelJob(jobState.jobId);
            await jobState.refresh();
          }}
        />
      ) : null}
      {page === "preview" ? (
        <PreviewPage
          clips={clips}
          selectedIds={previewSelection.selectedClipIds}
          onToggle={previewSelection.toggleClip}
          jobId={jobState.jobId ?? null}
          exportAvailable={exportAvailable}
        />
      ) : null}
      {page === "results" ? (
        <ResultsPage clips={clips} exportPath={jobState.resultPath} />
      ) : null}
      {page === "settings" ? (
        <SettingsPage apiBase={uiState.apiBase} onApiBaseChange={uiState.setApiBase} />
      ) : null}
    </AppShell>
  );
}
