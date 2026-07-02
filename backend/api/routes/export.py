from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api", tags=["export"])


@router.get("/result/{job_id}")
async def result(job_id: str, request: Request):
    job_store = request.app.state.job_store
    job = job_store.load_job(job_id)
    workdir = job_store.job_dir(job_id)
    preview = job_store.file_store.read_json(workdir / "clips" / "preview_manifest.json", default={})
    export_file = workdir / "exports" / "reel_001.mp4"
    return {
        "job": job.model_dump(mode="json"),
        "preview": preview,
        "export_available": export_file.exists(),
        "export_path": str(export_file) if export_file.exists() else None,
    }


@router.post("/retry/{job_id}")
async def retry(job_id: str, request: Request):
    orchestrator = request.app.state.orchestrator
    await orchestrator.retry_job(job_id)
    return {"job_id": job_id, "status": "queued"}


@router.post("/cancel/{job_id}")
async def cancel(job_id: str, request: Request):
    orchestrator = request.app.state.orchestrator
    orchestrator.cancel_job(job_id)
    return {"job_id": job_id, "status": "cancelled"}


@router.post("/export/{job_id}")
async def export(job_id: str, request: Request):
    job_store = request.app.state.job_store
    job_dir = job_store.job_dir(job_id)
    export_file = job_dir / "exports" / "reel_001.mp4"
    if not export_file.exists():
        raise HTTPException(status_code=404, detail="Export not ready")
    return {"job_id": job_id, "export_path": str(export_file)}


@router.get("/download/{job_id}")
async def download(job_id: str, request: Request):
    job_store = request.app.state.job_store
    job_dir = job_store.job_dir(job_id)
    export_file = job_dir / "exports" / "reel_001.mp4"
    if not export_file.exists():
        raise HTTPException(status_code=404, detail="Export file not found")
    return FileResponse(
        path=str(export_file),
        media_type="video/mp4",
        filename="trimora_reel_001.mp4",
    )
