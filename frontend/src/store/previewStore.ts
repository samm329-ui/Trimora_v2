import { useState } from "react";
import type { PreviewClip } from "../types/job";

export function usePreviewSelection() {
  const [selectedClipIds, setSelectedClipIds] = useState<string[]>([]);

  function toggleClip(clip: PreviewClip) {
    setSelectedClipIds((current) =>
      current.includes(clip.id)
        ? current.filter((id) => id !== clip.id)
        : [...current, clip.id]
    );
  }

  return { selectedClipIds, toggleClip };
}
