# Trimora Frontend

React 18 SPA with TypeScript, Vite, and Tailwind CSS.

## Pages

| Page | Route | Purpose |
|---|---|---|
| Upload | `/upload` | File picker, drag-and-drop upload |
| Status | `/status` | Progress timeline, job summary, retry/cancel |
| Preview | `/preview` | Clip grid with scores, export button |
| Results | `/results` | Final output, clip list, download |
| Settings | `/settings` | API base URL configuration |

## Architecture

- `services/` - API client calls to backend endpoints
- `store/` - Zustand state management (jobStore, previewStore, uiStore)
- `hooks/` - Reusable upload/status/preview helpers
- `components/` - Reusable UI components (cards, layout, preview grid, upload dropzone)
- `pages/` - Page-level components assembling the UI
- `types/` - TypeScript type definitions

## API Endpoints Used

- `POST /api/process` - Upload video
- `GET /api/status/{job_id}` - Poll job progress (2.5s interval)
- `GET /api/preview/{job_id}` - Fetch clip previews
- `GET /api/result/{job_id}` - Fetch final results
- `POST /api/retry/{job_id}` - Retry failed jobs
- `POST /api/cancel/{job_id}` - Cancel running jobs
- `GET /api/download/{job_id}` - Download rendered MP4

## State Management

| Store | Hook | Purpose |
|---|---|---|
| `jobStore` | `useJobState()` | Job ID, status, preview, polling |
| `previewStore` | `usePreviewSelection()` | Clip selection toggle |
| `uiStore` | `useUiState()` | Theme, API base URL |

## Setup

```bash
npm install
npm run dev        # Development server on port 5173
npm run build      # Production build
npm run preview    # Preview production build
```
