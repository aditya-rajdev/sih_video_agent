import asyncio
import contextlib
import io
import shutil
import uuid
from pathlib import Path
from typing import Any, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
OUTPUT = ROOT / "output"
FINAL = OUTPUT / "final_video.mp4"
JOBS = OUTPUT / "web_jobs"
JOBS.mkdir(parents=True, exist_ok=True)

import main as pipeline
from agents.content_agents import generate_social_outputs

app = FastAPI(title="FrameForge AI Content API")
content_jobs: dict[str, dict[str, Any]] = {}
video_jobs: dict[str, dict[str, Any]] = {}


class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=10000)
    duration: int = Field(60, ge=5, le=1800)
    tone: str = "educational"
    audience: str = "general audience"
    language: str = "English"
    detail_level: str = "standard"
    provider: str = "local"
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    code_model: str = ""
    outputs: List[str] = Field(default_factory=lambda: ["video"])


class ScriptEditRequest(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=3000)


ALLOWED_OUTPUTS = {"video", "linkedin", "x"}
ALLOWED_PROVIDERS = {"local", "openai", "xai", "gemini", "groq", "custom"}


def validate_provider(request: GenerateRequest) -> None:
    provider = request.provider.strip().lower() or "local"
    if provider not in ALLOWED_PROVIDERS:
        raise HTTPException(400, f"Unsupported provider: {provider}.")
    if provider != "local" and not request.api_key.strip():
        raise HTTPException(400, f"API key is required for provider '{provider}'.")
    if provider == "custom" and (not request.model.strip() or not request.base_url.strip()):
        raise HTTPException(400, "Custom provider requires model and base URL.")


def normalize_outputs(outputs: List[str]) -> List[str]:
    normalized = []
    for value in outputs:
        value = value.strip().lower()
        if value and value not in normalized:
            normalized.append(value)
    if not normalized:
        raise HTTPException(400, "Select at least one output format.")
    unknown = [value for value in normalized if value not in ALLOWED_OUTPUTS]
    if unknown:
        raise HTTPException(400, f"Unsupported output format(s): {', '.join(unknown)}")
    return normalized


def make_state(request: GenerateRequest) -> dict[str, Any]:
    return {
        "topic": request.topic.strip(),
        "duration": int(request.duration),
        "tone": request.tone.strip() or "educational",
        "audience": request.audience.strip() or "general audience",
        "language": request.language.strip() or "English",
        "detail_level": request.detail_level.strip() or "standard",
        "provider": request.provider.strip().lower() or "local",
        "api_key": request.api_key.strip(),
        "model": request.model.strip(),
        "base_url": request.base_url.strip(),
        "code_model": request.code_model.strip(),
    }


async def generate_content_task(jobid: str, request: GenerateRequest) -> None:
    job = content_jobs[jobid]
    try:
        state = make_state(request)
        outputs = normalize_outputs(request.outputs)
        job.update(status="running", progress=5, stage="Preparing content workflow...")
        job["logs"].append(f"Selected outputs: {', '.join(outputs)}")

        # Social deliverables are generated directly from the same source.
        if {"linkedin", "x"} & set(outputs):
            job.update(progress=20, stage="Generating LinkedIn / X content...")
            social = await asyncio.to_thread(generate_social_outputs, state, outputs)
            job.update(social)
            job["logs"].append("Social content generation completed.")

        # Video remains script-first: generate the standalone script now,
        # but do not render a video until the user explicitly approves it.
        if "video" in outputs:
            job.update(progress=45, stage="Writing video script...")
            result = await asyncio.to_thread(pipeline.script_writer, state)
            script = result["script"]
            pipeline.validate_script(script, expected_duration=state["duration"])
            job["script"] = script
            job["state"] = state
            job["logs"].append(
                f"Generated {len(script.scenes)} scenes totaling {script.total_duration}s."
            )

        job["state"] = state
        job["outputs"] = outputs
        job.update(
            status="completed",
            progress=100,
            stage="Content ready for review.",
        )
    except Exception as exc:
        job.update(
            status="failed",
            progress=100,
            stage="Content generation failed.",
            error=str(exc),
        )
        job["logs"].append("ERROR: " + str(exc))


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/content/generate")
async def generate_content(request: GenerateRequest):
    if not request.topic.strip():
        raise HTTPException(400, "Source content cannot be empty.")
    validate_provider(request)
    outputs = normalize_outputs(request.outputs)

    if any(job["status"] == "running" for job in content_jobs.values()):
        raise HTTPException(409, "Another content workflow is already running.")

    jobid = uuid.uuid4().hex[:10]
    content_jobs[jobid] = {
        "status": "running",
        "progress": 1,
        "stage": "Starting content agents...",
        "logs": [],
        "error": None,
        "outputs": outputs,
        "script": None,
        "research": None,
        "linkedin": None,
        "x_post": None,
        "state": None,
        "approved": False,
    }
    asyncio.create_task(generate_content_task(jobid, request))
    return {"job_id": jobid, "status": "running", "outputs": outputs}


