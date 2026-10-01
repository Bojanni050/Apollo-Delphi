# Apollo

**Apollo** is an AI-powered document reasoning, investigation and synthesis system.

Apollo does **not** do `Documents → LLM → Summary`. Every reasoning result is
persistent, inspectable, relational data:

```
DOCUMENTS → INGESTION → EVIDENCE → CLAIMS → ISSUES
    ├── Open Questions
    └── Contradictions
            ↓ INVESTIGATION → RESOLUTION → RESOLVED KNOWLEDGE
            ↓ DOCUMENT PLAN → DRAFT → VERIFICATION → FINAL DOCUMENT
```

## What Apollo actually does

1. Ingest documents (PDF, DOCX, TXT, Markdown)
2. Extract text, chunk and embed it, store vectors (pgvector)
3. Extract explicit **claims**, each traceable to source **evidence**
   (document, page, section, original text)
4. Detect **open questions** (sources that explicitly leave things unanswered)
   and **contradictions** (same subject, different values, different documents)
5. **Investigate** each issue: retrieve relevant evidence across the *whole*
   collection (semantic search + metadata), compare claims, reason about evidence
6. **Resolve** issues only when evidence supports a conclusion (explicit
   supersession statements, document dates); otherwise the issue stays
   **unresolved** — Apollo prefers explicit uncertainty over fabricated certainty
7. Accept **human review**: inspect issues/evidence/resolutions, accept, reject,
   add information; decisions are stored explicitly
8. Build a coherent **knowledge state** (facts, derived conclusions, assumptions,
   decisions, unresolved questions, resolved/remaining contradictions)
9. **Generate** a new document synthesized from the knowledge state (not from raw chunks)
10. **Verify** the generated document against the knowledge state with structured
    findings (unsupported claims, unresolved-presented-as-fact, duplicates, …)

## Stack

| Layer | Technology |
|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy |
| Database | PostgreSQL + pgvector (primary source of truth) |
| Migrations | Alembic |
| LLM | Provider-independent `LLMProvider` abstraction (mock / OpenAI-compatible) |
| Embeddings | Provider-independent `EmbeddingProvider` abstraction (mock / OpenAI-compatible) |

## Quick start (Docker)

Docker is optional: the desktop app below (`start.cmd`) runs everything without it, and it is the faster
setup (the embedding server on the GPU). The Compose file stays for servers and for people who prefer containers;
the backend there restarts itself when its code changes (`--reload`).

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000 (docs at `/docs`)
- PostgreSQL + pgvector runs in the `db` service; migrations run automatically.

### Quick start (local, no Docker)

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env   # optional: defaults work out of the box
uvicorn app.main:app --reload
```

With the default SQLite URL the schema is created at startup. For PostgreSQL:

```bash
export APOLLO_DATABASE_URL=postgresql+psycopg2://apollo:apollo@localhost:5432/apollo
alembic upgrade head
```

## Desktop app

Apollo also runs as a normal Windows application (Tauri 2): its own window, no browser, no Docker, no PostgreSQL.

The quickest way: **double-click `start.cmd`** (in a terminal: `.\start.cmd`). The first time it sets everything up
(the steps below), after that it just opens the app. `start.cmd setup` only sets up or updates.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-desktop.ps1   # once: .venv, packages, frontend build
npm run desktop                                                      # builds the frontend and opens the app
```

Needs Python 3.11+, Node.js, git, Rust (rustup) with the MSVC build tools; WebView2 ships with Windows 10/11.
The first start compiles the Rust shell and takes a few minutes.

**Without Docker, step by step** (what Compose did, and what replaces it):

| Docker Compose | Without Docker |
|---|---|
| `backend` + `frontend` | `start.cmd` (the app itself) |
| `db` (PostgreSQL + pgvector) | SQLite by default, or a local PostgreSQL via `DATABASE_URL` in `backend/.env` (`scripts\install-pgvector-windows.ps1`) |
| `llama` (CPU) | `scripts\llama-vulkan.ps1` on the GPU: `start.cmd` starts it for you (skip with `set APOLLO_LLAMA=0`) |

