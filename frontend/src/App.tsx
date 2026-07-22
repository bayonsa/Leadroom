import { useDeferredValue, useEffect, useMemo, useRef, useState, type CSSProperties, type RefObject } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table'
import {
  Activity,
  AlertTriangle,
  Archive,
  ArrowDownUp,
  ArrowUpRight,
  BarChart3,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  CircleStop,
  Cloud,
  Cpu,
  Database,
  Download,
  ExternalLink,
  FileJson,
  FolderInput,
  Gauge,
  HardDrive,
  ImagePlus,
  KeyRound,
  LayoutList,
  Layers3,
  Link2,
  LockKeyhole,
  Mail,
  MapPin,
  Menu,
  Palette,
  Phone,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  RotateCw,
  ScanSearch,
  Search,
  Save,
  Send,
  Server,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, ApiError } from './api'
import type { Candidate, EmailAccount, EmailAccountInput, EmailAccountsResponse, Lead, OutreachDraft, RepositoryLead, RunCreate, RunDetail, RunSummary, StorageSettingsUpdate, WorkspaceSettingsUpdate } from './types'
import { applyTheme, isThemeId, type ThemeId } from './theme'
import './App.css'
import './Brushstroke.css'
import './Themes.css'

const statusLabels: Record<string, string> = {
  created: 'Created', ready: 'Ready', queued: 'Queued', processing: 'Enriching',
  completed: 'Completed', failed: 'Failed', cancelled: 'Skipped', running: 'Enriching',
  searching: 'Searching', stopped: 'Stopped', approved: 'Approved', sent: 'Sent', blocked: 'Blocked',
}

const mojibakeReplacements: Array<[string, string]> = [
  ['\u00e2\u20ac\u201c', '\u2013'], ['\u00e2\u20ac\u201d', '\u2014'],
  ['\u00e2\u20ac\u02dc', '\u2018'], ['\u00e2\u20ac\u2122', '\u2019'],
  ['\u00e2\u20ac\u0153', '\u201c'], ['\u00e2\u20ac\u009d', '\u201d'],
  ['\u00e2\u20ac\u00a6', '\u2026'], ['\u00c2\u00b7', '\u00b7'],
]

function displayText(value: string) {
  return mojibakeReplacements.reduce((text, [broken, fixed]) => text.replaceAll(broken, fixed), value)
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`status status-${status}`}>{statusLabels[status] ?? status}</span>
}

function ErrorPanel({ error }: { error: Error }) {
  const detail = error instanceof ApiError ? error.detail : {
    problem: 'Could not load data', cause: error.message, fix: 'Check that the API is running and retry.',
  }
  return (
    <div className="error-panel" role="alert">
      <AlertTriangle size={20} />
      <div><strong>{detail.problem}</strong><p>{detail.cause}</p><small>{detail.fix}</small></div>
    </div>
  )
}

function useDialogFocus(dialog: RefObject<HTMLElement | null>, onClose: () => void) {
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const selector = 'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onClose(); return }
      if (event.key !== 'Tab' || !dialog.current) return
      const controls = [...dialog.current.querySelectorAll<HTMLElement>(selector)].filter((item) => item.offsetParent !== null)
      if (!controls.length) return
      const first = controls[0]
      const last = controls[controls.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', handleKey)
    return () => { window.removeEventListener('keydown', handleKey); previous?.focus() }
  }, [dialog, onClose])
}

function handleTabListKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  const tablist = event.currentTarget.closest('[role="tablist"]')
  const tabs = [...(tablist?.querySelectorAll<HTMLButtonElement>('[role="tab"]:not([disabled])') ?? [])]
  if (!tabs.length) return
  const currentIndex = tabs.indexOf(event.currentTarget)
  const nextIndex = event.key === 'Home'
    ? 0
    : event.key === 'End'
      ? tabs.length - 1
      : (currentIndex + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length
  event.preventDefault()
  tabs[nextIndex].focus()
  tabs[nextIndex].click()
}

