# Trimora Frontend Scaffold

This frontend matches the requirement document:
- Upload screen
- Processing screen
- Preview screen
- Results screen
- Settings screen

Connection model:
- `services/` calls backend endpoints
- `store/` manages UI state and polling
- `hooks/` expose reusable upload/status helpers
- `components/` render only backend-derived data
- `pages/` assemble product surfaces

Important behavior:
- progress is always read from the backend
- preview clips come from `/api/preview/{job_id}`
- job status comes from `/api/status/{job_id}`
- export data comes from `/api/result/{job_id}`
