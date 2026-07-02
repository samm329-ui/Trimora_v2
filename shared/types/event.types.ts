export interface PipelineEvent {
  job_id: string;
  name: string;
  payload: Record<string, unknown>;
}
