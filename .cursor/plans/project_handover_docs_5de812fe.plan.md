---
name: Project Handover Docs
overview: Produce a complete, evidence-based handover pack in PROJECT_DOCUMENTATION/ from the current VideoQA codebase, without changing application source. The audit already shows a FastAPI + Next.js local RAG app with SQLite, ChromaDB, Whisper, Ollama embeddings, and Gemini/Ollama generation, plus several unfinished or unused paths that documentation must label honestly.
todos:
  - id: diagrams
    content: Write Mermaid diagrams under PROJECT_DOCUMENTATION/diagrams/ matching implemented components only
    status: pending
  - id: core-docs
    content: Write architecture, structure, backend, frontend, API, database, and RAG pipeline docs from audited code
    status: pending
  - id: status-bugs
    content: Write PROJECT_STATUS.md, BUGS_AND_ISSUES.md, TESTING, ROADMAP with verified statuses
    status: pending
  - id: ops-handover
    content: Write setup, deployment, troubleshooting, changelog (from git log), README, overview, handover/executive summary
    status: pending
  - id: final-report
    content: Return the PHASE 10 counts and documentation location in the final chat report
    status: pending
isProject: false
---

# Project Audit Documentation Plan

## Scope and constraints

- **Write only** files under `[PROJECT_DOCUMENTATION/](PROJECT_DOCUMENTATION/)` (including `[PROJECT_DOCUMENTATION/diagrams/](PROJECT_DOCUMENTATION/diagrams/)`).
- **Do not** modify, delete, rename, or restructure application source (`videoqa/`, `frontend/src/`, migrations, Dockerfiles, tests).
- **Do not** copy secrets. Environment docs will list variable **names** and placeholders only, matching `[.env.example](.env.example)`.
- Treat existing `[README.md](README.md)` as marketing-adjacent: verify every claim against code. Example mismatch: README says “fully local / no cloud APIs”, but `[config.yaml](config.yaml)` defaults `llm_provider: gemini` and `[videoqa/core/generator.py](videoqa/core/generator.py)` calls Google GenAI unless `LLM_PROVIDER=ollama`.
- Ignore `[.frontend-build-verify-*](.frontend-build-verify-3433a415a74942eda49a8442ac4f3033)` folders (temporary copies). Document only `[frontend/src/](frontend/src/)`.
- Root scripts such as `[create_chunks.py](create_chunks.py)`, `[merge_chunks.py](merge_chunks.py)`, `[mp3_to_json.py](mp3_to_json.py)` will be labeled **ad-hoc / legacy**, not part of the live API pipeline.

## Verified architecture (source of truth)

```mermaid
flowchart LR
  subgraph ui [Frontend Next.js]
    Pages[App_Router_pages]
    Workspace[VideoWorkspace]
    ApiClient[lib/api.ts]
  end
  subgraph api [FastAPI videoqa.main]
    Ingest[/api/ingest]
    Videos[/api/videos]
    Jobs[/api/jobs]
    Query[/api/query]
    Health[/api/health]
  end
  subgraph ingestPipe [Ingestion]
    YtDlp[yt-dlp]
    FFmpeg[ffmpeg_split]
    Whisper[faster-whisper]
    Chunker[process_json_chunks]
    Embed[Ollama_bge-m3]
  end
  subgraph stores [Persistence]
    SQLite[(SQLite)]
    Chroma[(ChromaDB)]
    Media[data/media]
  end
  subgraph llm [Generation]
    Gemini[Gemini_default]
    OllamaLLM[Ollama_optional]
  end
  Pages --> ApiClient --> api
  Ingest --> ingestPipe
  ingestPipe --> SQLite
  ingestPipe --> Chroma
  Ingest --> Media
  Query --> Chroma
  Query --> Gemini
  Query --> OllamaLLM
  Query --> SQLite
  Videos --> Media
```



**Live RAG path:** frontend `[streamAnswer](frontend/src/lib/api.ts)` → `POST /api/query` in `[videoqa/api/query.py](videoqa/api/query.py)` → `create_embedding` (`[indexer.py](videoqa/core/indexer.py)`) → `search_vectors` (`[chroma.py](videoqa/vectorstore/chroma.py)`) → `stream_response` (`[generator.py](videoqa/core/generator.py)`).

**Not the live path:** `[videoqa/core/retriever.py](videoqa/core/retriever.py)` (`retrieve()` with a hardcoded Node.js-course prompt). Used by unit tests and CLI only.

**Auth:** none. No users, JWT, or login. Chat “session” is a SQLite `chat_sessions` row, not user auth.

## Verified API surface (17 endpoints)

Document all of these in `[API_DOCUMENTATION.md](PROJECT_DOCUMENTATION/API_DOCUMENTATION.md)`:


| Method | Path                                                                                       | Module                                           |
| ------ | ------------------------------------------------------------------------------------------ | ------------------------------------------------ |
| GET    | `/health`, `/api/health`                                                                   | `[videoqa/main.py](videoqa/main.py)`             |
| POST   | `/api/ingest/url`, `/api/ingest/file`                                                      | `[videoqa/api/ingest.py](videoqa/api/ingest.py)` |
| GET    | `/api/videos`, `/api/videos/{id}`, `/api/videos/{id}/transcript`, `/api/videos/{id}/media` | `[videoqa/api/videos.py](videoqa/api/videos.py)` |
| HEAD   | `/api/videos/{id}/media`                                                                   | same                                             |
| DELETE | `/api/videos/{id}`                                                                         | same                                             |
| GET    | `/api/jobs/{id}`                                                                           | `[videoqa/api/jobs.py](videoqa/api/jobs.py)`     |
| POST   | `/api/jobs/{id}/cancel`, `/api/jobs/{id}/retry`                                            | same                                             |
| POST   | `/api/query`, `/api/chat`                                                                  | `[videoqa/api/query.py](videoqa/api/query.py)`   |
| GET    | `/api/chats`, `/api/chats/{session_id}`                                                    | same                                             |


Auth requirement for every endpoint: **none**.

## Database (6 tables)

From `[db/migrations/001_initial.sql](db/migrations/001_initial.sql)` and `[002_chat_messages.sql](db/migrations/002_chat_messages.sql)`:

- `videos` (PK `id`, unique `video_id`)
- `transcript_segments` (FK `video_id` → `videos.video_id`)
- `chunks` (FK `video_id`)
- `chunks_fts` (FTS5; **not used** by live query — `search_chunks_bm25` exists in `[sqlite.py](videoqa/db/sqlite.py)` but is unused)
- `chat_sessions`
- `chat_messages`

Migrations: all `*.sql` in `db/migrations/` are executed on import of `[videoqa/main.py](videoqa/main.py)` via `run_migrations()` (idempotent `IF NOT EXISTS`). `[003_backfill_file_paths.sql](db/migrations/003_backfill_file_paths.sql)` is a no-op comment; actual backfill is `[scripts/backfill_file_paths.py](scripts/backfill_file_paths.py)`.

## Pipeline truth vs requested generic pipeline

**Ingestion (implemented):** URL/file → validation (URL parse / MIME+signature+ffprobe) → store in `data/media` (uploads) or download audio/captions (URLs) → optional YouTube VTT/SRT → else `split_audio` + `transcribe_audio` (faster-whisper) → insert segments → **fixed window of N transcript segments** (`merge_window_size: 5` in `[config.yaml](config.yaml)`, `[process_json_chunks](videoqa/core/chunker.py)`) → Ollama embeddings in batches → Chroma + SQLite.

**Not implemented as specified:** dedicated audio-extract-to-mp3 for uploads (`extract_audio` in `[audio.py](videoqa/core/audio.py)` is unused; Whisper reads the file via PyAV). No dedicated “text cleaning” module beyond caption HTML strip. No semantic chunking. No translation (`text_english` copies original). `caption_source` column is never written.

**QA (implemented):** question → embed via Ollama → Chroma cosine top-k, optionally filtered by `video_id` → threshold `abstention_threshold` (0.53) → grounded vs general prompt → stream Gemini or Ollama → citations built in Python (`normalise_citation`), not by the model.

**Not implemented:** query validation beyond non-empty text; answer validation; hybrid BM25; UI multi-video search (`scope` on `QueryRequest` is unused). Frontend always sends `video_id`. Library-wide search works only if `/api/query` is called without `video_id`.

## Frontend (Next.js 16 App Router)

Entry: `[frontend/src/app/layout.tsx](frontend/src/app/layout.tsx)` wraps `[AppShell](frontend/src/components/app-shell.tsx)`. API proxy: `[frontend/next.config.ts](frontend/next.config.ts)` rewrites `/api/*` to `BACKEND_URL`. State: React hooks only (`use-videos`, `use-ingestion`, `use-job-status`, `use-theme`). No Redux/Zustand.

Pages to document:

- `/` home — ingest + compact library
- `/library` — full library
- `/uploads` — ingest workspace
- `/video/[id]` and `/chat/[id]` — `[VideoWorkspace](frontend/src/components/video-workspace.tsx)`
- `/history` — chat sessions
- `/settings` — theme + health readout only (models not editable)
- `/help` — static help copy

## Feature status (draft for PROJECT_STATUS.md)

Mark **IMPLEMENTED** only with code evidence:

- YouTube URL ingest, local file ingest, Whisper (faster-whisper), timestamps on segments/chunks, windowed chunking, Ollama embeddings, Chroma index, semantic retrieval (single video from UI), RAG streaming, Gemini+Ollama generation, chat history persistence, local playback + media Range, job status/cancel/retry, Docker Compose, SQLite persistence, citation objects with timestamps.

**PARTIALLY IMPLEMENTED:** multi-video retrieval (backend only); multilingual (en/hi captions, no translation); GPU (`docker-compose.gpu.yml` exists, default is CPU); settings; YouTube seek-via-postMessage (present, treat as **NEEDS TESTING**); error handling (API errors exist; no central logging config in `main.py`).

