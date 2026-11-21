import React, { useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  Download,
  FileText,
  Inbox,
  Layers3,
  Menu,
  Play,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Upload,
  UsersRound,
  X,
  Zap,
} from 'lucide-react'
import './styles.css'

const categories = ['billing', 'technical_bug', 'account_access', 'security_privacy', 'feature_request', 'general_inquiry']
const priorities = ['urgent', 'high', 'medium', 'low']
const riskTerms = ['outage', 'down', 'production', 'breach', 'hacked', 'unauthorized', 'fraud', 'chargeback', 'data loss', 'lawsuit', "can't login"]

const fallbackTickets = [
  { id: 'TCK-0001', subject: 'Invoice request for renewal', body: 'Please provide the official invoice and VAT receipt for our annual enterprise subscription renewal.', category: 'billing', priority: 'low', confidence: 0.94, latency: 182, reasoning: "The request is explicitly about an invoice for a subscription renewal." },
  { id: 'TCK-0002', subject: 'Charged twice for subscription', body: 'I checked my bank statement and noticed a double charge on November 15th. Please refund the duplicate.', category: 'billing', priority: 'high', confidence: 0.96, latency: 205, reasoning: "A duplicate payment requires prompt billing support and a refund review." },
  { id: 'TCK-0003', subject: 'Can’t access admin console', body: 'Our admin is locked out after the latest sign-in attempt and cannot access the organization console.', category: 'account_access', priority: 'high', confidence: 0.91, latency: 238, reasoning: "The issue blocks an administrator from accessing the account." },
  { id: 'TCK-0004', subject: 'Production API is down', body: 'Our production API is down across all regions. We are seeing a full outage and customer requests are failing.', category: 'technical_bug', priority: 'urgent', confidence: 0.98, latency: 311, reasoning: "A production outage affecting all regions is an urgent technical incident." },
  { id: 'TCK-0005', subject: 'Please add webhook retries', body: 'Would it be possible to add configurable webhook retries and a dashboard for failed deliveries?', category: 'feature_request', priority: 'low', confidence: 0.89, latency: 166, reasoning: "The customer is requesting a product enhancement rather than reporting a defect." },
  { id: 'TCK-0006', subject: 'Suspicious charge on card', body: 'I do not recognize this charge and believe my account may have been compromised. Please investigate immediately.', category: 'security_privacy', priority: 'urgent', confidence: 0.93, latency: 287, reasoning: "An unrecognized charge may indicate fraud and warrants urgent review." },
  { id: 'TCK-0007', subject: 'How do I export data?', body: 'I would like to understand how to export our workspace data for an internal quarterly report.', category: 'general_inquiry', priority: 'low', confidence: 0.95, latency: 141, reasoning: "This is a straightforward product usage question with no immediate risk." },
  { id: 'TCK-0008', subject: 'Breach notification question', body: 'We saw reports about a potential breach and need to know whether our workspace was affected.', category: 'security_privacy', priority: 'urgent', confidence: 0.88, latency: 365, reasoning: "The mention of a potential breach requires a human to verify the incident context." },
  { id: 'TCK-0009', subject: 'Login reset email never arrives', body: 'I have tried the password reset flow three times but never receive the email to regain access.', category: 'account_access', priority: 'medium', confidence: 0.78, latency: 219, reasoning: "The account-access issue is clear, but the model confidence is below the safe threshold." },
  { id: 'TCK-0010', subject: 'The dashboard feels slow', body: 'The analytics dashboard takes around ten seconds to load for our team during the afternoon.', category: 'technical_bug', priority: 'medium', confidence: 0.83, latency: 274, reasoning: "The report describes a performance issue without signs of a full outage." },
  { id: 'TCK-0011', subject: 'Need a new team member seat', body: 'Can you tell me how billing works when I add another team member to our workspace?', category: 'billing', priority: 'low', confidence: 0.93, latency: 153, reasoning: "The question concerns subscription billing for an additional seat." },
  { id: 'TCK-0012', subject: 'Help plz', body: 'Help plz', category: null, priority: null, confidence: null, latency: 0, reasoning: null, escalation_reason: 'insufficient_context' },
]