function Shell() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [mobileNavigation, setMobileNavigation] = useState(() => window.matchMedia('(max-width: 800px)').matches)
  const location = useLocation()
  const reduceMotion = useReducedMotion()
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, retry: 1, refetchInterval: 15000 })
  const workspaceSettings = useQuery({ queryKey: ['settings'], queryFn: api.settings, staleTime: 30_000 })
  useEffect(() => {
    if (isThemeId(workspaceSettings.data?.theme)) applyTheme(workspaceSettings.data.theme)
  }, [workspaceSettings.data?.theme])
  const brandName = workspaceSettings.data?.workspace_name || 'Leadroom'
  const brandSubtitle = workspaceSettings.data?.workspace_subtitle || 'Signal desk'
  const logo = workspaceSettings.data?.logo_data_url || ''
  const pageLabel = location.pathname.startsWith('/new') ? 'Create run' : location.pathname.startsWith('/repository') ? 'Lead repository' : location.pathname.startsWith('/local-data') ? 'Local data engine' : location.pathname.startsWith('/outreach') ? 'Outreach review' : location.pathname.startsWith('/settings') ? 'Settings' : location.pathname.split('/').filter(Boolean).length > 1 ? 'Run workspace' : 'Runs overview'
  useEffect(() => {
    document.title = `${pageLabel} | ${brandName}`
  }, [pageLabel, brandName])
  useEffect(() => {
    const media = window.matchMedia('(max-width: 800px)')
    const update = () => setMobileNavigation(media.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  const navItems = [
    { to: '/runs', label: 'Runs', icon: LayoutList },
    { to: '/new', label: 'New run', icon: Plus },
    { to: '/repository', label: 'Repository', icon: Archive },
    { to: '/outreach', label: 'Outreach review', icon: ShieldCheck },
    { to: '/settings', label: 'Settings', icon: Settings },
  ]
  return (
    <div className="shell">
      <header className="topbar">
        <button className="icon-button mobile-menu" onClick={() => setMenuOpen(!menuOpen)} aria-label="Toggle navigation" aria-expanded={menuOpen} aria-controls="primary-navigation"><Menu /></button>
        <NavLink className="brand mobile-brand" to="/runs"><BrandMark logo={logo} name={brandName} /><span>{brandName}</span></NavLink>
        <div className={`health ${health.isError ? 'health-down' : ''}`} role="status" title={health.isError ? 'Local API offline' : 'Local API online'}><span />{health.isError ? 'API offline' : 'Local API online'}</div>
      </header>
      <AnimatePresence>{menuOpen && <motion.button className="sidebar-backdrop" aria-label="Close navigation" onClick={() => setMenuOpen(false)} initial={reduceMotion ? false : { opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />}</AnimatePresence>
      <aside id="primary-navigation" className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`} inert={mobileNavigation && !menuOpen} aria-hidden={mobileNavigation && !menuOpen}>
        <NavLink className="brand desktop-brand" to="/runs"><BrandMark logo={logo} name={brandName} /><span><strong>{brandName}</strong><small>{brandSubtitle}</small></span></NavLink>
        <nav onClick={() => setMenuOpen(false)}>
          <span className="nav-kicker">Workspace</span>
          {navItems.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to}>{({ isActive }) => <><span className="nav-icon"><Icon /></span><span>{label}</span>{isActive && <motion.span className="nav-active" layoutId="nav-active" transition={{ type: 'spring', stiffness: 420, damping: 34 }} />}</>}</NavLink>)}
        </nav>
        <div className="sidebar-meta"><span className="sidebar-meta-icon"><LockKeyhole /></span><span><strong>Private workspace</strong><small>Data stays on this machine</small></span></div>
      </aside>
      <main className="content">
        <span className="sr-only" aria-live="polite">{pageLabel}</span>
        <div className="workspace-bar"><div><span>Local workspace</span><ChevronRight /><strong>{pageLabel}</strong></div><div className={`health desktop-health ${health.isError ? 'health-down' : ''}`} role="status"><span />{health.isError ? 'API offline' : 'Systems ready'}</div></div>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={location.pathname}
            className="route-frame"
            initial={reduceMotion ? false : { opacity: 0, y: 8 }}
            animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
            exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -6 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
          >
            <Routes location={location}>
              <Route path="/" element={<RunsPage />} />
              <Route path="/runs" element={<RunsPage />} />
              <Route path="/runs/:runId" element={<RunPage />} />
              <Route path="/new" element={<NewRunPage />} />
              <Route path="/repository" element={<RepositoryPage />} />
              <Route path="/local-data" element={<LocalDataPage />} />
              <Route path="/outreach" element={<OutreachPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/runs" replace />} />
            </Routes>
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  )
}

function BrandMark({ logo, name }: { logo: string; name: string }) {
  return <span className={`brand-mark ${logo ? 'brand-mark-custom' : ''}`}>{logo ? <img src={logo} alt={`${name} logo`} /> : <Sparkles size={18} />}</span>
}

function RunsPage() {
  const queryClient = useQueryClient()
  const runs = useQuery({ queryKey: ['runs'], queryFn: api.listRuns, refetchInterval: 4000 })
  const control = useMutation({
    mutationFn: ({ runId, action }: { runId: string; action: 'stop' | 'continue' }) => action === 'stop' ? api.cancelRun(runId) : api.continueRun(runId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['runs'] }),
  })
  const remove = useMutation({
    mutationFn: api.deleteRun,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['runs'] }),
  })
  const totals = (runs.data ?? []).reduce((acc, run) => ({ candidates: acc.candidates + (run.counts?.candidates ?? 0), completed: acc.completed + (run.counts?.completed ?? 0) }), { candidates: 0, completed: 0 })
  return <section className="runs-page">
    <PageHeader eyebrow="Lead intelligence" title="Runs" subtitle="Discover, review and enrich companies from one focused workspace." action={runs.data?.length ? <NavLink className="button primary" to="/new"><Plus />New run</NavLink> : undefined} />
    {runs.isLoading && <LoadingRows />}
    {runs.error && <ErrorPanel error={runs.error} />}
    {runs.data?.length === 0 && <EmptyState />}
    {!!runs.data?.length && <>
      <div className="operations-strip" aria-label="Workspace summary"><Metric label="Total runs" value={runs.data.length} /><Metric label="Candidates found" value={totals.candidates} /><Metric label="Completed leads" value={totals.completed} accent /><div className="operations-pulse"><span><Activity /></span><div><strong>Workspace active</strong><small>Results persist after every site</small></div></div></div>
      <div className="section-heading"><div><span className="eyebrow">Activity</span><h2>Recent runs</h2></div><span>{runs.data.length} total</span></div>
      {(control.error || remove.error) && <ErrorPanel error={(control.error || remove.error) as Error} />}
      <div className="table-wrap runs-table"><table><thead><tr><th>Name</th><th>Status</th><th>Started</th><th>Updated</th><th><span className="sr-only">Run actions</span></th></tr></thead><tbody>
        {runs.data.map((run, index) => <motion.tr key={run.id} initial={{ opacity: 0, y: Math.min(10, 4 + index) }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .24, delay: index * .035 }}><RunRowCells run={run} busy={control.isPending || remove.isPending} onControl={(action) => control.mutate({ runId: run.id, action })} onDelete={() => { if (window.confirm(`Delete ${run.run_name}? Its candidates and run results will be removed. Leads already saved in the repository will stay safe.`)) remove.mutate(run.id) }} /></motion.tr>)}
      </tbody></table></div>
    </>}
  </section>
}

function RunRowCells({ run, busy, onControl, onDelete }: { run: RunSummary; busy: boolean; onControl: (action: 'stop' | 'continue') => void; onDelete: () => void }) {
  const active = run.status === 'searching' || run.status === 'running'
  return <><td data-label="Name"><NavLink className="row-title" aria-label={run.run_name} to={`/runs/${run.id}`}><span className="run-avatar run-avatar-letter" aria-hidden="true">{runInitial(run.run_name)}</span><span><strong>{run.run_name}</strong><small className="muted id-text">{run.id.slice(0, 8)}</small></span></NavLink></td><td data-label="Status"><StatusBadge status={run.status} /></td><td data-label="Started">{formatDate(run.created_at)}</td><td data-label="Updated">{formatDate(run.updated_at)}</td><td className="runs-actions"><div className="run-row-actions"><button className={`icon-button ${active ? 'stop-action' : 'continue-action'}`} disabled={busy} onClick={() => onControl(active ? 'stop' : 'continue')} aria-label={`${active ? 'Stop' : 'Continue'} ${run.run_name}`} title={active ? 'Stop run' : 'Continue run'}>{active ? <CircleStop /> : <Play />}</button><NavLink className="icon-button" aria-label={`Open ${run.run_name}`} title="Open run" to={`/runs/${run.id}`}><ArrowUpRight /></NavLink><button className="icon-button destructive" disabled={busy} onClick={onDelete} aria-label={`Delete ${run.run_name}`} title="Delete run"><Trash2 /></button></div></td></>
}

function runInitial(runName: string) {
  return runName.match(/[A-Za-z]/)?.[0].toUpperCase() ?? runName.match(/[0-9]/)?.[0] ?? '?'
}

function buildRunName(niche: string, now: Date) {
  const safeNiche = niche.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'market'
  const date = [now.getFullYear(), now.getMonth() + 1, now.getDate()].map((part, index) => String(part).padStart(index === 0 ? 4 : 2, '0')).join('')
  const time = [now.getHours(), now.getMinutes(), now.getSeconds()].map((part) => String(part).padStart(2, '0')).join('')
  return `${safeNiche.slice(0, 45)}_${date}_${time}_${String(now.getMilliseconds()).padStart(3, '0')}`
}

const CRAWL_PROFILES = {
  quick: { label: 'Quick', pages: 6, depth: 2, detail: 'Core contact pages' },
  deep: { label: 'Deep', pages: 20, depth: 3, detail: 'Sitemap + priority links' },
  exhaustive: { label: 'Exhaustive', pages: 40, depth: 4, detail: 'Broad internal crawl' },
} as const

function NewRunPage() {
  const navigate = useNavigate()
  const [runTimestamp] = useState(() => new Date())
  const [form, setForm] = useState<RunCreate>({ niche: '', location: 'London UK', max_results_per_query: 12, max_sites: 10, model: 'ollama/llama3.2:3b', run_name: buildRunName('', runTimestamp), delay_seconds: 1, search_provider: 'hybrid', discovery_mode: 'new_only', crawl_mode: 'deep' })
  const workspaceSettings = useQuery({ queryKey: ['settings'], queryFn: api.settings, staleTime: 30_000 })
  const localData = useQuery({ queryKey: ['local-data-status'], queryFn: api.localDataStatus, staleTime: 15_000 })
  const deferredNiche = useDeferredValue(form.niche.trim())
  const deferredLocation = useDeferredValue(form.location.trim())
  const history = useQuery({
    queryKey: ['discovery-history', deferredNiche.toLowerCase(), deferredLocation.toLowerCase()],
    queryFn: () => api.discoveryHistory(deferredNiche, deferredLocation),
    enabled: deferredNiche.length >= 2 && deferredLocation.length >= 2,
    staleTime: 30_000,
  })
  const create = useMutation({ mutationFn: api.createRun, onSuccess: (data) => navigate(`/runs/${data.run.id}`) })
  const effectiveModel = form.model === 'ollama/llama3.2:3b' ? workspaceSettings.data?.default_model ?? form.model : form.model
  const set = (key: keyof RunCreate, value: string | number) => setForm((old) => ({ ...old, [key]: value }))
  const sourceLabel = form.search_provider === 'osm_local' ? 'Local only' : form.search_provider === 'auto' ? 'Web only' : 'Local + web'
  const crawlProfile = CRAWL_PROFILES[form.crawl_mode]
  const modeCopy = form.discovery_mode === 'new_only' ? 'Only domains not seen in earlier matching runs.' : form.discovery_mode === 'reuse' ? 'Saved lead data is reused whenever it is available.' : 'Every returned website is searched and enriched again.'
  return <section className="new-run-page">
    <PageHeader eyebrow="Run builder" title="Find your next market" subtitle="Define a precise search, then choose how previous discoveries should shape the results." />
    <div className="new-run-layout">
    <form className="form-surface" onSubmit={(event) => { event.preventDefault(); create.mutate({ ...form, model: effectiveModel }) }}>
      <div className="step-label"><span>1</span>Market</div>
      <div className="form-grid">
        <label className="span-2">Business niche<input required value={form.niche} onChange={(e) => setForm((old) => ({ ...old, niche: e.target.value, run_name: buildRunName(e.target.value, runTimestamp) }))} placeholder="e.g. independent dental clinics" /></label>
        <label>Location<input required value={form.location} onChange={(e) => set('location', e.target.value)} /></label>
        <label>Run name<input readOnly value={form.run_name} title="Generated automatically from the niche and start time" /></label>
      </div>
      <div className="step-label"><span>2</span>Discovery source</div>
      <fieldset className="source-picker">
        <legend className="sr-only">Choose where Leadroom searches</legend>
        <div>
          <SourceOption icon={<Database />} title="Local" detail="Private index, no total result limit" value="osm_local" selected={form.search_provider} onSelect={(value) => set('search_provider', value)} disabled={!localData.data?.ready} />
          <SourceOption icon={<Search />} title="Web" detail="Fresh websites from internet search" value="auto" selected={form.search_provider} onSelect={(value) => set('search_provider', value)} />
          <SourceOption icon={<Layers3 />} title="Both" detail="Search together and merge evidence" value="hybrid" selected={form.search_provider} onSelect={(value) => set('search_provider', value)} recommended />
        </div>
      </fieldset>
      <div className="step-label"><span>3</span>Previous results</div>
      <fieldset className="discovery-fieldset">
        <legend className="sr-only">Choose how previously discovered sites are handled</legend>
        <div className="discovery-options">
          <DiscoveryOption icon={<ScanSearch />} title="Find unseen sites" detail="Skip domains already found for this market" value="new_only" selected={form.discovery_mode} onSelect={(value) => set('discovery_mode', value)} recommended />
          <DiscoveryOption icon={<Database />} title="Reuse saved" detail="Use existing lead data when available" value="reuse" selected={form.discovery_mode} onSelect={(value) => set('discovery_mode', value)} />
          <DiscoveryOption icon={<RotateCw />} title="Recheck every site" detail="Search and scrape returned domains again" value="refresh" selected={form.discovery_mode} onSelect={(value) => set('discovery_mode', value)} />
        </div>
      </fieldset>
      <MarketHistoryStrip loading={history.isFetching} history={history.data} hasScope={deferredNiche.length >= 2} />
      <details className="advanced-settings">
        <summary><span className="advanced-title"><SlidersHorizontal /><span><strong>Advanced settings</strong><small>{form.max_sites} per batch · {crawlProfile.label} crawl · {sourceLabel}</small></span></span><ChevronDown className="summary-chevron" /></summary>
        <div className="advanced-body">
          <fieldset className="crawl-picker"><legend>Crawl depth</legend><div>
            <CrawlOption mode="quick" selected={form.crawl_mode} onSelect={(value) => set('crawl_mode', value)} />
            <CrawlOption mode="deep" selected={form.crawl_mode} onSelect={(value) => set('crawl_mode', value)} recommended />
            <CrawlOption mode="exhaustive" selected={form.crawl_mode} onSelect={(value) => set('crawl_mode', value)} />
          </div></fieldset>
          <div className="form-grid">
          <label>Results per search<input type="number" min="1" max="100" value={form.max_results_per_query} onChange={(e) => set('max_results_per_query', Number(e.target.value))} /></label>
          <label>Candidates per batch<input type="number" min="1" max="500" value={form.max_sites} onChange={(e) => set('max_sites', Number(e.target.value))} /></label>
          <label>Delay per site (sec)<input type="number" min="0" max="60" step="0.5" value={form.delay_seconds} onChange={(e) => set('delay_seconds', Number(e.target.value))} /></label>
          <label>Local model<input value={effectiveModel} onChange={(e) => set('model', e.target.value)} /></label>
          <div className="unified-discovery span-2"><div className="unified-title"><Layers3 /><span><strong>{sourceLabel}</strong><small>{form.search_provider === 'osm_local' ? 'No overall limit. Continue in fast local batches from the same run.' : form.search_provider === 'auto' ? 'Live internet discovery without querying the local index.' : 'Local and internet results are deduplicated and merged.'}</small></span><em><Check />Selected</em></div></div>
          </div>
        </div>
      </details>
      {create.error && <ErrorPanel error={create.error} />}
      {create.isPending && <SearchProgress mode="initial" />}
      <div className="form-actions"><div className="form-action-note">{form.search_provider === 'osm_local' ? <Database /> : <Search />}<span>{form.search_provider === 'osm_local' ? <>Find the first <strong>{form.max_sites}</strong> local candidates; continue without a total limit</> : <>Find up to <strong>{form.max_sites}</strong> candidates for review</>}</span></div><NavLink className="button ghost" to="/runs">Cancel</NavLink><button className="button primary" disabled={create.isPending}><Search />{create.isPending ? 'Searching…' : 'Find candidates'}</button></div>
    </form>
    <aside className="run-brief" aria-label="Run brief">
      <div className="brief-head"><span><BarChart3 /></span><div><small>Live brief</small><strong>Search blueprint</strong></div><i>Draft</i></div>
      <div className="brief-market"><span>Target market</span><strong>{form.niche.trim() || 'Add a business niche'}</strong><small><MapPin />{form.location.trim() || 'No location selected'}</small></div>
      <div className="brief-mode"><span>Discovery strategy</span><AnimatePresence mode="wait" initial={false}><motion.div key={form.discovery_mode} initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }} transition={{ duration: .16 }}><strong>{form.discovery_mode === 'new_only' ? 'Unseen sites' : form.discovery_mode === 'reuse' ? 'Reuse saved' : 'Full refresh'}</strong><p>{modeCopy}</p></motion.div></AnimatePresence></div>
      <div className="brief-stats"><div><strong>{form.max_sites}</strong><span>sites</span></div><div><strong>{crawlProfile.pages}</strong><span>pages/site</span></div><div><strong>{crawlProfile.depth}</strong><span>link depth</span></div></div>
      <div className="brief-foot"><LockKeyhole /><span><strong>Local by design</strong><small>Research data stays in this workspace.</small></span></div>
    </aside>
    </div>
  </section>
}

function CrawlOption({ mode, selected, onSelect, recommended = false }: { mode: RunCreate['crawl_mode']; selected: RunCreate['crawl_mode']; onSelect: (mode: RunCreate['crawl_mode']) => void; recommended?: boolean }) {
  const profile = CRAWL_PROFILES[mode]
  return <label className={`crawl-option ${selected === mode ? 'selected' : ''}`}>
    <input type="radio" name="crawl-mode" value={mode} checked={selected === mode} onChange={() => onSelect(mode)} />
    <span><strong>{profile.label}{recommended && <small>Recommended</small>}</strong><em>{profile.pages} pages · depth {profile.depth}</em><i>{profile.detail}</i></span>
    <span className="radio-mark"><Check /></span>
  </label>
}

function DiscoveryOption({ icon, title, detail, value, selected, onSelect, recommended = false }: { icon: React.ReactNode; title: string; detail: string; value: RunCreate['discovery_mode']; selected: RunCreate['discovery_mode']; onSelect: (value: RunCreate['discovery_mode']) => void; recommended?: boolean }) {
  const reduceMotion = useReducedMotion()
  return <motion.label className={`discovery-option ${selected === value ? 'selected' : ''}`} whileTap={reduceMotion ? undefined : { scale: 0.99 }} transition={{ duration: 0.12 }}>
    <input type="radio" name="discovery-mode" value={value} checked={selected === value} onChange={() => onSelect(value)} />
    <span className="discovery-icon">{icon}</span>
    <span className="discovery-copy"><strong>{title}{recommended && <small>Recommended</small>}</strong><span>{detail}</span></span>
    <span className="radio-mark"><Check /></span>
  </motion.label>
}

function SourceOption({ icon, title, detail, value, selected, onSelect, recommended = false, disabled = false }: { icon: React.ReactNode; title: string; detail: string; value: RunCreate['search_provider']; selected: RunCreate['search_provider']; onSelect: (value: RunCreate['search_provider']) => void; recommended?: boolean; disabled?: boolean }) {
  return <label className={`source-option ${selected === value ? 'selected' : ''} ${disabled ? 'disabled' : ''}`}>
    <input type="radio" name="search-provider" value={value} checked={selected === value} disabled={disabled} onChange={() => onSelect(value)} />
    <span>{icon}</span><strong>{title}{recommended && <small>Recommended</small>}</strong><i><Check /></i><em>{disabled ? 'Local index is unavailable' : detail}</em>
  </label>
}

function MarketHistoryStrip({ loading, history, hasScope }: { loading: boolean; history?: { previous_runs: number; seen_domains: number; completed_leads: number }; hasScope: boolean }) {
  if (!hasScope) return <div className="market-history muted"><Database /><span>Type a niche to check this market's history.</span></div>
  if (loading && !history) return <div className="market-history muted" aria-live="polite"><RefreshCw className="spin" /><span>Checking market history...</span></div>
  if (!history?.seen_domains) return <div className="market-history market-new" aria-live="polite"><Sparkles /><span><strong>First search in this market</strong>No previous domains found.</span></div>
  return <div className="market-history" aria-live="polite"><Database /><span><strong>{history.seen_domains} sites already seen</strong>{history.completed_leads} enriched across {history.previous_runs} previous {history.previous_runs === 1 ? 'run' : 'runs'}.</span></div>
}

function RunPage() {
  const { runId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<'candidates' | 'progress' | 'leads'>('candidates')
  const [candidateSource, setCandidateSource] = useState<'all' | 'local' | 'web'>('all')
  const detail = useQuery({ queryKey: ['run', runId], queryFn: () => api.getRun(runId), refetchInterval: (q) => ['searching', 'running'].includes(q.state.data?.run.status ?? '') ? 1200 : 5000 })
  const action = useMutation({ mutationFn: (kind: 'start' | 'cancel' | 'retry' | 'continue') => api[`${kind}Run`](runId), onSuccess: (data: unknown) => { queryClient.invalidateQueries({ queryKey: ['run', runId] }); queryClient.invalidateQueries({ queryKey: ['runs'] }); if ((data as { kind?: string })?.kind === 'enrichment') setTab('progress') } })
  const discover = useMutation({ mutationFn: (source: 'local' | 'web' | 'both') => api.discoverMore(runId, source), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['run', runId] }); setTab('candidates') } })
  const remove = useMutation({ mutationFn: () => api.deleteRun(runId), onSuccess: () => { queryClient.removeQueries({ queryKey: ['run', runId] }); queryClient.invalidateQueries({ queryKey: ['runs'] }); navigate('/runs') } })
  if (detail.isLoading) return <LoadingRows />
  if (detail.error) return <ErrorPanel error={detail.error} />
  if (!detail.data) return null
  const { run, candidates, leads } = detail.data
  const selected = candidates.filter((item) => item.status !== 'cancelled').length
  const done = (run.counts.completed ?? 0) + (run.counts.failed ?? 0)
  const active = run.status === 'searching' || run.status === 'running'
  return <section className="run-page">
    <PageHeader eyebrow="Run workspace" title={run.run_name} subtitle={`Run ${run.id.slice(0, 8)} · ${candidates.length} candidate${candidates.length === 1 ? '' : 's'}`} action={<div className="header-actions">
      <button className="icon-button destructive" disabled={remove.isPending} onClick={() => { if (window.confirm(`Delete ${run.run_name}? Run candidates and results will be removed. Repository leads stay safe.`)) remove.mutate() }} aria-label="Delete run" title="Delete run"><Trash2 /></button>
      {active ? <button className="button danger" disabled={action.isPending} onClick={() => action.mutate('cancel')}><CircleStop />Stop</button> : <button className="button primary" disabled={action.isPending} onClick={() => action.mutate('continue')}><Play />Continue</button>}
    </div>} />
    {(action.error || discover.error || remove.error) && <ErrorPanel error={(action.error || discover.error || remove.error) as Error} />}
    {run.status === 'searching' && <SearchProgress mode={candidates.length ? 'continuation' : 'initial'} />}
    {!!run.discovery?.mode && <DiscoverySummaryBand discovery={run.discovery} />}
    <div className="run-overview">
      <Metric label="Candidates" value={candidates.length} />
      <Metric label="Selected" value={selected} />
      <Metric label="Completed" value={run.counts.completed ?? 0} />
      <Metric label="Clean leads" value={leads.length} accent />
      <div className="run-state"><StatusBadge status={run.status} /><span>{run.status === 'running' ? `${done} of ${selected} processed` : 'Latest persisted state'}</span></div>
    </div>
    <div className="tabs" role="tablist" aria-label="Run workspace">
      <button id="tab-candidates" role="tab" tabIndex={tab === 'candidates' ? 0 : -1} aria-selected={tab === 'candidates'} aria-controls="panel-candidates" className={tab === 'candidates' ? 'active' : ''} onKeyDown={handleTabListKeyDown} onClick={() => setTab('candidates')}><SlidersHorizontal />Candidates <span>{candidates.length}</span></button>
      <button id="tab-progress" role="tab" tabIndex={tab === 'progress' ? 0 : -1} aria-selected={tab === 'progress'} aria-controls="panel-progress" className={tab === 'progress' ? 'active' : ''} onKeyDown={handleTabListKeyDown} onClick={() => setTab('progress')}><Activity />Progress</button>
      <button id="tab-leads" role="tab" tabIndex={tab === 'leads' ? 0 : -1} aria-selected={tab === 'leads'} aria-controls="panel-leads" className={tab === 'leads' ? 'active' : ''} onKeyDown={handleTabListKeyDown} onClick={() => setTab('leads')}><Check />Leads <span>{leads.length}</span></button>
    </div>
    <div id={`panel-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`}>
      {tab === 'candidates' && <CandidatesPanel runId={runId} candidates={candidates} disabled={active} source={candidateSource} onSourceChange={setCandidateSource} discovering={discover.isPending || run.status === 'searching'} onDiscover={(mode) => discover.mutate(mode)} />}
      {tab === 'progress' && <ProgressPanel candidates={candidates} selected={selected} done={done} />}
      {tab === 'leads' && <LeadsPanel runId={runId} leads={leads} />}
    </div>
  </section>
}

function DiscoverySummaryBand({ discovery }: { discovery: NonNullable<RunSummary['discovery']> }) {
  const modeLabel = discovery.mode === 'new_only' ? 'New sites only' : discovery.mode === 'reuse' ? 'Saved data eligible' : 'Full refresh'
  return <div className="discovery-summary">
    <span><ScanSearch /><strong>{modeLabel}</strong></span>
    <span><strong>{discovery.new_candidates ?? discovery.count ?? 0}</strong> candidates found</span>
    {(discovery.local_results ?? 0) > 0 && <span><Database /><strong>{discovery.local_results}</strong> local</span>}
    {(discovery.web_results ?? 0) > 0 && <span><Search /><strong>{discovery.web_results}</strong> web</span>}
    {(discovery.merged_results ?? 0) > 0 && <span><Layers3 /><strong>{discovery.merged_results}</strong> merged</span>}
    {discovery.mode === 'new_only' && <span><strong>{discovery.previously_seen_filtered ?? 0}</strong> previously seen skipped</span>}
    <span><strong>{discovery.pages_searched ?? 0}</strong> search pages checked</span>
  </div>
}

function CandidatesPanel({ runId, candidates, disabled, source, onSourceChange, discovering, onDiscover }: { runId: string; candidates: Candidate[]; disabled: boolean; source: 'all' | 'local' | 'web'; onSourceChange: (source: 'all' | 'local' | 'web') => void; discovering: boolean; onDiscover: (source: 'local' | 'web' | 'both') => void }) {
  const queryClient = useQueryClient()
  const toggle = useMutation({
    mutationFn: ({ domain, selected }: { domain: string; selected: boolean }) => api.selectCandidate(runId, domain, selected),
    onMutate: ({ domain, selected }) => {
      const queryKey = ['run', runId]
      const previous = queryClient.getQueryData<RunDetail>(queryKey)
      queryClient.setQueryData<RunDetail>(queryKey, (current) => current ? {
        ...current,
        candidates: current.candidates.map((candidate) => candidate.domain === domain
          ? { ...candidate, status: selected ? 'queued' : 'cancelled' }
          : candidate),
      } : current)
      return { previous }
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(['run', runId], context.previous)
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['run', runId] }),
  })
  const sources = (candidate: Candidate) => candidate.sources ?? [candidate.source === 'osm_local' ? 'local' : 'web']
  const localCount = candidates.filter((candidate) => sources(candidate).includes('local')).length
  const webCount = candidates.filter((candidate) => sources(candidate).includes('web')).length
  const visibleCandidates = source === 'all' ? candidates : candidates.filter((candidate) => sources(candidate).includes(source))
  const discoveryMode = source === 'all' ? 'both' : source
  const discoveryLabel = source === 'local' ? 'Find more local' : source === 'web' ? 'Search more web' : 'Find mixed batch'
  return <div className="panel"><div className="panel-heading"><div><h2>Review candidates</h2><p>Remove directories, aggregators, or businesses that are out of scope.</p></div></div>
    <div className="candidate-toolbar"><div className="candidate-source-tabs" role="group" aria-label="Candidate sources"><button type="button" aria-pressed={source === 'all'} className={source === 'all' ? 'active' : ''} onClick={() => onSourceChange('all')}><Layers3 />All <span>{candidates.length}</span></button><button type="button" aria-pressed={source === 'local'} className={source === 'local' ? 'active' : ''} onClick={() => onSourceChange('local')}><Database />Local <span>{localCount}</span></button><button type="button" aria-pressed={source === 'web'} className={source === 'web' ? 'active' : ''} onClick={() => onSourceChange('web')}><Search />Web <span>{webCount}</span></button></div><button className="button ghost" disabled={discovering} onClick={() => onDiscover(discoveryMode)}>{discovering ? <RefreshCw className="spin" /> : source === 'local' ? <Database /> : <ScanSearch />}{discovering ? 'Searching...' : discoveryLabel}</button></div>
    <div className="candidate-list">{visibleCandidates.map((item) => { const checked = item.status !== 'cancelled'; return <label className="candidate" key={item.domain}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => toggle.mutate({ domain: item.domain, selected: e.target.checked })} />
      <span className="checkmark"><Check /></span><span className="candidate-main">
        <span className="candidate-identity"><strong title={displayText(item.title || item.domain)}>{displayText(item.title || item.domain)}</strong><span title={item.domain}>{item.domain}</span></span>
        <span className="candidate-meta"><small title={displayText(item.snippet)}>{displayText(item.snippet)}</small><span className="candidate-sources">{(item.sources ?? [item.source === 'osm_local' ? 'local' : 'web']).map((source) => <em className={`source-${source}`} role="img" aria-label={source === 'local' ? 'Local file' : 'Web result'} title={source === 'local' ? 'This result comes from the local database' : 'This result comes from the web'} key={source}>{source === 'local' ? <Database /> : <Search />}</em>)}</span></span>
      </span>
      {(item.homepage || item.osm_url) && <a className="icon-button" href={item.homepage || item.osm_url} target="_blank" rel="noreferrer" aria-label={`Open ${item.domain}`} onClick={(e) => e.stopPropagation()}><ExternalLink /></a>}
    </label>})}{visibleCandidates.length === 0 && <div className="candidate-source-empty"><Search /><strong>No {source} candidates yet</strong><span>Use {discoveryLabel.toLowerCase()} to add results to this run.</span></div>}</div>
  </div>
}

function ProgressPanel({ candidates, selected, done }: { candidates: Candidate[]; selected: number; done: number }) {
  const percent = selected ? Math.min(100, Math.round(done / selected * 100)) : 0
  return <div className="panel"><div className="progress-head"><div><h2>Enrichment progress</h2><p>Each result is persisted as it completes.</p></div><strong>{percent}%</strong></div>
    <div className="progress-track"><span style={{ width: `${percent}%` }} /></div>
    <div className="progress-list">{candidates.filter((c) => c.status !== 'cancelled').map((item) => {
      const checked = item.crawl_pages_checked ?? 0
      const limit = item.crawl_page_limit ?? CRAWL_PROFILES[item.crawl_mode ?? 'deep'].pages
      const pagePercent = limit ? Math.min(100, Math.round(checked / limit * 100)) : 0
      return <div key={item.domain}><span className={`status-dot dot-${item.status}`} /><span className="crawl-progress-copy"><strong>{item.domain}</strong>{checked > 0 && <span><small>{checked} of {limit} pages · {item.crawl_contacts_found ?? 0} contacts</small><i aria-label={`${checked} of ${limit} pages checked`}><em style={{ width: `${pagePercent}%` }} /></i></span>}</span><StatusBadge status={item.status} /></div>
    })}</div>
  </div>
}

function LeadsPanel({ runId, leads }: { runId: string; leads: Lead[] }) {
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState('')
  const [sorting, setSorting] = useState<SortingState>([{ id: 'lead_score', desc: true }])
  const [selected, setSelected] = useState<Lead | null>(null)
  const saveToRepository = useMutation({
    mutationFn: () => api.importToRepository(runId, leads.map((lead) => lead.domain)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['repository'] }),
  })
  const columns = useMemo<ColumnDef<Lead>[]>(() => [
    { accessorKey: 'business_name', header: 'Business', cell: ({ row }) => <button className="business-link" onClick={() => setSelected(row.original)}>{row.original.business_name || row.original.domain}<small>{row.original.domain}</small></button> },
    { accessorKey: 'city_or_area', header: 'Area' },
    { accessorKey: 'generic_email', header: 'Email', cell: ({ row }) => <ContactStack values={row.original.emails?.length ? row.original.emails : [row.original.generic_email]} kind="email" /> },
    { accessorKey: 'phone', header: 'Phone', cell: ({ row }) => <ContactStack values={row.original.phones?.length ? row.original.phones : [row.original.phone]} kind="phone" /> },
    { accessorKey: 'lead_score', header: 'Score', cell: ({ getValue }) => <span className="score">{String(getValue())}/10</span> },
  ], [])
  // TanStack Table intentionally exposes non-memoizable functions.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({ data: leads, columns, state: { sorting, globalFilter: filter }, onSortingChange: setSorting, onGlobalFilterChange: setFilter, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(), getFilteredRowModel: getFilteredRowModel() })
  if (!leads.length) return <div className="panel empty-inline"><Mail /><h2>No clean leads yet</h2><p>Start enrichment, then verified results will appear here.</p></div>
  return <div className="panel leads-panel">{saveToRepository.data && <div className="repository-result" role="status"><Check /><span><strong>{saveToRepository.data.added} added, {saveToRepository.data.updated} updated</strong>{saveToRepository.data.skipped ? `${saveToRepository.data.skipped} without a verified contact skipped. ` : ''}{saveToRepository.data.total} leads are now saved in the repository.</span><NavLink to="/repository">Open repository<ArrowUpRight /></NavLink></div>}{saveToRepository.error && <ErrorPanel error={saveToRepository.error} />}<div className="table-tools"><label className="search-input"><Search /><input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter leads" aria-label="Filter leads" /></label><div><button className="button primary" disabled={saveToRepository.isPending} onClick={() => saveToRepository.mutate()}><Upload />{saveToRepository.isPending ? 'Saving...' : `Save all ${leads.length}`}</button><a className="button ghost" href={api.exportUrl(runId, 'json')}><FileJson />JSON</a><a className="button ghost" href={api.exportUrl(runId, 'csv')}><Download />CSV</a></div></div>
    <div className="table-wrap"><table><thead>{table.getHeaderGroups().map((group) => <tr key={group.id}>{group.headers.map((header) => <th key={header.id}><button className="sort-button" onClick={header.column.getToggleSortingHandler()}>{flexRender(header.column.columnDef.header, header.getContext())}<ArrowDownUp /></button></th>)}</tr>)}</thead><tbody>{table.getRowModel().rows.map((row) => <tr key={row.id}>{row.getVisibleCells().map((cell) => <td data-label={typeof cell.column.columnDef.header === 'string' ? cell.column.columnDef.header : cell.column.id} key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}</tbody></table></div>
    {selected && <LeadDrawer runId={runId} lead={selected} onClose={() => setSelected(null)} />}
  </div>
}

function ContactStack({ values, kind }: { values: string[]; kind: 'email' | 'phone' }) {
  const contacts = values.filter(Boolean).slice(0, 3)
  if (!contacts.length) return <span className="muted">Not found</span>
  return <span className="contact-stack">{contacts.map((value) => <a key={value} href={`${kind === 'email' ? 'mailto:' : 'tel:'}${value}`}>{value}</a>)}</span>
}

type CollectionSummary = { name: string; count: number }

function CollectionPicker({ collections, selected, onChange }: { collections: CollectionSummary[]; selected: string[]; onChange: (values: string[]) => void }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<'recent' | 'count' | 'name'>('recent')
  const [recent, setRecent] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('leadroom-recent-collections') || '[]') as string[] } catch { return [] }
  })
  const root = useRef<HTMLDivElement>(null)
  const search = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (!open) return
    search.current?.focus()
    const close = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false) }
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', close); document.removeEventListener('keydown', escape) }
  }, [open])
  const remember = (name: string) => {
    const next = [name, ...recent.filter((value) => value !== name)].slice(0, 8)
    setRecent(next)
    localStorage.setItem('leadroom-recent-collections', JSON.stringify(next))
  }
  const toggle = (name: string) => {
    remember(name)
    onChange(selected.includes(name) ? selected.filter((value) => value !== name) : [...selected, name])
  }
  const matching = collections
    .filter((collection) => collection.name.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((left, right) => sort === 'count' ? right.count - left.count || left.name.localeCompare(right.name) : sort === 'name' ? left.name.localeCompare(right.name) : (recent.indexOf(left.name) < 0 ? 99 : recent.indexOf(left.name)) - (recent.indexOf(right.name) < 0 ? 99 : recent.indexOf(right.name)) || right.count - left.count)
  const visible = matching.slice(0, 100)
  const label = selected.length === 0 ? 'All leads' : selected.length === 1 ? selected[0] : `${selected.length} collections`
  return <div className="collection-picker" ref={root}>
    <button type="button" className={`collection-picker-trigger ${selected.length ? 'has-selection' : ''}`} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((value) => !value)}><Layers3 /><span><small>Collection</small><strong>{label}</strong></span><ChevronDown /></button>
    {open && <div className="collection-picker-popover" role="dialog" aria-label="Choose collections">
      <div className="collection-picker-search"><Search /><input ref={search} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search collections" aria-label="Search collections" /><select value={sort} onChange={(event) => setSort(event.target.value as typeof sort)} aria-label="Sort collections"><option value="recent">Recent</option><option value="count">Most leads</option><option value="name">Name</option></select></div>
      <button type="button" className={`collection-option collection-option-all ${selected.length === 0 ? 'selected' : ''}`} onClick={() => onChange([])}><Archive /><span><strong>All leads</strong><small>Complete repository</small></span>{selected.length === 0 && <Check />}</button>
      <div className="collection-option-list">{visible.map((collection) => <label className={`collection-option ${selected.includes(collection.name) ? 'selected' : ''}`} key={collection.name}><input type="checkbox" checked={selected.includes(collection.name)} onChange={() => toggle(collection.name)} /><span><strong>{collection.name}</strong><small>{recent.includes(collection.name) ? 'Recently used' : 'Search collection'}</small></span><em>{collection.count}</em></label>)}</div>
      {!visible.length && <div className="collection-picker-empty"><Search /><span><strong>No collections found</strong><small>Try a shorter search.</small></span></div>}
      <footer><span>{matching.length > visible.length ? `Showing ${visible.length} of ${matching.length}` : `${collections.length} collections`}</span>{selected.length > 0 && <button type="button" onClick={() => onChange([])}>Clear selection</button>}</footer>
    </div>}
  </div>
}

function CollectionManager({ collections, onClose, onChanged }: { collections: CollectionSummary[]; onClose: () => void; onChanged: () => void }) {
  const closeButton = useRef<HTMLButtonElement>(null)
  const dialog = useRef<HTMLElement>(null)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [target, setTarget] = useState('')
  const merge = useMutation({ mutationFn: () => api.mergeRepositoryCollections(selected, target), onSuccess: () => { setSelected([]); setTarget(''); onChanged() } })
  const remove = useMutation({ mutationFn: api.deleteRepositoryCollection, onSuccess: () => { setSelected([]); onChanged() } })
  useDialogFocus(dialog, onClose)
  useEffect(() => { closeButton.current?.focus() }, [])
  const matching = collections.filter((collection) => collection.name.toLowerCase().includes(query.trim().toLowerCase())).sort((left, right) => left.name.localeCompare(right.name))
  const visible = matching.slice(0, 200)
  const toggle = (name: string) => setSelected((current) => current.includes(name) ? current.filter((value) => value !== name) : [...current, name])
  return <div className="drawer-backdrop" onMouseDown={onClose}><aside ref={dialog} className="drawer collection-manager" role="dialog" aria-modal="true" aria-labelledby="collection-manager-title" onMouseDown={(event) => event.stopPropagation()}><div className="drawer-head"><div><small>Repository structure</small><h2 id="collection-manager-title">Manage collections</h2><span>Rename, merge, or archive categories without deleting leads.</span></div><button ref={closeButton} className="icon-button" onClick={onClose} aria-label="Close collection manager"><X /></button></div>
    <div className="collection-manager-tools"><label className="search-input"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a collection" aria-label="Find a collection" /></label><span>{matching.length > visible.length ? `${visible.length} of ${matching.length}` : `${collections.length} total`}</span></div>
    <div className="collection-manager-list">{visible.map((collection) => <div key={collection.name}><label><input type="checkbox" checked={selected.includes(collection.name)} onChange={() => toggle(collection.name)} /><span><strong>{collection.name}</strong><small>{collection.count} {collection.count === 1 ? 'lead' : 'leads'}</small></span></label><button type="button" className="icon-button destructive" disabled={collection.name === 'Uncategorised' || remove.isPending} onClick={() => { if (window.confirm(`Remove ${collection.name}? Its leads will move to Uncategorised.`)) remove.mutate(collection.name) }} aria-label={`Remove collection ${collection.name}`} title="Move leads to Uncategorised"><Trash2 /></button></div>)}</div>
    <form className="collection-merge-bar" onSubmit={(event) => { event.preventDefault(); merge.mutate() }}><div><strong>{selected.length ? `${selected.length} selected` : 'Select collections'}</strong><small>{selected.length === 1 ? 'Enter a new name to rename it.' : 'Combine selected collections under one name.'}</small></div><input required disabled={!selected.length} value={target} onChange={(event) => setTarget(event.target.value)} placeholder="Target collection name" aria-label="Target collection name" /><button className="button primary" disabled={!selected.length || !target.trim() || merge.isPending}><FolderInput />{selected.length === 1 ? 'Rename' : 'Merge'}</button></form>
    {(merge.error || remove.error) && <ErrorPanel error={(merge.error || remove.error) as Error} />}
  </aside></div>
}

function RepositoryPage() {
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState('')
  const [selectedCollections, setSelectedCollections] = useState<string[]>([])
  const [area, setArea] = useState('')
  const [source, setSource] = useState('')
  const [managingCollections, setManagingCollections] = useState(false)
  const [editing, setEditing] = useState<{ lead: RepositoryLead; mode: 'edit' | 'move' } | null>(null)
  const repository = useQuery({ queryKey: ['repository'], queryFn: api.repository })
  const remove = useMutation({
    mutationFn: api.deleteRepositoryLead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['repository'] }),
  })
  if (repository.isLoading) return <LoadingRows />
  if (repository.error) return <ErrorPanel error={repository.error} />
  const leads = repository.data?.leads ?? []
  const collectionCounts = new Map<string, number>()
  for (const lead of leads) {
    for (const name of new Set((lead.niches ?? []).filter(Boolean))) {
      collectionCounts.set(name, (collectionCounts.get(name) ?? 0) + 1)
    }
  }
  const collections = [...collectionCounts].map(([name, count]) => ({ name, count })).sort((left, right) => left.name.localeCompare(right.name))
  const niches = collections.map((collection) => collection.name)
  const areas = [...new Set(leads.flatMap((lead) => lead.locations ?? []).filter(Boolean))].sort()
  const query = filter.trim().toLowerCase()
  const filtered = leads.filter((lead) => {
    const matchesQuery = !query || [lead.business_name, lead.domain, lead.city_or_area, lead.business_type, ...(lead.niches ?? []), ...(lead.emails ?? []), ...(lead.phones ?? [])].some((value) => value?.toLowerCase().includes(query))
    return matchesQuery && (!selectedCollections.length || selectedCollections.some((collection) => lead.niches?.includes(collection))) && (!area || lead.locations?.includes(area)) && (!source || lead.sources?.includes(source as 'local' | 'web'))
  })
  const sourceRuns = new Set(leads.flatMap((lead) => lead.source_run_ids)).size
  const collectionCount = collectionCounts.size
  return <section>
    <PageHeader eyebrow="Lead collections" title="Repository" subtitle="Leads stay grouped by the business niche that found them. Continued searches grow the same collection." action={leads.length ? <div className="header-actions"><a className="button ghost" href={api.repositoryExportUrl('json')}><FileJson />JSON</a><a className="button primary" href={api.repositoryExportUrl('csv')}><Download />Export CSV</a></div> : undefined} />
    <div className="repository-overview"><Metric label="Saved leads" value={leads.length} accent /><Metric label="With email" value={leads.filter((lead) => lead.emails?.length || lead.generic_email).length} /><Metric label="With phone" value={leads.filter((lead) => lead.phones?.length || lead.phone).length} /><Metric label="Collections" value={collectionCount || sourceRuns} /></div>
    {!leads.length ? <div className="empty-state repository-empty"><Archive /><h2>Your repository is empty</h2><p>Open a completed run and save its leads here. Repeated imports merge by domain.</p><NavLink className="button primary" to="/runs"><LayoutList />Browse runs</NavLink></div> : <div className="panel repository-panel">
      <div className="repository-toolbar"><CollectionPicker collections={collections} selected={selectedCollections} onChange={setSelectedCollections} /><label className="search-input"><Search /><input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Search saved leads" aria-label="Search saved leads" /></label><div className="repository-filters"><label><span>Market</span><select aria-label="Filter by market" value={area} onChange={(event) => setArea(event.target.value)}><option value="">All markets</option>{areas.map((value) => <option key={value}>{value}</option>)}</select></label><label><span>Source</span><select aria-label="Filter by source" value={source} onChange={(event) => setSource(event.target.value)}><option value="">All sources</option><option value="local">Local index</option><option value="web">Live web</option></select></label></div><button type="button" className="icon-button collection-manage-button" onClick={() => setManagingCollections(true)} aria-label="Manage collections" title="Manage collections"><Settings /></button><span className="table-count">{filtered.length} leads</span></div>
      {selectedCollections.length > 0 && <div className="active-collection-filters" aria-label="Active collection filters">{selectedCollections.map((collection) => <button type="button" key={collection} onClick={() => setSelectedCollections(selectedCollections.filter((value) => value !== collection))}>{collection}<X /></button>)}<button type="button" className="clear-collection-filters" onClick={() => setSelectedCollections([])}>Clear all</button></div>}
      {remove.error && <ErrorPanel error={remove.error} />}
      <div className="table-wrap"><table><thead><tr><th>Business</th><th>Collection</th><th>Area</th><th>Email</th><th>Phone</th><th>Evidence</th><th>Score</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{filtered.map((lead) => <RepositoryRow key={lead.domain} lead={lead} removing={remove.isPending} onEdit={() => setEditing({ lead, mode: 'edit' })} onMove={() => setEditing({ lead, mode: 'move' })} onRemove={() => { if (window.confirm(`Remove ${lead.business_name || lead.domain} from the repository?`)) remove.mutate(lead.domain) }} />)}</tbody></table></div>
    </div>}
    {editing && <RepositoryLeadDrawer lead={editing.lead} collections={niches} mode={editing.mode} onClose={() => setEditing(null)} />}
    {managingCollections && <CollectionManager collections={collections} onClose={() => setManagingCollections(false)} onChanged={() => { setSelectedCollections([]); queryClient.invalidateQueries({ queryKey: ['repository'] }) }} />}
  </section>
}

function RepositoryRow({ lead, removing, onEdit, onMove, onRemove }: { lead: RepositoryLead; removing: boolean; onEdit: () => void; onMove: () => void; onRemove: () => void }) {
  const name = <>{lead.business_name || lead.domain}<small>{lead.domain}</small></>
  return <tr><td data-label="Business">{lead.website ? <a className="business-link" href={lead.website} target="_blank" rel="noreferrer">{name}</a> : <span className="business-link">{name}</span>}</td><td data-label="Collection"><span className="collection-stack">{(lead.niches?.length ? lead.niches : [lead.business_type]).filter(Boolean).slice(0, 2).map((value) => <em key={value}>{value}</em>)}</span></td><td data-label="Area">{lead.city_or_area || <span className="muted">Not found</span>}</td><td data-label="Email"><ContactStack values={lead.emails?.length ? lead.emails : [lead.generic_email]} kind="email" /></td><td data-label="Phone"><ContactStack values={lead.phones?.length ? lead.phones : [lead.phone]} kind="phone" /></td><td data-label="Evidence"><span className="repository-sources">{(lead.sources ?? []).map((value) => <em className={`source-${value}`} role="img" aria-label={value === 'local' ? 'Local file' : 'Web result'} title={value === 'local' ? 'This lead includes local database evidence' : 'This lead includes web evidence'} key={value}>{value === 'local' ? <Database /> : <Search />}</em>)}<small>{lead.source_run_ids.length} {lead.source_run_ids.length === 1 ? 'run' : 'runs'}</small></span></td><td data-label="Score"><span className="score">{lead.lead_score}/10</span></td><td className="repository-actions"><span className="row-actions"><button className="icon-button" onClick={onEdit} aria-label={`Edit ${lead.domain}`} title="Edit lead"><Pencil /></button><button className="icon-button" onClick={onMove} aria-label={`Move ${lead.domain}`} title="Move to collection"><FolderInput /></button><button className="icon-button destructive" disabled={removing} onClick={onRemove} aria-label={`Remove ${lead.domain}`} title="Remove from repository"><Trash2 /></button></span></td></tr>
}

function RepositoryLeadDrawer({ lead, collections, mode, onClose }: { lead: RepositoryLead; collections: string[]; mode: 'edit' | 'move'; onClose: () => void }) {
  const queryClient = useQueryClient()
  const closeButton = useRef<HTMLButtonElement>(null)
  const dialog = useRef<HTMLElement>(null)
  const [form, setForm] = useState({ business_name: lead.business_name || '', city_or_area: lead.city_or_area || '', website: lead.website || '', emails: (lead.emails ?? []).join('\n'), phones: (lead.phones ?? []).join('\n'), collection: lead.niches?.[0] || 'Uncategorised' })
  const save = useMutation({ mutationFn: () => api.updateRepositoryLead(lead.domain, mode === 'move' ? { collection: form.collection } : { business_name: form.business_name, city_or_area: form.city_or_area, website: form.website, emails: splitContacts(form.emails), phones: splitContacts(form.phones), collection: form.collection }), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['repository'] }); onClose() } })
  useDialogFocus(dialog, onClose)
  useEffect(() => { closeButton.current?.focus() }, [])
  return <div className="drawer-backdrop" onMouseDown={onClose}><aside ref={dialog} className="drawer repository-drawer" role="dialog" aria-modal="true" aria-labelledby="repository-drawer-title" onMouseDown={(event) => event.stopPropagation()}><div className="drawer-head"><div><small>{mode === 'move' ? 'Move to collection' : 'Repository lead'}</small><h2 id="repository-drawer-title">{lead.business_name || lead.domain}</h2><span>{lead.domain}</span></div><button ref={closeButton} className="icon-button" onClick={onClose} aria-label="Close repository editor"><X /></button></div>
    <form className="detail-section edit-form repository-edit-form" onSubmit={(event) => { event.preventDefault(); save.mutate() }}>
      {mode === 'edit' && <><label>Business name<input value={form.business_name} onChange={(event) => setForm({ ...form, business_name: event.target.value })} /></label><label>Area<input value={form.city_or_area} onChange={(event) => setForm({ ...form, city_or_area: event.target.value })} /></label><label>Website<input type="url" value={form.website} onChange={(event) => setForm({ ...form, website: event.target.value })} /></label><label>Emails<textarea value={form.emails} onChange={(event) => setForm({ ...form, emails: event.target.value })} placeholder="One email per line" /></label><label>Phone numbers<textarea value={form.phones} onChange={(event) => setForm({ ...form, phones: event.target.value })} placeholder="One number per line" /></label></>}
      <label>Collection<input required list="repository-collections" value={form.collection} onChange={(event) => setForm({ ...form, collection: event.target.value })} placeholder="Business niche" /></label><datalist id="repository-collections">{collections.map((collection) => <option key={collection} value={collection} />)}</datalist>
      {save.error && <ErrorPanel error={save.error} />}<button className="button primary" disabled={save.isPending}>{mode === 'move' ? <FolderInput /> : <Save />}{save.isPending ? 'Saving...' : mode === 'move' ? 'Move lead' : 'Save changes'}</button>
    </form>
  </aside></div>
}

function splitContacts(value: string) { return [...new Set(value.split(/[\n,;]/).map((item) => item.trim()).filter(Boolean))].slice(0, 3) }

function LeadDrawer({ runId, lead, onClose }: { runId: string; lead: Lead; onClose: () => void }) {
  const queryClient = useQueryClient()
  const closeButton = useRef<HTMLButtonElement>(null)
  const dialog = useRef<HTMLElement>(null)
  const [form, setForm] = useState({ business_name: lead.business_name, generic_email: lead.generic_email, phone: lead.phone, city_or_area: lead.city_or_area, website_quality_note: lead.website_quality_note })
  const save = useMutation({ mutationFn: () => api.updateLead(runId, lead.domain, form), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['run', runId] }); onClose() } })
  const fields = [['generic_email', 'Email', lead.generic_email, Mail], ['phone', 'Phone', lead.phone, Phone], ['city_or_area', 'Area', lead.city_or_area, MapPin]] as const
  useDialogFocus(dialog, onClose)
  useEffect(() => { closeButton.current?.focus() }, [])
  return <div className="drawer-backdrop" onMouseDown={onClose}><aside ref={dialog} className="drawer" role="dialog" aria-modal="true" aria-labelledby="lead-drawer-title" onMouseDown={(e) => e.stopPropagation()}><div className="drawer-head"><div><small>Lead details</small><h2 id="lead-drawer-title">{lead.business_name}</h2><a href={lead.website} target="_blank" rel="noreferrer">{lead.domain}<ExternalLink /></a></div><button ref={closeButton} className="icon-button" onClick={onClose} aria-label="Close details"><X /></button></div>
    <div className="score-block"><strong>{lead.lead_score}</strong><span>Lead score<small>{lead.lead_reason}</small></span></div>
    <div className="detail-section"><h3>Contact evidence</h3>{fields.map(([key, label, value, Icon]) => <div className="evidence" key={key}><Icon /><span><small>{label}</small><strong>{value || 'Not found'}</strong>{lead.field_evidence?.[key]?.source_url && <a href={lead.field_evidence[key].source_url} target="_blank" rel="noreferrer">{lead.field_evidence[key].method ?? 'source'}<ExternalLink /></a>}</span></div>)}</div>
    <div className="detail-section"><h3>Services</h3><div className="tags">{lead.services?.map((service) => <span key={service}>{service}</span>)}</div></div>
    {lead.website_quality_note && <div className="detail-section"><h3>Website note</h3><p>{lead.website_quality_note}</p></div>}
    <div className="detail-section"><NavLink className="button ghost" to={`/outreach?run=${encodeURIComponent(runId)}&domain=${encodeURIComponent(lead.domain)}`}><ShieldCheck />Review outreach eligibility</NavLink></div>
    <form className="detail-section edit-form" onSubmit={(e) => { e.preventDefault(); save.mutate() }}><h3>Edit lead</h3>
      <label>Business name<input value={form.business_name} onChange={(e) => setForm({ ...form, business_name: e.target.value })} /></label>
      <label>Email<input type="email" value={form.generic_email} onChange={(e) => setForm({ ...form, generic_email: e.target.value })} /></label>
      <label>Phone<input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
      <label>Area<input value={form.city_or_area} onChange={(e) => setForm({ ...form, city_or_area: e.target.value })} /></label>
      {save.error && <ErrorPanel error={save.error} />}
      <button className="button primary" disabled={save.isPending}>{save.isPending ? 'Saving…' : 'Save changes'}</button>
    </form>
  </aside></div>
}

function OutreachPage() {
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const runs = useQuery({ queryKey: ['runs'], queryFn: api.listRuns })
  const drafts = useQuery({ queryKey: ['outreach-drafts'], queryFn: api.listDrafts })
  const workspaceSettings = useQuery({ queryKey: ['settings'], queryFn: api.settings, staleTime: 30_000 })
  const emailAccounts = useQuery({ queryKey: ['email-accounts'], queryFn: api.emailAccounts, staleTime: 30_000 })
  const suppressions = useQuery({ queryKey: ['suppressions'], queryFn: api.listSuppressions })
  const [mode, setMode] = useState<'bulk' | 'single'>(searchParams.get('domain') ? 'single' : 'bulk')
  const [draftForm, setDraftForm] = useState({ run_id: searchParams.get('run') ?? '', domain: searchParams.get('domain') ?? '', subscriber_type: 'corporate', lawful_basis_note: '', sender_identity: '', opt_out_address: '', offer_summary: '', consent_confirmed: false, tone: 'professional', links: '', ai_personalize: true })
  const [suppressionForm, setSuppressionForm] = useState<{ value: string; kind: 'email' | 'domain'; reason: string }>({ value: '', kind: 'email', reason: '' })
  const [preflightSelection, setPreflightSelection] = useState<string[]>([])
  const [auditSelection, setAuditSelection] = useState<string[]>([])
  const [bulkReviewer, setBulkReviewer] = useState('')
  const [bulkEligibility, setBulkEligibility] = useState(false)
  const [bulkPrivacy, setBulkPrivacy] = useState(false)
  const [sendJobId, setSendJobId] = useState('')
  const [emailAccountId, setEmailAccountId] = useState('')
  const activeEmailAccountId = emailAccountId || emailAccounts.data?.default_account_id || ''
  const campaignPayload = { ...draftForm, links: draftForm.links.split(/\r?\n/).map((link) => link.trim()).filter(Boolean) }
  const create = useMutation({ mutationFn: () => api.createDraft(campaignPayload), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['outreach-drafts'] }); setDraftForm({ ...draftForm, domain: '', consent_confirmed: false }) } })
  const preflight = useMutation({ mutationFn: () => api.outreachPreflight(draftForm.run_id), onSuccess: (data) => setPreflightSelection(data.results.filter((item) => item.eligible).map((item) => item.domain)) })
  const createBulk = useMutation({ mutationFn: () => api.createDraftsBulk({ ...campaignPayload, domain: undefined, domains: preflightSelection }), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['outreach-drafts'] }); setPreflightSelection([]); preflight.reset() } })
  const approveBulk = useMutation({ mutationFn: () => api.approveDraftsBulk(auditSelection, { reviewed_by: bulkReviewer, corporate_status_confirmed: bulkEligibility, privacy_notice_confirmed: bulkPrivacy }), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['outreach-drafts'] }); setAuditSelection([]); setBulkEligibility(false); setBulkPrivacy(false) } })
  const exportBulk = useMutation({ mutationFn: () => api.exportOutreach(auditSelection), onSuccess: (blob) => { downloadBlob(blob, 'approved_outreach.json'); queryClient.invalidateQueries({ queryKey: ['outreach-drafts'] }); setAuditSelection([]) } })
  const sendBulk = useMutation({ mutationFn: () => api.sendOutreach(auditSelection, activeEmailAccountId), onSuccess: (job) => { setSendJobId(job.id); setAuditSelection([]); queryClient.invalidateQueries({ queryKey: ['outreach-drafts'] }) } })
  const sendJob = useQuery({ queryKey: ['outreach-send', sendJobId], queryFn: () => api.outreachSendStatus(sendJobId), enabled: Boolean(sendJobId), refetchInterval: (query) => ['completed', 'failed', 'stopped'].includes(query.state.data?.status ?? '') ? false : 750 })
  const stopSend = useMutation({ mutationFn: () => api.stopOutreachSend(sendJobId), onSuccess: () => sendJob.refetch() })
  const sendStatus = sendJob.data?.status ?? ''
  useEffect(() => { if (['completed', 'failed', 'stopped'].includes(sendStatus)) queryClient.invalidateQueries({ queryKey: ['outreach-drafts'] }) }, [sendStatus, queryClient])
  const suppress = useMutation({ mutationFn: () => api.addSuppression(suppressionForm), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['suppressions'] }); setSuppressionForm({ ...suppressionForm, value: '', reason: '' }) } })
  const eligibleDomains = preflight.data?.results.filter((item) => item.eligible).map((item) => item.domain) ?? []
  const selectedDrafts = drafts.data?.filter((draft) => auditSelection.includes(draft.id)) ?? []
  const selectedAreDrafts = selectedDrafts.length > 0 && selectedDrafts.every((draft) => draft.status === 'draft')
  const selectedAreApproved = selectedDrafts.length > 0 && selectedDrafts.every((draft) => draft.status === 'approved')
  const toggleAudit = (id: string) => setAuditSelection((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
  return <section>
    <PageHeader eyebrow="Compliance desk" title="Outreach review" subtitle="Turn verified leads into reviewed outreach, individually or in one controlled batch." />
    <div className="compliance-notice"><span className="notice-icon"><ShieldCheck /></span><div><strong>Human approval before delivery</strong><p>Leadroom can send approved drafts through your connected mailbox. Every recipient is checked against suppression records immediately before delivery.</p></div><span className="notice-badge">Controlled send</span></div>
    <div className="outreach-mode-switch" role="group" aria-label="Draft creation mode"><button type="button" aria-pressed={mode === 'bulk'} className={mode === 'bulk' ? 'active' : ''} onClick={() => setMode('bulk')}><Layers3 />Bulk campaign<small>Process a complete run</small></button><button type="button" aria-pressed={mode === 'single'} className={mode === 'single' ? 'active' : ''} onClick={() => setMode('single')}><Mail />Single lead<small>Handle an exception</small></button></div>
    <div className="compliance-layout">
      <form className="panel compliance-form draft-form" onSubmit={(e) => { e.preventDefault(); if (mode === 'bulk') preflight.mutate(); else create.mutate() }}><header><div><small>{mode === 'bulk' ? 'Campaign builder' : 'Draft builder'}</small><h2>{mode === 'bulk' ? 'Prepare a batch' : 'Prepare one lead'}</h2><p>{mode === 'bulk' ? 'Choose a completed run and set the shared campaign details once.' : 'Use verified lead evidence to create a reviewable draft.'}</p></div>{mode === 'bulk' ? <Layers3 /> : <Mail />}</header>
        <div className="form-grid"><label>Source run<select required value={draftForm.run_id} onChange={(e) => { setDraftForm({ ...draftForm, run_id: e.target.value }); preflight.reset(); setPreflightSelection([]) }}><option value="">Select a run</option>{runs.data?.map((run) => <option key={run.id} value={run.id}>{run.run_name} ({run.counts?.completed ?? 0} leads)</option>)}</select></label>{mode === 'single' && <label>Lead domain<input required value={draftForm.domain} onChange={(e) => setDraftForm({ ...draftForm, domain: e.target.value })} placeholder="example.com" /></label>}
          <label>Subscriber type<select value={draftForm.subscriber_type} onChange={(e) => setDraftForm({ ...draftForm, subscriber_type: e.target.value })}><option value="corporate">Corporate body</option><option value="sole_trader">Sole trader</option><option value="unknown">Unknown</option></select></label>
          <label>Sender identity<input required value={draftForm.sender_identity} onChange={(e) => setDraftForm({ ...draftForm, sender_identity: e.target.value })} placeholder="Company or sender name" /></label>
          <label className="span-2">Lawful-basis note<input required minLength={10} value={draftForm.lawful_basis_note} onChange={(e) => setDraftForm({ ...draftForm, lawful_basis_note: e.target.value })} placeholder="Record the evidence supporting this contact" /></label>
          <label>Opt-out address<input required type="email" value={draftForm.opt_out_address} onChange={(e) => setDraftForm({ ...draftForm, opt_out_address: e.target.value })} placeholder="privacy@example.com" /></label>
          <label className="checkbox-label consent-control"><input type="checkbox" checked={draftForm.consent_confirmed} onChange={(e) => setDraftForm({ ...draftForm, consent_confirmed: e.target.checked })} /><span><Check /></span><em><strong>Consent recorded</strong><small>Required for unknown or sole traders</small></em></label>
          <label>Tone<select value={draftForm.tone} onChange={(e) => setDraftForm({ ...draftForm, tone: e.target.value })}><option value="professional">Professional</option><option value="warm">Warm</option><option value="concise">Concise</option><option value="friendly">Friendly</option></select></label><label className="checkbox-label consent-control"><input type="checkbox" checked={draftForm.ai_personalize} onChange={(e) => setDraftForm({ ...draftForm, ai_personalize: e.target.checked })} /><span><Sparkles /></span><em><strong>AI personalization</strong><small>Grounded in each lead's evidence</small></em></label>
          <label className="span-2">Base message<textarea required minLength={10} value={draftForm.offer_summary} onChange={(e) => setDraftForm({ ...draftForm, offer_summary: e.target.value })} placeholder="Write the core offer, outcome, and call to action. You can use {business_name}, {service}, and {location}." /></label><label className="span-2">Links<textarea className="campaign-links" value={draftForm.links} onChange={(e) => setDraftForm({ ...draftForm, links: e.target.value })} placeholder={'https://example.com/opt-in\nhttps://example.com/case-study'} /></label></div>
        {(create.error || preflight.error || createBulk.error) && <ErrorPanel error={(create.error || preflight.error || createBulk.error) as Error} />}
        {mode === 'bulk' && preflight.data && <div className="bulk-preflight"><div className="preflight-summary"><span><strong>{preflight.data.eligible}</strong>Ready</span><span><strong>{preflight.data.blocked}</strong>Blocked</span><span><strong>{preflight.data.total}</strong>Checked</span><button type="button" className="button ghost" onClick={() => setPreflightSelection(preflightSelection.length === eligibleDomains.length ? [] : eligibleDomains)}>{preflightSelection.length === eligibleDomains.length ? 'Clear eligible' : 'Select all eligible'}</button></div><div className="preflight-list">{preflight.data.results.map((item) => <label className={`preflight-row ${item.eligible ? '' : 'blocked'}`} key={item.domain}><input type="checkbox" disabled={!item.eligible} checked={preflightSelection.includes(item.domain)} onChange={() => setPreflightSelection((current) => current.includes(item.domain) ? current.filter((domain) => domain !== item.domain) : [...current, item.domain])} /><span><strong>{item.business_name}</strong><small>{item.email || item.domain}</small></span><em>{item.eligible ? `${item.lead_score}/10` : item.reasons.join(' / ')}</em></label>)}</div></div>}
        <footer><small>{mode === 'bulk' ? 'Suppression, evidence, score, and duplicate checks run before creation.' : 'Drafts enter the audit queue before export.'}</small>{mode === 'bulk' && preflight.data ? <button type="button" className="button primary" disabled={!preflightSelection.length || createBulk.isPending} onClick={() => createBulk.mutate()}><Layers3 />{createBulk.isPending ? 'Creating...' : `Create ${preflightSelection.length} drafts`}</button> : <button className="button primary" disabled={create.isPending || preflight.isPending}><ShieldCheck />{mode === 'bulk' ? preflight.isPending ? 'Checking...' : 'Check eligibility' : create.isPending ? 'Creating...' : 'Create draft'}</button>}</footer>
      </form>
      <form className="panel compliance-form suppression-form" onSubmit={(e) => { e.preventDefault(); suppress.mutate() }}><header><div><small>Do not contact</small><h2>Suppression list</h2><p>Block an address or entire domain from export.</p></div><CircleStop /></header><div className="form-grid"><label>Type<select value={suppressionForm.kind} onChange={(e) => setSuppressionForm({ ...suppressionForm, kind: e.target.value as 'email' | 'domain' })}><option value="email">Email</option><option value="domain">Domain</option></select></label><label>Value<input required value={suppressionForm.value} onChange={(e) => setSuppressionForm({ ...suppressionForm, value: e.target.value })} placeholder={suppressionForm.kind === 'email' ? 'name@example.com' : 'example.com'} /></label><label className="span-2">Reason<input required value={suppressionForm.reason} onChange={(e) => setSuppressionForm({ ...suppressionForm, reason: e.target.value })} placeholder="Why this contact is blocked" /></label></div>{suppress.error && <ErrorPanel error={suppress.error} />}<button className="button ghost" disabled={suppress.isPending}><Plus />{suppress.isPending ? 'Adding...' : 'Add suppression'}</button>
        <div className="suppression-list">{suppressions.data?.map((item) => <div key={item.id}><strong>{item.display_hint}</strong><small>{item.reason}</small></div>)}{suppressions.data?.length === 0 && <p className="muted">No suppression records.</p>}</div>
      </form>
    </div>
    <div className="outreach-list"><div className="section-heading"><div><small>Approval workspace</small><h2>Draft audit queue</h2></div><span>{drafts.data?.length ?? 0} drafts</span></div>{drafts.error && <ErrorPanel error={drafts.error} />}
      {sendJob.data && <div className={`send-queue send-${sendJob.data.status}`}><div><span><Send /><strong>{sendJob.data.status === 'sending' ? 'Sending campaign' : sendJob.data.message}</strong><small>{sendJob.data.completed} of {sendJob.data.total} processed / {sendJob.data.sent} sent / {sendJob.data.failed} failed{sendJob.data.email_account_label ? ` / via ${sendJob.data.email_account_label}` : ''}</small></span><em>{sendJob.data.percent}%</em></div><div className="progress-track"><span style={{ width: `${sendJob.data.percent}%` }} /></div>{['queued', 'sending'].includes(sendJob.data.status) && <button className="button ghost" disabled={stopSend.isPending} onClick={() => stopSend.mutate()}><CircleStop />Stop</button>}</div>}
      {auditSelection.length > 0 && <div className="bulk-audit-toolbar"><div><strong>{auditSelection.length} selected</strong><small>{selectedAreDrafts ? 'Ready for one approval decision' : selectedAreApproved ? 'Choose a sender, then send or export' : 'Select items with the same status'}</small></div>{selectedAreDrafts && <><label>Reviewer<input value={bulkReviewer} onChange={(e) => setBulkReviewer(e.target.value)} placeholder="Your name" /></label><label className="checkbox-label"><input type="checkbox" checked={bulkEligibility} onChange={(e) => setBulkEligibility(e.target.checked)} />Status checked</label><label className="checkbox-label"><input type="checkbox" checked={bulkPrivacy} onChange={(e) => setBulkPrivacy(e.target.checked)} />Privacy checked</label><button className="button primary" disabled={!bulkReviewer || !bulkEligibility || !bulkPrivacy || approveBulk.isPending} onClick={() => approveBulk.mutate()}><ShieldCheck />Approve {auditSelection.length}</button></>}{selectedAreApproved && <><label className="outreach-sender-select"><span>Send from</span><select aria-label="Send from" value={activeEmailAccountId} onChange={(event) => setEmailAccountId(event.target.value)}><option value="">Select account</option>{emailAccounts.data?.accounts.map((account) => <option value={account.id} key={account.id}>{account.label} - {account.from_email}</option>)}</select></label><button className="button primary" disabled={!workspaceSettings.data?.email_configured || !activeEmailAccountId || auditSelection.length > 25 || sendBulk.isPending} onClick={() => sendBulk.mutate()} title={workspaceSettings.data?.email_configured ? 'Send approved emails' : 'Connect an email account in Settings'}><Send />{sendBulk.isPending ? 'Queueing...' : `Send ${auditSelection.length}`}</button><button className="button ghost" disabled={auditSelection.length > 25 || exportBulk.isPending} onClick={() => exportBulk.mutate()}><Download />Export</button></>}<button className="icon-button" onClick={() => setAuditSelection([])} aria-label="Clear selection"><X /></button></div>}
      {(approveBulk.error || exportBulk.error || sendBulk.error || sendJob.error || stopSend.error) && <ErrorPanel error={(approveBulk.error || exportBulk.error || sendBulk.error || sendJob.error || stopSend.error) as Error} />}{drafts.data?.map((draft) => <OutreachDraftRow key={draft.id} draft={draft} selected={auditSelection.includes(draft.id)} onSelect={() => toggleAudit(draft.id)} />)}{drafts.data?.length === 0 && <div className="panel empty-inline outreach-empty"><ShieldCheck /><div><h2>No drafts waiting</h2><p>New drafts will appear here for evidence and consent review.</p></div></div>}</div>
  </section>
}

function downloadBlob(blob: Blob, filename: string) { const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url) }

function OutreachDraftRow({ draft, selected, onSelect }: { draft: OutreachDraft; selected: boolean; onSelect: () => void }) {
  const queryClient = useQueryClient()
  const [reviewedBy, setReviewedBy] = useState('')
  const [eligibility, setEligibility] = useState(false)
  const [privacy, setPrivacy] = useState(false)
  const approve = useMutation({ mutationFn: () => api.approveDraft(draft.id, { reviewed_by: reviewedBy, corporate_status_confirmed: eligibility, privacy_notice_confirmed: privacy }), onSuccess: () => queryClient.invalidateQueries({ queryKey: ['outreach-drafts'] }) })
  const exportDraft = useMutation({ mutationFn: () => api.exportOutreach([draft.id]), onSuccess: (blob) => { const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'approved_outreach.json'; anchor.click(); URL.revokeObjectURL(url); queryClient.invalidateQueries({ queryKey: ['outreach-drafts'] }) } })
  return <article className={`outreach-row ${selected ? 'selected' : ''}`}><div className="outreach-head"><label className="audit-selector" title="Select for bulk action"><input type="checkbox" checked={selected} disabled={!['draft', 'approved'].includes(draft.status)} onChange={onSelect} /><span><Check /></span></label><div><strong>{draft.subject}</strong><small>{draft.recipient_email} / {draft.lead_domain}</small></div><StatusBadge status={draft.status} /></div>{draft.delivery_error && <div className="delivery-error"><AlertTriangle /><span><strong>Last send failed</strong><small>{draft.delivery_error}</small></span></div>}<pre>{draft.body}</pre><div className="audit-note"><small>Lawful basis</small><p>{draft.lawful_basis_note}</p></div>
    {draft.status === 'draft' && <div className="approval-controls"><label>Reviewer<input value={reviewedBy} onChange={(e) => setReviewedBy(e.target.value)} /></label><label className="checkbox-label"><input type="checkbox" checked={eligibility} onChange={(e) => setEligibility(e.target.checked)} />{draft.subscriber_type === 'corporate' ? 'Corporate status checked' : 'Consent evidence checked'}</label><label className="checkbox-label"><input type="checkbox" checked={privacy} onChange={(e) => setPrivacy(e.target.checked)} />Privacy notice checked</label><button className="button primary" disabled={!reviewedBy || !eligibility || !privacy || approve.isPending} onClick={() => approve.mutate()}>Approve</button></div>}
    {draft.status === 'approved' && <button className="button ghost" disabled={exportDraft.isPending} onClick={() => exportDraft.mutate()}><Download />Export approved draft</button>}
    {(approve.error || exportDraft.error) && <ErrorPanel error={(approve.error || exportDraft.error) as Error} />}
  </article>
}

function LocalDataPage() {
  const queryClient = useQueryClient()
  const [niche, setNiche] = useState('beauty')
  const [location, setLocation] = useState('London UK')
  const status = useQuery({ queryKey: ['local-data-status'], queryFn: api.localDataStatus, refetchInterval: 10_000 })
  const update = useMutation({ mutationFn: api.updateLocalData, onSuccess: () => { window.setTimeout(() => queryClient.invalidateQueries({ queryKey: ['local-data-status'] }), 800) } })
  const preview = useMutation({ mutationFn: () => api.localDataPreview(niche, location) })
  const data = status.data
  const coverage = data?.businesses ? [
    { label: 'Websites', value: data.with_website, tone: 'green' },
    { label: 'Phone numbers', value: data.with_phone, tone: 'blue' },
    { label: 'Email addresses', value: data.with_email, tone: 'amber' },
  ] : []
  return <section className="local-data-page">
    <PageHeader eyebrow="Private data plane" title="Local data engine" subtitle="Search a self-hosted map index before touching the public web." action={<div className="page-actions"><button className="button ghost" onClick={() => status.refetch()} disabled={status.isFetching}><RefreshCw className={status.isFetching ? 'spin' : ''} />Refresh status</button><button className="button primary" onClick={() => update.mutate()} disabled={!data?.ready || update.isPending || data?.update_status === 'running'}><RefreshCw className={update.isPending || data?.update_status === 'running' ? 'spin' : ''} />{data?.update_status === 'running' ? 'Syncing data' : 'Sync now'}</button></div>} />
    {status.error && <ErrorPanel error={status.error} />}
    {update.error && <ErrorPanel error={update.error} />}
    <section className={`engine-hero ${data?.ready ? 'engine-ready' : ''}`}>
      <div className="engine-copy"><span className="engine-kicker"><i />{data?.ready ? 'Index online' : data?.database === 'online' ? 'Awaiting dataset' : 'Engine offline'}</span><h2>{data?.ready ? 'Your private discovery index is live.' : 'Build the private discovery layer.'}</h2><p>{data?.message ?? 'Checking PostgreSQL and PostGIS...'}</p><div className="engine-signals"><span><Server />{data?.engine ?? 'PostgreSQL + PostGIS'}</span><span><Cpu />{data?.latency_ms ? `${data.latency_ms} ms bridge` : 'Local compute'}</span><span><LockKeyhole />No paid API</span></div></div>
      <div className="engine-core" aria-label={data?.ready ? 'Local index online' : 'Local index pending'}><div className="core-grid"><span /><span /><span /><span /><span /><span /><span /><span /><span /></div><div className="core-label"><Database /><strong>{(data?.businesses ?? 0).toLocaleString()}</strong><small>business records</small></div></div>
    </section>
    <div className="engine-metrics"><Metric label="Indexed businesses" value={data?.businesses ?? 0} accent /><Metric label="With a website" value={data?.with_website ?? 0} /><Metric label="With a phone" value={data?.with_phone ?? 0} /><Metric label="With an email" value={data?.with_email ?? 0} /></div>
    <section className="engine-workbench">
      <div className="engine-search"><header><div><span className="eyebrow">Query console</span><h2>Test the local index</h2></div><span className={`engine-state ${data?.ready ? 'online' : ''}`}><i />{data?.ready ? 'Ready' : 'Unavailable'}</span></header><form onSubmit={(event) => { event.preventDefault(); preview.mutate() }}><label>Business niche<input value={niche} onChange={(event) => setNiche(event.target.value)} /></label><label>Location<input value={location} onChange={(event) => setLocation(event.target.value)} /></label><button className="button primary" disabled={!data?.ready || preview.isPending}><ScanSearch />{preview.isPending ? 'Searching...' : 'Run local query'}</button></form>{preview.error && <ErrorPanel error={preview.error} />}{preview.data && <div className="preview-results"><div className="preview-summary"><strong>{preview.data.count} matches</strong><span>{preview.data.elapsed_ms} ms</span></div>{preview.data.results.map((candidate) => <motion.article key={candidate.domain} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}><span className="result-source"><MapPin /></span><div><strong>{candidate.title}</strong><small>{candidate.snippet || candidate.city_or_area}</small></div><div className="result-contact">{candidate.email && <Mail />}{candidate.phone && <Phone />}{candidate.url && <ExternalLink />}</div></motion.article>)}</div>}</div>
      <aside className="engine-inspector"><header><span><span className="eyebrow">Dataset health</span><h2>Contact coverage</h2></span><span className={`sync-state sync-${data?.update_status ?? 'not_configured'}`}><i />{data?.update_status === 'running' ? 'Syncing' : data?.update_status === 'failed' ? 'Needs attention' : 'Auto-sync on'}</span></header>{coverage.length ? <div className="coverage-list">{coverage.map((item) => { const percent = Math.round(item.value / (data?.businesses || 1) * 100); return <div key={item.label}><span><strong>{item.label}</strong><em>{percent}%</em></span><div><i className={`coverage-${item.tone}`} style={{ width: `${percent}%` }} /></div><small>{item.value.toLocaleString()} records</small></div> })}</div> : <div className="engine-empty"><Database /><strong>No imported records</strong><small>Run the Great Britain import to populate this index.</small></div>}<div className="pipeline-strip"><span><Database /><small>OSM PBF</small></span><ChevronRight /><span><Layers3 /><small>osm2pgsql</small></span><ChevronRight /><span><Server /><small>PostGIS</small></span></div><div className={`sync-note sync-note-${data?.update_status ?? 'not_configured'}`}><RefreshCw className={data?.update_status === 'running' ? 'spin' : ''} /><span><strong>{data?.update_schedule ?? 'Automatic updates'}</strong><small>{data?.update_message ?? 'Checking update service...'}</small></span></div><dl className="engine-facts"><div><dt>Dataset</dt><dd>{data?.dataset ?? 'OpenStreetMap'}</dd></div><div><dt>Last sync</dt><dd>{data?.last_updated_at ? formatDate(data.last_updated_at) : data?.last_imported_at ? formatDate(data.last_imported_at) : 'Not imported'}</dd></div><div><dt>PostGIS</dt><dd>{data?.postgis_version?.split(' ')[0] ?? 'Offline'}</dd></div></dl><a className="osm-attribution" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a></aside>
    </section>
  </section>
}

function LocalDataSettings() {
  const queryClient = useQueryClient()
  const [niche, setNiche] = useState('beauty')
  const [location, setLocation] = useState('London UK')
  const status = useQuery({ queryKey: ['local-data-status'], queryFn: api.localDataStatus, refetchInterval: 15_000 })
  const update = useMutation({ mutationFn: api.updateLocalData, onSuccess: () => { window.setTimeout(() => queryClient.invalidateQueries({ queryKey: ['local-data-status'] }), 800) } })
  const preview = useMutation({ mutationFn: () => api.localDataPreview(niche, location) })
  const data = status.data
  return <section className="settings-section local-index-settings" id="local-data">
    <header><div><span className="settings-icon"><Database /></span><div><h2>Local discovery index</h2><p>Private search data used by Local and Both modes in every run.</p></div></div><span className={`connection-state ${data?.ready ? 'is-online' : ''}`}><i />{data?.ready ? 'Online' : 'Unavailable'}</span></header>
    <div className="settings-body local-index-body">
      {status.error && <ErrorPanel error={status.error} />}{update.error && <ErrorPanel error={update.error} />}
      <div className="local-index-status"><div><span className="local-index-pulse"><Database /></span><span><strong>{data?.ready ? 'Local index ready' : data?.database === 'online' ? 'Dataset required' : 'Local index offline'}</strong><small>{data?.message ?? 'Checking the local discovery service...'}</small></span></div><div className="local-index-actions"><button className="button ghost" type="button" onClick={() => status.refetch()} disabled={status.isFetching}><RefreshCw className={status.isFetching ? 'spin' : ''} />Refresh</button><button className="button primary" type="button" onClick={() => update.mutate()} disabled={!data?.ready || update.isPending || data?.update_status === 'running'}><RefreshCw className={update.isPending || data?.update_status === 'running' ? 'spin' : ''} />{data?.update_status === 'running' ? 'Syncing' : 'Sync data'}</button></div></div>
      <div className="local-index-metrics"><Metric label="Businesses" value={data?.businesses ?? 0} accent /><Metric label="Websites" value={data?.with_website ?? 0} /><Metric label="Phones" value={data?.with_phone ?? 0} /><Metric label="Emails" value={data?.with_email ?? 0} /></div>
      <div className="local-index-meta"><span><small>Dataset</small><strong>{data?.dataset ?? 'OpenStreetMap'}</strong></span><span><small>Last sync</small><strong>{data?.last_updated_at ? formatDate(data.last_updated_at) : data?.last_imported_at ? formatDate(data.last_imported_at) : 'Not imported'}</strong></span><span><small>Schedule</small><strong>{data?.update_schedule ?? 'Automatic updates'}</strong></span></div>
      <form className="local-index-query" onSubmit={(event) => { event.preventDefault(); preview.mutate() }}><div><span><ScanSearch /></span><span><strong>Test local search</strong><small>Check what the private index returns before starting a run.</small></span></div><label>Business niche<input value={niche} onChange={(event) => setNiche(event.target.value)} /></label><label>Location<input value={location} onChange={(event) => setLocation(event.target.value)} /></label><button className="button ghost" disabled={!data?.ready || preview.isPending}><Search />{preview.isPending ? 'Searching...' : 'Test query'}</button></form>
      {preview.error && <ErrorPanel error={preview.error} />}{preview.data && <div className="local-preview"><span><strong>{preview.data.count} matches</strong><small>{preview.data.elapsed_ms} ms</small></span><div>{preview.data.results.slice(0, 5).map((candidate) => <span key={candidate.domain}><strong>{candidate.title}</strong><small>{candidate.city_or_area || candidate.domain}</small></span>)}</div></div>}
    </div>
  </section>
}

function formatModelSize(bytes: number) {
  if (!bytes) return 'Size unavailable'
  return `${(bytes / 1024 ** 3).toFixed(bytes >= 10 * 1024 ** 3 ? 0 : 1)} GB`
}

function OllamaModelManager({ modelName, enabled, onSelect }: { modelName: string; enabled: boolean; onSelect: (model: string) => void }) {
  const queryClient = useQueryClient()
  const [pickerOpen, setPickerOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const deferredSearch = useDeferredValue(searchTerm)
  const [modelTag, setModelTag] = useState(modelName)
  const [jobId, setJobId] = useState('')
  const handledJob = useRef('')
  const models = useQuery({ queryKey: ['ollama-models'], queryFn: api.ollamaModels, enabled, refetchInterval: false })
  const catalog = useQuery({ queryKey: ['ollama-catalog', deferredSearch], queryFn: () => api.ollamaCatalog(deferredSearch), enabled: enabled && pickerOpen, staleTime: 10 * 60 * 1000 })
  const pull = useMutation({ mutationFn: (tag: string) => api.pullOllamaModel(tag), onSuccess: (job) => setJobId(job.id) })
  const pullStatus = useQuery({ queryKey: ['ollama-pull', jobId], queryFn: () => api.ollamaPullStatus(jobId), enabled: Boolean(jobId), refetchInterval: (query) => ['completed', 'failed'].includes(query.state.data?.status ?? '') ? false : 700 })
  const benchmark = useMutation({ mutationFn: () => api.benchmarkOllamaModel(modelName) })
  const installed = useMemo(() => models.data?.models ?? [], [models.data?.models])
  const installedNames = useMemo(() => installed.map((model) => model.name || model.model || '').filter(Boolean), [installed])
  const isInstalled = installed.some((model) => (model.name || model.model) === modelName || (model.name || model.model) === `${modelName}:latest`)
  const pickerRows = useMemo(() => {
    const rows = installed.map((model) => ({
      name: model.name || model.model || '', description: `${model.details?.parameter_size || 'Local model'} · ${model.details?.quantization_level || model.details?.family || 'Ollama'} · ${formatModelSize(model.size)}`,
      installed: true, local: true, capabilities: [] as string[],
    }))
    const known = new Set(rows.map((row) => row.name))
    for (const family of catalog.data?.models ?? []) {
      const names = deferredSearch.trim() ? [family.name, ...family.variants.map((variant) => `${family.name}:${variant}`)] : [family.name]
      for (const name of names) {
        const existing = installedNames.find((installedName) => installedName === name || installedName === `${name}:latest`)
        if (existing || known.has(name)) continue
        known.add(name)
        rows.push({ name, description: family.description, installed: false, local: family.local, capabilities: family.capabilities })
        if (rows.length >= 60) break
      }
      if (rows.length >= 60) break
    }
    return rows
  }, [catalog.data?.models, deferredSearch, installed, installedNames])
  useEffect(() => {
    if (pullStatus.data?.status === 'completed' && handledJob.current !== pullStatus.data.id) {
      handledJob.current = pullStatus.data.id
      queryClient.invalidateQueries({ queryKey: ['ollama-models'] })
      if (modelName !== pullStatus.data.model) onSelect(pullStatus.data.model)
      setPickerOpen(false)
    }
  }, [modelName, onSelect, pullStatus.data, queryClient])
  if (!enabled) return <div className="model-manager-locked"><HardDrive /><span><strong>Save Ollama first</strong><small>Choose Ollama as the provider and save settings to manage local models.</small></span></div>
  return <section className="ollama-manager">
    <header><div><span className="model-manager-icon"><HardDrive /></span><span><strong>Ollama models</strong><small>{installed.length} installed on this computer</small></span></div><button type="button" className="icon-button" onClick={() => models.refetch()} disabled={models.isFetching} aria-label="Refresh installed models" title="Refresh installed models"><RefreshCw className={models.isFetching ? 'spin' : ''} /></button></header>
    {models.error && <ErrorPanel error={models.error} />}
    <div className="model-picker-shell">
      <button type="button" className={`model-picker-trigger ${pickerOpen ? 'open' : ''}`} onClick={() => setPickerOpen(!pickerOpen)} aria-expanded={pickerOpen}><span className="model-state"><Bot /></span><span><small>Active model</small><strong>{modelName}</strong></span><ChevronDown /></button>
      {pickerOpen && <div className="model-picker-popover">
        <label className="model-search"><Search /><input autoFocus value={searchTerm} onChange={(event) => setSearchTerm(event.target.value)} placeholder="Find a model..." aria-label="Find model" />{searchTerm && <button type="button" onClick={() => setSearchTerm('')} aria-label="Clear model search"><X /></button>}</label>
        <div className="model-picker-list" role="listbox" aria-label="Ollama model catalog">
          {(models.isLoading || catalog.isLoading) && !pickerRows.length && <LoadingRows />}
          {pickerRows.map((row) => { const selected = row.name === modelName || row.name === `${modelName}:latest`; const downloading = pullStatus.data?.model === row.name && !['completed', 'failed'].includes(pullStatus.data.status); return <button type="button" role="option" aria-selected={selected} className={`model-picker-row ${selected ? 'selected' : ''}`} disabled={!row.local || downloading} onClick={() => { setModelTag(row.name); if (row.installed) { onSelect(row.name); setPickerOpen(false) } else pull.mutate(row.name) }} key={row.name}><span className="model-row-copy"><strong>{row.name}</strong><small>{row.description || (row.local ? 'Available from the Ollama library' : 'Ollama cloud model')}</small>{row.capabilities.length > 0 && <span className="model-capabilities">{row.capabilities.slice(0, 3).map((item) => <em key={item}>{item}</em>)}</span>}</span><span className="model-row-action">{downloading ? `${pullStatus.data?.percent ?? 0}%` : selected ? <Check /> : row.installed ? <HardDrive /> : row.local ? <Download /> : <Cloud />}</span></button> })}
          {!models.isLoading && !catalog.isLoading && !pickerRows.length && <div className="models-empty"><Search /><span><strong>No matching models</strong><small>Try another name or use an exact model tag below.</small></span></div>}
        </div>
        {catalog.error && <div className="catalog-offline"><AlertTriangle />Online catalog unavailable. Installed models still work.</div>}
        <footer><span><HardDrive />Installed</span><span><Download />Downloadable</span><span><Cloud />Cloud only</span></footer>
      </div>}
    </div>
    <details className="manual-model-download"><summary>Install an exact model tag</summary><form className="model-download" onSubmit={(event) => { event.preventDefault(); pull.mutate(modelTag.trim()) }}><label>Model tag<input required value={modelTag} onChange={(event) => setModelTag(event.target.value)} placeholder="e.g. qwen3.5:4b" /></label><button className="button ghost" disabled={!modelTag.trim() || pull.isPending || pullStatus.data?.status === 'downloading'}><Download />{pull.isPending ? 'Starting...' : 'Download'}</button></form></details>
    {(pull.error || pullStatus.error) && <ErrorPanel error={(pull.error || pullStatus.error) as Error} />}
    {pullStatus.data && <div className={`download-progress download-${pullStatus.data.status}`}><div><span><strong>{pullStatus.data.model}</strong><small>{pullStatus.data.error || pullStatus.data.message}</small></span><em>{pullStatus.data.status === 'completed' ? 'Installed' : pullStatus.data.status === 'failed' ? 'Failed' : `${pullStatus.data.percent}%`}</em></div><div className="download-track"><span style={{ width: `${pullStatus.data.percent}%` }} /></div>{pullStatus.data.total > 0 && <small>{formatModelSize(pullStatus.data.completed)} of {formatModelSize(pullStatus.data.total)}</small>}</div>}
    <div className="model-benchmark"><div><span className="model-manager-icon"><Gauge /></span><span><strong>Lead extraction fit test</strong><small>Checks structured output, contact accuracy, services, location, and speed.</small></span></div><button type="button" className="button ghost" disabled={!isInstalled || benchmark.isPending} onClick={() => benchmark.mutate()}><Gauge />{benchmark.isPending ? 'Testing model...' : 'Test selected model'}</button></div>
    {!isInstalled && installed.length > 0 && <p className="benchmark-hint">Select an installed model or download <strong>{modelName}</strong> before testing.</p>}
    {benchmark.error && <ErrorPanel error={benchmark.error} />}
    {benchmark.data && <div className={`benchmark-result verdict-${benchmark.data.verdict}`}><div className="benchmark-score"><strong>{benchmark.data.score}</strong><span>/10<small>{benchmark.data.verdict.replace('_', ' ')}</small></span></div><div className="benchmark-checks">{benchmark.data.checks.map((check) => <span className={check.passed ? 'passed' : ''} key={check.label}>{check.passed ? <Check /> : <X />}<strong>{check.label}</strong><small>{check.points} pts</small></span>)}</div><footer><span>{benchmark.data.duration_seconds}s total</span><span>{benchmark.data.tokens_per_second ? `${benchmark.data.tokens_per_second} tokens/sec` : 'Speed unavailable'}</span></footer></div>}
  </section>
}

const themeOptions: Array<{ id: ThemeId; name: string; color: string }> = [
  { id: 'brushstroke', name: 'Brushstroke', color: '#b45309' },
  { id: 'genesis', name: 'Genesis', color: '#6366f1' },
  { id: 'flip7', name: 'Flip7', color: '#2ba8a2' },
  { id: 'rawblock', name: 'RawBlock', color: '#000000' },
  { id: 'evreghen', name: 'Evreghen', color: '#fe6e00' },
  { id: 'ember', name: 'Ember Studio', color: '#c2410c' },
  { id: 'insightdeck', name: 'InsightDeck', color: '#9333ea' },
  { id: 'vercel', name: 'Vercel Interface', color: '#171717' },
  { id: 'trustblue', name: 'Trust Blue Pay', color: '#003087' },
  { id: 'zengrid', name: 'ZenGrid', color: '#78716c' },
]

function ThemeSelector({ selected, onSelect }: { selected: ThemeId; onSelect: (theme: ThemeId) => void }) {
  const selectWithKeyboard = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    const keys = ['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End']
    if (!keys.includes(event.key)) return
    event.preventDefault()
    const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? themeOptions.length - 1 : (index + (['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : -1) + themeOptions.length) % themeOptions.length
    onSelect(themeOptions[nextIndex].id)
    const buttons = event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="radio"]')
    buttons?.[nextIndex]?.focus()
  }
  return <section className="settings-section theme-settings theme-settings-compact"><header><div><span className="settings-icon"><Palette /></span><div><h2>Appearance</h2><p>Select a workspace theme.</p></div></div><span className="connection-state is-online"><i />Lightweight</span></header><div className="settings-body theme-dots" role="radiogroup" aria-label="Workspace theme">
    {themeOptions.map((theme, index) => <button type="button" role="radio" aria-label={theme.name} aria-checked={selected === theme.id} tabIndex={selected === theme.id ? 0 : -1} title={theme.name} className={`theme-dot ${selected === theme.id ? 'selected' : ''}`} style={{ '--theme-color': theme.color } as CSSProperties} onKeyDown={(event) => selectWithKeyboard(event, index)} onClick={() => onSelect(theme.id)} key={theme.id}>{selected === theme.id && <Check />}<span className="sr-only">{theme.name}</span></button>)}
  </div></section>
}

const emptyEmailAccount: EmailAccountInput = {
  label: '', host: '', port: 587, security: 'starttls', username: '', password: '', clear_password: false,
  from_email: '', from_name: '', reply_to: '',
}

function EmailAccountsSettings() {
  const queryClient = useQueryClient()
  const accounts = useQuery({ queryKey: ['email-accounts'], queryFn: api.emailAccounts })
  const [selectedId, setSelectedId] = useState('')
  const [form, setForm] = useState<EmailAccountInput>(emptyEmailAccount)
  const selected = accounts.data?.accounts.find((account) => account.id === selectedId)
  const loadAccount = (account: EmailAccount) => {
    setSelectedId(account.id)
    setForm({ label: account.label, host: account.host, port: account.port, security: account.security, username: account.username, password: '', clear_password: false, from_email: account.from_email, from_name: account.from_name, reply_to: account.reply_to })
  }
  const sync = (data: EmailAccountsResponse, preferredId = '') => {
    queryClient.setQueryData(['email-accounts'], data)
    queryClient.invalidateQueries({ queryKey: ['settings'] })
    const next = data.accounts.find((account) => account.id === preferredId) ?? data.accounts.at(-1)
    if (next) loadAccount(next)
    else { setSelectedId(''); setForm(emptyEmailAccount) }
  }
  const save = useMutation({
    mutationFn: () => selectedId ? api.updateEmailAccount(selectedId, form) : api.createEmailAccount(form),
    onSuccess: (data) => sync(data, selectedId),
  })
  const remove = useMutation({ mutationFn: api.deleteEmailAccount, onSuccess: (data) => sync(data, data.default_account_id) })
  const makeDefault = useMutation({ mutationFn: api.setDefaultEmailAccount, onSuccess: (data) => sync(data, selectedId) })
  const test = useMutation({ mutationFn: api.testEmailAccount })
  const busy = save.isPending || remove.isPending || makeDefault.isPending
  return <section className="settings-section email-settings email-accounts-settings"><header><div><span className="settings-icon"><Mail /></span><div><h2>Email accounts</h2><p>Choose which company mailbox sends each approved campaign.</p></div></div><span className={`connection-state ${accounts.data?.accounts.length ? 'is-online' : ''}`}><i />{accounts.data?.accounts.length ?? 0} connected</span></header><div className="settings-body email-account-workspace">
    <aside className="email-account-list"><div className="email-account-list-head"><span><strong>Senders</strong><small>SMTP accounts available to Outreach</small></span><button type="button" className="icon-button" onClick={() => { setSelectedId(''); setForm(emptyEmailAccount); test.reset() }} aria-label="Add email account" title="Add email account"><Plus /></button></div>
      {accounts.isLoading && <LoadingRows />}
      {accounts.data?.accounts.map((account) => <button type="button" className={`email-account-card ${selectedId === account.id ? 'selected' : ''}`} aria-pressed={selectedId === account.id} onClick={() => { loadAccount(account); test.reset() }} key={account.id}><span className="email-account-avatar">{(account.from_name || account.label || account.from_email).slice(0, 1).toUpperCase()}</span><span><strong>{account.label}</strong><small>{account.from_email}</small></span>{account.is_default ? <em><Check />Default</em> : <ChevronRight />}</button>)}
      {!accounts.isLoading && !accounts.data?.accounts.length && <div className="email-account-empty"><Mail /><strong>No sender accounts</strong><small>Add the SMTP details supplied by your email company.</small></div>}
    </aside>
    <form className="email-account-editor" onSubmit={(event) => { event.preventDefault(); save.mutate() }}><div className="email-account-editor-head"><span><small>{selected ? 'Editing sender' : 'New sender'}</small><h3>{selected?.label || 'Connect a company mailbox'}</h3></span>{selected?.is_default && <em><Check />Default sender</em>}</div>
      <div className="email-account-identity"><label>Account label<input required value={form.label} onChange={(event) => setForm({ ...form, label: event.target.value })} placeholder="e.g. Northstar Sales" /></label><label>From email<input required type="email" value={form.from_email} onChange={(event) => setForm({ ...form, from_email: event.target.value })} placeholder="sales@company.com" /></label><label>Sender name<input value={form.from_name} onChange={(event) => setForm({ ...form, from_name: event.target.value })} placeholder="Company or team name" /></label><label>Reply-to<input type="email" value={form.reply_to} onChange={(event) => setForm({ ...form, reply_to: event.target.value })} placeholder="replies@company.com" /></label></div>
      <div className="email-account-server"><label className="email-host-field">SMTP host<input required value={form.host} onChange={(event) => setForm({ ...form, host: event.target.value })} placeholder="smtp.company.com" /></label><label>Port<input required type="number" min="1" max="65535" value={form.port} onChange={(event) => setForm({ ...form, port: Number(event.target.value) || 587 })} /></label><label>Security<select value={form.security} onChange={(event) => setForm({ ...form, security: event.target.value as EmailAccountInput['security'] })}><option value="starttls">STARTTLS</option><option value="ssl">SSL/TLS</option><option value="none">None</option></select></label><label>Username<input value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} autoComplete="username" placeholder="Usually your email address" /></label><label>Password or app password<input type="password" value={form.password ?? ''} onChange={(event) => setForm({ ...form, password: event.target.value, clear_password: false })} autoComplete="new-password" placeholder={selected?.password_configured ? 'Stored securely - enter to replace' : 'Enter account password'} /></label></div>
      <div className="email-account-note"><LockKeyhole /><span><strong>Stored on this Windows account</strong><small>Credentials are encrypted locally. Outlook New can keep receiving the same mailbox independently.</small></span></div>
      {(accounts.error || save.error || remove.error || makeDefault.error || test.error) && <ErrorPanel error={(accounts.error || save.error || remove.error || makeDefault.error || test.error) as Error} />}
      {test.isSuccess && <div className="email-account-test-success" role="status"><Check /><span><strong>Connection verified</strong><small>{test.data.sender} is ready to send.</small></span></div>}
      <footer><div>{selected && !selected.is_default && <button type="button" className="button ghost" disabled={busy} onClick={() => makeDefault.mutate(selected.id)}><Check />Make default</button>}{selected && <button type="button" className="button text-danger" disabled={busy} onClick={() => { if (window.confirm(`Remove ${selected.label}?`)) remove.mutate(selected.id) }}><Trash2 />Remove</button>}</div><div>{selected && <button type="button" className="button ghost" disabled={busy || test.isPending} onClick={() => test.mutate(selected.id)}><Activity />{test.isPending ? 'Testing...' : 'Test account'}</button>}<button className="button primary" disabled={busy}><Save />{save.isPending ? 'Saving...' : selected ? 'Save account' : 'Add account'}</button></div></footer>
    </form>
  </div></section>
}

function withWorkspaceFallback(payload: WorkspaceSettingsUpdate): WorkspaceSettingsUpdate {
  return {
    ...payload,
    workspace_name: payload.workspace_name.trim() || 'Leadroom',
    workspace_subtitle: payload.workspace_subtitle.trim() || 'Signal desk',
  }
}

function StorageSettingsPanel() {
  const queryClient = useQueryClient()
  const storage = useQuery({ queryKey: ['storage-settings'], queryFn: api.storageSettings })
  const [override, setOverride] = useState<StorageSettingsUpdate | null>(null)
  const form = override ?? (storage.data ? {
    data_root: storage.data.data_root,
    downloads_root: storage.data.downloads_root || storage.data.active_data_root,
    data_action: 'move' as const,
    move_downloads: true,
  } : null)
  const save = useMutation({
    mutationFn: api.updateStorageSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(['storage-settings'], data)
      setOverride((current) => current ? { ...current, data_root: data.data_root, downloads_root: data.downloads_root } : null)
    },
  })
  const browse = useMutation({
    mutationFn: ({ field, path }: { field: 'data_root' | 'downloads_root'; path: string }) => api.browseStorageFolder(path).then((result) => ({ field, path: result.path })),
    onSuccess: ({ field, path }) => { if (path && form) setOverride({ ...form, [field]: path }) },
  })
  if (storage.isLoading || !form) return <section className="settings-section storage-settings"><header><div><span className="settings-icon"><HardDrive /></span><div><h2>Storage</h2><p>Workspace data and large local downloads.</p></div></div></header><LoadingRows /></section>
  return <section className="settings-section storage-settings"><header><div><span className="settings-icon"><HardDrive /></span><div><h2>Storage</h2><p>Choose where Leadroom keeps workspace data and large downloads.</p></div></div>{storage.data?.restart_required ? <span className="connection-state storage-restart"><i />Restart pending</span> : <span className="connection-state is-online"><i />Active</span>}</header><div className="settings-body storage-body">
    <div className="storage-location"><div className="storage-location-title"><span className="storage-location-icon"><Database /></span><span><strong>Workspace data</strong><small>SQLite database and exported lead files</small></span><em>{formatModelSize(storage.data?.workspace_bytes ?? 0)}</em></div><label>Folder<div className="storage-path-control"><input value={form.data_root} onChange={(event) => setOverride({ ...form, data_root: event.target.value })} spellCheck={false} /><button type="button" className="button ghost" disabled={browse.isPending} onClick={() => browse.mutate({ field: 'data_root', path: form.data_root })}><FolderInput />Browse</button></div></label><div className="storage-path-meta"><span><strong>{formatModelSize(storage.data?.data_disk.free_bytes ?? 0)} free</strong><small>{storage.data?.database_exists ? `Database found · ${formatModelSize(storage.data.database_bytes)}` : 'No database in selected folder yet'}</small></span><code title={storage.data?.database_path}>{storage.data?.database_path}</code></div>
      <fieldset className="storage-mode"><legend>When the app restarts</legend><label className={form.data_action === 'move' ? 'selected' : ''}><input type="radio" name="storage-action" checked={form.data_action === 'move'} onChange={() => setOverride({ ...form, data_action: 'move' })} /><FolderInput /><span><strong>Move current workspace</strong><small>Safely copy and verify the current database</small></span><Check /></label><label className={form.data_action === 'use' ? 'selected' : ''}><input type="radio" name="storage-action" checked={form.data_action === 'use'} onChange={() => setOverride({ ...form, data_action: 'use' })} /><Database /><span><strong>Use selected folder</strong><small>Open its existing database or create a new one</small></span><Check /></label></fieldset>
    </div>
    <div className="storage-location"><div className="storage-location-title"><span className="storage-location-icon"><Archive /></span><span><strong>Large downloads</strong><small>Browser runtime, page cache, and future Ollama models</small></span><em>{formatModelSize(storage.data?.downloads_disk.free_bytes ?? 0)} free</em></div><label>Folder<div className="storage-path-control"><input value={form.downloads_root} onChange={(event) => setOverride({ ...form, downloads_root: event.target.value })} spellCheck={false} /><button type="button" className="button ghost" disabled={browse.isPending} onClick={() => browse.mutate({ field: 'downloads_root', path: form.downloads_root })}><FolderInput />Browse</button></div></label><div className="storage-breakdown"><span><strong>Cache</strong><code>{storage.data?.cache_dir}</code></span><span><strong>Browser</strong><code>{storage.data?.browser_dir}</code></span><span><strong>Ollama</strong><code>{storage.data?.ollama_dir}</code></span></div><label className="storage-move-toggle"><input type="checkbox" checked={form.move_downloads} onChange={(event) => setOverride({ ...form, move_downloads: event.target.checked })} /><span><strong>Move Leadroom cache and browser files</strong><small>Existing Ollama models stay in place; new downloads use this folder after Ollama restarts.</small></span></label></div>
    {(storage.error || save.error || browse.error) && <ErrorPanel error={(storage.error || save.error || browse.error) as Error} />}
    {save.isSuccess && <div className="storage-saved" role="status"><RefreshCw /><span><strong>Storage locations saved</strong><small>Close and reopen Leadroom to apply the change. Restart Ollama before downloading another model.</small></span></div>}
    <footer className="storage-actions"><span><LockKeyhole />A tiny locator file remains in Windows AppData so Leadroom can find these folders.</span><button type="button" className="button primary" disabled={save.isPending || !form.data_root.trim() || !form.downloads_root.trim()} onClick={() => save.mutate(form)}><Save />{save.isPending ? 'Checking folders...' : 'Save storage locations'}</button></footer>
  </div></section>
}

function SettingsPage() {
  const queryClient = useQueryClient()
  const reduceMotion = useReducedMotion()
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const [formOverride, setForm] = useState<WorkspaceSettingsUpdate | null>(null)
  const [domainInput, setDomainInput] = useState('')
  const [localError, setLocalError] = useState('')
  const [savedNotice, setSavedNotice] = useState(0)
  const form = formOverride ?? (settings.data ? {
    model_provider: settings.data.model_provider, model_name: settings.data.model_name,
    model_endpoint: settings.data.model_endpoint, clear_api_key: false, blocked_domains: settings.data.blocked_domains,
    workspace_name: settings.data.workspace_name, workspace_subtitle: settings.data.workspace_subtitle, logo_data_url: settings.data.logo_data_url,
    theme: isThemeId(settings.data.theme) ? settings.data.theme : 'brushstroke',
    smtp_host: settings.data.smtp_host ?? '', smtp_port: settings.data.smtp_port ?? 587,
    smtp_security: settings.data.smtp_security ?? 'starttls', smtp_username: settings.data.smtp_username ?? '',
    clear_smtp_password: false, smtp_from_email: settings.data.smtp_from_email ?? '',
    smtp_from_name: settings.data.smtp_from_name ?? '', smtp_reply_to: settings.data.smtp_reply_to ?? '',
  } satisfies WorkspaceSettingsUpdate : null)
  const saved = useMutation({
    mutationFn: (payload: WorkspaceSettingsUpdate) => api.updateSettings(withWorkspaceFallback(payload)),
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
      const theme = isThemeId(data.theme) ? data.theme : 'brushstroke'
      applyTheme(theme)
      setForm({ model_provider: data.model_provider, model_name: data.model_name, model_endpoint: data.model_endpoint, clear_api_key: false, blocked_domains: data.blocked_domains, workspace_name: data.workspace_name, workspace_subtitle: data.workspace_subtitle, logo_data_url: data.logo_data_url, theme, smtp_host: data.smtp_host ?? '', smtp_port: data.smtp_port ?? 587, smtp_security: data.smtp_security ?? 'starttls', smtp_username: data.smtp_username ?? '', clear_smtp_password: false, smtp_from_email: data.smtp_from_email ?? '', smtp_from_name: data.smtp_from_name ?? '', smtp_reply_to: data.smtp_reply_to ?? '' })
      setSavedNotice((value) => value + 1)
    },
  })
  const themeSaved = useMutation({
    mutationFn: api.updateTheme,
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
      setSavedNotice((value) => value + 1)
    },
  })
  const testConnection = useMutation({
    mutationFn: async (payload: WorkspaceSettingsUpdate) => { await api.updateSettings(withWorkspaceFallback(payload)); return api.testModelConnection() },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['settings'] }),
  })
  const addDomain = () => {
    if (!form) return
    const domain = domainInput.trim().toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0]
    if (!/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}$/.test(domain)) {
      setLocalError('Enter a valid domain such as example.com')
      return
    }
    setForm({ ...form, blocked_domains: [...new Set([...form.blocked_domains, domain])].sort() })
    setDomainInput('')
    setLocalError('')
  }
  const readLogo = (file?: File) => {
    if (!file) return
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 500_000) {
      setLocalError('Choose a PNG, JPEG, or WebP image smaller than 500 KB')
      return
    }
    const reader = new FileReader()
    reader.onload = () => { if (form && typeof reader.result === 'string') setForm({ ...form, logo_data_url: reader.result }); setLocalError('') }
    reader.readAsDataURL(file)
  }
  useEffect(() => {
    if (!savedNotice) return
    const timer = window.setTimeout(() => setSavedNotice(0), 3200)
    return () => window.clearTimeout(timer)
  }, [savedNotice])
  if (settings.error) return <section className="narrow"><PageHeader eyebrow="System" title="Settings" subtitle="Workspace identity, model runtime, and discovery rules" /><ErrorPanel error={settings.error} /><button className="button ghost" onClick={() => settings.refetch()}><Activity />Retry</button></section>
  if (settings.isLoading || !form) return <section className="narrow"><PageHeader eyebrow="System" title="Settings" subtitle="Workspace identity, model runtime, and discovery rules" /><LoadingRows /></section>
  const apiConfigured = settings.data?.api_key_configured && !form.clear_api_key
  return <section className="settings-page narrow"><PageHeader eyebrow="System" title="Settings" subtitle="Workspace identity, model runtime, and discovery rules" action={<button className="button primary" disabled={saved.isPending} onClick={() => saved.mutate(form)}><Save />{saved.isPending ? 'Saving...' : 'Save changes'}</button>} />
    {(saved.error || themeSaved.error) && <ErrorPanel error={(saved.error || themeSaved.error) as Error} />}{testConnection.error && <ErrorPanel error={testConnection.error} />}{localError && <div className="inline-field-error" role="alert"><AlertTriangle />{localError}</div>}
    <AnimatePresence>{savedNotice > 0 && <motion.div
      className="settings-success"
      role="status"
      initial={reduceMotion ? { opacity: 1 } : { opacity: 0, y: -8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={reduceMotion
        ? { opacity: 0, transition: { duration: 0.01 } }
        : { opacity: 0, y: -6, scale: 0.98, transition: { duration: 0.55, ease: 'easeInOut' } }}
      transition={reduceMotion ? { duration: 0.01 } : { duration: 0.24, ease: 'easeOut' }}
    ><Check />Settings saved</motion.div>}</AnimatePresence>
    <div className="settings-layout">
      <section className="settings-section branding-settings"><header><div><span className="settings-icon"><ImagePlus /></span><div><h2>Brand identity</h2><p>Shown in the workspace navigation.</p></div></div></header><div className="settings-body branding-grid">
        <div className="brand-preview"><BrandMark logo={form.logo_data_url} name={form.workspace_name || 'Leadroom'} /><span><strong>{form.workspace_name.trim() || 'Leadroom'}</strong><small>{form.workspace_subtitle.trim() || 'Signal desk'}</small></span></div>
        <div className="logo-actions"><label className="button ghost"><Upload />Choose logo<input className="sr-only" type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => readLogo(event.target.files?.[0])} /></label>{form.logo_data_url && <button className="icon-button destructive" onClick={() => setForm({ ...form, logo_data_url: '' })} aria-label="Remove logo" title="Remove logo"><Trash2 /></button>}</div>
        <label>Workspace name<input value={form.workspace_name} maxLength={40} onChange={(event) => setForm({ ...form, workspace_name: event.target.value })} /></label>
        <label>Subtitle<input value={form.workspace_subtitle} maxLength={60} onChange={(event) => setForm({ ...form, workspace_subtitle: event.target.value })} /></label>
      </div></section>
      <ThemeSelector selected={form.theme} onSelect={(theme) => { applyTheme(theme); setForm({ ...form, theme }); themeSaved.mutate(theme) }} />
      <StorageSettingsPanel />
      <section className="settings-section model-settings"><header><div><span className="settings-icon"><Bot /></span><div><h2>Model runtime</h2><p>Default connection for new enrichment runs.</p></div></div><span className={`connection-state ${testConnection.isSuccess ? 'is-online' : ''}`}><i />{testConnection.isSuccess ? 'Connected' : form.model_provider === 'ollama' ? 'Local' : 'API'}</span></header><div className="settings-body">
        <fieldset className="provider-switch"><legend>Provider</legend><label className={form.model_provider === 'ollama' ? 'selected' : ''}><input type="radio" checked={form.model_provider === 'ollama'} onChange={() => setForm({ ...form, model_provider: 'ollama', model_name: 'llama3.2:3b', model_endpoint: 'http://localhost:11434' })} /><Cpu /><span><strong>Ollama</strong><small>Local model</small></span><Check /></label><label className={form.model_provider === 'openai_compatible' ? 'selected' : ''}><input type="radio" checked={form.model_provider === 'openai_compatible'} onChange={() => setForm({ ...form, model_provider: 'openai_compatible', model_name: 'gpt-4o-mini', model_endpoint: 'https://api.openai.com/v1' })} /><Server /><span><strong>API</strong><small>OpenAI-compatible</small></span><Check /></label></fieldset>
        <div className={`model-fields ${form.model_provider === 'ollama' ? 'ollama-fields' : ''}`}>{form.model_provider === 'openai_compatible' && <label>Model name<input value={form.model_name} onChange={(event) => setForm({ ...form, model_name: event.target.value })} placeholder="Model identifier" /></label>}<label className="endpoint-field"><span>Endpoint</span><span className="input-with-icon"><Link2 /><input type="url" value={form.model_endpoint} onChange={(event) => setForm({ ...form, model_endpoint: event.target.value })} /></span></label>{form.model_provider === 'openai_compatible' && <label className="api-key-field"><span>API key {apiConfigured && <em>Configured</em>}</span><span className="input-with-icon"><KeyRound /><input type="password" value={form.api_key ?? ''} onChange={(event) => setForm({ ...form, api_key: event.target.value, clear_api_key: false })} placeholder={apiConfigured ? 'Keep existing key' : 'Enter API key'} /></span></label>}</div>
        <div className="model-actions">{apiConfigured && <button className="button text-danger" onClick={() => setForm({ ...form, api_key: '', clear_api_key: true })}><Trash2 />Remove key</button>}<button className="button ghost" disabled={testConnection.isPending} onClick={() => testConnection.mutate(form)}><Activity />{testConnection.isPending ? 'Testing...' : 'Save & test connection'}</button></div>
        {form.model_provider === 'ollama' && <OllamaModelManager modelName={form.model_name} enabled={settings.data?.model_provider === 'ollama'} onSelect={(model) => { const next = { ...form, model_name: model }; setForm(next); saved.mutate(next) }} />}
      </div></section>
      <EmailAccountsSettings />
      <LocalDataSettings />
      <section className="settings-section filter-settings"><header><div><span className="settings-icon"><ShieldCheck /></span><div><h2>Discovery filters</h2><p>Domains excluded before candidate review.</p></div></div><span className="count-badge">{form.blocked_domains.length}</span></header><div className="settings-body">
        <form className="domain-entry" onSubmit={(event) => { event.preventDefault(); addDomain() }}><label><span>Block another domain</span><span className="input-with-icon"><Search /><input value={domainInput} onChange={(event) => setDomainInput(event.target.value)} placeholder="example.com" /></span></label><button className="button ghost" type="submit"><Plus />Add filter</button></form>
        <div className="domain-tags" aria-label="Blocked domains">{form.blocked_domains.map((domain) => <span className="domain-tag domain-tag-custom" key={domain}><code>{domain}</code><button onClick={() => setForm({ ...form, blocked_domains: form.blocked_domains.filter((item) => item !== domain) })} aria-label={`Remove ${domain}`} title="Remove filter"><X /></button></span>)}</div>
      </div></section>
    </div>
  </section>
}

function PageHeader({ eyebrow, title, subtitle, action }: { eyebrow?: string; title: string; subtitle: string; action?: React.ReactNode }) { return <div className="page-header"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1><p>{subtitle}</p></div>{action}</div> }
function Metric({ label, value, accent = false }: { label: string; value: number; accent?: boolean }) { return <div className={`metric ${accent ? 'metric-accent' : ''}`}><strong>{value}</strong><span>{label}</span></div> }
function SearchProgress({ mode }: { mode: 'initial' | 'continuation' }) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const started = Date.now()
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => window.clearInterval(timer)
  }, [])
  const stages = mode === 'initial'
    ? ['Contacting the search provider', 'Running market queries', 'Filtering directories and duplicates', 'Preparing candidates for review']
    : ['Opening the next result pages', 'Skipping domains already seen', 'Checking market relevance', 'Preparing the next candidate batch']
  const stage = stages[Math.min(stages.length - 1, Math.floor(elapsed / 4))]
  const time = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`
  return <div className="search-progress" role="status" aria-live="polite"><div className="search-progress-head"><span><ScanSearch /><span><strong>Search in progress</strong><small>{stage}</small></span></span><time>{time}</time></div><div className="search-progress-track" role="progressbar" aria-label="Searching for candidates" aria-valuetext={`${stage}, ${time} elapsed`}><span /></div><div className="search-progress-foot"><span>Results are filtered before they enter this run.</span><span>Elapsed</span></div></div>
}
function LoadingRows() { return <div className="loading" aria-label="Loading"><span /><span /><span /></div> }
function EmptyState() { return <div className="empty-state"><Search /><h2>No runs yet</h2><p>Start with a niche and location, then review candidates before enrichment.</p><NavLink className="button primary" to="/new"><Plus />Create first run</NavLink></div> }
function formatDate(value?: string) { return value ? new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—' }

export default Shell
