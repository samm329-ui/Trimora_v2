import { useState } from "react";
import { uploadVideo } from "../services/uploadService";

export function useUpload() {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  async function startUpload(file: File) {
    setUploading(true);
    setUploadError(null);
    try {
      return await uploadVideo(file);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      setUploadError(message);
      throw err;
    } finally {
      setUploading(false);
    }
  }

  return { uploading, uploadError, startUpload };
}
