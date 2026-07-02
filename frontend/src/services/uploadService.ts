import { request } from "./api";
import type { ProcessResponse } from "../types/api";

export async function uploadVideo(file: File): Promise<ProcessResponse> {
  const form = new FormData();
  form.append("file", file);

  return request<ProcessResponse>("/api/process", {
    method: "POST",
    body: form
  });
}
