export type RunStatus = 'created' | 'ready' | 'searching' | 'running' | 'completed' | 'failed' | 'cancelled' | 'stopped'

export interface RunSummary {
  id: string
  run_name: string
  status: RunStatus
  counts: Record<string, number>
  created_at?: string
  updated_at?: string
  discovery?: DiscoverySummary
}

export type DiscoveryMode = 'new_only' | 'reuse' | 'refresh'

export interface DiscoverySummary {
  mode?: DiscoveryMode
  source_mode?: 'local' | 'web' | 'both'
  next_pages?: Partial<Record<'local' | 'web' | 'both', number>>
  count?: number
  previous_market_domains?: number
  raw_results?: number
  relevant_results?: number
  previously_seen_filtered?: number
  duplicates_filtered?: number
  local_results?: number
  web_results?: number
  merged_results?: number
  new_candidates?: number
  pages_searched?: number
  target_reached?: boolean
}

export interface MarketHistory {
  previous_runs: number
  seen_domains: number
  completed_leads: number
}

export interface Candidate {
  title: string
  url: string
  homepage: string
  snippet: string
  domain: string
  status: string
  crawl_mode?: 'quick' | 'deep' | 'exhaustive'
  crawl_pages_checked?: number
  crawl_page_limit?: number
  crawl_current_url?: string
  crawl_contacts_found?: number
  source?: string
  sources?: Array<'local' | 'web'>
  osm_url?: string
  phone?: string
  email?: string
  city_or_area?: string
}

export interface LocalDataStatus {
  engine: string
  dataset: string
  ready: boolean
  database: 'online' | 'offline'
  businesses: number
  with_website: number
  with_phone: number
  with_email: number
  last_imported_at: string | null
  last_updated_at?: string | null
  update_status?: 'idle' | 'running' | 'failed' | 'not_configured'
  update_message?: string
  update_schedule?: string
  message: string
  postgis_version?: string
  latency_ms?: number
}

export interface LocalDataPreview {
  count: number
  elapsed_ms: number
  results: Candidate[]
}

export interface FieldEvidence {
  source_url?: string
  method?: string
}

export interface Lead {
  business_name: string
  website: string
  city_or_area: string
  business_type: string
  services: string[]
  generic_email: string
  emails: string[]
  phone: string
  phones: string[]
  contact_page: string
  booking_page: string
  instagram_or_social: string
  has_online_booking: boolean
  website_quality_note: string
  lead_score: number
  lead_reason: string
  domain: string
  field_evidence: Record<string, FieldEvidence>
  enrichment_errors: string[]
}

export interface RepositoryLead extends Lead {
  source_run_ids: string[]
  niches?: string[]
  locations?: string[]
  sources?: Array<'local' | 'web'>
  created_at: string
  updated_at: string
}

export interface RepositoryResponse {
  count: number
  leads: RepositoryLead[]
}

export interface RunDetail {
  run: RunSummary
  candidates: Candidate[]
  leads: Lead[]
}

export interface RunCreate {
  niche: string
  location: string
  max_results_per_query: number
  max_sites: number
  model: string
  run_name: string
  delay_seconds: number
  search_provider: 'hybrid' | 'osm_local' | 'auto' | 'brave' | 'ddgs'
  discovery_mode: DiscoveryMode
  crawl_mode: 'quick' | 'deep' | 'exhaustive'
}

export interface WorkspaceSettings {
  model_provider: 'ollama' | 'openai_compatible'
  model_name: string
  default_model: string
  model_endpoint: string
  ollama_base_url: string
  api_key_configured: boolean
  blocked_domains: string[]
  workspace_name: string
  workspace_subtitle: string
  logo_data_url: string
  theme: 'brushstroke' | 'genesis' | 'flip7' | 'rawblock' | 'evreghen' | 'ember' | 'insightdeck' | 'vercel' | 'trustblue' | 'zengrid'
  smtp_host: string
  smtp_port: number
  smtp_security: 'starttls' | 'ssl' | 'none'
  smtp_username: string
  smtp_password_configured: boolean
  smtp_from_email: string
  smtp_from_name: string
  smtp_reply_to: string
  email_accounts: EmailAccount[]
  default_email_account_id: string
  email_configured: boolean
}

