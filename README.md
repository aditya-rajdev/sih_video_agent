# FrameForge AI Content Generator

A unified AI content transformation dashboard for generating multiple communication deliverables from one source.

## Current connected outputs

- Video — script → user review → approval → HTML/CSS/JS video → Playwright → FFmpeg → MP4
- LinkedIn Post — institutional post + hashtags
- X Post — single post or short thread + hashtags

The same source, audience, tone, language and detail preferences are shared across selected outputs.

## AI providers

The dashboard supports both **local** and **API** models:

- Local Ollama — default `qwen3:8b`
- OpenAI API
- xAI / Grok API
- Google Gemini API
- Groq API
- Custom OpenAI-compatible API

For local generation, no API key is required.

## Workflow

```text
Source Information
        ↓
Select Video / LinkedIn / X
        ↓
Common Preferences
        ↓
Generate Selected Content
        ↓
┌──────────────┬────────────────┬─────────────┐
│ Video Script │ LinkedIn Post  │ X Post      │
└──────────────┴────────────────┴─────────────┘
        ↓
Review Video Script
        ↓
Approve Script
        ↓
Do you want the video?
   ├─ No → Save Script
   └─ Yes → Scene/Asset/Code Pipeline
                 ↓
             Playwright
                 ↓
               FFmpeg
                 ↓
              Final MP4
```

## Windows setup

### 1. Python

Use Python 3.10:

```powershell
py -3.10 --version
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### 2. Python packages

```powershell
python -m pip install -r requirements.txt
```

### 3. Ollama + Qwen3 8B

Install Ollama separately, then:

```powershell
ollama --version
ollama pull qwen3:8b
ollama list
```

Optional Ollama host setting:

```powershell
[System.Environment]::SetEnvironmentVariable("OLLAMA_HOST", "http://127.0.0.1:11434", "User")
```

Restart PowerShell after changing the user environment variable.

### 4. Chromium for Playwright

```powershell
python -m playwright install chromium
```

### 5. FFmpeg + FFprobe

Preferred Windows installation:

```powershell
winget install Gyan.FFmpeg
```

Alternative if Chocolatey is installed:

```powershell
choco install ffmpeg -y
```

Verify:

```powershell
ffmpeg -version
ffprobe -version
```

### 6. API providers

Enter the API key in the dashboard when using an API provider.

For Groq, OpenAI, xAI or Gemini you may also set keys in your own `.env`/deployment environment. Never commit real keys to Git.

## Run the dashboard

From the project root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn web.backend.server:app --host 127.0.0.1 --port 8000 --reload
```

Open:

```text
http://127.0.0.1:8000
```

## Important security note

The project should never contain a real API key in source control. Copy `.env.example` to your own private environment configuration if needed, and keep `.env` ignored by Git.

## Project structure

```text
FrameForge/
├── agents/
│   ├── llm_provider.py
│   ├── content_agents.py
│   ├── script_editor.py
│   ├── code_generator.py
│   ├── code_validator.py
│   ├── code_fixer.py
│   └── asset_verifier.py
├── assets/images/
├── web/
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── backend/server.py
├── browser_renderer.py
├── ffmpeg_renderer.py
├── main.py
├── pipeline_timer.py
└── requirements.txt
```

## Output behavior

When Video + LinkedIn + X are selected together, one generation request creates:

1. A video script for review.
2. A LinkedIn draft.
3. An X post/thread.

The video is **not rendered automatically**. The user must explicitly approve the video script and then choose **Yes, Generate Video**.

If the user chooses **No, Save Script**, the video pipeline does not start.

## Supported video renderer

Video scenes are generated as self-contained HTML/CSS/JS and rendered with Playwright/Chromium. Frames are combined with FFmpeg into a vertical MP4.

The renderer is not an AI video-generation API.
