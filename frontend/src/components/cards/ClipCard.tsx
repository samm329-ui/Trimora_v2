import type { PreviewClip } from "../../types/job";
import { Button } from "../shared/Button";

export function ClipCard({
  clip,
  selected,
  onToggle
}: {
  clip: PreviewClip;
  selected?: boolean;
  onToggle?: (clip: PreviewClip) => void;
}) {
  return (
    <article className="flex flex-col gap-3 rounded-2xl border border-slate-800 bg-slate-900/70 p-4 shadow-lg">
      <div className="aspect-video rounded-xl bg-slate-800/80" />
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold">{clip.title}</div>
          <div className="text-xs text-slate-400">Score {clip.total_score.toFixed(2)}</div>
        </div>
        <div className="rounded-full border border-slate-700 px-2 py-1 text-xs text-slate-300">
          {clip.duration.toFixed(1)}s
        </div>
      </div>
      <div className="text-xs leading-5 text-slate-400">{clip.transcript_snippet ?? "Preview snippet unavailable."}</div>
      <div className="flex items-center gap-2">
        <Button onClick={() => onToggle?.(clip)} className="flex-1">
          {selected ? "Selected" : "Select"}
        </Button>
      </div>
    </article>
  );
}
