# API Contracts

Frontend calls only the backend API endpoints defined by the product requirements.

Required:
- POST /api/process
- GET /api/status/{job_id}
- GET /api/preview/{job_id}
- GET /api/result/{job_id}
- POST /api/retry/{job_id}
- POST /api/cancel/{job_id}

Frontend behavior:
- never computes job state locally
- polls status from backend
- renders preview and results from backend payloads only
