from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status/{job_id}")
async def status(job_id: str, request: Request):
    job_store = request.app.state.job_store
    try:
        job = job_store.load_job(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.model_dump(mode="json")
