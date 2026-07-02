import { request } from "./api";
import type { JobRecord } from "../types/job";
import type { ResultResponse } from "../types/api";

export async function getJobStatus(jobId: string): Promise<JobRecord> {
  return request<JobRecord>(`/api/status/${jobId}`);
}

export async function getJobResult(jobId: string): Promise<ResultResponse> {
  return request<ResultResponse>(`/api/result/${jobId}`);
}

export async function retryJob(jobId: string): Promise<{ job_id: string; status: string }> {
  return request(`/api/retry/${jobId}`, { method: "POST" });
}

export async function cancelJob(jobId: string): Promise<{ job_id: string; status: string }> {
  return request(`/api/cancel/${jobId}`, { method: "POST" });
}