`start.cmd` runs `llama-vulkan.ps1 -Optional`: it only starts the server when the model is there (in `backend\models`
or in the app's own `models` folder) and never stops the app from opening. In the app set the Base URL to
`http://localhost:8082/v1` once. The data in the Docker volumes is not moved along: the desktop app starts empty and
folders are added again in seconds (documents are read first, then embedded in the background).

- **How it works.** `src-tauri/` is only a window and a process supervisor: it starts `backend/.venv`'s Python
  (`python -m app.serve`) on a free port, waits until the API answers, and points the window at it. The page and
  the API share one origin, so there is no CORS to configure. Closing the window stops the API (a Windows Job
  Object reaps the process tree even if the app is killed).
- **Own data folder.** Everything lives in `%LOCALAPPDATA%\Apollo-Delphi`: `apollo.db` (SQLite), `uploads`,
  `workspaces` (the werkmap repositories) and `models` (downloaded GGUF files). Back that folder up to back up
  the app. The database is built and upgraded by Alembic at every start. Search runs over the stored vectors in
  Python and keyword search in memory, which is fine for one person's documents; Docker Compose with
  PostgreSQL/pgvector remains the setup for larger collections. The two do not share data.
- **A local PostgreSQL instead of SQLite.** Put `DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/apollo_desktop`
  in `backend/.env` (git ignores it; `APOLLO_DATABASE_URL` works too, in the environment or in that file, and wins).
  At every start the app checks that the database exists and creates it when it does not (the user needs the
  CREATE DATABASE right, a superuser has it), and checks that the server has the pgvector extension. Windows has no official pgvector download:
  `scripts/install-pgvector-windows.ps1`, run as administrator, builds it from the official source with the MSVC
  build tools and copies it into your PostgreSQL. Uploads and werkmappen stay in the data folder; the migrations
  run at every start, as for SQLite.
- **Folder picker.** In the desktop app the setup wizard browses your real folders.
- **Not an installer yet.** The shell runs from this repository: it starts the repository's `.venv`, so moving the
  folder means running the setup again. A self-contained installer would have to bundle Python as well.
- **API log.** If the app does not start, the window shows the last lines of
  `%TEMP%\apollo-delphi-backend.log`.

## Configuration

All configuration is environment-driven (see `.env.example`). Keys:

- `APOLLO_DATABASE_URL` — Postgres (primary) or SQLite (dev/tests)
- `LLM_PROVIDER` / `LLM_MODEL` — `mock` (deterministic, offline) or `openai`
- `EMBEDDING_PROVIDER` (`mock` | `openai`) / `EMBEDDING_MODEL` / `EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` — any
  OpenAI-compatible `/embeddings` endpoint (OpenAI, Ollama, llama-server, Jina, Gemini, …); all configurable in the app.
  Every vector records its model and dimension; changing model means re-indexing (see *Embeddings* below).
- `OPENAI_API_KEY` — only for real providers; **never hard-code keys**
- `UPLOAD_DIR`, `MAX_UPLOAD_SIZE_MB`, `ALLOWED_EXTENSIONS`
- `CHUNK_SIZE_CHARS`, `CHUNK_OVERLAP_CHARS`, `SEARCH_TOP_K`

## The mock providers (important)

Apollo defaults to deterministic mock LLM/embedding providers so the **entire**
pipeline runs offline and tests are reproducible. These are not fake results:
claim extraction, contradiction detection, open-question detection,
supersession-based resolution, knowledge synthesis and verification are real
implementations operating on your actual document text. Switching
`LLM_PROVIDER=openai` replaces the reasoning stages with LLM-backed structured
outputs validated by Pydantic models — the data model and pipeline are identical.

## API

```
GET    /api/health
POST   /api/documents                      upload (multipart); optional form field relative_path = the file's path
                                           inside an uploaded folder ("docs/adr/001.md"): names the document and is
                                           kept under the werkmap's Inbox. The Documents page's "Map uploaden" walks
                                           a chosen folder recursively and skips what is already there.
GET    /api/documents                      list
GET    /api/documents/{id}
DELETE /api/documents/{id}
POST   /api/documents/{id}/index          extraction → chunking → embedding → vectors
GET    /api/documents/{id}/text            the extracted text of a document with its pages and the lines of its
                                           fragments, for the reading pane
GET    /api/documents/{id}/file            the original file, inline (a PDF is shown in the viewer of the browser)
GET    /api/documents/{id}/html            a Word document converted to HTML (mammoth), for the formatted view
POST   /api/documents/index-queue          index documents in the background and return at once: first every
                                           document is READ (extract, cut into fragments: status `parsed`, readable and
                                           searchable by words within seconds), then they are EMBEDDED one at a time
                                           (status `indexed`)
GET    /api/documents/index-queue          progress: total, parsed, done, failed, phase, current, seconds per document
POST   /api/documents/folder/scan          read a folder of this machine recursively: what would be imported (with
                                           hashes) and what is skipped, and why
POST   /api/documents/folder/file          import one scanned file, named by its path ("folder/docs/a.md")
GET    /api/search?q=...&workspace_id=&mode=   hybrid search (default): meaning + exact words, fused with RRF;
                                           mode=semantic|keyword to use one leg; only that werkmap's documents
POST   /api/ask                              ask a question in a werkmap: cited answer ([n] -> fragments), checked
GET    /api/ask/history?workspace_id=       earlier questions and answers of a werkmap
GET    /api/embeddings/status              active model, dimension, how much of the index is current
GET/PUT /api/embeddings/settings           embedding provider, endpoint, key (write-only), model
POST   /api/embeddings/test                embed a probe text: proves the endpoint answers, reveals the dimension
POST   /api/embeddings/reindex             re-embed stale documents (?everything=true for all, ?workspace_id=)
GET    /api/embeddings/catalog             recommended local models per runtime (ollama | llamacpp)
GET/POST /api/embeddings/models/pull       download a recommended model to a local runtime, with progress
POST   /api/analysis                       run analysis over the collection
GET    /api/analysis/{id}
GET    /api/analysis/{id}/claims
GET    /api/analysis/{id}/issues
GET    /api/issues                         list issues
GET    /api/issues/{id}                    detail incl. claims + evidence
POST   /api/issues/{id}/investigate        investigate + propose resolution
POST   /api/issues/{id}/resolve            human review (accept/reject/unresolved)
GET    /api/knowledge                      knowledge state
POST   /api/knowledge/build?analysis_run_id=
POST   /api/documents/generate             plan → draft → verify from knowledge state
GET    /api/documents/generated/list
GET    /api/documents/generated/{id}
GET    /api/documents/generated/{id}/verification
```

## Project structure

```
apollo/
├── frontend/                  React + TS + Vite + Tailwind
│   └── src/pages/              Documents, Analysis, Issues, Knowledge, Generated
├── backend/
│   ├── app/
│   │   ├── api/                FastAPI routers (no ORM objects cross the boundary)
│   │   ├── core/               config, LLM provider abstraction, embeddings abstraction
│   │   ├── db/                 session, dialect-adaptive vector column
│   │   ├── models/            documents, chunks, claims, evidence, issues,
│   │   │                      investigations, resolutions, knowledge, generated docs,
│   │   │                      verification findings, human decisions
│   │   ├── schemas/           Pydantic request/response models
│   │   └── services/          documents, extraction, chunking, embeddings, search,
│   │                          analysis, issues, resolution, knowledge, generation,
│   │                          verification
│   └── tests/                 unit + integration + end-to-end
├── migrations/                Alembic (pgvector-aware)
├── docker-compose.yml         Postgres+pgvector, backend, frontend
├── .env.example
└── README.md
```

## Database model

`documents`, `document_chunks` (with vector column), `claims`, `evidence`,
`claim_evidence`, `issues`, `issue_evidence`, `issue_claims`, `investigations`,
`resolutions`, `human_decisions`, `analysis_runs`, `knowledge_items`,
`generated_documents`, `verification_findings`.

Proper foreign keys throughout; JSON only for flexible metadata. The reasoning
state is queryable relational data, never a single JSON blob.

## Evidence semantics

Every claim links to evidence rows with `evidence_type`:

- `explicit` — directly stated in a source (page/section/original text preserved)
- `derived` — inferred from multiple pieces of evidence
- `assumption` — required for reasoning but not established
- `uncertainty` — insufficient evidence

Inferences and assumptions are never silently converted into facts.

## Testing

```bash
cd backend
pytest
```

36 tests: unit (extraction, chunking, embeddings, claim extraction, issue and
contradiction detection), integration (upload, indexing, failures, search), and
an end-to-end test covering the complete loop:

```
Upload A/B/C → index → analyze → claims → open questions → contradictions →
investigate → resolve (supersession) → human accept → knowledge state →
generate → verify
```

All tests use the deterministic mock providers; no external API is required.

## GitHub repository ingestion

You can add a **GitHub repository** to a workspace (Documents page, "GitHub
repository" card, or `POST /api/github/ingest`):

```json
{"repo_url": "https://github.com/owner/repo", "workspace_id": 1}
```

- The repository (docs, config, code) is downloaded and indexed as **one
  document per repository** — the interface stays clean, not one row per file.
- The digest keeps per-file sections (`## FILE: path`) so extracted claims
  remain traceable to concrete repo paths.
- The standard analysis pipeline then finds **discrepancies between your
  documents and the repository**: e.g. a plan stating "the frontend is Vue"
  against a repo whose README says React/TypeScript surfaces as a
  contradiction issue with evidence on both sides.
- Public repos work without configuration; for higher rate limits or private
  repos set `APOLLO_GITHUB_TOKEN` in the environment.

## Security

- Upload validation: extension allowlist, size limit, empty-file rejection
- Server-generated storage names; filenames never touch the filesystem
- Path traversal and filename tricks rejected
- No filesystem paths exposed through the API
- Pydantic validation on all inputs; no ORM objects exposed
- Secrets only via environment variables

## Embeddings

Semantic search needs an embedding model. `mock` is deterministic and offline but not semantic; for real
search point `EMBEDDING_PROVIDER=openai` at any OpenAI-compatible endpoint (Instellingen › Embeddingmodel).

- **Hosted**: OpenAI (`text-embedding-3-small`), Jina, Gemini's OpenAI endpoint, …
- **Local**: a running Ollama or `llama-server`. The app can download the recommended models for you
  (`BAAI/bge-m3` via an Ollama pull; GGUF files for llama.cpp into `LLAMACPP_MODELS_DIR`). It does not
  change your configuration by itself: after a download you choose the model, save, and re-index.
- **On the GPU (Vulkan, Windows)**: embedding on a CPU takes about 1.3 s per fragment with Jina code 1.5B (100
  documents ≈ half an hour); an AMD Radeon RX 7800 XT does it in 0.04 s (about 30 times faster, 36 documents in 3 s).
  Docker Desktop cannot give a Vulkan GPU to a container, so `scripts/llama-vulkan.ps1` runs the official Windows
  build of llama-server directly (it downloads it once, 32 MB, and checks GitHub's SHA-256), on port 8082. Set the
  Base URL to `http://localhost:8082/v1` and keep the same model name: the vectors are practically identical
  (cosine 0.9998), so nothing has to be re-indexed. `-Stop` stops it.
- **llama.cpp in docker-compose**: `docker compose --profile llama up -d llama` (or `COMPOSE_PROFILES=llama` in
  `.env`) starts a `llama-server` that serves a GGUF from `backend/models`, the folder the app downloads into.
  Download the model in Instellingen, choose it (Base URL becomes `http://llama:8080/v1`), save, test, re-index.
  The server loads one model at start: for another one set `LLAMA_MODEL_FILE` (and `LLAMA_POOLING`: `last` for
  the Jina code model, `cls` for bge-m3) and run `up -d llama` again.
- **Name translation**: the same logical model has different names per runtime (`BAAI/bge-m3` is `bge-m3` on
  Ollama and `bge-m3-Q8_0.gguf` on llama-server); the app sends the right one for the configured endpoint.
- **Safety**: each chunk stores `embedding_model` and `embedding_dim`; vectors returned with the wrong size are
  rejected before storage, and search only compares vectors produced by the active model. Documents embedded
  with another model show up as *stale* until re-indexed.

## Search

`GET /api/search` is hybrid by default: a **semantic** leg (vectors, only those of the active embedding model)
and a **keyword** leg (PostgreSQL full-text with the language-neutral `'simple'` configuration and a GIN index;
an in-memory BM25 on SQLite) are merged with Reciprocal Rank Fusion (`1/(60+rank)` per leg). Embeddings find
paraphrases; the keyword leg finds exact amounts, names and identifiers (`250000`, `Maria Chen`, `ADR-0042`) that
embeddings handle poorly, which is what claims and contradictions are made of. A hit found by both legs ranks first
and is labelled `match: both`. Keyword search does not depend on embeddings, so documents embedded with an older
model stay findable until they are re-indexed. If the embedding endpoint is down, hybrid falls back to keywords.
Tuning: `SEARCH_RRF_K` (60) and `SEARCH_CANDIDATE_MULTIPLIER` (5).

## Asking questions

`POST /api/ask {question, workspace_id, follow_up_of?}` answers from the documents of one werkmap only. Retrieval is the hybrid
search above; the main model gets the fragments as numbered sources, must use *only* those, and marks each
statement with `[n]`. The answer is then **checked** before you see it:

- a `[n]` that points at a source that was never offered is removed and reported (models invent citations);
- an answer with no valid citation is marked `grounded: false`;
- every number in the answer must occur in the sources it cites, otherwise it is reported;
- when the documents do not contain the answer the model must say so (`NO_ANSWER`) and you are told, instead of
  receiving a guess. With an empty werkmap no model is called at all.

The cited fragments are returned verbatim, and each question with its answer is stored (`qa_entries`) so it stays
inspectable. With the offline `mock` model the answer is *extractive* (the best matching sentences, each cited) and
is labelled as such. The UI page is *Vragen*; `ASK_TOP_K` (8) sets how many fragments the model reads.

**Follow-up questions.** Pass `follow_up_of` (the id of an earlier answer in the same werkmap) to continue a
conversation. The follow-up is first rewritten into a question that stands on its own ("En wanneer?" → "Wanneer is
het havenbudget klaar?"), by the model, or offline by putting the previous question's topic in front of it. That
rewrite (`standalone_question`) is what retrieval searches for and is shown in the UI. The last `ASK_HISTORY_TURNS`
(3) turns are given to the model as context, explicitly *not* as a source: every statement still needs a freshly
retrieved fragment and goes through the same checks, so a number that only the conversation mentions is flagged.