export interface EmailAccount {
  id: string
  label: string
  host: string
  port: number
  security: 'starttls' | 'ssl' | 'none'
  username: string
  password_configured: boolean
  from_email: string
  from_name: string
  reply_to: string
  is_default: boolean
}

export interface EmailAccountInput {
  label: string
  host: string
  port: number
  security: EmailAccount['security']
  username: string
  password?: string
  clear_password: boolean
  from_email: string
  from_name: string
  reply_to: string
}

export interface EmailAccountsResponse {
  accounts: EmailAccount[]
  default_account_id: string
}

export interface WorkspaceSettingsUpdate {
  model_provider: WorkspaceSettings['model_provider']
  model_name: string
  model_endpoint: string
  api_key?: string
  clear_api_key: boolean
  blocked_domains: string[]
  workspace_name: string
  workspace_subtitle: string
  logo_data_url: string
  theme: WorkspaceSettings['theme']
  smtp_host: string
  smtp_port: number
  smtp_security: WorkspaceSettings['smtp_security']
  smtp_username: string
  smtp_password?: string
  clear_smtp_password: boolean
  smtp_from_email: string
  smtp_from_name: string
  smtp_reply_to: string
}

export interface StorageSettings {
  data_root: string
  downloads_root: string
  active_data_root: string
  database_path: string
  database_exists: boolean
  database_bytes: number
  workspace_bytes: number
  cache_dir: string
  browser_dir: string
  ollama_dir: string
  data_disk: { free_bytes: number; total_bytes: number }
  downloads_disk: { free_bytes: number; total_bytes: number }
  restart_required: boolean
  ollama_restart_required: boolean
}

export interface StorageSettingsUpdate {
  data_root: string
  downloads_root: string
  data_action: 'move' | 'use'
  move_downloads: boolean
}

export interface OllamaModel {
  name: string
  model?: string
  modified_at?: string
  size: number
  digest?: string
  details?: {
    format?: string
    family?: string
    parameter_size?: string
    quantization_level?: string
  }
}

export interface OllamaModelsResponse {
  status: string
  endpoint: string
  selected_model: string
  models: OllamaModel[]
}

export interface OllamaCatalogModel {
  name: string
  family: string
  description: string
  capabilities: string[]
  variants: string[]
  cloud: boolean
  local: boolean
  url: string
}

export interface OllamaCatalogResponse {
  status: string
  selected_model: string
  installed: string[]
  models: OllamaCatalogModel[]
}

export interface OllamaPullJob {
  id: string
  model: string
  status: 'queued' | 'downloading' | 'completed' | 'failed'
  message: string
  completed: number
  total: number
  percent: number
  error: string
  updated_at: string
}

export interface ModelBenchmark {
  model: string
  score: number
  verdict: 'recommended' | 'usable' | 'not_recommended'
  duration_seconds: number
  tokens_per_second: number | null
  checks: Array<{ label: string; passed: boolean; points: number }>
  sample: Record<string, unknown>
}

export interface Problem {
  problem: string
  cause: string
  fix: string
}

export interface OutreachDraft {
  id: string
  run_id: string
  lead_domain: string
  recipient_email: string
  subscriber_type: string
  consent_confirmed: boolean
  lawful_basis_note: string
  subject: string
  body: string
  status: 'draft' | 'approved' | 'queued' | 'sending' | 'uncertain' | 'sent' | 'exported' | 'blocked'
  approved_by: string
  created_at: string
  delivery_status: '' | 'released' | 'sent' | 'failed' | 'uncertain' | 'sent_after_suppression'
  delivery_error: string
  provider_message_id: string
  sent_at: string
}

export interface OutreachSendJob {
  id: string
  status: 'queued' | 'sending' | 'completed' | 'stopped' | 'failed'
  message: string
  total: number
  completed: number
  sent: number
  failed: number
  percent: number
  current_draft_id: string
  email_account_id: string
  email_account_label: string
  from_email: string
  results: Array<{ draft_id: string; status: 'sent' | 'failed'; error: string }>
}

export interface OutreachPreflightResult {
  domain: string
  business_name: string
  email: string
  lead_score: number
  eligible: boolean
  reasons: string[]
}

export interface OutreachPreflight {
  run_id: string
  total: number
  eligible: number
  blocked: number
  results: OutreachPreflightResult[]
}

export interface Suppression {
  id: number
  kind: 'email' | 'domain'
  display_hint: string
  reason: string
  created_at: string
}
