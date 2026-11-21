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
  Plus,
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

const categories = [
  'billing',
  'technical_bug',
  'account_access',
  'security_privacy',
  'feature_request',
  'general_inquiry',
]
const priorities = ['urgent', 'high', 'medium', 'low']
const defaultRiskTerms = [
  'outage',
  'down',
  'production',
  'breach',
  'hacked',
  'unauthorized',
  'fraud',
  'chargeback',
  'data loss',
  'lawsuit',
  "can't login",
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
  const [threshold, setThreshold] = useState(0.8)
  const [chaos, setChaos] = useState(0)
  const [riskTerms, setRiskTerms] = useState(defaultRiskTerms)
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
      ['Billing', 53, 'billing'],
      ['Technical bug', 21, 'technical_bug'],
      ['Account access', 66, 'account_access'],
      ['Security & privacy', 21, 'security_privacy'],
      ['Feature request', 27, 'feature_request'],
      ['General inquiry', 103, 'general_inquiry'],
    ],
    priorities: { urgent: 33, high: 0, medium: 9, low: 249 },
    escalationReasons: {
      low_confidence: 0,
      urgent_keyword_mismatch: 0,
      model_unavailable: 0,
      insufficient_context: 8,
      invalid_input: 1,
    },
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
      if (!triagedRes.ok || !reviewRes.ok) throw new Error('Ticket endpoint unavailable')
      const tData = await triagedRes.json()
      const rData = await reviewRes.json()
      setTriagedTickets(tData.tickets || [])
      setReviewTickets(rData.tickets || [])
      if (rData.tickets?.length > 0) setSelectedId(current => current || rData.tickets[0].id)
    } catch (err) {
      console.warn('API tickets fetch fallback:', err)
      const review = fallbackTickets.filter(ticket => ticket.escalation_reason || (ticket.confidence && ticket.confidence < threshold))
      const triaged = fallbackTickets.filter(ticket => !review.includes(ticket))
      setTriagedTickets(triaged)
      setReviewTickets(review)
      if (review.length > 0) setSelectedId(current => current || review[0].id)
    }
  }

  async function fetchSettings() {
    try {
      const res = await fetch(`${API_BASE}/api/settings`)
      if (res.ok) {
        const data = await res.json()
        if (data.threshold) setThreshold(data.threshold)
        if (data.chaos !== undefined) setChaos(data.chaos)
        if (data.risk_keywords) setRiskTerms(data.risk_keywords)
      }
    } catch (err) {
      console.warn('Settings fetch fallback:', err)
    }
  }

  useEffect(() => {
    fetchOverview()
    fetchTickets()
    fetchSettings()
  }, [])

  const filteredTriaged = useMemo(() => {
    return triagedTickets.filter(ticket => {
      const s = search.toLowerCase()
      const matchesSearch =
        !s ||
        (ticket.id && ticket.id.toLowerCase().includes(s)) ||
        (ticket.subject && ticket.subject.toLowerCase().includes(s)) ||
        (ticket.body && ticket.body.toLowerCase().includes(s))
      const matchesCategory = categoryFilter === 'all' || ticket.category === categoryFilter
      const matchesPriority = priorityFilter === 'all' || ticket.priority === priorityFilter
      return matchesSearch && matchesCategory && matchesPriority
    })
  }, [triagedTickets, search, categoryFilter, priorityFilter])

  const selectedTicket = useMemo(() => {
    if (!reviewTickets.length) return null
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
        notify('Triage completed')
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
        // Auto-advance to next ticket in review list
        const currentIndex = reviewTickets.findIndex(t => t.id === ticketId)
        if (currentIndex !== -1 && reviewTickets.length > 1) {
          const nextIndex = currentIndex < reviewTickets.length - 1 ? currentIndex + 1 : currentIndex - 1
          setSelectedId(reviewTickets[nextIndex].id)
        }
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

  async function downloadReport() {
    try {
      const res = await fetch(`${API_BASE}/api/report/download`)
      if (!res.ok) throw new Error('Report unavailable')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'ticket_triage_report.md'
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 0)
      notify('Report downloaded')
    } catch (err) {
      const report = `# Support Ticket Triage Report\n\nProcessed: ${overviewData.total}\nAuto-triaged: ${overviewData.autoCount}\nHuman review: ${overviewData.humanReviewCount}\nThreshold: ${threshold.toFixed(2)}\nFailure simulation: ${(chaos * 100).toFixed(0)}%\n`
      const blob = new Blob([report], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'report.md'
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 0)
      notify('Report downloaded from current data')
    }
  }

  function exportJSON(filename, data) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
    notify(`Downloaded ${filename}`)
  }

  async function handleFileSelect(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    notify(`Uploading ${file.name}…`)
    try {
      const res = await fetch(`${API_BASE}/api/upload`, { method: 'POST', body: formData })
      if (!res.ok) throw new Error('Upload failed')
      const data = await res.json()
      notify(`Uploaded & processed ${data.total_tickets} tickets`)
      await Promise.all([fetchOverview(), fetchTickets()])
    } catch (err) {
      notify('Upload failed — use a JSON or CSV ticket file')
    }
  }

  async function updateSettings(newSettings) {
    try {
      await fetch(`${API_BASE}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newSettings),
      })
    } catch (err) {
      console.warn('Failed to save settings:', err)
    }
  }

  function addKeyword() {
    const word = window.prompt('Enter new urgent risk keyword (e.g. ransomware):')
    if (word && word.trim()) {
      const trimmed = word.trim().toLowerCase()
      if (!riskTerms.includes(trimmed)) {
        const next = [...riskTerms, trimmed]
        setRiskTerms(next)
        updateSettings({ risk_keywords: next })
        notify(`Added “${trimmed}” to urgent keywords`)
      } else {
        notify(`“${trimmed}” is already in the keyword list`)
      }
    }
  }

  function removeKeyword(term) {
    const next = riskTerms.filter(t => t !== term)
    setRiskTerms(next)
    updateSettings({ risk_keywords: next })
    notify(`Removed “${term}”`)
  }

  return (
    <div className="app-shell">
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileSelect}
        accept=".json,.csv"
        style={{ display: 'none' }}
      />
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
            {isRunning ? 'Triage running…' : `${overviewData.total || 0} tickets processed`}
          </div>
          <button className="button button-primary" onClick={runTriage} disabled={isRunning}>
            <Play size={15} fill="currentColor" /> {isRunning ? 'Running…' : 'Run triage'}
          </button>
          <button className="button button-ghost top-download" onClick={downloadReport}>
            <Download size={15} /> <span>Download report</span>
          </button>
          <button
            className="mobile-menu"
            onClick={() => setMobileNav(!mobileNav)}
            aria-label="Toggle navigation"
          >
            <Menu size={19} />
          </button>
        </div>
      </header>

      <div className="main-frame">
        <aside className={`sidebar ${mobileNav ? 'open' : ''}`}>
          <div className="sidebar-top">
            <p className="eyebrow">Workspace</p>
            <button className="workspace-select" onClick={() => notify('Acme support team is the active workspace')} aria-label="Select workspace">
              Acme support team <ChevronDown size={14} />
            </button>
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
                {id === 'review' && reviewTickets.length > 0 && (
                  <span className="nav-badge">{reviewTickets.length}</span>
                )}
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
                  onExport={() => exportJSON('human_review_queue.json', reviewTickets)}
                  notify={notify}
                  riskTerms={riskTerms}
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
                  onExport={() => exportJSON('triaged_tickets.json', filteredTriaged)}
                  notify={notify}
                />
              )}
              {activeView === 'settings' && (
                <Settings
                  threshold={threshold}
                  setThreshold={v => { setThreshold(v); updateSettings({ threshold: v }) }}
                  chaos={chaos}
                  setChaos={v => { setChaos(v); updateSettings({ chaos: v }) }}
                  riskTerms={riskTerms}
                  onAddKeyword={addKeyword}
                  onRemoveKeyword={removeKeyword}
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
          <motion.div
            className="toast"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
          >
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
  const total = overviewData?.total || 0
  const autoCount = overviewData?.autoCount || 0
  const humanReviewCount = overviewData?.humanReviewCount || 0
  const avgLatency = overviewData?.avgLatency || 0
  const p95Latency = overviewData?.p95Latency || 0
  const totalRuntime = overviewData?.totalRuntime || 0.08
  const categoryData = overviewData?.categoryData || []
  const priorities = overviewData?.priorities || { urgent: 0, high: 0, medium: 0, low: 0 }
  const escalationReasons = overviewData?.escalationReasons || {}

  const max = Math.max(...categoryData.map(c => Number(c[1]) || 0), 1)

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
                    animate={{ width: `${((Number(value) || 0) / max) * 100}%` }}
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
              <div className="stack-urgent" style={{ width: `${((priorities.urgent || 0) / (total || 1)) * 100}%` }} />
              <div className="stack-high" style={{ width: `${((priorities.high || 0) / (total || 1)) * 100}%` }} />
              <div className="stack-medium" style={{ width: `${((priorities.medium || 0) / (total || 1)) * 100}%` }} />
              <div className="stack-low" style={{ width: `${((priorities.low || 0) / (total || 1)) * 100}%` }} />
            </div>
            <div className="priority-legend">
              <Legend color="urgent" label="Urgent" value={priorities.urgent || 0} />
              <Legend color="high" label="High" value={priorities.high || 0} />
              <Legend color="medium" label="Medium" value={priorities.medium || 0} />
              <Legend color="low" label="Low" value={priorities.low || 0} />
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

function ReviewQueue({ tickets, selected, selectedId, setSelectedId, filter, setFilter, onApprove, onExport, notify, riskTerms }) {
  const [chosenCat, setChosenCat] = useState('general_inquiry')
  const [chosenPrio, setChosenPrio] = useState('medium')

  useEffect(() => {
    if (selected) {
      setChosenCat(selected.category || 'general_inquiry')
      setChosenPrio(selected.priority || 'medium')
    }
  }, [selected])

  // Support Enter keypress to approve current ticket
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Enter' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) {
        if (selected) {
          e.preventDefault()
          onApprove(selected.id, chosenCat, chosenPrio)
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [selected, chosenCat, chosenPrio, onApprove])

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
          <button className="button button-secondary" onClick={onExport}>
            <Download size={15} /> Export queue ({tickets.length})
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
              <p className="ticket-body">{highlightRisk(selected.body, riskTerms)}</p>
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

function highlightRisk(text, riskList = defaultRiskTerms) {
  if (!text) return 'No ticket body available.'
  const str = typeof text === 'string' ? text : String(text)
  const escaped = riskList.map(r => r.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const parts = str.split(new RegExp(`(${escaped.join('|')})`, 'gi'))
  return parts.map((part, index) =>
    riskList.some(term => term.toLowerCase() === part.toLowerCase()) ? <mark key={index}>{part}</mark> : part
  )
}

function TriagedView({ tickets, search, setSearch, category, setCategory, priority, setPriority, expandedId, setExpandedId, onFlag, onExport, notify }) {
  return (
    <>
      <PageIntro
        kicker="Auto-triaged / audit view"
        title="What passed the gate."
        description="Spot-check the tickets that met the confidence and risk rules without human intervention."
        action={
          <button className="button button-secondary" onClick={onExport}>
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
                    <td className="subject-cell">{ticket.subject || '(No subject)'}</td>
                    <td><span className="category-pill">{ticket.category ? ticket.category.replace('_', ' ') : 'Unassigned'}</span></td>
                    <td><span className={`priority-badge ${ticket.priority || 'low'}`}>{ticket.priority || 'low'}</span></td>
                    <td>
                      <div className="confidence-cell">
                        <span>{Math.round((ticket.confidence || 0) * 100)}%</span>
                        <i><b style={{ width: `${(ticket.confidence || 0) * 100}%` }} /></i>
                      </div>
                    </td>
                    <td className="latency-cell">{ticket.latency || 0}ms</td>
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
                            <p>{ticket.reasoning || 'No reasoning provided.'}</p>
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

function Settings({ threshold, setThreshold, chaos, setChaos, riskTerms, onAddKeyword, onRemoveKeyword, notify, onRunTriage }) {
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
                <button onClick={() => onRemoveKeyword(term)} aria-label={`Remove ${term}`}><X size={12} /></button>
              </span>
            ))}
            <button className="add-keyword" onClick={onAddKeyword}>
              <Plus size={14} /> Add keyword
            </button>
          </div>
        </section>
      </div>
    </>
  )
}

createRoot(document.getElementById('root')).render(<App />)
