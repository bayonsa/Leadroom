import type { EmailAccountInput, EmailAccountsResponse, Lead, LocalDataPreview, LocalDataStatus, MarketHistory, ModelBenchmark, OllamaCatalogResponse, OllamaModelsResponse, OllamaPullJob, OutreachDraft, OutreachPreflight, OutreachSendJob, Problem, RepositoryLead, RepositoryResponse, RunCreate, RunDetail, RunSummary, StorageSettings, StorageSettingsUpdate, Suppression, WorkspaceSettings, WorkspaceSettingsUpdate } from './types'

export const API_BASE = import.meta.env.VITE_API_URL ?? '/api/v1'

export class ApiError extends Error {
  detail: Problem
  status: number

  constructor(detail: Problem, status: number) {
    super(detail.cause)
    this.detail = detail
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const fallback: Problem = {
      problem: 'Request failed',
      cause: `The API returned ${response.status}.`,
      fix: 'Check that the local API is running and try again.',
    }
    throw new ApiError(await response.json().catch(() => fallback), response.status)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string; database: string }>('/health'),
  listRuns: () => request<RunSummary[]>('/runs'),
  getRun: (runId: string) => request<RunDetail>(`/runs/${runId}`),
  createRun: (payload: RunCreate) =>
    request<RunDetail>('/runs', { method: 'POST', body: JSON.stringify(payload) }),
  discoveryHistory: (niche: string, location: string) =>
    request<MarketHistory>(`/discovery/history?niche=${encodeURIComponent(niche)}&location=${encodeURIComponent(location)}`),
  selectCandidate: (runId: string, domain: string, selected: boolean) =>
    request(`/runs/${runId}/candidates/${encodeURIComponent(domain)}`, {
      method: 'PUT',
      body: JSON.stringify({ selected }),
    }),
  startRun: (runId: string) => request(`/runs/${runId}/start`, { method: 'POST' }),
  cancelRun: (runId: string) => request(`/runs/${runId}/cancel`, { method: 'POST' }),
  continueRun: (runId: string) => request<{ run_id: string; status: string; kind: 'discovery' | 'enrichment'; recovered: number }>(`/runs/${runId}/continue`, { method: 'POST' }),
  deleteRun: (runId: string) => request<{ id: string; status: string }>(`/runs/${runId}`, { method: 'DELETE' }),
  retryRun: (runId: string) => request(`/runs/${runId}/retry`, { method: 'POST' }),
  discoverMore: (runId: string, source: 'local' | 'web' | 'both') => request<{ run_id: string; status: string; kind: 'discovery'; source: string }>(`/runs/${runId}/discover-more?source=${source}`, { method: 'POST' }),
  updateLead: (runId: string, domain: string, changes: Partial<Pick<Lead, 'business_name' | 'generic_email' | 'phone' | 'city_or_area' | 'website_quality_note'>>) =>
    request<Lead>(`/runs/${runId}/leads/${encodeURIComponent(domain)}`, {
      method: 'PATCH', body: JSON.stringify(changes),
    }),
  repository: () => request<RepositoryResponse>('/repository'),
  importToRepository: (runId: string, domains?: string[]) =>
    request<{ added: number; updated: number; skipped: number; total: number }>('/repository/import', {
      method: 'POST', body: JSON.stringify({ run_id: runId, domains }),
    }),
  deleteRepositoryLead: (domain: string) =>
    request<{ domain: string; status: string }>(`/repository/${encodeURIComponent(domain)}`, { method: 'DELETE' }),
  updateRepositoryLead: (domain: string, changes: { business_name?: string; city_or_area?: string; website?: string; emails?: string[]; phones?: string[]; collection?: string }) =>
    request<RepositoryLead>(`/repository/${encodeURIComponent(domain)}`, { method: 'PATCH', body: JSON.stringify(changes) }),
  mergeRepositoryCollections: (sources: string[], target: string) =>
    request<{ status: string; sources: string[]; target: string; updated_leads: number }>('/repository/collections/merge', {
      method: 'POST', body: JSON.stringify({ sources, target }),
    }),
  deleteRepositoryCollection: (name: string) =>
    request<{ status: string; collection: string; moved_to: string; updated_leads: number }>(`/repository/collections/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  repositoryExportUrl: (format: 'csv' | 'json') => `${API_BASE}/repository/export?format=${format}`,
  localDataStatus: () => request<LocalDataStatus>('/local-data/status'),
  updateLocalData: () => request<{ status: string; message: string }>('/local-data/update', { method: 'POST' }),
  localDataPreview: (niche: string, location: string) =>
    request<LocalDataPreview>(`/local-data/preview?niche=${encodeURIComponent(niche)}&location=${encodeURIComponent(location)}`),
  settings: () => request<WorkspaceSettings>('/settings'),
  updateSettings: (payload: WorkspaceSettingsUpdate) =>
    request<WorkspaceSettings>('/settings', { method: 'PUT', body: JSON.stringify(payload) }),
  updateTheme: (theme: WorkspaceSettings['theme']) =>
    request<WorkspaceSettings>('/settings/theme', { method: 'PATCH', body: JSON.stringify({ theme }) }),
  storageSettings: () => request<StorageSettings>('/settings/storage'),
  updateStorageSettings: (payload: StorageSettingsUpdate) =>
    request<StorageSettings>('/settings/storage', { method: 'PUT', body: JSON.stringify(payload) }),
  browseStorageFolder: (initialPath: string) =>
    request<{ path: string }>('/settings/storage/browse', { method: 'POST', body: JSON.stringify({ initial_path: initialPath }) }),
  emailAccounts: () => request<EmailAccountsResponse>('/settings/email-accounts'),
  createEmailAccount: (payload: EmailAccountInput) => request<EmailAccountsResponse>('/settings/email-accounts', { method: 'POST', body: JSON.stringify(payload) }),
  updateEmailAccount: (accountId: string, payload: EmailAccountInput) => request<EmailAccountsResponse>(`/settings/email-accounts/${accountId}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteEmailAccount: (accountId: string) => request<EmailAccountsResponse>(`/settings/email-accounts/${accountId}`, { method: 'DELETE' }),
  setDefaultEmailAccount: (accountId: string) => request<EmailAccountsResponse>(`/settings/email-accounts/${accountId}/default`, { method: 'PATCH' }),
  testEmailAccount: (accountId: string) => request<{ status: string; account_id: string; label: string; sender: string }>(`/settings/email-accounts/${accountId}/test`, { method: 'POST' }),
  testModelConnection: () => request<{ status: string; provider: string; model: string }>('/settings/test-model', { method: 'POST' }),
  testEmailConnection: () => request<{ status: string; host: string; port: number; security: string; sender: string }>('/settings/test-email', { method: 'POST' }),
  ollamaModels: () => request<OllamaModelsResponse>('/settings/ollama/models'),
  ollamaCatalog: (query: string) => request<OllamaCatalogResponse>(`/settings/ollama/catalog?q=${encodeURIComponent(query)}`),
  pullOllamaModel: (model: string) => request<OllamaPullJob>('/settings/ollama/pull', { method: 'POST', body: JSON.stringify({ model }) }),
  ollamaPullStatus: (jobId: string) => request<OllamaPullJob>(`/settings/ollama/pulls/${jobId}`),
  benchmarkOllamaModel: (model: string) => request<ModelBenchmark>('/settings/ollama/benchmark', { method: 'POST', body: JSON.stringify({ model }) }),
  listDrafts: () => request<OutreachDraft[]>('/outreach/drafts'),
  createDraft: (payload: Record<string, unknown>) =>
    request<OutreachDraft>('/outreach/drafts', { method: 'POST', body: JSON.stringify(payload) }),
  outreachPreflight: (runId: string) =>
    request<OutreachPreflight>('/outreach/preflight', { method: 'POST', body: JSON.stringify({ run_id: runId }) }),
  createDraftsBulk: (payload: Record<string, unknown>) =>
    request<{ created: number; skipped: number; drafts: OutreachDraft[]; errors: Array<{ domain: string; reason: string }> }>('/outreach/drafts/bulk', { method: 'POST', body: JSON.stringify(payload) }),
  approveDraft: (draftId: string, payload: Record<string, unknown>) =>
    request<OutreachDraft>(`/outreach/drafts/${draftId}/approve`, {
      method: 'POST', body: JSON.stringify(payload),
    }),
  approveDraftsBulk: (draftIds: string[], payload: Record<string, unknown>) =>
    request<{ approved: number; drafts: OutreachDraft[] }>('/outreach/drafts/approve-bulk', {
      method: 'POST', body: JSON.stringify({ draft_ids: draftIds, ...payload }),
    }),
  sendOutreach: (draftIds: string[], emailAccountId: string) => request<OutreachSendJob>('/outreach/send', { method: 'POST', body: JSON.stringify({ draft_ids: draftIds, email_account_id: emailAccountId }) }),
  outreachSendStatus: (jobId: string) => request<OutreachSendJob>(`/outreach/send/${jobId}`),
  stopOutreachSend: (jobId: string) => request<OutreachSendJob>(`/outreach/send/${jobId}/stop`, { method: 'POST' }),
  listSuppressions: () => request<Suppression[]>('/compliance/suppressions'),
  addSuppression: (payload: { value: string; kind: 'email' | 'domain'; reason: string }) =>
    request<Suppression>('/compliance/suppressions', { method: 'POST', body: JSON.stringify(payload) }),
  exportOutreach: async (draftIds: string[]) => {
    const response = await fetch(`${API_BASE}/outreach/export`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ draft_ids: draftIds }),
    })
    if (!response.ok) throw new ApiError(await response.json(), response.status)
    return response.blob()
  },
  exportUrl: (runId: string, format: 'csv' | 'json') => `${API_BASE}/runs/${runId}/export?format=${format}`,
}
