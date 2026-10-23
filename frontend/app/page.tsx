'use client'

import { useState, useEffect } from 'react'
import {
  Activity,
  ArrowUpRight,
  Bell,
  ChevronDown,
  CircleHelp,
  Database,
  FileCheck2,
  GitBranch,
  LayoutDashboard,
  LogOut,
  Menu,
  Search,
  Settings,
  Sparkles,
  Target,
  Upload,
  Users,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth-context'
import { useGraphStats } from '@/lib/hooks/use-graph-stats'
import { useIngestionHistory, useWorkspace, useEngagements, useAttackPaths } from '@/lib/hooks/use-dashboard-data'

type PageKey = 'Overview' | 'Attack paths' | 'Campaign plans' | 'Threat actors' | 'Data ingestion'

const navItems: { label: PageKey; icon: typeof LayoutDashboard; count?: string }[] = [
  { label: 'Overview', icon: LayoutDashboard },
  { label: 'Attack paths', icon: GitBranch, count: '24' },
  { label: 'Campaign plans', icon: Target },
  { label: 'Threat actors', icon: Users },
  { label: 'Data ingestion', icon: Upload },
]

function BrandMark() {
  return <div className="brand-mark"><span /><span /><span /></div>
}

function Sidebar({ collapsed, onToggle, activePage, onNavigate, workspace }: { collapsed: boolean; onToggle: () => void; activePage: PageKey; onNavigate: (page: PageKey) => void; workspace: { org_name: string } | null }) {
  const { logout } = useAuth();
  return (
    <aside className={`sidebar ${collapsed ? 'sidebar-collapsed' : ''}`}>
      <div className="sidebar-brand">
        <BrandMark />
        {!collapsed && <div><strong>ETHIO</strong><span>RTAP</span></div>}
      </div>
      <div className="workspace-switcher">
        <div className="workspace-icon">
          {workspace ? workspace.org_name.substring(0, 2).toUpperCase() : '??'}
        </div>
        {!collapsed && <div className="workspace-copy"><span>{workspace ? workspace.org_name : 'Loading workspace...'}</span></div>}
        {!collapsed && <ChevronDown size={14} />}
      </div>
      <nav className="main-nav" aria-label="Primary navigation">
        <div className="nav-label">{!collapsed && 'WORKSPACE'}</div>
        {navItems.map(({ label, icon: Icon, count }) => (
          <button onClick={() => onNavigate(label)} className={`nav-item ${activePage === label ? 'active' : ''}`} key={label} title={collapsed ? label : undefined}>
            <Icon size={18} /><span>{!collapsed && label}</span>{!collapsed && count && <em>{count}</em>}
          </button>
        ))}
        <div className="nav-label settings-label">{!collapsed && 'SYSTEM'}</div>
        <button className="nav-item" title={collapsed ? 'Settings' : undefined}><Settings size={18} />{!collapsed && <span>Settings</span>}</button>
        <button className="nav-item" title={collapsed ? 'Help center' : undefined}><CircleHelp size={18} />{!collapsed && <span>Help center</span>}</button>
        <button className="nav-item" onClick={logout}><LogOut size={18} />{!collapsed && <span>Logout</span>}</button>
      </nav>
      <div className="sidebar-bottom">
        <button className="collapse-button" onClick={onToggle} aria-label="Toggle sidebar"><Menu size={18} />{!collapsed && 'Collapse menu'}</button>
      </div>
    </aside>
  )
}

function Topbar({ onMenu, page, workspace }: { onMenu: () => void; page: PageKey; workspace: { email: string } | null }) {
  const { data: engagements = [], selectedEngagementId, selectEngagement } = useEngagements();
  return <header className="topbar">
    <button className="mobile-menu" onClick={onMenu} aria-label="Open menu"><Menu size={20} /></button>
    <div className="breadcrumbs"><span>Workspace</span><b>/</b><strong>{page}</strong></div>
    <div className="topbar-actions">
      <div className="mr-4">
        <select 
          className="bg-[#0d141e] border border-[#1d2a39] rounded px-2 py-1 text-xs outline-none"
          value={selectedEngagementId || ''}
          onChange={(e) => selectEngagement(e.target.value)}
        >
          {engagements.map((eng) => (
            <option key={eng.id} value={eng.id}>{eng.name}</option>
          ))}
        </select>
      </div>
      <div className="api-status"><i /> API operational</div>
      <button className="icon-button" aria-label="Search"><Search size={18} /></button>
      <button className="icon-button notification" aria-label="Notifications"><Bell size={18} /><i /></button>
      <div className="avatar" title={workspace?.email}>{workspace?.email?.slice(0,2).toUpperCase()}</div><ChevronDown size={14} className="user-chevron" />
    </div>
  </header>
}

function StatCard({ label, value, detail, icon: Icon, color, trend }: { label: string; value: string; detail: string; icon: typeof Activity; color: string; trend?: string }) {
  return <div className="stat-card">
    <div className="stat-top"><span>{label}</span><div className={`stat-icon ${color}`}><Icon size={17} /></div></div>
    <div className="stat-value">{value}</div>
    <div className="stat-detail"><span className={trend?.startsWith('+') ? 'positive' : ''}>{trend}</span> {detail}</div>
  </div>
}

function RiskBadge({ tone, children }: { tone: string; children: React.ReactNode }) {
  return <span className={`risk-badge ${tone}`}><i />{children}</span>
}

function Dashboard({ workspace, navigate }: { workspace: { email: string } | null; navigate: (page: PageKey) => void }) {
  const { stats, isLoading, error } = useGraphStats();
  const { data: activity = [], isLoading: isActivityLoading } = useIngestionHistory();
  const { selectedEngagementId } = useEngagements();
  const { data: paths = [], isLoading: isPathsLoading } = useAttackPaths('User', 'Domain Admin');
  const [activeTab, setActiveTab] = useState('Attack paths');
  const [healthStatus, setHealthStatus] = useState<'ok' | 'error' | 'checking'>('checking');
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    // Fetch health status - only if authenticated to avoid 401 loops
    if (isAuthenticated) {
      fetch('/health')
        .then(res => {
          if (res.ok) setHealthStatus('ok');
          else setHealthStatus('error');
        })
        .catch(() => setHealthStatus('error'));
    }
  }, [isAuthenticated]);

  const totalAssets = stats ? Object.values(stats.nodes).reduce((a, b) => a + b, 0) : 0;
  const totalRelationships = stats ? Object.values(stats.relationships).reduce((a, b) => a + b, 0) : 0;

  // Format relative time
  const formatRelativeTime = (date) => {
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    const intervals = {
      year: 31536000,
      month: 2592000,
      week: 604800,
      day: 86400,
      hour: 3600,
      minute: 60,
      second: 1
    };
    for (const [unit, secondsInUnit] of Object.entries(intervals)) {
      const interval = Math.floor(seconds / secondsInUnit);
      if (interval >= 1) {
        return `${interval} ${unit}${interval === 1 ? '' : 's'} ago`;
      }
    }
    return 'just now';
  };

  return <div className="dashboard">
    <div className="page-heading">
      <div>
        <div className="eyebrow"><span className="pulse-dot" /> LIVE SECURITY POSTURE</div>
        <h1>Good morning, {workspace ? workspace.email.split('@')[0] : 'there'}</h1>
        <p>Here&apos;s what&apos;s happening across your attack surface today.</p>
      </div>
      <div className="heading-actions">
        <Button variant="outline" className="export-button" disabled>
          <FileCheck2 data-icon="inline-start" /> Export report
        </Button>
        <Button className="analyze-button" disabled>
          <Sparkles data-icon="inline-start" /> New analysis
        </Button>
      </div>
    </div>

    {isLoading ? (
      <div className="p-10 text-center text-[#718096]">Loading statistics...</div>
    ) : error ? (
       <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm mb-6">{error}</div>
    ) : (
      <>
        <div className="stats-grid">
          <StatCard label="Total assets" value={totalAssets.toLocaleString()} trend="" detail="ingested nodes" icon={Database} color="green" />
          <StatCard label="Relationships" value={totalRelationships.toLocaleString()} trend="" detail="graph edges" icon={GitBranch} color="purple" />
          {/* Removed fake stats: Critical exposures, Risk score */}
        </div>

        <div className="content-grid">

          {/* Recent activity panel */}
          <section className="panel ingestion-panel">
            <div className="panel-header">
              <div>
                <h2>Recent activity</h2>
                <p>Latest changes in your workspace</p>
              </div>
              <button className="more-button">View all <ArrowUpRight size={14} /></button>
            </div>
            <div className="activity-list">
              {isActivityLoading ? (
                <div className="text-center py-4 text-muted">Loading activity...</div>
              ) : activity.length > 0 ? (
                activity.map((item: any) => (
                  <div key={item.id} className="activity-item">
                    <div className="activity-icon green"><Upload size={16} /></div>
                    <div>
                      <strong>Data ingested: {item.filename}</strong>
                      <br />
                      <span className="text-xs text-muted">
                        {(item.node_count || 0).toLocaleString()} nodes · {(item.edge_count || 0).toLocaleString()} relationships
                      </span>
                    </div>
                    <time>{formatRelativeTime(new Date(item.ingested_at))}</time>
                  </div>
                ))
              ) : (
                <div className="text-center py-4 text-muted">No recent activity</div>
              )}
            </div>
          </section>
        </div>
      </>
    )}

    <section className="panel paths-panel">
      <div className="panel-header paths-header">
        <div>
          <h2>Priority attack paths</h2>
          <p>Highest scoring paths that need your attention</p>
        </div>
        <div className="panel-actions">
          <div className="tabs">
            {['Attack paths', 'Recent scans'].map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={activeTab === tab ? 'selected' : ''}
              >
                {tab}
              </button>
            ))}
          </div>
          <Button variant="outline" size="sm">View all <ArrowUpRight data-icon="inline-end" /></Button>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>PATH</th>
              <th>ENTRY POINT</th>
              <th>OBJECTIVE</th>
              <th>RISK SCORE</th>
              <th>HOPS</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {/* Path rows will be populated when engagement is selected */}
            {isPathsLoading ? (
              <tr>
                <td colSpan={6} className="text-center py-4 text-muted">Loading attack paths...</td>
              </tr>
            ) : paths.length > 0 ? (
              paths.map((path: any, index: number) => (
                <tr key={index}>
                  <td>{path.path_name || 'Generic Path'}</td>
                  <td>{path.start_node || 'Unknown'}</td>
                  <td>{path.end_node || 'Domain Admin'}</td>
                  <td>{path.score ? path.score.toFixed(2) : 'N/A'}</td>
                  <td>{path.hops || 0}</td>
                  <td className="text-right">
                    <Button variant="ghost" size="sm">View</Button>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="text-center py-4 text-muted">
                  {selectedEngagementId ? "No attack paths found for this engagement." : "Select an engagement to view attack paths."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>

    <div className="bottom-grid">
      <section className="panel quick-panel">
        <div className="panel-header">
          <div>
            <h2>Quick actions</h2>
            <p>Common tasks to keep your workspace current</p>
          </div>
        </div>
        <div className="quick-actions">
          <button onClick={() => navigate('Data ingestion')}>
            <div className="quick-icon cyan"><Upload size={19} /></div>
            <span>
              <strong>Ingest data</strong><br />
              <small>Upload collection</small>
            </span>
            <ArrowUpRight size={16} />
          </button>
        </div>
      </section>
    </div>
  </div>
}

function WorkspacePage({ page, onNavigate }: { page: PageKey; onNavigate: (page: PageKey) => void }) {
  // Placeholder content for each tab
  const placeholderMessage = "Not available yet";
  return <div className="dashboard"><div className="page-heading"><div><div className="eyebrow"><span className="pulse-dot" /> WORKSPACE</div><h1>Workspace</h1><p>Select a tab to view its content.</p></div><Button className="analyze-button" onClick={() => onNavigate(page === 'Data ingestion' ? 'Data ingestion' : page)}><Upload data-icon="inline-start" /> {page === 'Data ingestion' ? 'Upload collection' : 'Create new'}</Button></div><section className="panel paths-panel"><div className="panel-header"><div><h2>Workspace items</h2><p>Everything is ready for review</p></div><Button variant="outline" size="sm" onClick={() => onNavigate('Overview')}>Back to overview</Button></div><div className="quick-actions"><p className="text-center py-4">{placeholderMessage}</p></div></section></div>
}

import IngestPage from './ingest/page'

export default function Page() {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [activePage, setActivePage] = useState<PageKey>('Overview')
  const { data: workspace } = useWorkspace()
  const navigate = (page: PageKey) => { setActivePage(page); setMobileOpen(false) }

  return (
    <div className="app-shell">
      <div className={`sidebar-wrap ${mobileOpen ? 'mobile-open' : ''}`}>
        <Sidebar 
          collapsed={collapsed} 
          onToggle={() => setCollapsed(!collapsed)} 
          activePage={activePage} 
          onNavigate={navigate} 
          workspace={workspace}
        />
      </div>
      {mobileOpen && <button className="mobile-overlay" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X /></button>}
      <div className={`main-area ${collapsed ? 'main-expanded' : ''}`}>
        <Topbar onMenu={() => setMobileOpen(true)} page={activePage} workspace={workspace} />
        <main>
          {activePage === 'Overview' ? (
            <Dashboard workspace={workspace} navigate={navigate} />
          ) : activePage === 'Data ingestion' ? (
            <IngestPage />
          ) : (
            <WorkspacePage page={activePage} onNavigate={navigate} />
          )}
        </main>
      </div>
    </div>
  )
}