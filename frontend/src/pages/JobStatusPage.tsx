import type { JobRecord } from "../types/job";
import { ProgressTimeline } from "../components/status/ProgressTimeline";
import { Button } from "../components/shared/Button";

export function JobStatusPage({
  job,
  onRefresh,
  onRetry,
  onCancel
}: {
  job: JobRecord | null;
  onRefresh: () => void;
  onRetry: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
      <ProgressTimeline job={job} />
      <div className="grid gap-4">
        <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg">
          <div className="mb-2 text-base font-semibold">Job summary</div>
          <div className="space-y-2 text-sm text-slate-300">
            <div>Job ID: {job?.job_id ?? "—"}</div>
            <div>Preview clips: {job?.preview_count ?? 0}</div>
            <div>Exports: {job?.export_count ?? 0}</div>
          </div>
        </div>
        <div className="flex gap-2">
          <Button onClick={onRefresh}>Refresh</Button>
          <Button onClick={onRetry}>Retry</Button>
          <Button onClick={onCancel}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}
