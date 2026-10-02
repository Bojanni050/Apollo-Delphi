export const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

/**
 * A date from the API as a Date. The server stores UTC; SQLite hands it back without a time zone ("2026-10-02T00:59:25"),
 * which the browser would read as local time and show hours off. Without a zone it is UTC.
 */
export const serverDate = (iso: string): Date => new Date(/([zZ]|[+-]\d\d:?\d\d)$/.test(iso) ? iso : `${iso}Z`)

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      // keep statusText
    }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export interface DocumentRecord {
  id: number
  filename: string
  title: string | null
  file_type: string
  file_size: number
  /** SHA-256 of the file. */
  content_hash: string
  indexing_status: 'pending' | 'processing' | 'parsed' | 'indexed' | 'failed'
  error_message: string | null
  created_at: string
  indexed_at: string | null
  document_date: string | null
  source_type: string
  source_url: string | null
  repo_path: string | null
  /** Where the copy in the werkmap's git repository lives ("Inbox/a.md", "Reports/a.md" once Delphi Pulse sorted it). */
  inbox_path: string | null
  /** The virtual folder (group), set by accepting a Delphi Pulse suggestion. */
  group_name: string | null
}

export interface AnalysisStats {
  documents_analyzed: number
  claims: number
  open_questions: number
  contradictions: number
  /** The groups the run was limited to; absent = every document. */
  groups?: string[] | null
}

export interface AnalysisRun {
  id: number
  status: string
  stats: AnalysisStats | null
  error_message: string | null
  started_at: string
  completed_at: string | null
}

export interface Claim {
  id: number
  document_id: number
  statement: string
  subject: string | null
  predicate: string | null
  value: string | null
  unit: string | null
  status: string
  confidence: number
}

export interface EvidenceRecord {
  id: number
  document_id: number
  evidence_type: string
  page_number: number | null
  section: string | null
  line_start: number | null
  line_end: number | null
  original_text: string
}

export interface Resolution {
  id: number
  issue_id: number
  status: string
  conclusion: string | null
  reasoning: string | null
  explanation_type: string | null
  confidence: number
  unresolved_uncertainty: string | null
  resolved_by: string
  created_at: string
}

export interface Issue {
  id: number
  analysis_run_id: number
  issue_type: 'open_question' | 'contradiction'
  title: string
  question: string | null
  status: string
  severity: string
  created_at: string
}

export interface IssueDetail extends Issue {
  description: string | null
  claims: Claim[]
  evidence: EvidenceRecord[]
  resolution: Resolution | null
}

export interface KnowledgeItem {
  id: number
  analysis_run_id: number
  item_type: string
  statement: string
  explanation: string | null
  confidence: number
  provenance: string | null
  source_refs: string | null
}

export interface SearchHit {
  chunk_id: number
  document_id: number
  document_filename: string
  excerpt: string
  page_number: number | null
  section: string | null
  line_start: number | null
  line_end: number | null
  similarity: number
  score: number
  match: 'semantic' | 'keyword' | 'both'
}

export type SearchMode = 'hybrid' | 'semantic' | 'keyword'

export interface SearchResponse {
  query: string
  /** The mode that actually ran: hybrid falls back to keyword when the embedding endpoint is down. */
  mode: SearchMode
  results: SearchHit[]
}

export interface Citation {
  n: number
  chunk_id: number
  document_id: number
  document_filename: string
  page_number: number | null
  section: string | null
  line_start: number | null
  line_end: number | null
  excerpt: string
  match: 'semantic' | 'keyword' | 'both'
}

export interface Answer {
  id: number
  workspace_id: number | null
  /** The answer this question follows up on; null for a first question. */
  parent_id: number | null
  question: string
  /** What retrieval searched for when this was a follow-up (the question rewritten to stand on its own). */
  standalone_question: string | null
  answer: string
  answered: boolean
  grounded: boolean
  citations: Citation[]
  warnings: string[]
  sources_considered: number
  search_mode: string
  model_provider: string
  model_name: string
  created_at: string
}

export interface VerificationFinding {
  id: number
  severity: 'info' | 'warning' | 'error'
  finding_type: string
  statement: string | null
  evidence: string | null
  expected: string | null
  recommendation: string | null
}

