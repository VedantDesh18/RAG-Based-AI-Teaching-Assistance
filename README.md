# RAG-Based AI Teaching Assistant

A production-ready, local-first **Retrieval-Augmented Generation (RAG)** teaching assistant that turns educational videos and course documents into an interactive conversation. Students paste a YouTube URL or upload a file, and within minutes can ask questions in plain English — receiving precise, grounded answers with verified video timestamps, transcript excerpts, and deep-linked citations.

![Status](https://img.shields.io/badge/status-active-brightgreen)
![Docker](https://img.shields.io/badge/docker-compose-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## ✨ Features

| Feature | Description |
|---|---|
| **YouTube URL Ingestion** | Paste a YouTube URL → automatic download, transcription, chunking, and indexing |
| **File Upload** | Upload video/audio files directly for processing |
| **Semantic Q&A** | Ask questions in natural language; get answers grounded in video content |
| **Timestamped Citations** | Every answer includes clickable timestamp links jumping to the exact video moment |
| **Streaming Responses** | Real-time SSE-streamed LLM answers for responsive UX |
| **Video Library** | Browse all ingested videos with metadata, duration, and transcript status |
| **Chat History** | Persistent conversation history per video with SQLite storage |
| **Background Jobs** | Async ingestion pipeline with real-time job status tracking |
| **Fully Local** | Runs entirely on your machine — no cloud APIs, no data leaves your system |
| **GPU Acceleration** | Optional NVIDIA GPU support for faster Whisper transcription |

---

## 🏗️ Architecture & Pipeline

```text
Educational Videos / Audio Uploads / YouTube URLs
                       │
                       ▼
            Video & Audio Processing
                 (yt-dlp, FFmpeg)
                       │
                       ▼
            Speech-to-Text Transcription
              (OpenAI faster-whisper)
                       │
                       ▼
            Timestamped Transcript Segments
                       │
                       ▼
            Cleaning & Windowed Chunking
                       │
                       ▼
               Embedding Generation
              (Ollama / BGE-M3 model)
                       │
                       ▼
                Vector Database
             (ChromaDB Persistent)
                       │
      Student Question │
                       ▼
            Cosine Similarity Search
          (Top-K Chunks + Thresholding)
                       │
                       ▼
               Grounded Prompting
                       │
                       ▼
               LLM Streamed Answer
                (Ollama / Llama 3.2)
                       │
                       ▼
          Verified Answer + Citations
              (with video timestamps)
```

---

## 📁 Project Structure

```
RAG-Based AI Teaching Assistance/
├── videoqa/                    # Python backend package
│   ├── main.py                 # FastAPI application entrypoint
│   ├── config.py               # Configuration management (env vars, YAML)
│   ├── api/                    # REST API route handlers
│   │   ├── ingest.py           #   POST /api/ingest — YouTube URL & file upload ingestion
│   │   ├── query.py            #   POST /api/query — RAG Q&A with SSE streaming
│   │   ├── videos.py           #   GET  /api/videos — Video library CRUD
│   │   └── jobs.py             #   GET  /api/jobs   — Background job status
│   ├── core/                   # Core business logic
│   │   ├── downloader.py       #   YouTube/URL downloading via yt-dlp
│   │   ├── audio.py            #   Audio extraction & FFmpeg processing
│   │   ├── transcriber.py      #   Speech-to-text via faster-whisper
│   │   ├── chunker.py          #   Transcript windowed chunking
│   │   ├── indexer.py          #   ChromaDB vector indexing
│   │   ├── retriever.py        #   Semantic similarity search
│   │   ├── generator.py        #   LLM answer generation
│   │   └── ingestion.py        #   End-to-end ingestion orchestrator
│   ├── vectorstore/
│   │   └── chroma.py           #   ChromaDB client & collection management
│   ├── db/
│   │   └── sqlite.py           #   SQLite ORM (videos, segments, chunks, chats)
│   └── utils/
│       └── url_parser.py       #   URL validation & YouTube ID extraction
├── frontend/                   # Next.js web application
│   ├── src/
│   │   ├── app/                #   App Router pages
│   │   │   ├── page.tsx        #     Landing / dashboard
│   │   │   ├── chat/           #     Chat interface with video player
│   │   │   ├── library/        #     Video library browser
│   │   │   ├── uploads/        #     File upload interface
│   │   │   ├── history/        #     Chat history viewer
│   │   │   ├── settings/       #     App configuration
│   │   │   └── help/           #     Help & documentation
│   │   ├── components/         #   Reusable React components
│   │   │   ├── app-shell.tsx   #     Navigation shell & sidebar
│   │   │   ├── video-workspace.tsx  # Video player + chat workspace
│   │   │   ├── ingestion-panel.tsx  # URL/file ingestion UI
│   │   │   ├── library-view.tsx     # Video library grid
│   │   │   └── video-card.tsx       # Individual video card
│   │   ├── hooks/              #   Custom React hooks
│   │   └── lib/                #   Shared utilities
│   ├── Dockerfile              #   Frontend container build
│   └── next.config.ts          #   Next.js config with API proxy rewrites
├── db/migrations/              # SQLite schema migrations
├── eval/                       # Evaluation harness
│   ├── run_eval.py             #   Automated RAG quality evaluation
│   ├── golden_questions/       #   Ground-truth Q&A test sets
│   └── baselines/              #   Baseline comparison results
├── tests/                      # Automated tests
│   ├── unit/                   #   Unit tests
│   └── integration/            #   API contract tests
├── scripts/                    # Utility scripts
├── docker-compose.yml          # Multi-service Docker Compose orchestration
├── docker-compose.gpu.yml      # GPU override for NVIDIA CUDA acceleration
├── Dockerfile                  # Backend container build
├── start_project.ps1           # 1-click Windows startup & verification script
├── config.yaml                 # Application configuration
├── requirements.txt            # Python dependencies
├── pyproject.toml              # Python package metadata
├── .env.example                # Environment variable template
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

- **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** (v24.0+ recommended)
- **[Ollama](https://ollama.ai/)** installed and running on your host machine

Pull the required models in Ollama:
```bash
ollama pull bge-m3:latest
ollama pull llama3.2
```

### Setup & Run

1. **Clone the repository**
   ```bash
   git clone https://github.com/VedantDesh18/RAG-Based-AI-Teaching-Assistance.git
   cd "RAG-Based AI Teaching Assistance"
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # On Windows PowerShell:
   Copy-Item .env.example .env
   ```
   Review `.env` and adjust if needed. Defaults connect to your host Ollama instance.

3. **Launch the application**

   **Option A — 1-Click PowerShell Script (Windows, Recommended):**
   ```powershell
   .\start_project.ps1
   ```
   > This automatically detects and starts Docker Desktop if needed, launches all services, runs 5 end-to-end integration tests, and opens the app in your browser.

   **Option B — Standard Docker Compose (Cross-Platform):**
   ```bash
   docker compose up --build
   ```

4. **Open the application**

   | Service | URL |
   |---|---|
   | **Frontend UI** | [http://localhost:3000](http://localhost:3000) |
   | **Backend API Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) |
   | **Health Check** | [http://localhost:8000/health](http://localhost:8000/health) |

---

## 🐳 Docker Services

| Service | Container | Port | Description |
|---|---|---|---|
| **backend** | `videoqa-backend` | `8000` | FastAPI REST API, SSE streaming, ingestion worker |
| **frontend** | `videoqa-frontend` | `3000` | Next.js web application with API proxy |
| **ollama** *(optional)* | `videoqa-ollama` | `11434` | In-Docker Ollama LLM & embedding server |

### Common Commands

```bash
# Stop all services
docker compose down

# Rebuild and restart
docker compose up --build -d

# View all logs
docker compose logs -f

# View backend logs only
docker compose logs -f backend

# View frontend logs only
docker compose logs -f frontend

# Remove everything including data volumes
docker compose down -v
```

---

## ⚙️ Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://host.docker.internal:11434` | Ollama HTTP API endpoint |
| `EMBEDDING_MODEL` | `bge-m3:latest` | Ollama model for text embeddings |
| `LLM_MODEL` | `llama3.2` | Ollama model for answer generation |
| `WHISPER_MODEL` | `base` | Whisper model size (`tiny` / `base` / `small` / `medium` / `large-v2` / `large-v3`) |
| `WHISPER_DEVICE` | `cpu` | Inference device (`cpu` or `cuda`) |
| `WHISPER_COMPUTE_TYPE` | `int8` | Quantization (`int8` for CPU, `float16` for GPU) |
| `WHISPER_BEAM_SIZE` | `1` | Decoding beam width; `1` minimizes CPU/RAM use during uploads |
| `WHISPER_CPU_THREADS` / `WHISPER_NUM_WORKERS` | `2` / `1` | Bounds CTranslate2's transcription worker pool |
| `WHISPER_MAX_SEGMENT_SEC` | `600` | Maximum source duration transcribed per piece |
| `MKL_NUM_THREADS` / `OMP_NUM_THREADS` | `2` | Bounds CPU thread-pool memory used by transcription |
| `EMBEDDING_BATCH_SIZE` | `16` | Number of chunks embedded and persisted per Ollama request |
| `VIDEOQA_CORS_ORIGINS` | `http://localhost:3000,...` | Exact allowed frontend origins (includes local ports 3000 and 3001) |
| `BACKEND_URL` | `http://backend:8000` | Internal Docker URL for Next.js proxy |
| `NEXT_PUBLIC_API_URL` | *(empty)* | Optional direct public API URL |
| `CHROMA_PATH` | `data/chroma` | ChromaDB index storage path |
| `DB_PATH` | `data/db/videoqa.db` | SQLite database path |
| `MEDIA_ROOT` | `data/media` | Canonical writable storage for newly uploaded media |
| `LEGACY_MEDIA_ROOT` | `videos` | Read-only root for existing local media |

---

## 💾 Data Persistence

All data survives container restarts via host-mounted bind mounts and named Docker volumes:

| Data | Location | Type |
|---|---|---|
| SQLite database | `./data/db/videoqa.db` | Bind mount |
| ChromaDB vectors | `./data/chroma/` | Bind mount |
| New uploads | `./data/media/` | Bind mount; canonical writable media root |
| Legacy local videos | `./videos/` | Read-only bind mount in Docker; set `LEGACY_MEDIA_ROOT` when stored elsewhere |
| Whisper model cache | `videoqa_whisper_cache` volume | Named volume |

## 🎥 Local Media Playback and Recovery

New uploads are written atomically under `MEDIA_ROOT` before a queued SQLite record is committed and background transcription starts. The database stores a portable reference such as `media/<generated-name>.mp4`; the public video API returns a media URL rather than a local filesystem path. Existing videos under `videos/` remain readable through `LEGACY_MEDIA_ROOT` and are not moved by migration.

The upload endpoint is `POST /api/ingest/file`, with the file sent in the multipart field named `file`. By default, the browser calls the same-origin Next.js proxy, which forwards `/api/*` to `BACKEND_URL`. The browser creates the multipart boundary; clients must not set `Content-Type` manually for `FormData`. Next.js's rewrite proxy has a 10 MB default request-body limit, so `frontend/next.config.ts` raises `experimental.proxyClientMaxBodySize` just above the backend's configured 2 GiB upload limit. The player uses `GET /api/videos/{video_id}/media`; this route also supports `HEAD` and byte ranges for seeking. A stored file remains playable while its job is queued, processing, or failed. RAG chat becomes available after a video is ready and has indexed transcript chunks.

If indexing fails, the video workspace shows the saved error (including the failed processing stage) and offers **Retry indexing**. Retry uses `POST /api/jobs/{video_id}/retry`, keeps the video ID and source file, and is limited to three attempts. It is enabled only while the saved source remains readable.

To inspect legacy path repair, run the migration in dry-run mode first:

```powershell
python scripts/backfill_file_paths.py
```

Review every proposed match. The script never assigns an ambiguous candidate. When the report contains only intended matches, apply it:

```powershell
python scripts/backfill_file_paths.py --apply
```

Apply mode creates a timestamped SQLite backup beside the configured database before writing. The script is safe to rerun; it reports already-correct references and preserves video IDs, transcripts, chunks, and vector associations.

For a local development restart, run the backend and frontend in separate PowerShell windows:

```powershell
# Repository root
python -m uvicorn videoqa.main:app --host 127.0.0.1 --port 8000
```

```powershell
# In a second window
Set-Location frontend
$env:BACKEND_URL = "http://127.0.0.1:8000"
npm run dev
```

Verify a stored video's headers and seek response (replace the ID):

```powershell
$videoId = "f7cc259539c"
curl.exe -I "http://127.0.0.1:8000/api/videos/$videoId/media"
curl.exe -H "Range: bytes=0-1023" -o NUL -i "http://127.0.0.1:8000/api/videos/$videoId/media"
```

`GET /api/health` reports SQLite, ChromaDB, media storage, FFmpeg/ffprobe, faster-whisper, Ollama, and configured Ollama model availability separately. Optional transcription dependencies do not gate media playback.

---

## 🖥️ CPU vs. GPU Acceleration

### CPU (Default — No Special Setup)
Runs `faster-whisper` on CPU with `int8` quantization. Works on any machine.

### NVIDIA GPU (Optional)
Requires [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

1. Set in `.env`:
   ```env
   WHISPER_DEVICE=cuda
   WHISPER_COMPUTE_TYPE=float16
   ```
2. Start with GPU override:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
   ```

---

## 🔧 Running Ollama in Docker (Optional)

If you prefer not to install Ollama on your host:

```bash
# Start with the Ollama profile
docker compose --profile with-ollama up --build

# Pull required models into the container
docker compose exec ollama ollama pull bge-m3:latest
docker compose exec ollama ollama pull llama3.2
```

Set `OLLAMA_URL=http://ollama:11434` in your `.env`.

---

## 🧪 Testing

### Automated Integration Tests (via `start_project.ps1`)

The startup script runs **5 automated integration tests**:

| # | Test | What It Verifies |
|---|---|---|
| 1 | Backend Health | `GET /health` returns `{"status": "healthy"}` |
| 2 | AI Service Health | `GET /api/health` — backend + Ollama connectivity |
| 3 | Video Library DB | `GET /api/videos` — SQLite database access |
| 4 | Frontend Proxy | `GET localhost:3000/api/health` — Next.js → backend proxy rewrite |
| 5 | Frontend HTTP | `GET localhost:3000` — Next.js serves HTTP 200 |

### Unit & Integration Tests

```bash
# Run from the repository root
python -m pytest -q

# Check the production frontend build
Set-Location frontend
npm run build
```

Latest upload/chat verification (2026-10-18): the full Python suite passed (56 tests, 2 dependency deprecation warnings); the Next.js production build and TypeScript check passed. A browser upload of an 11.47 MB synthetic MP4 through the Next.js proxy returned HTTP 202, and the exact bytes and portable SQLite reference were verified in an isolated test store. The video loaded in the browser after the synthetic worker failed, with the indexing error and retry action visible. After adding a test transcript chunk, the chat field enabled; Enter and Send both returned the deterministic answer and timestamp citation, and the saved session used the selected video ID. GET/HEAD/Range returned 200/200/206. Browser retrieval/generation were deterministic stubs; production Ollama/Chroma generation was not exercised by this browser run. `npm run lint` still reports existing React hook-rule errors in the history page and shared effects.

### Evaluation Harness

```bash
# Run RAG quality evaluation against golden question set
python eval/run_eval.py
```

---

## 📊 Current Project Status

> **Last verified:** October 11, 2026 — All 5/5 integration tests passing ✅

### ✅ Completed

| Component | Status | Details |
|---|---|---|
| **Backend API** | ✅ Production-ready | FastAPI with health checks, CORS, SSE streaming |
| **Video Ingestion Pipeline** | ✅ Complete | YouTube URL download → audio extraction → transcription → chunking → indexing |
| **Speech-to-Text** | ✅ Complete | `faster-whisper` with configurable model sizes (tiny → large-v3) |
| **Vector Store** | ✅ Migrated | ChromaDB persistent store (migrated from legacy `embeddings.joblib`) |
| **Semantic Retrieval** | ✅ Complete | Cosine similarity search with top-K chunk retrieval |
| **LLM Answer Generation** | ✅ Complete | Grounded prompting with Ollama / Llama 3.2, streamed via SSE |
| **SQLite Database** | ✅ Complete | Videos, transcript segments, chunks, jobs, chat messages |
| **Frontend UI** | ✅ Complete | Next.js app with chat, video library, uploads, history, settings, help pages |
| **Docker Deployment** | ✅ Complete | Multi-service Docker Compose with health checks & auto-restart |
| **GPU Support** | ✅ Complete | Optional NVIDIA CUDA acceleration via `docker-compose.gpu.yml` |
| **1-Click Startup** | ✅ Complete | `start_project.ps1` — auto-starts Docker Desktop, launches services, runs tests |
| **Evaluation Harness** | ✅ Complete | Golden question set with automated RAG quality metrics |
| **Video Library (16 videos)** | ✅ Indexed | 16 educational videos fully transcribed and queryable |

### 🔮 Roadmap / Future Work

- [ ] Overlapping windowed chunking (sliding window with stride < window size)
- [ ] Explicit similarity-score threshold for out-of-domain rejection
- [ ] Multi-user authentication & access control
- [ ] Playlist bulk ingestion (process entire YouTube playlists)
- [ ] Visual understanding (OCR of slides, keyframe extraction)
- [ ] Embeddable chat widget for external websites
- [ ] Analytics dashboard (popular questions, usage patterns)

---

## 🛠️ Troubleshooting

1. **Docker Desktop not running / `start_project.ps1` fails:**
   - The script auto-detects and launches Docker Desktop. If it still fails, start Docker Desktop manually and retry.
   - On first run, Docker image builds may take 5–10 minutes.

2. **Ollama connection fails (`services.ollama: unavailable`):**
   - Ensure Ollama is running: `ollama serve` or check [http://localhost:11434](http://localhost:11434).
   - Verify `OLLAMA_URL=http://host.docker.internal:11434` in `.env`.
   - Or use `--profile with-ollama` to run Ollama in Docker.

3. **Port 8000 or 3000 already in use:**
   - Change `ports` in `docker-compose.yml` (e.g., `"8001:8000"`) and update `VIDEOQA_CORS_ORIGINS` in `.env`.

4. **Whisper model download is slow on first run:**
   - `large-v2` is ~3 GB, downloaded once and cached in the `videoqa_whisper_cache` volume.
   - For faster testing, set `WHISPER_MODEL=base` or `WHISPER_MODEL=small` in `.env`.

5. **`GET /` returns 404 or uploads still use old backend behavior:**
   - `GET /` is not an application page; use `GET /health` or `GET /api/health` for health checks. A root 404 does not diagnose the upload route.
   - The Docker backend image does not bind-mount the Python source. After backend code changes, rebuild and recreate it with `docker compose up --build -d backend`. Check `docker compose ps backend` and `http://localhost:8000/api/health` afterward. Do not use `docker compose down -v` for this; it removes named data volumes.

6. **Uploads larger than 10 MiB fail through the frontend:**
   - Rebuild/restart the frontend so it loads `experimental.proxyClientMaxBodySize` from `frontend/next.config.ts`. Keep the file in multipart field `file` and let the browser set the multipart `Content-Type` boundary. If using a direct backend URL instead of the same-origin proxy, add that exact frontend origin to `VIDEOQA_CORS_ORIGINS` and restart the backend.

7. **A ready video has disabled chat despite transcript chunks:**
   - Chat eligibility uses the actual rows in the `chunks` table, not a stale cached `videos.chunk_count`. Rebuild/restart the backend so video detail and query validation calculate the count from indexed chunks.

---

## 📄 License

This project is developed as an educational research project.