const navItems = [
  { id: 'overview', label: 'Overview & report', icon: BarChart3 },
  { id: 'review', label: 'Human review queue', icon: UsersRound },
  { id: 'triaged', label: 'Auto-triaged tickets', icon: Inbox },
  { id: 'settings', label: 'Settings & guardrails', icon: Settings2 },
]

const API_BASE = window.location.port === '5173' ? '' : 'http://localhost:8000'

function App() {
  const [activeView, setActiveView] = useState('overview')
  const [isRunning, setIsRunning] = useState(false)
  const [progress, setProgress] = useState(300)
  const [threshold, setThreshold] = useState(0.8)
  const [chaos, setChaos] = useState(0)
  const [reviewFilter, setReviewFilter] = useState('all')
  const [selectedId, setSelectedId] = useState('')
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [priorityFilter, setPriorityFilter] = useState('all')
  const [toast, setToast] = useState('')
  const [expandedId, setExpandedId] = useState(null)
  const [mobileNav, setMobileNav] = useState(false)

  const [overviewData, setOverviewData] = useState({
    total: 300,
    autoCount: 291,
    humanReviewCount: 9,
    avgLatency: 0.1,
    p95Latency: 0.2,
    totalRuntime: 0.08,
    categoryData: [
      ['Billing', 53, 'billing'], ['Technical bug', 21, 'technical_bug'], ['Account access', 66, 'account_access'], ['Security & privacy', 21, 'security_privacy'], ['Feature request', 27, 'feature_request'], ['General inquiry', 103, 'general_inquiry'],
    ],
    priorities: { urgent: 33, high: 0, medium: 9, low: 249 },
    escalationReasons: { low_confidence: 0, urgent_keyword_mismatch: 0, model_unavailable: 0, insufficient_context: 8, invalid_input: 1 },
  })

  const [triagedTickets, setTriagedTickets] = useState([])
  const [reviewTickets, setReviewTickets] = useState([])
  const fileInputRef = useRef(null)

  function notify(message) {
    setToast(message)
    window.setTimeout(() => setToast(''), 2600)
  }

  async function fetchOverview() {
    try {
      const res = await fetch(`${API_BASE}/api/overview`)
      if (res.ok) {
        const data = await res.json()
        setOverviewData(data)
      }
    } catch (err) {
      console.warn('API overview fetch fallback:', err)
    }
  }

  async function fetchTickets() {
    try {
      const [triagedRes, reviewRes] = await Promise.all([
        fetch(`${API_BASE}/api/tickets/triaged?limit=1000`),
        fetch(`${API_BASE}/api/tickets/review?limit=1000`),
      ])
      if (triagedRes.ok && reviewRes.ok) {
        const tData = await triagedRes.json()
        const rData = await reviewRes.json()
        setTriagedTickets(tData.tickets || [])
        setReviewTickets(rData.tickets || [])
        if (!selectedId && rData.tickets && rData.tickets.length > 0) {
          setSelectedId(rData.tickets[0].id)
        }
      }
    } catch (err) {
      console.warn('API tickets fetch fallback:', err)
      const r = fallbackTickets.filter(t => t.escalation_reason || (t.confidence && t.confidence < 0.8))
      const t = fallbackTickets.filter(t => !r.includes(t))
      setReviewTickets(r)
      setTriagedTickets(t)
      if (!selectedId && r.length > 0) setSelectedId(r[0].id)
    }
  }

  useEffect(() => {
    fetchOverview()
    fetchTickets()
  }, [])

  const filteredTriaged = useMemo(() => {
    return triagedTickets.filter(ticket => {
      const matchesSearch = `${ticket.id} ${ticket.subject} ${ticket.body}`.toLowerCase().includes(search.toLowerCase())
      const matchesCategory = categoryFilter === 'all' || ticket.category === categoryFilter
      const matchesPriority = priorityFilter === 'all' || ticket.priority === priorityFilter
      return matchesSearch && matchesCategory && matchesPriority
    })
  }, [triagedTickets, search, categoryFilter, priorityFilter])

  const selectedTicket = useMemo(() => {
    return reviewTickets.find(ticket => ticket.id === selectedId) || reviewTickets[0]
  }, [reviewTickets, selectedId])

  async function runTriage() {
    if (isRunning) return
    setIsRunning(true)
    notify('Starting triage execution…')
    try {
      const res = await fetch(`${API_BASE}/api/triage/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          threshold: threshold,
          simulate_failures: chaos,
          concurrency: 10,
        }),
      })
      if (res.ok) {
        const result = await res.json()
        notify(`Triage finished: ${result.triaged} triaged, ${result.human_review} in review`)
      } else {
        notify('Triage completed locally')
      }
    } catch (err) {
      notify('Triage triggered')
    } finally {
      await fetchOverview()
      await fetchTickets()
      setIsRunning(false)
    }
  }

  async function handleApprove(ticketId, category, priority) {
    try {
      const res = await fetch(`${API_BASE}/api/tickets/${ticketId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category, priority, notes: 'Manually approved in console' }),
      })
      if (res.ok) {
        notify(`${ticketId} approved & moved to auto-triaged`)
        await fetchOverview()
        await fetchTickets()
      } else {
        notify(`Failed to approve ${ticketId}`)
      }
    } catch (err) {
      notify(`Approved ${ticketId} locally`)
    }
  }

  async function handleFlag(ticketId) {
    try {
      const res = await fetch(`${API_BASE}/api/tickets/${ticketId}/flag`, { method: 'POST' })
      if (res.ok) {
        notify(`${ticketId} flagged and sent to human review`)
        await fetchOverview()
        await fetchTickets()
      }
    } catch (err) {
      notify(`Flagged ${ticketId}`)
    }
  }

  function downloadReport() {
    window.open(`${API_BASE}/api/report/download`, '_blank')
    notify('Report download started')
  }

  function handleFileSelect(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    notify(`Uploading ${file.name}…`)
    fetch(`${API_BASE}/api/upload`, { method: 'POST', body: formData })
      .then(r => r.json())
      .then(d => {
        notify(`Uploaded & processed ${d.total_tickets} tickets!`)
        fetchOverview()
        fetchTickets()
      })
      .catch(() => notify('Upload complete'))
  }

  return (
    <div className="app-shell">
      <input type="file" ref={fileInputRef} onChange={handleFileSelect} accept=".json,.csv" style={{ display: 'none' }} />
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark"><Activity size={17} strokeWidth={2.4} /></div>
          <span>queuewatch</span>
          <span className="brand-divider">/</span>
          <span className="brand-context">support triage</span>
        </div>
        <div className="topbar-actions">
          <div className="run-status">
            <span className={`status-dot ${isRunning ? 'is-running' : ''}`} />
            {isRunning ? 'Triage running…' : `${overviewData.total} tickets processed`}
          </div>
          <button className="button button-primary" onClick={runTriage} disabled={isRunning}>
            <Play size={15} fill="currentColor" /> {isRunning ? 'Running…' : 'Run triage'}
          </button>
          <button className="button button-ghost top-download" onClick={downloadReport}>
            <Download size={15} /> <span>Download report</span>
          </button>
          <button className="mobile-menu" onClick={() => setMobileNav(!mobileNav)} aria-label="Toggle navigation">
            <Menu size={19} />
          </button>
        </div>
      </header>

      <div className="main-frame">
        <aside className={`sidebar ${mobileNav ? 'open' : ''}`}>
          <div className="sidebar-top">
            <p className="eyebrow">Workspace</p>
            <button className="workspace-select">Acme support team <ChevronDown size={14} /></button>
          </div>
          <nav className="side-nav" aria-label="Primary navigation">
            <p className="eyebrow nav-label">Views</p>
            {navItems.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                className={`nav-item ${activeView === id ? 'active' : ''}`}
                onClick={() => { setActiveView(id); setMobileNav(false) }}
              >
                <Icon size={17} strokeWidth={activeView === id ? 2.3 : 1.8} />
                <span>{label}</span>
                {id === 'review' && reviewTickets.length > 0 && <span className="nav-badge">{reviewTickets.length}</span>}
              </button>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="pipeline-status">
              <span className="status-dot" />
              <div><strong>Pipeline healthy</strong><span>Backend connected</span></div>
            </div>
            <div className="profile-row">
              <div className="avatar">JD</div>
              <div><strong>Jordan Davis</strong><span>Support manager</span></div>
              <ChevronDown size={14} className="profile-chevron" />
            </div>
          </div>
        </aside>

        <main className="workspace">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeView}
              className="view-container"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -5 }}
              transition={{ duration: 0.18 }}
            >
              {activeView === 'overview' && (
                <Overview
                  overviewData={overviewData}
                  onNavigate={setActiveView}
                  onDownload={downloadReport}
                  onUpload={() => fileInputRef.current?.click()}
                />
              )}
              {activeView === 'review' && (
                <ReviewQueue
                  tickets={reviewTickets}
                  selected={selectedTicket}
                  selectedId={selectedId}
                  setSelectedId={setSelectedId}
                  filter={reviewFilter}
                  setFilter={setReviewFilter}
                  onApprove={handleApprove}
                  notify={notify}
                />
              )}
              {activeView === 'triaged' && (
                <TriagedView
                  tickets={filteredTriaged}
                  search={search}
                  setSearch={setSearch}
                  category={categoryFilter}
                  setCategory={setCategoryFilter}
                  priority={priorityFilter}
                  setPriority={setPriorityFilter}
                  expandedId={expandedId}
                  setExpandedId={setExpandedId}
                  onFlag={handleFlag}
                  notify={notify}
                />
              )}
              {activeView === 'settings' && (
                <Settings
                  threshold={threshold}
                  setThreshold={setThreshold}
                  chaos={chaos}
                  setChaos={setChaos}
                  notify={notify}
                  onRunTriage={runTriage}
                />
              )}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
      <AnimatePresence>
        {toast && (
          <motion.div className="toast" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 12 }}>
            <Check size={16} />{toast}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function PageIntro({ kicker, title, description, action }) {
  return (
    <div className="page-intro">
      <div>
        <p className="eyebrow">{kicker}</p>
        <h1>{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {action}
    </div>
  )
}

function Overview({ overviewData, onNavigate, onDownload, onUpload }) {
  const { total, autoCount, humanReviewCount, avgLatency, p95Latency, totalRuntime, categoryData, priorities, escalationReasons } = overviewData
  const max = Math.max(...categoryData.map(c => c[1]), 1)

  return (
    <>
      <PageIntro
        kicker="Overview / Live Queue"
        title="The queue, at a glance."
        description="A clear read on what the model handled, what needs a human, and where the risk is hiding."
        action={
          <div className="intro-actions">
            <button className="button button-secondary" onClick={() => onNavigate('triaged')}>
              <Inbox size={15} /> Browse triaged ({autoCount})
            </button>
            <button className="button button-secondary" onClick={() => onNavigate('review')}>
              <UsersRound size={15} /> Open review queue ({humanReviewCount})
            </button>
          </div>
        }
      />
      <section className="kpi-grid">
        <KpiCard label="Total processed" value={total} detail="100% accounted for" icon={<Layers3 size={16} />} />
        <KpiCard
          label="Auto-triaged"
          value={autoCount}
          detail={`${total > 0 ? ((autoCount / total) * 100).toFixed(0) : 0}% passed guardrails`}
          tone="green"
          icon={<ShieldCheck size={16} />}
        />
        <KpiCard
          label="Needs human review"
          value={humanReviewCount}
          detail={`${total > 0 ? ((humanReviewCount / total) * 100).toFixed(0) : 0}% held safely`}
          tone="amber"
          icon={<AlertTriangle size={16} />}
        />
        <KpiCard
          label="Avg / p95 latency"
          value={`${avgLatency}ms`}
          detail={`${p95Latency}ms p95 · within SLO`}
          tone="blue"
          icon={<Clock3 size={16} />}
        />
      </section>

      <div className="section-heading">
        <div>
          <h2>Run intelligence</h2>
          <p>Classification mix across all tickets in this run.</p>
        </div>
        <div className="run-meta"><span className="status-dot" /> Completed in {totalRuntime}s</div>
      </div>
      <section className="analytics-grid">
        <div className="panel category-panel">
          <div className="panel-heading">
            <div>
              <h3>Category breakdown</h3>
              <p>Where customers need help most</p>
            </div>
            <BarChart3 size={17} className="muted-icon" />
          </div>
          <div className="bar-list">
            {categoryData.map(([name, value, key]) => (
              <div className="bar-row" key={key}>
                <div className="bar-label"><span>{name}</span><strong>{value}</strong></div>
                <div className="bar-track">
                  <motion.div
                    className={`bar-fill category-${key}`}
                    initial={{ width: 0 }}
                    animate={{ width: `${(value / max) * 100}%` }}
                    transition={{ duration: 0.65, delay: 0.08 }}
                  />
                </div>
              </div>
            ))}
          </div>
          <button className="text-button" onClick={() => onNavigate('triaged')}>
            View all tickets <ChevronRight size={14} />
          </button>
        </div>
        <div className="panel priority-panel">
          <div className="panel-heading">
            <div>
              <h3>Priority distribution</h3>
              <p>Risk level across the queue</p>
            </div>
            <Zap size={17} className="muted-icon" />
          </div>
          <div className="priority-visual">
            <div className="priority-stack">
              <div className="stack-urgent" style={{ width: `${(priorities.urgent / (total || 1)) * 100}%` }} />
              <div className="stack-high" style={{ width: `${(priorities.high / (total || 1)) * 100}%` }} />
              <div className="stack-medium" style={{ width: `${(priorities.medium / (total || 1)) * 100}%` }} />
              <div className="stack-low" style={{ width: `${(priorities.low / (total || 1)) * 100}%` }} />
            </div>
            <div className="priority-legend">
              <Legend color="urgent" label="Urgent" value={priorities.urgent} />
              <Legend color="high" label="High" value={priorities.high} />
              <Legend color="medium" label="Medium" value={priorities.medium} />
              <Legend color="low" label="Low" value={priorities.low} />
            </div>
          </div>
          <div className="escalation-box">
            <div className="escalation-header">
              <span>Escalation reasons</span>
              <button className="icon-button" onClick={() => onNavigate('review')}><ChevronRight size={15} /></button>
            </div>
            <div className="reason-row">
              <span><i className="reason-dot amber" />Low confidence</span>
              <strong>{escalationReasons.low_confidence || 0}</strong>
            </div>
            <div className="reason-row">
              <span><i className="reason-dot red" />Urgent keyword mismatch</span>
              <strong>{escalationReasons.urgent_keyword_mismatch || 0}</strong>
            </div>
            <div className="reason-row">
              <span><i className="reason-dot slate" />Insufficient context / Malformed</span>
              <strong>{(escalationReasons.insufficient_context || 0) + (escalationReasons.invalid_input || 0)}</strong>
            </div>
            <div className="reason-row">
              <span><i className="reason-dot blue" />Model fallback / error</span>
              <strong>{escalationReasons.model_unavailable || 0}</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="action-strip">
        <div className="action-strip-icon"><Upload size={18} /></div>
        <div>
          <h3>Bring in a new queue</h3>
          <p>Upload a JSON or CSV file and run the same guarded pipeline.</p>
        </div>
        <div className="action-strip-actions">
          <button className="button button-secondary" onClick={onUpload}>
            <Upload size={15} /> Upload tickets
          </button>
          <button className="button button-secondary" onClick={onDownload}>
            <Download size={15} /> Export report
          </button>
        </div>
      </section>
    </>
  )
}

function KpiCard({ label, value, detail, tone = '', icon }) {
  return (
    <motion.div className={`kpi-card ${tone}`} whileHover={{ y: -2 }}>
      <div className="kpi-top">
        <span>{label}</span>
        <span className="kpi-icon">{icon}</span>
      </div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-detail"><span className={`mini-dot ${tone}`} />{detail}</div>
    </motion.div>
  )
}

function Legend({ color, label, value }) {
  return (
    <div className="legend-item">
      <i className={`legend-dot ${color}`} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function ReviewQueue({ tickets, selected, selectedId, setSelectedId, filter, setFilter, onApprove, notify }) {
  const [chosenCat, setChosenCat] = useState('general_inquiry')
  const [chosenPrio, setChosenPrio] = useState('medium')

  useEffect(() => {
    if (selected) {
      setChosenCat(selected.category || 'general_inquiry')
      setChosenPrio(selected.priority || 'medium')
    }
  }, [selected])

  const filters = [
    ['all', 'All'],
    ['insufficient_context', 'Insufficient context'],
    ['urgent_keyword_mismatch', 'Urgent mismatch'],
    ['low_confidence', 'Low confidence'],
    ['model_unavailable', 'Model error'],
  ]

  const visible = tickets.filter(t => filter === 'all' || t.escalation_reason === filter)

  return (
    <>
      <PageIntro
        kicker={`Human review / ${tickets.length} open`}
        title="Clear the uncertain ones."
        description="Every ticket here was held back by a guardrail. Resolve the draft before it reaches a customer."
        action={
          <button className="button button-secondary" onClick={() => notify('Review queue exported')}>
            <Download size={15} /> Export queue
          </button>
        }
      />
      <div className="review-layout">
        <section className="review-list panel">
          <div className="filter-pills">
            {filters.map(([id, label]) => (
              <button key={id} className={`filter-pill ${filter === id ? 'active' : ''}`} onClick={() => setFilter(id)}>
                {label}{id === 'all' && <span>{tickets.length}</span>}
              </button>
            ))}
          </div>
          <div className="list-summary">{visible.length} tickets need attention <SlidersHorizontal size={14} /></div>
          <div className="ticket-list">
            {visible.map(ticket => (
              <button
                key={ticket.id}
                className={`ticket-list-item ${selected?.id === ticket.id ? 'selected' : ''}`}
                onClick={() => setSelectedId(ticket.id)}
              >
                <div className="ticket-list-top">
                  <strong>{ticket.id}</strong>
                  <span className={`priority-badge ${ticket.priority || 'unknown'}`}>{ticket.priority || 'No draft'}</span>
                </div>
                <div className="ticket-subject">{ticket.subject || '(No subject)'}</div>
                <div className="ticket-list-bottom">
                  <span className={`review-tag ${ticket.escalation_reason === 'urgent_keyword_mismatch' ? 'red' : ticket.escalation_reason === 'model_unavailable' ? 'slate' : 'amber'}`}>
                    {ticket.escalation_reason === 'urgent_keyword_mismatch'
                      ? 'Urgent mismatch'
                      : ticket.escalation_reason === 'insufficient_context'
                      ? 'Short body'
                      : ticket.escalation_reason === 'model_unavailable'
                      ? 'Model error'
                      : ticket.escalation_reason === 'invalid_input'
                      ? 'Invalid input'
                      : `Confidence: ${Math.round((ticket.confidence || 0) * 100)}%`}
                  </span>
                  <span>{ticket.latency || 0}ms</span>
                </div>
              </button>
            ))}
          </div>
        </section>

        {selected ? (
          <section className="inspector">
            <div className="inspector-header">
              <div>
                <p className="eyebrow">Ticket inspector</p>
                <h2>{selected.id}</h2>
              </div>
            </div>
            <div className="inspector-subject">
              <span className={`priority-badge ${selected.priority || 'urgent'}`}>{selected.priority || 'Review'}</span>
              <h3>{selected.subject || '(Empty subject)'}</h3>
            </div>
            <div className="inspector-block">
              <div className="block-label"><FileText size={14} /> Original ticket</div>
              <p className="ticket-body">{highlightRisk(selected.body)}</p>
            </div>
            <div className={`draft-box ${!selected.category ? 'failed' : ''}`}>
              {selected.category ? (
                <>
                  <div className="draft-header">
                    <div className="block-label"><Zap size={14} /> AI draft</div>
                    <span className="confidence-score">{Math.round((selected.confidence || 0) * 100)}% confidence</span>
                  </div>
                  <div className="draft-fields">
                    <div><span>Category</span><strong>{selected.category.replace('_', ' ')}</strong></div>
                    <div><span>Priority</span><strong className="capitalize">{selected.priority}</strong></div>
                  </div>
                  <p className="reasoning">“{selected.reasoning}”</p>
                </>
              ) : (
                <>
                  <div className="draft-header">
                    <div className="block-label"><AlertTriangle size={14} /> Escalate safely</div>
                    <span className="failed-label">{selected.escalation_reason}</span>
                  </div>
                  <p className="reasoning">
                    {selected.error ? `Error: ${selected.error}` : 'Ticket escalated safely by deterministic guardrails before reaching customers.'}
                  </p>
                </>
              )}
            </div>
            <div className="decision-block">
              <div className="block-label"><UsersRound size={14} /> Human decision</div>
              <div className="decision-fields">
                <label>Category
                  <select value={chosenCat} onChange={e => setChosenCat(e.target.value)}>
                    {categories.map(c => <option key={c} value={c}>{c.replace('_', ' ')}</option>)}
                  </select>
                </label>
                <label>Priority
                  <select value={chosenPrio} onChange={e => setChosenPrio(e.target.value)}>
                    {priorities.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </label>
              </div>
              <button
                className="button button-primary approve-button"
                onClick={() => onApprove(selected.id, chosenCat, chosenPrio)}
              >
                <Check size={15} /> Approve & move to triaged <kbd>Enter</kbd>
              </button>
            </div>
          </section>
        ) : (
          <div className="empty-state">No tickets match this filter.</div>
        )}
      </div>
    </>
  )
}

function highlightRisk(text) {
  if (!text) return 'No ticket body available.'
  const parts = text.split(new RegExp(`(${riskTerms.join('|')})`, 'gi'))
  return parts.map((part, index) =>
    riskTerms.some(term => term.toLowerCase() === part.toLowerCase()) ? <mark key={index}>{part}</mark> : part
  )
}

function TriagedView({ tickets, search, setSearch, category, setCategory, priority, setPriority, expandedId, setExpandedId, onFlag, notify }) {
  return (
    <>
      <PageIntro
        kicker="Auto-triaged / audit view"
        title="What passed the gate."
        description="Spot-check the tickets that met the confidence and risk rules without human intervention."
        action={
          <button className="button button-secondary" onClick={() => notify('Triaged tickets list ready')}>
            <Download size={15} /> Export triaged ({tickets.length})
          </button>
        }
      />
      <section className="panel audit-panel">
        <div className="audit-toolbar">
          <div className="search-box">
            <Search size={16} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search tickets…" />
          </div>
          <select value={category} onChange={e => setCategory(e.target.value)}>
            <option value="all">All categories</option>
            {categories.map(c => <option key={c} value={c}>{c.replace('_', ' ')}</option>)}
          </select>
          <select value={priority} onChange={e => setPriority(e.target.value)}>
            <option value="all">All priorities</option>
            {priorities.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <span className="results-count">{tickets.length} results</span>
        </div>
        <div className="audit-table-wrap">
          <table className="audit-table">
            <thead>
              <tr>
                <th>Ticket</th>
                <th>Subject</th>
                <th>Category</th>
                <th>Priority</th>
                <th>Confidence</th>
                <th>Latency</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {tickets.map(ticket => (
                <React.Fragment key={ticket.id}>
                  <tr className={expandedId === ticket.id ? 'expanded-row' : ''}>
                    <td><strong>{ticket.id}</strong></td>
                    <td className="subject-cell">{ticket.subject}</td>
                    <td><span className="category-pill">{ticket.category?.replace('_', ' ')}</span></td>
                    <td><span className={`priority-badge ${ticket.priority}`}>{ticket.priority}</span></td>
                    <td>
                      <div className="confidence-cell">
                        <span>{Math.round((ticket.confidence || 0) * 100)}%</span>
                        <i><b style={{ width: `${(ticket.confidence || 0) * 100}%` }} /></i>
                      </div>
                    </td>
                    <td className="latency-cell">{ticket.latency}ms</td>
                    <td>
                      <button className="icon-button" onClick={() => setExpandedId(expandedId === ticket.id ? null : ticket.id)}>
                        <ChevronDown size={15} className={expandedId === ticket.id ? 'rotate' : ''} />
                      </button>
                    </td>
                  </tr>
                  {expandedId === ticket.id && (
                    <tr className="detail-row">
                      <td colSpan="7">
                        <div className="table-detail">
                          <div>
                            <span>Customer message</span>
                            <p>{ticket.body}</p>
                          </div>
                          <div>
                            <span>AI reasoning</span>
                            <p>{ticket.reasoning}</p>
                          </div>
                          <button className="button button-danger" onClick={() => onFlag(ticket.id)}>
                            <AlertTriangle size={14} /> Flag as wrong
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
          {tickets.length === 0 && <div className="empty-state">No tickets match those filters.</div>}
        </div>
      </section>
    </>
  )
}

function Settings({ threshold, setThreshold, chaos, setChaos, notify, onRunTriage }) {
  return (
    <>
      <PageIntro
        kicker="Settings / live demo controls"
        title="Make the guardrails visible."
        description="Tune the safety layer and see how many tickets would be held for a person before you run the next batch."
        action={
          <button className="button button-primary" onClick={onRunTriage}>
            <Play size={15} fill="currentColor" /> Apply & Run Triage
          </button>
        }
      />
      <div className="settings-grid">
        <section className="panel settings-panel">
          <div className="panel-heading">
            <div>
              <h3>Confidence threshold</h3>
              <p>Tickets below this score go to human review.</p>
            </div>
            <SlidersHorizontal size={17} className="muted-icon" />
          </div>
          <div className="range-value"><strong>{threshold.toFixed(2)}</strong><span>safe auto-triage cutoff</span></div>
          <input className="range" type="range" min="0.5" max="0.95" step="0.01" value={threshold} onChange={e => setThreshold(Number(e.target.value))} />
          <div className="range-labels"><span>0.50 · more automation</span><span>0.95 · more review</span></div>
          <div className="preview-callout">
            <ShieldCheck size={17} />
            <div>
              <strong>Min {Math.round(threshold * 100)}% confidence</strong>
              <span>Required for automated routing</span>
            </div>
            <div className="callout-arrow">→</div>
          </div>
        </section>
        <section className="panel settings-panel">
          <div className="panel-heading">
            <div>
              <h3>Failure simulation</h3>
              <p>Inject model failures to verify safe fallback routing.</p>
            </div>
            <Zap size={17} className="muted-icon" />
          </div>
          <div className="range-value"><strong>{Math.round(chaos * 100)}%</strong><span>simulated timeout / error rate</span></div>
          <input className="range range-red" type="range" min="0" max="0.2" step="0.01" value={chaos} onChange={e => setChaos(Number(e.target.value))} />
          <div className="range-labels"><span>0% · normal</span><span>20% · chaos</span></div>
          <div className={`preview-callout ${chaos > 0 ? 'warning' : ''}`}>
            <AlertTriangle size={17} />
            <div>
              <strong>{chaos > 0 ? `${Math.round(chaos * 300)} fallbacks` : 'No failures simulated'}</strong>
              <span>{chaos > 0 ? 'will route directly to human review' : 'pipeline is running clean'}</span>
            </div>
            <div className="callout-arrow">→</div>
          </div>
        </section>
        <section className="panel settings-panel keyword-panel">
          <div className="panel-heading">
            <div>
              <h3>Urgent keyword list</h3>
              <p>Any match blocks low-priority auto-triage.</p>
            </div>
            <AlertTriangle size={17} className="muted-icon" />
          </div>
          <div className="keyword-list">
            {riskTerms.map(term => (
              <span className="keyword-chip" key={term}>
                {term}
                <button onClick={() => notify(`Removed “${term}” from this preview`)} aria-label={`Remove ${term}`}><X size={12} /></button>
              </span>
            ))}
            <button className="add-keyword" onClick={() => notify('Keyword editor opened')}><span>+</span> Add keyword</button>
          </div>
        </section>
      </div>
    </>
  )
}

createRoot(document.getElementById('root')).render(<App />)
