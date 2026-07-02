import type { PreviewClip } from "../../types/job";
import { ClipCard } from "../cards/ClipCard";

export function PreviewGrid({
  clips,
  selectedIds,
  onToggle
}: {
  clips: PreviewClip[];
  selectedIds: string[];
  onToggle?: (clip: PreviewClip) => void;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {clips.map((clip) => (
        <ClipCard
          key={clip.id}
          clip={clip}
          selected={selectedIds.includes(clip.id)}
          onToggle={onToggle}
        />
      ))}
    </div>
  );
}