@app.get("/api/content/{jobid}")
async def content_status(jobid: str):
    job = content_jobs.get(jobid)
    if not job:
        raise HTTPException(404, "Content job not found.")

    payload = {
        "status": job["status"],
        "progress": job["progress"],
        "stage": job["stage"],
        "logs": job["logs"],
        "error": job["error"],
        "outputs": job["outputs"],
        "approved": job["approved"],
        "research": job.get("research"),
        "linkedin": job.get("linkedin"),
        "x_post": job.get("x_post"),
    }
    if job.get("script") is not None:
        payload["script"] = job["script"].model_dump()
    return payload


@app.post("/api/content/{jobid}/script/edit")
async def edit_script(jobid: str, request: ScriptEditRequest):
    job = content_jobs.get(jobid)
    if not job or job.get("script") is None:
        raise HTTPException(404, "Video script not found.")
    if job["approved"]:
        raise HTTPException(409, "Approved scripts cannot be edited.")

    try:
        llm = pipeline.get_agent_llm(job["state"])
        edited = await asyncio.to_thread(
            pipeline.edit_video_script,
            job["script"],
            request.instruction.strip(),
            llm,
        )
        pipeline.validate_script(edited, expected_duration=job["state"]["duration"])
        job["script"] = edited
        job["logs"].append("Video script edited successfully.")
        return {"status": "completed", "script": edited.model_dump()}
    except Exception as exc:
        raise HTTPException(400, f"Script edit failed: {exc}") from exc


@app.post("/api/content/{jobid}/script/regenerate")
async def regenerate_script(jobid: str):
    job = content_jobs.get(jobid)
    if not job or job.get("state") is None:
        raise HTTPException(404, "Content job not found.")
    if "video" not in job.get("outputs", []):
        raise HTTPException(409, "Video output was not selected.")
    if job["approved"]:
        raise HTTPException(409, "Approved scripts cannot be regenerated.")

    try:
        regenerated = await asyncio.to_thread(
            pipeline.regenerate_script,
            job["state"],
        )
        pipeline.validate_script(regenerated, expected_duration=job["state"]["duration"])
        job["script"] = regenerated
        job["logs"].append("Video script regenerated successfully.")
        return {"status": "completed", "script": regenerated.model_dump()}
    except Exception as exc:
        raise HTTPException(400, f"Script regeneration failed: {exc}") from exc


@app.post("/api/content/{jobid}/script/approve")
async def approve_script(jobid: str):
    job = content_jobs.get(jobid)
    if not job or job.get("script") is None:
        raise HTTPException(404, "Video script not found.")
    if job["status"] != "completed":
        raise HTTPException(409, "Content generation is not complete.")

    pipeline.validate_script(job["script"], expected_duration=job["state"]["duration"])
    job["approved"] = True
    job["logs"].append("Video script approved by user.")
    return {"status": "approved", "script": job["script"].model_dump()}


@app.post("/api/content/{jobid}/save-script")
async def save_script(jobid: str):
    job = content_jobs.get(jobid)
    if not job or job.get("script") is None:
        raise HTTPException(404, "Video script not found.")
    if not job["approved"]:
        raise HTTPException(409, "Approve the video script before saving it.")

    await asyncio.to_thread(pipeline.save_video_script, job["script"])
    job["logs"].append("Approved video script saved.")
    return {"status": "saved", "path": "output/scripts/approved_script.json"}


