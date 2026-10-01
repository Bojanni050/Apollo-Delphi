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
POST   /api/documents                      upload (multipart)
GET    /api/documents                      list
GET    /api/documents/{id}
DELETE /api/documents/{id}
POST   /api/documents/{id}/index          extraction → chunking → embedding → vectors
GET    /api/search?q=...&workspace_id=&mode=   hybrid search (default): meaning + exact words, fused with RRF;
                                           mode=semantic|keyword to use one leg; only that werkmap's documents
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
