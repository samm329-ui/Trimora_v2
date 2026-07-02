import type { ChangeEvent } from "react";
import { Button } from "../shared/Button";

export function UploadDropzone({
  onFile,
  disabled
}: {
  onFile: (file: File) => void;
  disabled?: boolean;
}) {
  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) onFile(file);
  }

  return (
    <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/60 p-6 shadow-lg">
      <div className="mb-3 text-lg font-semibold">Upload a video</div>
      <p className="mb-5 max-w-xl text-sm text-slate-400">
        Submit one long video and let the backend create a job, process it in the background, and generate previews.
      </p>
      <label className="inline-flex cursor-pointer">
        <input
          type="file"
          accept="video/*"
          className="hidden"
          onChange={handleChange}
          disabled={disabled}
        />
        <Button disabled={disabled}>Choose video</Button>
      </label>
    </div>
  );
}