async def run_video_job(jobid: str, content_job: dict[str, Any]) -> None:
    job = video_jobs[jobid]
    try:
        job.update(status="running", progress=2, stage="Starting video pipeline...")
        state = dict(content_job["state"])
        state["script"] = content_job["script"]
        state["script_approved"] = True
        state["generate_video"] = True

        # The downstream pipeline is CPU/subprocess heavy, so run it off the
        # FastAPI event loop.
        def _run_with_logs():
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                result = pipeline.run_video_from_approved_script(state)
            return result, buffer.getvalue()

        (final_video, _), captured_logs = await asyncio.to_thread(_run_with_logs)
        for line in captured_logs.splitlines():
            line = line.strip()
            if not line:
                continue
            job["logs"].append(line)
            detected = video_progress_from_log(line)
            if detected:
                job["progress"], job["stage"] = detected
        source = Path(final_video)
        if not source.exists():
            source = FINAL
        if not source.exists():
            raise FileNotFoundError("Final video was not created.")

        destination = JOBS / f"{jobid}.mp4"
        shutil.copy2(source, destination)
        job["video"] = str(destination)
        job.update(status="completed", progress=100, stage="Video complete.")
    except Exception as exc:
        job.update(status="failed", progress=100, stage="Video generation failed.", error=str(exc))


@app.post("/api/content/{jobid}/video")
async def generate_video(jobid: str):
    content_job = content_jobs.get(jobid)
    if not content_job or content_job.get("script") is None:
        raise HTTPException(404, "Video script not found.")
    if "video" not in content_job.get("outputs", []):
        raise HTTPException(409, "Video output was not selected.")
    if not content_job["approved"]:
        raise HTTPException(409, "Approve the video script before generating video.")
    if any(job["status"] == "running" for job in video_jobs.values()):
        raise HTTPException(409, "Another video is already being generated.")

    jobid_video = uuid.uuid4().hex[:10]
    video_jobs[jobid_video] = {
        "status": "running",
        "progress": 1,
        "stage": "Starting video pipeline...",
        "logs": [],
        "error": None,
        "video": None,
    }
    asyncio.create_task(run_video_job(jobid_video, content_job))
    return {"job_id": jobid_video, "status": "running"}


def video_progress_from_log(line: str):
    x = line.lower()
    stages = [
        (("scene planner", "planning scenes"), 18, "Planning scenes..."),
        (("asset planner", "asset plan"), 28, "Planning assets..."),
        (("image requirement", "image requirements"), 34, "Planning image requirements..."),
        (("code generator", "generating scene code"), 50, "Generating scene code..."),
        (("validator", "validating"), 65, "Validating scene code..."),
        (("fixer", "fixing"), 70, "Fixing scene code..."),
        (("browser renderer", "playwright", "rendering"), 84, "Rendering browser frames..."),
        (("ffmpeg", "final video"), 96, "Composing final MP4..."),
    ]
    for words, progress, text in stages:
        if any(word in x for word in words):
            return progress, text
    return None


@app.get("/api/video/{jobid}")
async def video_status(jobid: str):
    job = video_jobs.get(jobid)
    if not job:
        raise HTTPException(404, "Video job not found.")
    return {key: job[key] for key in ("status", "progress", "stage", "logs", "error")}


@app.get("/api/video/{jobid}/file")
async def video_file(jobid: str):
    job = video_jobs.get(jobid)
    if not job or job["status"] != "completed":
        raise HTTPException(404, "Video is not ready.")
    path = Path(job["video"])
    if not path.exists():
        raise HTTPException(404, "Video file not found.")
    return FileResponse(path, media_type="video/mp4", filename="frameforge-video.mp4")


@app.get("/api/video/{jobid}/download")
async def video_download(jobid: str):
    job = video_jobs.get(jobid)
    if not job or job["status"] != "completed":
        raise HTTPException(404, "Video is not ready.")
    path = Path(job["video"])
    if not path.exists():
        raise HTTPException(404, "Video file not found.")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename="frameforge-video.mp4",
        headers={"Cache-Control": "no-store"},
    )


app.mount("/", StaticFiles(directory=WEB, html=True), name="frontend")
