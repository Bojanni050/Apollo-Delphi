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
  similarity: number
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
  created_at: string
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
  search: (q: string) => request<{ query: string; results: SearchHit[] }>(`/api/search?q=${encodeURIComponent(q)}`),
  runAnalysis: (workspaceId?: number | null) =>
    request<AnalysisRun>(`/api/analysis${workspaceId ? `?workspace_id=${workspaceId}` : ''}`, { method: 'POST' }),
  listIssues: (status?: string) =>
    request<Issue[]>(`/api/issues${status ? `?status=${status}` : ''}`),
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
  getKnowledge: () => request<KnowledgeItem[]>('/api/knowledge'),
  generateDocument: (title: string, analysisRunId?: number) =>
    request<GeneratedDocument>(
      `/api/documents/generate?title=${encodeURIComponent(title)}${analysisRunId ? `&analysis_run_id=${analysisRunId}` : ''}`,
      { method: 'POST' },
    ),
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
  createWorkspace: (name: string) =>
    request<Workspace>('/api/workspaces', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }),
}