export interface GeneratedDocument {
  id: number
  workspace_id: number | null
  title: string
  status: string
  content: string | null
  outline: string | null
  verification_status: string
  revision: number
  generation_metadata: string | null
  created_at: string
}

/** A document in full, for the reading pane. Line numbers refer to ``text``. */
export interface DocumentText {
  id: number
  workspace_id: number | null
  filename: string
  title: string | null
  file_type: string
  source_type: string
  text: string
  line_count: number
  /** The line where each page starts (PDF). */
  pages: { page_number: number; line: number }[]
  /** The indexed fragments and the lines they cover. */
  chunks: { id: number; chunk_index: number; section: string | null; page_number: number | null; line_start: number | null; line_end: number | null }[]
  truncated: boolean
}

/** A folder of the machine the backend runs on, read recursively by the backend (no browser upload). */
export interface FolderScan {
  /** Full path of the folder. */
  root: string
  /** The folder's own name: the first part of every imported file's name. */
  name: string
  files: { path: string; size: number; content_hash: string }[]
  skipped: { path: string; reason: string }[]
  /** More importable files than are listed. */
  truncated: boolean
}

/** Progress of the background indexing. */
export interface IndexProgress {
  active: boolean
  /** Documents in this batch; how many are read (parsed), completely indexed (embedded) and failed. */
  total: number
  parsed: number
  done: number
  failed: number
  /** "lezen" or "embedden" while a document is being worked on. */
  phase: string | null
  current: string | null
  /** Seconds of embedding per document so far in this batch. */
  seconds_per_document: number | null
  errors: { document_id: number; filename: string; error: string | null }[]
  added: number
}

export interface FolderBrowse {
  current_path: string
  /** null at the top (a drive root or "/"). */
  parent_path: string | null
  folders: { name: string; path: string }[]
  truncated: boolean
  drives: string[]
  quick_access: { name: string; path: string }[]
}

export interface Workspace {
  id: number
  name: string
  working_dir: string | null
  created_at: string
}

export interface Commit {
  sha: string
  author: string
  date: string
  message: string
}

export interface PulseConnection {
  document_id: number
  filename: string | null
  relation: 'relates-to' | 'supports' | 'contradicts' | 'extends'
  why: string
}

export interface PulseItem {
  id: number
  run_id: number
  document_id: number
  filename: string
  summary: string
  tags: string[]
  connections: PulseConnection[]
  confidence: number
  decision: 'pending' | 'accepted' | 'dismissed'
  /** Suggested type folder in the werkmap's repository (Reports, Drafts...), whether it is outside the fixed list, and the suggested group. */
  folder: string | null
  folder_is_new: boolean
  group: string | null
}

export interface PulseRun {
  id: number
  workspace_id: number
  status: string
  provider: string
  model: string
  stats: { documents: number; analysed: number; skipped: number; errors: number } | null
  error_message: string | null
  started_at: string
  completed_at: string | null
}

/** Delphi Weave: the groups, documents and connections as accepted in Delphi Pulse. */
export interface WeaveDocument {
  id: number
  filename: string
  group: string | null
  folder: string | null
  tags: string[]
}

export interface WeaveConnection {
  source: number
  target: number
  relation: 'relates-to' | 'supports' | 'contradicts' | 'extends'
  why: string
}

export interface Weave {
  documents: WeaveDocument[]
  connections: WeaveConnection[]
}

export interface PulseResult {
  run: PulseRun | null
  items: PulseItem[]
}

export type LLMTierName = 'main' | 'background'

export interface LLMTier {
  tier: LLMTierName
  provider: string
  model: string
  base_url: string
  configured: boolean
  inherits: boolean
  error: string | null
}

export interface LLMStatus {
  tiers: LLMTier[]
}

export type Provider = 'mock' | 'openai' | 'anthropic'

export interface TierSettings {
  provider: Provider | ''
  model: string
  base_url: string
  api_key_set: boolean
}

export interface LLMSettings {
  main: TierSettings
  background: TierSettings
  timeout_seconds: number
}

export interface TierUpdate {
  provider?: Provider | ''
  model?: string
  base_url?: string
  api_key?: string
}

