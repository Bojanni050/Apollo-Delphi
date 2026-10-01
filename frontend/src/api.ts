export const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

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
  indexing_status: 'pending' | 'processing' | 'indexed' | 'failed'
  error_message: string | null
  created_at: string
  indexed_at: string | null
  document_date: string | null
  source_type: string
  source_url: string | null
  repo_path: string | null
}

export interface AnalysisStats {
  documents_analyzed: number
  claims: number
  open_questions: number
  contradictions: number
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

export interface ModelList {
  models: string[]
  error: string | null
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
  uploadDocument: (file: File, workspaceId?: number | null) => {
    const form = new FormData()
    form.append('file', file)
    const qs = workspaceId ? `?workspace_id=${workspaceId}` : ''
    return request<DocumentRecord>(`/api/documents${qs}`, { method: 'POST', body: form })
  },
  indexDocument: (id: number) => request<DocumentRecord>(`/api/documents/${id}/index`, { method: 'POST' }),
  deleteDocument: (id: number) => request<void>(`/api/documents/${id}`, { method: 'DELETE' }),
  search: (q: string, workspaceId?: number | null, mode: SearchMode = 'hybrid') =>
    request<SearchResponse>(
      `/api/search?q=${encodeURIComponent(q)}&mode=${mode}${workspaceId ? `&workspace_id=${workspaceId}` : ''}`,
    ),
  ask: (question: string, workspaceId?: number | null, followUpOf?: number | null) =>
    request<Answer>('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, workspace_id: workspaceId ?? null, follow_up_of: followUpOf ?? null }),
    }),
  askHistory: (workspaceId?: number | null) =>
    request<Answer[]>(`/api/ask/history${workspaceId ? `?workspace_id=${workspaceId}` : ''}`),
  runAnalysis: (workspaceId?: number | null) =>
    request<AnalysisRun>(`/api/analysis${workspaceId ? `?workspace_id=${workspaceId}` : ''}`, { method: 'POST' }),
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
  unassigned: () => request<Unassigned>('/api/workspaces/unassigned'),
  adoptUnassigned: (workspaceId: number) =>
    request<AdoptResult>(`/api/workspaces/${workspaceId}/adopt-unassigned`, { method: 'POST' }),
  workspaceHistory: (id: number) => request<Commit[]>(`/api/workspaces/${id}/history`),
  getPulse: (workspaceId: number) => request<PulseResult>(`/api/workspaces/${workspaceId}/pulse`),
  runPulse: (workspaceId: number, force = false) =>
    request<PulseResult>(`/api/workspaces/${workspaceId}/pulse${force ? '?force=true' : ''}`, { method: 'POST' }),
  decidePulseItem: (id: number, decision: 'accepted' | 'dismissed') =>
    request<PulseItem>(`/api/pulse/items/${id}/decision`, {
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
  llmModels: (tier: LLMTierName, provider: string, baseUrl: string) =>
    request<ModelList>(`/api/llm/models?tier=${tier}&provider=${provider}&base_url=${encodeURIComponent(baseUrl)}`),
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
