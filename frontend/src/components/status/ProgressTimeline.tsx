import type { JobRecord } from "../../types/job";

const ORDER = [
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
  "complete"
] as const;

export function ProgressTimeline({ job }: { job: JobRecord | null }) {
  const activeIndex = job ? ORDER.indexOf(job.status as (typeof ORDER)[number]) : -1;

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-base font-semibold">Processing state</div>
          <div className="text-sm text-slate-400">{job?.status ?? "idle"}</div>
        </div>
        <div className="text-sm text-slate-300">{Math.round((job?.progress ?? 0) * 100)}%</div>
      </div>
      <div className="grid gap-2">
        {ORDER.map((step, index) => {
          const done = activeIndex >= index && activeIndex !== -1;
          return (
            <div
              key={step}
              className={`flex items-center justify-between rounded-xl px-3 py-2 text-sm ${
                done ? "bg-emerald-500/15 text-emerald-300" : "bg-slate-800/70 text-slate-400"
              }`}
            >
              <span>{step.replace(/_/g, " ")}</span>
              <span>{done ? "done" : "pending"}</span>
            </div>
          );
        })}
      </div>
      {job?.error ? (
        <div className="mt-4 rounded-xl border border-red-900 bg-red-950/50 p-3 text-sm text-red-200">
          {job.error}
        </div>
      ) : null}
    </div>
  );
}