**NOT IMPLEMENTED:** user authentication; notes generation; quiz generation; Colab/cloud GPU offload; hybrid BM25; semantic chunking; production job queue (uses FastAPI `BackgroundTasks` in-process); user accounts.

**NEEDS TESTING:** live Gemini (`test_gemini_live_smoke.py` is opt-in); GPU path; long-video memory; YouTube JS API seek.

Do not mark live features as “working” solely because tests exist; most RAG tests mock embeddings/LLM.

## Bugs and issues to document (verified in code)

Severity in `[BUGS_AND_ISSUES.md](PROJECT_DOCUMENTATION/BUGS_AND_ISSUES.md)`:

1. **High — docs vs runtime:** default LLM is Gemini (cloud key required); embeddings still require Ollama. README “fully local” is false for defaults.
2. **Medium — duplicate `stream_ollama`:** `[query.py](videoqa/api/query.py)` defines `stream_ollama` after importing it from generator; live streaming uses `stream_response`, so this is dead/confusing code plus a unittest.mock branch in `stream_response`.
3. **Medium — unused legacy retriever** with course-specific prompt; tests still target it.
4. **Medium — in-process ingestion jobs** die on process restart; no durable worker.
5. **Medium — no authentication** on destructive endpoints (`DELETE /api/videos/{id}`).
6. **Low — unused FTS, unused `extract_audio`, unused `QueryRequest.scope`, unused `caption_source`.**
7. **Low — leftover deps:** `pandas`, `scikit-learn`, `joblib` appear tied to legacy/eval, not the FastAPI chat path.
8. **Medium — URL ingest duration cap** hardcoded 4 hours in `[ingest_url](videoqa/core/ingestion.py)` vs config-driven cap for file uploads.
9. **Low — Whisper fallback** to cached `small` if configured model fails (`[transcriber.py](videoqa/core/transcriber.py)`), which can surprise operators on low-RAM machines.
10. **Low — `split_audio` uses `-c copy`**, which can fail or cut inaccurately on some containers.

Performance notes (for PHASE 6): Whisper on CPU (`base`, int8, beam 1) is the heaviest local step; Ollama embeddings need a running Ollama; Gemini latency is network; Chroma is local. Cloud/Colab GPU = **proposed**, not implemented.

## Documentation files to generate

Create these 18 markdown files plus diagram snippets:

1. `README.md` — intro + quick start pointing to setup guide
2. `PROJECT_OVERVIEW.md`
3. `SYSTEM_ARCHITECTURE.md` — mermaid for high-level, ingest, RAG, deploy; label proposed nodes
4. `PROJECT_STRUCTURE.md` — real tree, skip verify folders
5. `BACKEND_DOCUMENTATION.md`
6. `FRONTEND_DOCUMENTATION.md` — component hierarchy mermaid
7. `API_DOCUMENTATION.md` — table + per-endpoint samples
8. `DATABASE_DOCUMENTATION.md` — ER mermaid
9. `RAG_PIPELINE.md`
10. `PROJECT_STATUS.md` — feature table with statuses
11. `BUGS_AND_ISSUES.md`
12. `SETUP_AND_INSTALLATION.md` — Docker (`start_project.ps1` / `docker compose`) and local Python+Next paths from repo files only
13. `DEPLOYMENT_GUIDE.md` — compose, GPU override, volumes; no invented K8s
14. `TESTING_DOCUMENTATION.md` — pytest markers `live` / `live_gemini`, frontend `npm test`
15. `DEVELOPMENT_ROADMAP.md`
16. `TROUBLESHOOTING.md`
17. `HANDOVER_GUIDE.md` + executive summary (PHASE 10)
18. `CHANGELOG.md` — from `git log` only; no invented history

Also `diagrams/` with standalone mermaid files: `01-system-architecture.mmd`, `02-ingestion-pipeline.mmd`, `03-rag-qa-pipeline.mmd`, `04-database-er.mmd`, `05-deployment.mmd`, `06-frontend-components.mmd`.

Cross-reference instead of repeating long explanations. Each file still has a short standalone intro.

`.env.example` already exists at repo root and is sanitized; setup docs will **reference it**, not duplicate credentials. Will not rewrite root `.env.example` unless a documented variable is missing from it (currently it already matches `config.py` / compose).

## Execution order after approval

1. Re-read any remaining files needed for samples (`ingest.py` remainder, `storage.py`, tests headers, `git log --oneline`).
2. Write diagrams first, then status/bugs (facts), then architecture/API/DB, then setup/testing/roadmap/handover.
3. Finish with a concise audit report in chat: files inspected, endpoints, tables, diagrams, feature counts, bugs, items needing human confirmation (e.g. whether a Gemini key is provisioned; whether GPU hosts exist).

**Items needing manual confirmation (will be listed, not guessed):** presence of a real `GEMINI_API_KEY`; Ollama models actually pulled; whether Docker is the intended primary run path; production hosting target.