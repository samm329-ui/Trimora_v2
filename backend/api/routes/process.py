from __future__ import annotations

import os

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from backend.models.job import JobRecord
from backend.utils.validation import is_allowed_video

router = APIRouter(prefix="/api", tags=["process"])


@router.post("/process")
async def process_video(request: Request, file: UploadFile = File(...)):
    job_store = request.app.state.job_store
    orchestrator = request.app.state.orchestrator

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    if not is_allowed_video(file.filename):
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed: .mp4, .mov, .mkv, .webm, .m4v")

    if file.size is not None:
        if file.size == 0:
            raise HTTPException(status_code=400, detail="Empty file")
        MAX_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
        if file.size > MAX_SIZE:
            raise HTTPException(status_code=400, detail="File too large (max 2GB)")

    safe_filename = os.path.basename(file.filename)

    record: JobRecord = job_store.create_job(safe_filename)
    job_dir = job_store.job_dir(record.job_id)
    input_path = job_dir / "input" / safe_filename

    content = await file.read()
    input_path.write_bytes(content)
    job_store.update_job(record.job_id, source_path=str(input_path), status=record.status)

    await orchestrator.start_job(record.job_id)
    return {"job_id": record.job_id, "status": record.status.value, "progress": record.progress}
