import type { PreviewClip } from "../types/job";
import { Button } from "../components/shared/Button";

export function ResultsPage({
  clips,
  exportPath
}: {
  clips: PreviewClip[];
  exportPath: string | null;
}) {
  return (
    <div className="grid gap-5">
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg">
        <h2 className="mb-2 text-xl font-semibold">Results</h2>
        <p className="text-sm text-slate-400">
          Final output and selected preview items are displayed here when the backend marks the job export-ready or complete.
        </p>
        <div className="mt-3 text-sm text-slate-300">
          Export path: {exportPath ?? "not available yet"}
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {clips.map((clip) => (
          <div key={clip.id} className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="font-medium">{clip.title}</div>
            <div className="mt-1 text-sm text-slate-400">Score {clip.total_score.toFixed(2)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