export interface LLMSettingsUpdate {
  main?: TierUpdate
  background?: TierUpdate
  timeout_seconds?: number
}

/** What an endpoint says about a model; OpenRouter and EdenAI say a lot, most only give the id. */
export interface ModelInfo {
  id: string
  name: string | null
  provider: string | null
  description: string | null
  context_length: number | null
  /** USD per 1M tokens; null = not stated, 0 = free. */
  input_per_million: number | null
  output_per_million: number | null
  cache_read_per_million: number | null
  cache_write_per_million: number | null
  max_output_tokens: number | null
  /** "text", "image", "file", "audio", "video" */
  input_modalities: string[]
  output_modalities: string[]
  /** tools, parallel_tools, reasoning, structured_output, web_search, prompt_caching, computer_use */
  features: string[]
  regions: string[]
  /** Unix time the model was added. */
  created: number | null
}

export interface ModelList {
  models: string[]
  items: ModelInfo[]
  error: string | null
}

export interface RetrievalSettings {
  search_top_k: number
  search_rrf_k: number
  search_candidate_multiplier: number
  ask_top_k: number
  ask_history_turns: number
}

export interface EmbeddingSettings {
  provider: 'mock' | 'openai'
  model: string
  base_url: string
  api_key_set: boolean
  batch_size: number
  runtime: 'ollama' | 'llamacpp'
}

export interface EmbeddingSettingsUpdate {
  provider?: 'mock' | 'openai'
  model?: string
  base_url?: string
  api_key?: string
  batch_size?: number
  runtime?: 'ollama' | 'llamacpp'
}

export interface IndexStatus {
  provider: string | null
  model: string | null
  dimensions: number | null
  error: string | null
  chunks_total: number
  chunks_current: number
  documents_indexed: number
  documents_stale: number
  by_model: Record<string, number>
}

export interface EmbeddingTest {
  ok: boolean
  model: string | null
  dimensions: number | null
  millis: number | null
  error: string | null
}

export interface LocalRuntime {
  id: string
  label: string
  available: boolean
  message: string | null
  address: string
  /** The Base URL to use for a model served by this runtime. */
  endpoint: string
  active: boolean
}

export interface CatalogModel {
  name: string
  label: string
  role: string | null
  dimension: number | null
  note: string | null
  runtime: string
  identifier: string | null
  downloadable: boolean
  installed: boolean
  in_use: boolean
  official: boolean | null
  source: string | null
}

export interface EmbeddingCatalog {
  runtime: string
  runtimes: LocalRuntime[]
  models: CatalogModel[]
}

export interface PullStatus {
  model: string
  runtime: string
  status: 'idle' | 'starting' | 'downloading' | 'completed' | 'failed'
  percent: number | null
  message: string | null
  reindex_recommended: boolean
}

export interface ReindexResult {
  model: string
  requested: number
  reindexed: number
  failed: { document_id: number; error: string | null }[]
}

export interface Unassigned {
  documents: number
  analysis_runs: number
  generated_documents: number
}

export interface AdoptResult extends Unassigned {
  mirrored_to_repository: number
  not_mirrored: { document_id: number; filename: string; reason: string }[]
}

export interface LLMTestResult {
  ok: boolean
  tier: string
  model: string
  reply: string | null
  error: string | null
}

export interface WorkspaceDetail extends Workspace {
  document_count: number
  latest_analysis_run_id: number | null
}

