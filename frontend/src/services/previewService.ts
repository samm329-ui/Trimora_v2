import { request } from "./api";
import type { PreviewManifest } from "../types/job";

export async function getPreview(jobId: string): Promise<PreviewManifest> {
  return request<PreviewManifest>(`/api/preview/${jobId}`);
}
