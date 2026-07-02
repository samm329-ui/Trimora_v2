from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api", tags=["preview"])


@router.get("/preview/{job_id}")
async def preview(job_id: str, request: Request):
    job_dir = request.app.state.job_store.job_dir(job_id)
    path = job_dir / "clips" / "preview_manifest.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Preview not ready")
    return request.app.state.job_store.file_store.read_json(path)