export const api = {
  listDocuments: (workspaceId?: number | null) =>
    request<DocumentRecord[]>(`/api/documents${workspaceId ? `?workspace_id=${workspaceId}` : ''}`),
  /** ``relativePath``: the file's path inside an uploaded folder ("docs/adr/001.md"); it names the document. */
  uploadDocument: (file: File, workspaceId?: number | null, relativePath?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (relativePath) form.append('relative_path', relativePath)
    const qs = workspaceId ? `?workspace_id=${workspaceId}` : ''
    return request<DocumentRecord>(`/api/documents${qs}`, { method: 'POST', body: form })
  },
  indexDocument: (id: number) => request<DocumentRecord>(`/api/documents/${id}/index`, { method: 'POST' }),
  deleteDocument: (id: number) => request<void>(`/api/documents/${id}`, { method: 'DELETE' }),
  search: (q: string, workspaceId?: number | null, mode: SearchMode = 'hybrid', group?: string | null) =>
    request<SearchResponse>(
      `/api/search?q=${encodeURIComponent(q)}&mode=${mode}${workspaceId ? `&workspace_id=${workspaceId}` : ''}${
        group ? `&group=${encodeURIComponent(group)}` : ''
      }`,
    ),
  ask: (question: string, workspaceId?: number | null, followUpOf?: number | null) =>
    request<Answer>('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, workspace_id: workspaceId ?? null, follow_up_of: followUpOf ?? null }),
    }),
  askHistory: (workspaceId?: number | null) =>
    request<Answer[]>(`/api/ask/history${workspaceId ? `?workspace_id=${workspaceId}` : ''}`),
  /** Analyse the werkmap, or only the documents of the given groups ("__none__" = those without a group). */
  runAnalysis: (workspaceId?: number | null, groups: string[] = []) => {
    const qs = [workspaceId ? `workspace_id=${workspaceId}` : '', ...groups.map((g) => `groups=${encodeURIComponent(g)}`)].filter(Boolean).join('&')
    return request<AnalysisRun>(`/api/analysis${qs ? `?${qs}` : ''}`, { method: 'POST' })
  },
  listIssues: (status?: string, workspaceId?: number | null) => {
    const qs = [status ? `status=${status}` : '', workspaceId ? `workspace_id=${workspaceId}` : ''].filter(Boolean).join('&')
    return request<Issue[]>(`/api/issues${qs ? `?${qs}` : ''}`)
  },
  getIssue: (id: number) => request<IssueDetail>(`/api/issues/${id}`),
  investigateIssue: (id: number) => request<IssueDetail>(`/api/issues/${id}/investigate`, { method: 'POST' }),
  resolveIssue: (id: number, decision: string, note?: string) =>
    request<Resolution>(`/api/issues/${id}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, note }),
    }),
  buildKnowledge: (analysisRunId: number) =>
    request<KnowledgeItem[]>(`/api/knowledge/build?analysis_run_id=${analysisRunId}`, { method: 'POST' }),
  getKnowledge: (workspaceId?: number | null) =>
    request<KnowledgeItem[]>(`/api/knowledge${workspaceId ? `?workspace_id=${workspaceId}` : ''}`),
  generateDocument: (title: string, analysisRunId?: number, workspaceId?: number | null) =>
    request<GeneratedDocument>(
      `/api/documents/generate?title=${encodeURIComponent(title)}${analysisRunId ? `&analysis_run_id=${analysisRunId}` : ''}${workspaceId ? `&workspace_id=${workspaceId}` : ''}`,
      { method: 'POST' },
    ),
  listGenerated: (workspaceId?: number | null) =>
    request<GeneratedDocument[]>(`/api/documents/generated/list${workspaceId ? `?workspace_id=${workspaceId}` : ''}`),
  getVerification: (id: number) => request<VerificationFinding[]>(`/api/documents/generated/${id}/verification`),
  health: () => request<Record<string, string>>('/api/health'),
  ingestGithub: (repoUrl: string, workspaceId?: number | null) =>
    request<{ repository: string; branch: string; files_selected: number; documents_created: number; errors: string[] }>(
      '/api/github/ingest',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_url: repoUrl, workspace_id: workspaceId ?? null }),
      },
    ),
  listWorkspaces: () => request<Workspace[]>('/api/workspaces'),
  createWorkspace: (name: string, workingDir?: string) =>
    request<Workspace>('/api/workspaces', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, working_dir: workingDir || null }),
    }),
  documentText: (id: number) => request<DocumentText>(`/api/documents/${id}/text`),
  documentHtml: (id: number) => request<{ html: string; warnings: number }>(`/api/documents/${id}/html`),
  /** The original file, to show inline (a PDF in the viewer of the browser). */
  documentFileUrl: (id: number) => `${API_BASE}/api/documents/${id}/file`,
  scanFolder: (path: string) =>
    request<FolderScan>('/api/documents/folder/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    }),
  /** Import one file of a scanned folder (the backend reads it from disk). */
  importFolderFile: (workspaceId: number | null, root: string, path: string) =>
    request<DocumentRecord>('/api/documents/folder/file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: workspaceId, root, path }),
    }),
  /** Index in the background and return at once: every pending document of the werkmap, or just ``documentIds``. */
  queueIndexing: (workspaceId: number | null, documentIds?: number[]) =>
    request<IndexProgress>('/api/documents/index-queue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: workspaceId, document_ids: documentIds ?? null }),
    }),
  indexingProgress: () => request<IndexProgress>('/api/documents/index-queue'),
  browseFolders: (path?: string) =>
    request<FolderBrowse>(`/api/system/folders${path ? `?path=${encodeURIComponent(path)}` : ''}`),
  unassigned: () => request<Unassigned>('/api/workspaces/unassigned'),
  adoptUnassigned: (workspaceId: number) =>
    request<AdoptResult>(`/api/workspaces/${workspaceId}/adopt-unassigned`, { method: 'POST' }),
  workspaceHistory: (id: number) => request<Commit[]>(`/api/workspaces/${id}/history`),
  weave: (workspaceId: number) => request<Weave>(`/api/workspaces/${workspaceId}/weave`),
  getPulse: (workspaceId: number) => request<PulseResult>(`/api/workspaces/${workspaceId}/pulse`),
  runPulse: (workspaceId: number, force = false) =>
    request<PulseResult>(`/api/workspaces/${workspaceId}/pulse${force ? '?force=true' : ''}`, { method: 'POST' }),
  decidePulseItem: (id: number, decision: 'accepted' | 'dismissed') =>
    request<PulseItem>(`/api/pulse/items/${id}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision }),
    }),
  /** Accept or dismiss every suggestion of the werkmap that still awaits a decision. */
  decideAllPulse: (workspaceId: number, decision: 'accepted' | 'dismissed') =>
    request<{ decision: string; decided: number }>(`/api/workspaces/${workspaceId}/pulse/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision }),
    }),
  llmStatus: () => request<LLMStatus>('/api/llm/status'),
  getLlmSettings: () => request<LLMSettings>('/api/llm/settings'),
  updateLlmSettings: (body: LLMSettingsUpdate) =>
    request<LLMSettings>('/api/llm/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  /** Models the endpoint offers, for what is typed in the form: nothing needs to be saved first. The key travels in the body. */
  llmModels: (tier: LLMTierName, provider: string, baseUrl: string, apiKey = '') =>
    request<ModelList>('/api/llm/models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tier, provider, base_url: baseUrl, api_key: apiKey || null }),
    }),
  getRetrievalSettings: () => request<RetrievalSettings>('/api/retrieval/settings'),
  updateRetrievalSettings: (body: Partial<RetrievalSettings>) =>
    request<RetrievalSettings>('/api/retrieval/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  getEmbeddingSettings: () => request<EmbeddingSettings>('/api/embeddings/settings'),
  updateEmbeddingSettings: (body: EmbeddingSettingsUpdate) =>
    request<EmbeddingSettings>('/api/embeddings/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  embeddingStatus: () => request<IndexStatus>('/api/embeddings/status'),
  embeddingTest: () => request<EmbeddingTest>('/api/embeddings/test', { method: 'POST' }),
  reindex: (everything = false) =>
    request<ReindexResult>(`/api/embeddings/reindex${everything ? '?everything=true' : ''}`, { method: 'POST' }),
  embeddingCatalog: (runtime?: string) =>
    request<EmbeddingCatalog>(`/api/embeddings/catalog${runtime ? `?runtime=${runtime}` : ''}`),
  pullStatus: (runtime: string, model: string) =>
    request<PullStatus>(`/api/embeddings/models/pull?runtime=${runtime}&model=${encodeURIComponent(model)}`),
  startPull: (runtime: string, model: string) =>
    request<PullStatus>('/api/embeddings/models/pull', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ runtime, model }),
    }),
  llmTest: (tier: LLMTierName) => request<LLMTestResult>(`/api/llm/test?tier=${tier}`, { method: 'POST' }),
}

/** "regel 12" or "regels 12–18"; empty when the range is unknown. */
export function formatLines(start: number | null, end: number | null): string {
  if (start == null) return ''
  return end == null || end === start ? `regel ${start}` : `regels ${start}–${end}`
}
