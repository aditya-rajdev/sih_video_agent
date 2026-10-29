# FrameForge AI Web UI

From the existing project root:

```powershell
.\venv\Scripts\Activate.ps1
pip install -r web\backend\requirements.txt
python -m uvicorn web.backend.server:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000

The website POSTs the topic to FastAPI. FastAPI starts the existing `main.py`, sends the topic through stdin, watches its stdout, then serves `output/final_video.mp4` when complete.

This MVP allows one job at a time because the current pipeline uses shared output folders. Add a job queue/per-job workspace before public multi-user deployment.


## Frontend workflow update
This version implements the script-first UI: Generate Script -> Preview -> Edit/Regenerate/Approve/Cancel -> separate video decision. The backend in this ZIP is intentionally unchanged; the new UI expects the script workflow endpoints described in app.js. Backend integration is the next step.


## UI update
- Added `assets/appbar_india_header.png` for the government-style top-bar tricolor and landmark background.
- Video downloads now use the `/api/video/{jobid}/download` endpoint and a browser Blob download flow for reliable MP4 saving.
