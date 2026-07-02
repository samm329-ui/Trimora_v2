import { useState } from "react";
import { UploadDropzone } from "../components/upload/UploadDropzone";
import { Button } from "../components/shared/Button";

export function UploadPage({
  onUpload,
  uploading
}: {
  onUpload: (file: File) => Promise<void>;
  uploading: boolean;
}) {
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="grid gap-6">
      <UploadDropzone
        disabled={uploading}
        onFile={async (file) => {
          setError(null);
          try {
            await onUpload(file);
          } catch (err) {
            setError(err instanceof Error ? err.message : "Upload failed");
          }
        }}
      />
      {uploading ? (
        <div className="flex items-center gap-2 text-sm text-slate-300">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-400 border-t-transparent" />
          Uploading and processing...
        </div>
      ) : null}
      {error ? <div className="text-sm text-red-300">{error}</div> : null}
      <p className="text-sm text-slate-400">
        The frontend only submits the file and reads the backend response. All processing state comes from polling.
      </p>
    </div>
  );
}
