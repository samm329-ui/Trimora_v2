import { useState } from "react";
import type { PreviewClip } from "../types/job";
import { PreviewGrid } from "../components/preview/PreviewGrid";
import { Button } from "../components/shared/Button";

export function PreviewPage({
  clips,
  selectedIds,
  onToggle,
  jobId,
  exportAvailable
}: {
  clips: PreviewClip[];
  selectedIds: string[];
  onToggle: (clip: PreviewClip) => void;
  jobId: string | null;
  exportAvailable: boolean;
}) {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  async function handleExport() {
    if (!jobId) return;
    setExporting(true);
    setExportError(null);
    try {
      const res = await fetch(`/api/export/${jobId}`, { method: "POST" });
      if (!res.ok) throw new Error("Export failed");
      const data = await res.json();
      const anchor = document.createElement("a");
      anchor.href = `/api/download/${jobId}`;
      anchor.download = "trimora_reel_001.mp4";
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="grid gap-4">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">Preview shorts</h2>
          <p className="text-sm text-slate-400">These come from the backend preview manifest.</p>
        </div>
        <div className="flex items-center gap-3">
          <Button onClick={handleExport} disabled={!exportAvailable || exporting}>
            {exporting ? "Exporting..." : exportAvailable ? "Download reel" : "Export pending"}
          </Button>
          <div className="text-sm text-slate-300">{clips.length} clips</div>
        </div>
      </div>
      {exportError ? <div className="text-sm text-red-300">{exportError}</div> : null}
      <PreviewGrid clips={clips} selectedIds={selectedIds} onToggle={onToggle} />
    </div>
  );
}
