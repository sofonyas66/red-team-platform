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
import { useIngestionHistory, useWorkspace, useEngagements, useAttackPaths, useGraphNodes, useTopPaths, useOverview } from '@/lib/hooks/use-dashboard-data'
import api from '@/lib/api-client'

type PageKey = 'Overview' | 'Attack paths' | 'Campaign plans' | 'Threat actors' | 'Data ingestion' | 'Engagements'

const navItems: { label: PageKey; icon: typeof LayoutDashboard; count?: string }[] = [
  { label: 'Overview', icon: LayoutDashboard },
  { label: 'Engagements', icon: Database },
  { label: 'Attack paths', icon: GitBranch },
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
      <div className="mr-4 flex items-center gap-2">
        <select 
          className="bg-[#0d141e] border border-[#1d2a39] rounded px-2 py-1 text-xs outline-none"
          value={selectedEngagementId || ''}
          onChange={(e) => selectEngagement(e.target.value || null)}
        >
          <option value="">Select engagement</option>
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
  const { data: overview, isLoading, error } = useOverview();
  const { selectedEngagementId } = useEngagements();
  const [showAllActivity, setShowAllActivity] = useState(false);

  const formatRelativeTime = (isoString: string | null | undefined) => {
    if (!isoString) return 'Never';
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return 'Never';
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 60) return 'just now';
    const intervals: Record<string, number> = {
      year: 31536000,
      month: 2592000,
      week: 604800,
      day: 86400,
      hour: 3600,
      minute: 60,
    };
    for (const [unit, secondsInUnit] of Object.entries(intervals)) {
      const interval = Math.floor(seconds / secondsInUnit);
      if (interval >= 1) {
        return `${interval} ${unit}${interval === 1 ? '' : 's'} ago`;
      }
    }
    return 'just now';
  };

  const handleRowClick = (source: string, target: string) => {
    if (selectedEngagementId) {
      const key = `rtap_last_query_${selectedEngagementId}`;
      localStorage.setItem(key, JSON.stringify({ source, target }));
    }
    localStorage.setItem('rtap_attack_source', source);
    localStorage.setItem('rtap_attack_target', target);
    window.dispatchEvent(new Event('rtap_attack_update'));
    navigate('Attack paths');
  };

  const handleGeneratePlanClick = (e: React.MouseEvent, source: string, target: string) => {
    e.stopPropagation();
    if (selectedEngagementId) {
      const key = `rtap_last_query_${selectedEngagementId}`;
      localStorage.setItem(key, JSON.stringify({ source, target }));
    }
    localStorage.setItem('rtap_attack_source', source);
    localStorage.setItem('rtap_attack_target', target);
    navigate('Campaign plans');
  };

  if (!selectedEngagementId) {
    return (
      <div className="dashboard">
        <div className="page-heading">
          <div>
            <div className="eyebrow"><span className="pulse-dot" /> LIVE SECURITY POSTURE</div>
            <h1>Good morning, {workspace ? workspace.email.split('@')[0] : 'there'}</h1>
            <p>Please select an engagement from the top bar to view overview metrics.</p>
          </div>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return <div className="p-10 text-center text-[#718096]">Loading overview data...</div>;
  }

  if (error || !overview) {
    const detail = error?.response?.data?.detail || error?.message || 'Failed to load overview data.';
    return <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm mb-6">{detail}</div>;
  }

  const {
    engagement,
    asset_count,
    relationship_count,
    top_paths = [],
    rel_type_breakdown = {},
    privileged_accounts = 0,
    recent_ingestion = [],
    pipeline = { ingested: false, last_ingested_at: null, paths_found: 0, threat_actors: false },
    gat_status = 'not_started',
  } = overview;

  return (
    <div className="dashboard">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="pulse-dot" /> LIVE SECURITY POSTURE — {engagement.name}</div>
          <h1>Good morning, {workspace ? workspace.email.split('@')[0] : 'there'}</h1>
          <p>
            Engagement <strong>{engagement.name}</strong> · Last ingested: <strong>{formatRelativeTime(pipeline.last_ingested_at)}</strong>
          </p>
        </div>
      </div>

      {/* Pipeline Strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <div onClick={() => navigate('Data ingestion')} className="cursor-pointer p-3 bg-[#0d141e] border border-[#1d2a39] rounded-lg hover:border-cyan-500/50 transition">
          <div className="text-xs text-[#9aa4b2] mb-1 flex items-center justify-between">
            <span>1. INGESTION</span>
            <Upload size={14} className="text-cyan-400" />
          </div>
          <div className="text-sm font-semibold text-[#e2e8f0]">
            {pipeline.ingested ? <span className="text-emerald-400">Ingested</span> : <span className="text-amber-400">Pending</span>}
          </div>
          <div className="text-xs text-[#718096] mt-0.5">{formatRelativeTime(pipeline.last_ingested_at)}</div>
        </div>

        <div onClick={() => navigate('Attack paths')} className="cursor-pointer p-3 bg-[#0d141e] border border-[#1d2a39] rounded-lg hover:border-cyan-500/50 transition">
          <div className="text-xs text-[#9aa4b2] mb-1 flex items-center justify-between">
            <span>2. ATTACK PATHS</span>
            <GitBranch size={14} className="text-cyan-400" />
          </div>
          <div className="text-sm font-semibold text-[#e2e8f0]">
            {pipeline.paths_found} {pipeline.paths_found === 1 ? 'path' : 'paths'} found
          </div>
          <div className="text-xs text-[#718096] mt-0.5">Top paths analyzed</div>
        </div>

        <div onClick={() => navigate('Threat actors')} className="cursor-pointer p-3 bg-[#0d141e] border border-[#1d2a39] rounded-lg hover:border-cyan-500/50 transition">
          <div className="text-xs text-[#9aa4b2] mb-1 flex items-center justify-between">
            <span>3. THREAT ACTORS</span>
            <Users size={14} className="text-cyan-400" />
          </div>
          <div className="text-sm font-semibold text-[#e2e8f0]">
            {pipeline.threat_actors ? 'Actors available' : 'No actors'}
          </div>
          <div className="text-xs text-[#718096] mt-0.5">ETI-Core database</div>
        </div>

        <div onClick={() => navigate('Campaign plans')} className="cursor-pointer p-3 bg-[#0d141e] border border-[#1d2a39] rounded-lg hover:border-cyan-500/50 transition">
          <div className="text-xs text-[#9aa4b2] mb-1 flex items-center justify-between">
            <span>4. CAMPAIGN PLAN</span>
            <Target size={14} className="text-cyan-400" />
          </div>
          <div className="text-sm font-semibold text-[#e2e8f0]">
            {pipeline.plans_count ? `${pipeline.plans_count} plans` : 'Plan Generator'}
          </div>
          <div className="text-xs text-[#718096] mt-0.5">Create execution plan</div>
        </div>
      </div>

      {/* Exposure & Asset Stats */}
      <div className="stats-grid mb-6">
        <StatCard label="Total assets" value={asset_count.toLocaleString()} detail="ingested nodes" icon={Database} color="green" />
        <StatCard label="Relationships" value={relationship_count.toLocaleString()} detail="graph edges" icon={GitBranch} color="purple" />
        <StatCard label="Privileged accounts" value={privileged_accounts.toLocaleString()} detail="users with admincount" icon={Users} color="amber" />
      </div>

      {/* Relationship Type Breakdown */}
      {Array.isArray(rel_type_breakdown) && rel_type_breakdown.length > 0 && (
        <section className="panel mb-6 p-4">
          <div className="panel-header mb-3">
            <div>
              <h2 className="text-sm font-semibold text-[#e2e8f0]">Relationship types</h2>
              <p className="text-xs text-[#9aa4b2]">Top relationship types across this engagement graph</p>
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
            {rel_type_breakdown.map((item: any) => (
              <div key={item.rel_type} className="bg-[#0b1118] border border-[#1d2a39] p-2.5 rounded text-center">
                <div className="text-xs text-[#9aa4b2] font-mono truncate" title={item.rel_type}>{item.rel_type}</div>
                <div className="text-sm font-bold text-[#e2e8f0] mt-0.5">{item.count?.toLocaleString()}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* GAT Training State Banner */}
      {gat_status !== 'ready' && (
        <div className="mb-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="animate-spin h-5 w-5 border-2 border-amber-500 border-t-transparent rounded-full" />
            <div>
              <div className="text-sm font-medium text-amber-300">Model is training for this engagement</div>
              <div className="text-xs text-amber-400">Scores will appear shortly</div>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => window.location.reload()} className="h-7">
            <span className="flex items-center gap-1"><svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Refresh</span>
          </Button>
        </div>
      )}
      {/* GAT Failed State */}
      {gat_status === 'failed' && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="text-red-400">✕</div>
            <div>
              <div className="text-sm font-medium text-red-300">Model training failed for this engagement</div>
              <div className="text-xs text-red-400">Retry after checking ingestion completed successfully</div>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => window.location.reload()} className="h-7">
            <span className="flex items-center gap-1"><svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Retry</span>
          </Button>
        </div>
      )}

      {/* Priority Attack Paths Table */}
      <section className="panel paths-panel mb-6">
        <div className="panel-header paths-header">
          <div>
            <h2>Priority attack paths</h2>
            <p>Sorted by risk level, step count, and model score</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => navigate('Attack paths')}>View all <ArrowUpRight data-icon="inline-end" /></Button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>RISK LEVEL</th>
                <th>PATH CHAIN</th>
                <th>MODEL SCORE</th>
                <th>STEPS / HOPS</th>
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {top_paths.length > 0 ? (
                top_paths.map((path: any, index: number) => {
                  const nodes = path.nodes || [];
                  const rels = path.rels || [];
                  const chainParts: string[] = [];
                  for (let i = 0; i < nodes.length; i++) {
                    const shortNode = nodes[i].split('@')[0];
                    chainParts.push(shortNode);
                    if (i < rels.length) {
                      chainParts.push(`-[${rels[i]}]->`);
                    }
                  }
                  const pathChainStr = chainParts.join(' ');

                  const scoreDisplay = (path.score !== null && path.score !== undefined && path.score > 0)
                    ? `${path.score.toFixed(3)} relative`
                    : 'Unscored';

                  const badgeClass = path.label === 'High' ? 'high' : path.label === 'Medium' ? 'medium' : 'low';

                  return (
                    <tr
                      key={index}
                      className="cursor-pointer hover:bg-[#131d2a] transition"
                      onClick={() => handleRowClick(path.source, path.target)}
                      title="Click to select in Attack paths scanner"
                    >
                      <td>
                        <div className="flex items-center gap-2">
                          <RiskBadge tone={badgeClass}>{path.label}</RiskBadge>
                          {path.source_privileged && (
                            <span className="text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30 px-1.5 py-0.5 rounded font-mono">
                              Already privileged
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="font-mono text-xs max-w-2xl whitespace-pre-wrap break-words">{pathChainStr}</td>
                      <td>{scoreDisplay}</td>
                      <td title="Steps exclude MemberOf, Contains and GpLink.">
{path.steps} step{path.steps===1?"":"s"} · {path.hops} hop{path.hops===1?"":"s"}</td>
                      <td>
                        <Button 
                          variant="outline" 
                          size="sm" 
                          className="h-7 text-[10px] uppercase tracking-wider py-0 px-2 border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/10"
                          onClick={(e) => handleGeneratePlanClick(e, path.source, path.target)}
                        >
                          Generate Plan
                        </Button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={5} className="text-center py-4 text-muted">
                    No attack paths found for this engagement.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Bottom Grid: Recent Activity & Quick Actions */}
      <div className="bottom-grid">
        <section className="panel ingestion-panel">
          <div className="panel-header">
            <div>
              <h2>Recent ingestion activity</h2>
              <p>Ingestion records for this engagement</p>
            </div>
            <button className="more-button" onClick={() => setShowAllActivity(!showAllActivity)}>
              {showAllActivity ? 'Show less' : 'View all'}
            </button>
          </div>
          <div className="activity-list">
            {recent_ingestion.length > 0 ? (
              (showAllActivity ? recent_ingestion : recent_ingestion.slice(0, 3)).map((item: any, idx: number) => (
                <div key={idx} className="activity-item">
                  <div className="activity-icon green"><Upload size={16} /></div>
                  <div>
                    <strong>Data ingested: {item.filename}</strong>
                    <br />
                    <span className="text-xs text-muted">Status: {item.status}</span>
                  </div>
                  <time>{formatRelativeTime(item.ingested_at)}</time>
                </div>
              ))
            ) : (
              <div className="text-center py-4 text-muted">No recent ingestion activity</div>
            )}
          </div>
        </section>

        <section className="panel quick-panel">
          <div className="panel-header">
            <div>
              <h2>Quick actions</h2>
              <p>Common tasks to keep your workspace current</p>
            </div>
          </div>
          <div className="quick-actions">
            <button onClick={() => navigate('Attack paths')}>
              <div className="quick-icon cyan"><GitBranch size={19} /></div>
              <span>
                <strong>Find paths</strong><br />
                <small>Scan attack paths</small>
              </span>
              <ArrowUpRight size={16} />
            </button>
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
  );
}

function AttackPathsPage({ onNavigate }: { onNavigate: (page: PageKey) => void }) {
  const { selectedEngagementId, data: engagements = [] } = useEngagements();
  const selectedEng = engagements.find(e => e.id === selectedEngagementId);
  const { data: nodes = { users: [], computers: [] }, isLoading: nodesLoading } = useGraphNodes();
  const { data: topPathsData, isLoading: topLoading, refetch: refetchTopPaths } = useTopPaths();
  const topPaths = topPathsData?.paths || [];
  const topGatStatus = topPathsData?.gat_status || 'not_started';
  const [source, setSource] = useState('');
  const [target, setTarget] = useState('');
  const [appliedSource, setAppliedSource] = useState('');
  const [appliedTarget, setAppliedTarget] = useState('');
  const { data: attackPathsData, isLoading, refetch: refetchAttackPaths } = useAttackPaths(appliedSource || undefined, appliedTarget || undefined);
  const paths = attackPathsData?.paths || [];
  const attackGatStatus = attackPathsData?.gat_status || 'not_started';

  // Load last query for this engagement when it changes
  useEffect(() => {
    if (!selectedEngagementId) {
      setSource(''); setTarget(''); setAppliedSource(''); setAppliedTarget('');
      return;
    }
    const key = `rtap_last_query_${selectedEngagementId}`;
    const saved = localStorage.getItem(key);
    if (saved) {
      try {
        const { source: s, target: t } = JSON.parse(saved);
        setSource(s || '');
        setTarget(t || '');
        setAppliedSource(s || '');
        setAppliedTarget(t || '');
      } catch {}
    } else {
      setSource(''); setTarget(''); setAppliedSource(''); setAppliedTarget('');
    }
    // global sync for overview
    setTimeout(() => {
      localStorage.setItem('rtap_attack_source', source);
      localStorage.setItem('rtap_attack_target', target);
      window.dispatchEvent(new Event('rtap_attack_update'));
    }, 0);
  }, [selectedEngagementId]);

  const handleScan = () => {
    if (!source || !target || !selectedEngagementId) return;
    setAppliedSource(source);
    setAppliedTarget(target);
    // persist per engagement
    const key = `rtap_last_query_${selectedEngagementId}`;
    localStorage.setItem(key, JSON.stringify({ source, target }));
    const histKey = `rtap_scan_history_${selectedEngagementId}`;
    try {
      const hist = JSON.parse(localStorage.getItem(histKey) || '[]');
      hist.unshift({ source, target, ts: Date.now() });
      localStorage.setItem(histKey, JSON.stringify(hist.slice(0, 20)));
    } catch {}
    localStorage.setItem('rtap_attack_source', source);
    localStorage.setItem('rtap_attack_target', target);
    window.dispatchEvent(new Event('rtap_attack_update'));
  }

  const userOptions = nodes.users || [];
  const computerOptions = nodes.computers || [];

  return (
    <div className="dashboard">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="pulse-dot" /> WORKSPACE</div>
          <h1>Attack paths</h1>
          <p>Find and prioritise attack paths for {selectedEng?.name || 'selected engagement'}</p>
        </div>
        <Button className="analyze-button" onClick={() => onNavigate('Data ingestion')}><Upload data-icon="inline-start" /> Upload collection</Button>
      </div>
      <section className="panel paths-panel">
        <div className="panel-header">
          <div>
            <h2>Path scanner</h2>
            <p>Select source user and target computer to discover attack paths</p>
          </div>
        </div>
        <div className="p-4 bg-[#0b1118] border border-[#1d2a39] rounded-xl mb-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
            <div>
              <label className="text-xs text-[#9aa4b2] mb-1 block">Source user</label>
              <select
                className="w-full bg-[#0d141e] border border-[#1d2a39] rounded px-3 py-2 text-sm outline-none"
                value={source}
                onChange={e => setSource(e.target.value)}
                disabled={nodesLoading || !selectedEngagementId}
              >
                <option value="">Select user…</option>
                {userOptions.map(u => <option key={u} value={u}>{u}</option>)} 
              </select>
            </div>
            <div>
              <label className="text-xs text-[#9aa4b2] mb-1 block">Target computer</label>
              <select
                className="w-full bg-[#0d141e] border border-[#1d2a39] rounded px-3 py-2 text-sm outline-none"
                value={target}
                onChange={e => setTarget(e.target.value)}
                disabled={nodesLoading || !selectedEngagementId}
              >
                <option value="">Select computer…</option>
                {computerOptions.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <Button onClick={handleScan} className="w-full analyze-button" disabled={!source || !target}>
                <Sparkles data-icon="inline-start" /> Scan paths
              </Button>
            </div>
          </div>
          {!selectedEngagementId && <div className="text-xs text-amber-400 mt-2">Select an engagement from the top bar to load users/computers.</div>}
          {nodesLoading && <div className="text-xs text-[#9aa4b2] mt-2">Loading nodes…</div>}
        </div>
        <div className="panel-header">
          <div>
            <h2>Results</h2>
            <p>{appliedSource && appliedTarget ? `${paths.length} paths found for ${appliedSource} → ${appliedTarget}` : topPaths.length > 0 ? `${topPaths.length} top paths for engagement` : 'No scan yet'}</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => onNavigate('Overview')}>Back to overview</Button>
        </div>
        {/* GAT Training State Banner */}
        {((appliedSource && appliedTarget && attackGatStatus !== 'ready') || (!appliedSource && !appliedTarget && topGatStatus !== 'ready')) && (
          <div className="mb-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="animate-spin h-5 w-5 border-2 border-amber-500 border-t-transparent rounded-full" />
              <div>
                <div className="text-sm font-medium text-amber-300">Model is training for this engagement</div>
                <div className="text-xs text-amber-400">Scores will appear shortly</div>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => { refetchTopPaths(); refetchAttackPaths(); }} className="h-7">
              <span className="flex items-center gap-1"><svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Refresh</span>
            </Button>
          </div>
        )}
        {/* GAT Failed State */}
        {((appliedSource && appliedTarget && attackGatStatus === 'failed') || (!appliedSource && !appliedTarget && topGatStatus === 'failed')) && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="text-red-400">✕</div>
              <div>
                <div className="text-sm font-medium text-red-300">Model training failed for this engagement</div>
                <div className="text-xs text-red-400">Retry after checking ingestion completed successfully</div>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => { refetchTopPaths(); refetchAttackPaths(); }} className="h-7">
              <span className="flex items-center gap-1"><svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Retry</span>
            </Button>
          </div>
        )}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>RISK</th>
                <th>PATH CHAIN</th>
                <th>MODEL SCORE</th>
                <th>STEPS / HOPS</th>
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {isLoading || topLoading ? (
                <tr><td colSpan={5} className="text-center py-4 text-muted">Loading attack paths...</td></tr>
              ) : paths.length > 0 ? (
                paths.map((path: any, index: number) => {
                  const nodesList = path.nodes || [];
                  const entry = nodesList[0] || 'Unknown';
                  const objective = nodesList[nodesList.length - 1] || 'Unknown';
                  const pathLabel = nodesList.length > 1 ? `${entry.split('@')[0]} → ${objective.split('@')[0]}` : 'Generic Path';
                  return (
                    <tr key={index}>
                      <td className="font-mono text-xs">{pathLabel}</td>
                      <td className="font-mono text-xs max-w-lg whitespace-pre-wrap break-words">{path.nodes.map((n: string) => n.split('@')[0]).join(' → ')}</td>
                      <td>{path.score != null && typeof path.score === 'number' ? path.score.toFixed(3) : 'Not scored'}</td>
                      <td>{path.steps} steps · {path.hops} hops</td>
                      <td>
                        <Button 
                          variant="outline" 
                          size="sm" 
                          className="h-7 text-[10px] uppercase tracking-wider py-0 px-2 border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/10"
                          onClick={() => {
                            localStorage.setItem('rtap_attack_source', path.source);
                            localStorage.setItem('rtap_attack_target', path.target);
                            onNavigate('Campaign plans');
                          }}
                        >
                          Generate Plan
                        </Button>
                      </td>
                    </tr>
                  );
                })
              ) : topPaths.length > 0 ? (
                topPaths.map((path: any, index: number) => {
                  const badgeClass = path.label === 'High' ? 'high' : path.label === 'Medium' ? 'medium' : 'low';
                  const handleLocalRowClick = () => {
                    const key = `rtap_last_query_${selectedEngagementId}`;
                    localStorage.setItem(key, JSON.stringify({ source: path.source, target: path.target }));
                    localStorage.setItem('rtap_attack_source', path.source);
                    localStorage.setItem('rtap_attack_target', path.target);
                    window.dispatchEvent(new Event('rtap_attack_update'));
                    setSource(path.source);
                    setTarget(path.target);
                    setAppliedSource(path.source);
                    setAppliedTarget(path.target);
                  };

                  return (
                    <tr key={`top-${index}`} className="cursor-pointer hover:bg-[#131d2a] transition" onClick={handleLocalRowClick}>
                      <td className="font-mono text-xs">
                        <div className="flex items-center gap-2">
                          <RiskBadge tone={badgeClass}>{path.label}</RiskBadge>
                          {path.source_privileged && <span className="text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30 px-1.5 py-0.5 rounded font-mono">Already privileged</span>}
                        </div>
                      </td>
                      <td className="font-mono text-xs max-w-lg whitespace-pre-wrap break-words">{path.nodes.map((n: string) => n.split('@')[0]).join(' → ')}</td>
                      <td>{typeof path.score === 'number' && path.score > 0 ? `${path.score.toFixed(3)} relative` : 'Unscored'}</td>
                      <td title="Steps exclude MemberOf, Contains and GpLink.">{path.steps} step{path.steps===1?"":"s"} · {path.hops} hop{path.hops===1?"":"s"}</td>
                      <td>
                        <Button 
                          variant="outline" 
                          size="sm" 
                          className="h-7 text-[10px] uppercase tracking-wider py-0 px-2 border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/10"
                          onClick={(e) => {
                            e.stopPropagation();
                            localStorage.setItem('rtap_attack_source', path.source);
                            localStorage.setItem('rtap_attack_target', path.target);
                            onNavigate('Campaign plans');
                          }}
                        >
                          Generate Plan
                        </Button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr><td colSpan={5} className="text-center py-4 text-muted">{appliedSource && appliedTarget ? 'No attack paths found.' : 'Select source and target to scan, or see top paths above.'}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function CampaignPlansPage({ onNavigate }: { onNavigate: (page: PageKey) => void }) {
  const { selectedEngagementId, data: engagements = [] } = useEngagements();
  const selectedEng = engagements.find(e => e.id === selectedEngagementId);
  const { data: nodes = { users: [], computers: [] }, isLoading: nodesLoading } = useGraphNodes();
  const { data: topPathsData, isLoading: topLoading, refetch: refetchTopPaths } = useTopPaths();
  const topGatStatus = topPathsData?.gat_status || 'not_started';

  const [source, setSource] = useState('');
  const [target, setTarget] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generatedPlan, setGeneratedPlan] = useState<any>(null);
  const [savedPlans, setSavedPlans] = useState<any[]>([]);
  const [loadingSaved, setLoadingSaved] = useState(false);

  useEffect(() => {
    const s = localStorage.getItem('rtap_attack_source');
    const t = localStorage.getItem('rtap_attack_target');
    if (s) setSource(s);
    if (t) setTarget(t);
  }, []);

  useEffect(() => {
    if (selectedEngagementId) {
      fetchSavedPlans();
    }
  }, [selectedEngagementId]);

  const fetchSavedPlans = async () => {
    setLoadingSaved(true);
    try {
      const res = await api.get(`/plans?engagement_id=${selectedEngagementId}`);
      setSavedPlans(res.data);
    } catch (e) {
      console.error("Failed to fetch saved plans", e);
    } finally {
      setLoadingSaved(false);
    }
  };

  const handleGenerate = async () => {
    if (!source || !target || !selectedEngagementId) return;
    setLoading(true);
    setError(null);
    setGeneratedPlan(null);

    localStorage.setItem('rtap_attack_source', source);
    localStorage.setItem('rtap_attack_target', target);
    if (selectedEngagementId) {
      localStorage.setItem(`rtap_last_query_${selectedEngagementId}`, JSON.stringify({ source, target }));
    }

    try {
      const res = await api.post(`/plan/generate?engagement_id=${selectedEngagementId}`, {
        source,
        target
      }, { timeout: 120000 });
      setGeneratedPlan({
        id: res.data.id,
        plan: res.data.plan,
        used_llm: res.data.used_llm,
        rag_used: res.data.rag_used,
        matched_actor: res.data.matched_actor,
        timestamp: res.data.timestamp
      });
      fetchSavedPlans();
    } catch (err: any) {
      if (err.response) {
        const status = err.response.status;
        if (status === 404) setError("No attack path found or nodes missing.");
        else if (status === 422) setError("Invalid request data.");
        else if (status === 429) setError("Too many requests. Please wait.");
        else if (status === 503) setError("LLM service unavailable.");
        else setError(`Server error: ${err.response.data?.detail || status}`);
      } else if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        setError("Request timed out (120s).");
      } else {
        setError("Network error. Check your connection.");
      }
    } finally {
      setLoading(false);
    }
  };

  const openSavedPlan = async (planId: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/plans/${planId}`);
      const pj = res.data.path_json || {};
      setGeneratedPlan({
        id: res.data.id,
        plan: pj.plan || "Plan text not stored in older records.",
        used_llm: res.data.used_llm,
        rag_used: res.data.rag_used,
        matched_actor: pj.matched_actor || "Unknown",
        timestamp: res.data.created_at,
        path_json: pj
      });
    } catch (err) {
      setError("Failed to load plan details.");
    } finally {
      setLoading(false);
    }
  };

  const userOptions = nodes.users || [];
  const computerOptions = nodes.computers || [];

  return (
    <div className="dashboard">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="pulse-dot" /> WORKSPACE</div>
          <h1>Campaign plans</h1>
          <p>Generate and view automated red team execution plans for {selectedEng?.name || 'selected engagement'}</p>
        </div>
        <Button className="analyze-button" onClick={() => onNavigate('Attack paths')}><GitBranch data-icon="inline-start" /> Attack paths</Button>
      </div>

      {/* Generator Form */}
      <section className="panel paths-panel mb-6">
        <div className="panel-header">
          <div>
            <h2>Plan generator</h2>
            <p>Select source and target to generate an AI-driven campaign plan</p>
          </div>
        </div>
        <div className="p-4 bg-[#0b1118] border border-[#1d2a39] rounded-xl">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end mb-4">
            <div>
              <label className="text-xs text-[#9aa4b2] mb-1 block">Source user</label>
              <select
                className="w-full bg-[#0d141e] border border-[#1d2a39] rounded px-3 py-2 text-sm outline-none"
                value={source}
                onChange={e => setSource(e.target.value)}
                disabled={nodesLoading || !selectedEngagementId}
              >
                <option value="">Select source user…</option>
                {userOptions.map(u => <option key={u} value={u}>{u}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-[#9aa4b2] mb-1 block">Target computer</label>
              <select
                className="w-full bg-[#0d141e] border border-[#1d2a39] rounded px-3 py-2 text-sm outline-none"
                value={target}
                onChange={e => setTarget(e.target.value)}
                disabled={nodesLoading || !selectedEngagementId}
              >
                <option value="">Select target computer…</option>
                {computerOptions.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <Button onClick={handleGenerate} className="w-full analyze-button" disabled={!source || !target || loading || !selectedEngagementId}>
                {loading ? <span className="animate-spin mr-2">⏳</span> : <Sparkles data-icon="inline-start" />} 
                {loading ? 'Generating (up to 120s)...' : 'Generate plan'}
              </Button>
            </div>
          </div>
          {!selectedEngagementId && <div className="text-xs text-amber-400">Select an engagement from the top bar to enable plan generation.</div>}
          {error && <div className="p-3 bg-red-500/10 border border-red-500/20 rounded text-red-400 text-xs mt-2">{error}</div>}
        </div>
      </section>

      {/* GAT Training State Banner */}
      {topGatStatus !== 'ready' && (
        <div className="mb-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="animate-spin h-5 w-5 border-2 border-amber-500 border-t-transparent rounded-full" />
            <div>
              <div className="text-sm font-medium text-amber-300">Model is training for this engagement</div>
              <div className="text-xs text-amber-400">Scores will appear shortly</div>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => { refetchTopPaths(); }} className="h-7">
            <span className="flex items-center gap-1"><svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Refresh</span>
          </Button>
        </div>
      )}
      {/* GAT Failed State */}
      {topGatStatus === 'failed' && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="text-red-400">✕</div>
            <div>
              <div className="text-sm font-medium text-red-300">Model training failed for this engagement</div>
              <div className="text-xs text-red-400">Retry after checking ingestion completed successfully</div>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => { refetchTopPaths(); }} className="h-7">
            <span className="flex items-center gap-1"><svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Retry</span>
          </Button>
        </div>
      )}

      {/* Generated Plan View */}
      {generatedPlan && (
        <section className="panel paths-panel mb-6">
          <div className="panel-header">
            <div>
              <h2>Campaign Plan Result</h2>
              <p>Generated at {new Date(generatedPlan.timestamp).toLocaleString()}</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-1 bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded text-xs font-semibold">
                AI generated
              </span>
              <span className="px-2 py-1 bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 rounded text-xs font-semibold">
                RAG: {generatedPlan.rag_used ? 'on' : 'off'}
              </span>
            </div>
          </div>
          <div className="p-4 bg-[#0b1118] border border-[#1d2a39] rounded-xl space-y-4">
            <div className="flex flex-wrap gap-4 text-xs text-[#9aa4b2] border-b border-[#1d2a39] pb-3">
              <div>Matched Actor: <strong className="text-[#e2e8f0]">{generatedPlan.matched_actor}</strong></div>
              {generatedPlan.path_json?.nodes && (
                <div>Path Chain: <strong className="text-[#e2e8f0] font-mono">{generatedPlan.path_json.nodes.join(' → ')}</strong></div>
              )}
            </div>
            <div className="text-sm text-[#e2e8f0] whitespace-pre-line leading-relaxed font-sans bg-[#0d141e] p-4 rounded border border-[#1d2a39]">
              {generatedPlan.plan}
            </div>
          </div>
        </section>
      )}

      {/* Saved Plans List */}
      <section className="panel paths-panel">
        <div className="panel-header">
          <div>
            <h2>Saved plans</h2>
            <p>Previous campaign plans for {selectedEng?.name || 'this engagement'}</p>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>SOURCE</th>
                <th>TARGET</th>
                <th>MODEL</th>
                <th>RAG</th>
                <th>CREATED</th>
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {loadingSaved ? (
                <tr><td colSpan={6} className="text-center py-4 text-muted">Loading saved plans...</td></tr>
              ) : savedPlans.length > 0 ? (
                savedPlans.map((p: any) => (
                  <tr key={p.id} className="cursor-pointer hover:bg-[#131d2a] transition" onClick={() => openSavedPlan(p.id)}>
                    <td className="font-mono text-xs">{p.source}</td>
                    <td className="font-mono text-xs">{p.target}</td>
                    <td>{p.used_llm ? 'AI' : 'Template'}</td>
                    <td>{p.rag_used ? 'On' : 'Off'}</td>
                    <td>{new Date(p.created_at).toLocaleString()}</td>
                    <td>
                      <Button variant="outline" size="sm" className="h-7 text-[10px]" onClick={(e) => { e.stopPropagation(); openSavedPlan(p.id); }}>
                        View
                      </Button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan={6} className="text-center py-4 text-muted">No saved plans yet. Generate one above.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function ThreatActorsPage({ onNavigate }: { onNavigate: (page: PageKey) => void }) {
  return (
    <div className="dashboard">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="pulse-dot" /> WORKSPACE</div>
          <h1>Threat actors</h1>
          <p>ETI-Core threat actors for the selected engagement</p>
        </div>
        <Button className="analyze-button" onClick={() => onNavigate('Data ingestion')}><Upload data-icon="inline-start" /> Upload collection</Button>
      </div>
      <section className="panel paths-panel">
        <div className="panel-header"><div><h2>Threat actors</h2><p>API /actors available</p></div><Button variant="outline" size="sm" onClick={() => onNavigate('Overview')}>Back to overview</Button></div>
        <div className="table-wrap"><p className="text-center py-4 text-muted">Threat actor listing UI coming soon.</p></div>
      </section>
    </div>
  );
}

function EngagementsPage({ onNavigate }: { onNavigate: (page: PageKey) => void }) {
  const [engagements, setEngagements] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const { data: workspace } = useWorkspace()

  useEffect(() => {
    fetchEngagements()
  }, [])

  const fetchEngagements = async () => {
    setLoading(true)
    try {
      const res = await api.get('/engagements')
      setEngagements(res.data)
    } catch (e) {
      alert('Failed to load engagements')
    } finally {
      setLoading(false)
    }
  }

  const createEngagement = async () => {
    if (!name.trim()) return
    setCreating(true)
    try {
      const res = await api.post('/engagements', { name: name.trim() })
      setEngagements(prev => [...prev, res.data])
      setName('')
    } catch (e) {
      alert('Failed to create engagement')
    } finally {
      setCreating(false)
    }
  }

  const updateEngagement = async (id: string) => {
    try {
      await api.patch(`/engagements/${id}`, { name: editName.trim() })
      setEngagements(prev => prev.map(e => e.id === id ? { ...e, name: editName.trim() } : e))
      setEditing(null)
    } catch (e) {
      alert('Failed to update')
    }
  }

  const deleteEngagement = async (id: string) => {
    const ok = window.prompt('Type DELETE to confirm removal of this engagement')
    if (ok !== 'DELETE') return
    try {
      await api.delete(`/engagements/${id}`)
      setEngagements(prev => prev.filter(e => e.id !== id))
    } catch (e: any) {
      alert('Failed to delete: ' + (e?.response?.data?.detail || e.message))
    }
  }

  return (
    <div className="dashboard">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="pulse-dot" /> WORKSPACE</div>
          <h1>Engagements</h1>
          <p>Manage red team engagements for your organization</p>
        </div>
        <Button className="analyze-button" onClick={() => onNavigate('Data ingestion')}><Upload data-icon="inline-start" /> Upload collection</Button>
      </div>
      <section className="panel paths-panel">
        <div className="panel-header">
          <div>
            <h2>Engagements</h2>
            <p>Create, rename or delete engagements</p>
          </div>
        </div>
        <div className="p-4 bg-[#0b1118] border border-[#1d2a39] rounded-xl mb-4">
          <div className="flex gap-2">
            <input 
              className="flex-1 bg-[#0d141e] border border-[#1d2a39] rounded px-3 py-2 text-sm outline-none" 
              placeholder="New engagement name" 
              value={name} 
              onChange={e => setName(e.target.value)} 
              onKeyDown={e => e.key === 'Enter' && createEngagement()} 
            />
            <Button onClick={createEngagement} disabled={creating || !name.trim()}>
              {creating ? 'Creating...' : 'Create'}
            </Button>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>NAME</th>
                <th>STATUS</th>
                <th>NODES</th>
                <th>CREATED</th>
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} className="text-center py-4 text-muted">Loading...</td></tr>
              ) : engagements.length > 0 ? (
                engagements.map((eng: any) => (
                  <tr key={eng.id}>
                    <td>
                      {editing === eng.id ? (
                        <input 
                          className="bg-[#0d141e] border border-[#1d2a39] rounded px-2 py-1 text-sm w-48" 
                          value={editName} 
                          onChange={e => setEditName(e.target.value)} 
                          onKeyDown={e => e.key === 'Enter' && updateEngagement(eng.id)} 
                        />
                      ) : (
                        eng.name
                      )}
                    </td>
                    <td><span className="risk-badge default">{eng.status || 'active'}</span></td>
                    <td>{eng.node_count ?? '-'}</td>
                    <td>{eng.created_at ? new Date(eng.created_at).toLocaleDateString() : '-'}</td>
                    <td>
                      <div className="flex gap-2">
                        {editing === eng.id ? (
                          <>
                            <Button size="sm" variant="outline" onClick={() => updateEngagement(eng.id)}>Save</Button>
                            <Button size="sm" variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
                          </>
                        ) : (
                          <>
                            <Button size="sm" variant="outline" onClick={() => { setEditing(eng.id); setEditName(eng.name); }}>Rename</Button>
                            <Button size="sm" variant="destructive" onClick={() => deleteEngagement(eng.id)}>Delete</Button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan={5} className="text-center py-4 text-muted">No engagements yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function WorkspacePage({ page, onNavigate }: { page: PageKey; onNavigate: (page: PageKey) => void }) {
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
          ) : activePage === 'Engagements' ? (
            <EngagementsPage onNavigate={navigate} />
          ) : activePage === 'Attack paths' ? (
            <AttackPathsPage onNavigate={navigate} />
          ) : activePage === 'Campaign plans' ? (
            <CampaignPlansPage onNavigate={navigate} />
          ) : activePage === 'Threat actors' ? (
            <ThreatActorsPage onNavigate={navigate} />
          ) : (
            <WorkspacePage page={activePage} onNavigate={navigate} />
          )}
        </main>
      </div>
    </div>
  )
}