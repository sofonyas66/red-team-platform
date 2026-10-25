'use client'

import { useState, useEffect } from 'react'
import { 
  Upload, 
  FileUp, 
  Loader2, 
  CheckCircle2, 
  AlertCircle, 
  Info,
  ChevronRight,
  Database,
  GitBranch,
  Search,
  X,
  Plus,
  Brain
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import api from '@/lib/api-client'
import { cn } from '@/lib/utils'

interface Engagement {
  id: string
  name: string
}

interface IngestResponse {
  status: string
  nodes_ingested: Record<string, number>
  relationships_ingested: Record<string, number>
  skipped_ace_types: string[]
  computers_with_uncollected_sessions: number
  computers_with_uncollected_localgroups: number
  skipped: boolean
  message: string
}

export default function IngestPage() {
  const [file, setFile] = useState<File | null>(null)
  const [engagements, setEngagements] = useState<Engagement[]>([])
  const [engagementId, setEngagementId] = useState('')
  const [loadingEngagements, setLoadingEngagements] = useState(true)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newEngagementName, setNewEngagementName] = useState('')
  const [creatingEngagement, setCreatingEngagement] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<IngestResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [gatStatus, setGatStatus] = useState<any>(null)
  const [retraining, setRetraining] = useState(false)

  useEffect(() => {
    fetchEngagements()
  }, [])

  useEffect(() => {
    if (!engagementId) return
    const fetchGatStatus = async () => {
      try {
        const res = await api.get(`/gnn_status?engagement_id=${engagementId}`)
        setGatStatus(res.data)
      } catch {}
    }
    fetchGatStatus()
    const interval = setInterval(fetchGatStatus, 3000)
    return () => clearInterval(interval)
  }, [engagementId])

  const fetchEngagements = async () => {
    setLoadingEngagements(true)
    try {
      const res = await api.get<Engagement[]>('/engagements')
      setEngagements(res.data)
      const currentId = localStorage.getItem('engagement_id');
      if (currentId && res.data.some(e => e.id === currentId)) {
        setEngagementId(currentId);
      } else if (res.data.length > 0) {
        setEngagementId(res.data[0].id)
      }
    } catch (err: any) {
      const status = err.response?.status ? `[HTTP ${err.response.status}] ` : ''
      const detail = err.response?.data?.detail || err.message || 'Failed to fetch engagements'
      setError(`${status}${typeof detail === 'object' ? JSON.stringify(detail) : detail}`)
    } finally {
      setLoadingEngagements(false)
    }
  }

  const handleCreateEngagement = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newEngagementName.trim()) return
    setCreatingEngagement(true)
    setError(null)
    try {
      const res = await api.post<Engagement>('/engagements', { name: newEngagementName.trim() })
      const created = res.data
      setEngagements(prev => [...prev, created])
      setEngagementId(created.id)
      setNewEngagementName('')
      setShowCreateForm(false)
    } catch (err: any) {
      const status = err.response?.status ? `[HTTP ${err.response.status}] ` : ''
      const detail = err.response?.data?.detail || err.message || 'Failed to create engagement'
      setError(`${status}${typeof detail === 'object' ? JSON.stringify(detail) : detail}`)
    } finally {
      setCreatingEngagement(false)
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0])
      setError(null)
      setResult(null)
    }
  }

  const handleRetrain = async () => {
    if (!engagementId) return
    setRetraining(true)
    setError(null)
    try {
      await api.post(`/gat/retrain?engagement_id=${engagementId}`)
    } catch (err: any) {
      const status = err.response?.status ? `[HTTP ${err.response.status}] ` : ''
      const detail = err.response?.data?.detail || err.message || 'Retrain failed'
      setError(`${status}${typeof detail === 'object' ? JSON.stringify(detail) : detail}`)
    } finally {
      setRetraining(false)
    }
  }

  const handleUpload = async () => {
    if (!file || !engagementId) return

    setUploading(true)
    setError(null)
    setResult(null)

    const formData = new FormData()
    formData.append('file', file)
    formData.append('engagement_id', engagementId)

    try {
      const response = await api.post<IngestResponse>('/ingest/bloodhound', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })
      setResult(response.data)
    } catch (err: any) {
      const status = err.response?.status ? `[HTTP ${err.response.status}] ` : ''
      const detail = err.response?.data?.detail || err.message || 'An unexpected error occurred during ingestion.'
      setError(`${status}${typeof detail === 'object' ? JSON.stringify(detail) : detail}`)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="dashboard">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="pulse-dot" /> DATA PIPELINE</div>
          <h1>BloodHound Ingestion</h1>
          <p>Import SharpHound collections to build your security graph.</p>
        </div>
      </div>

      <div className="content-grid">
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Upload Collection</h2>
              <p>SharpHound v6 ZIP archive or JSON files</p>
            </div>
          </div>

          <div className="mt-6 space-y-6">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-[10px] font-bold uppercase tracking-wider text-[#465668]">Engagement</label>
                {engagements.length > 0 && !showCreateForm && (
                  <button 
                    onClick={() => setShowCreateForm(true)}
                    className="text-xs text-green-500 hover:underline flex items-center gap-1 font-medium"
                  >
                    <Plus size={12} /> New Engagement
                  </button>
                )}
              </div>

              {loadingEngagements ? (
                <div className="w-full bg-[#14202d] border border-[#1d2a39] rounded-lg px-3 py-2 text-sm text-[#718096] flex items-center gap-2">
                  <Loader2 className="animate-spin" size={16} /> Loading engagements...
                </div>
              ) : engagements.length === 0 || showCreateForm ? (
                <div className="p-4 bg-[#14202d] border border-green-500/30 rounded-lg space-y-3">
                  <p className="text-xs font-medium text-orange-400">
                    {engagements.length === 0 ? "No engagements, create one" : "Create new engagement"}
                  </p>
                  <form onSubmit={handleCreateEngagement} className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Engagement name..."
                      value={newEngagementName}
                      onChange={(e) => setNewEngagementName(e.target.value)}
                      className="flex-1 bg-[#0d141e] border border-[#1d2a39] rounded-lg px-3 py-1.5 text-sm focus:border-green-500 outline-none"
                    />
                    <Button type="submit" size="sm" disabled={creatingEngagement || !newEngagementName.trim()}>
                      {creatingEngagement ? <Loader2 className="animate-spin" size={14} /> : 'Create'}
                    </Button>
                    {engagements.length > 0 && (
                      <Button type="button" variant="ghost" size="sm" onClick={() => setShowCreateForm(false)}>
                        Cancel
                      </Button>
                    )}
                  </form>
                </div>
              ) : (
                <select
                  value={engagementId}
                  onChange={(e) => setEngagementId(e.target.value)}
                  className="w-full bg-[#14202d] border border-[#1d2a39] rounded-lg px-3 py-2 text-sm focus:border-green-500 outline-none transition-colors"
                >
                  {engagements.map((eng) => (
                    <option key={eng.id} value={eng.id}>
                      {eng.name} ({eng.id.slice(0, 8)}...)
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div 
              className={cn(
                "border-2 border-dashed rounded-xl p-10 flex flex-col items-center justify-center text-center transition-colors",
                file ? "border-green-500/50 bg-green-500/5" : "border-[#1d2a39] hover:border-[#35d399]/50"
              )}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault()
                if (e.dataTransfer.files?.[0]) {
                  setFile(e.dataTransfer.files[0])
                  setError(null)
                  setResult(null)
                }
              }}
            >
              <div className="w-12 h-12 rounded-full bg-[#1d2a39] flex items-center justify-center mb-4 text-[#718096]">
                {file ? <FileUp className="text-green-500" /> : <Upload />}
              </div>
              
              {file ? (
                <div className="space-y-1">
                  <p className="text-sm font-medium">{file.name}</p>
                  <p className="text-xs text-[#718096]">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                  <button onClick={() => setFile(null)} className="text-xs text-red-400 hover:underline mt-2">Remove file</button>
                </div>
              ) : (
                <div className="space-y-1">
                  <p className="text-sm font-medium">Drag and drop or <span className="text-green-500 cursor-pointer" onClick={() => document.getElementById('file-input')?.click()}>browse</span></p>
                  <p className="text-xs text-[#718096]">Supports .zip and .json</p>
                </div>
              )}
              <input id="file-input" type="file" className="hidden" accept=".zip,.json" onChange={handleFileChange} />
            </div>

            <Button 
              className="w-full h-10 font-bold" 
              disabled={!file || !engagementId || uploading} 
              onClick={handleUpload}
            >
              {uploading ? (
                <><Loader2 className="animate-spin mr-2" /> Ingesting Data...</>
              ) : (
                <><Database className="mr-2" /> Start Ingestion</>
              )}
            </Button>

            <div className="pt-4 border-t border-[#1d2a39]/50">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-[#465668]">Graph Neural Network</h3>
                <Button 
                  size="sm" 
                  variant="outline"
                  disabled={!engagementId || retraining || gatStatus?.status === 'training'}
                  onClick={handleRetrain}
                >
                  {retraining || gatStatus?.status === 'training' ? (
                    <><Loader2 className="animate-spin mr-1" size={14} /> Training...</>
                  ) : (
                    <><Brain className="mr-1" size={14} /> Retrain Model</>
                  )}
                </Button>
              </div>
              <div className="p-3 bg-[#14202d] rounded-lg border border-[#1d2a39] text-xs space-y-1">
                <div className="flex justify-between">
                  <span className="text-[#718096]">Status</span>
                  <span className={gatStatus?.status === 'ready' ? 'text-green-400' : gatStatus?.status === 'training' ? 'text-yellow-400' : 'text-[#718096]'}>
                    {gatStatus?.status || 'unknown'}
                  </span>
                </div>
                {gatStatus?.last_updated && (
                  <div className="flex justify-between">
                    <span className="text-[#718096]">Last updated</span>
                    <span>{new Date(gatStatus.last_updated).toLocaleString()}</span>
                  </div>
                )}
                {gatStatus?.error && (
                  <div className="text-red-400">Error: {gatStatus.error}</div>
                )}
              </div>
            </div>

            {error && (
              <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg flex gap-3 items-start">
                <AlertCircle className="text-red-500 shrink-0 mt-0.5" size={16} />
                <div className="text-xs text-red-400 font-medium whitespace-pre-wrap">{error}</div>
              </div>
            )}
          </div>
        </section>

        <section className="panel flex flex-col">
          <div className="panel-header">
            <div>
              <h2>Ingestion Results</h2>
              <p>Details from the latest operation</p>
            </div>
          </div>

          {!result && !uploading && (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-10 opacity-50">
              <Info size={32} className="mb-4 text-[#718096]" />
              <p className="text-sm">No ingestion data to display</p>
              <p className="text-xs text-[#718096] mt-1">Upload a collection to see the summary</p>
            </div>
          )}

          {uploading && (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-10">
              <Loader2 size={32} className="mb-4 text-green-500 animate-spin" />
              <p className="text-sm">Processing security graph...</p>
              <p className="text-xs text-[#718096] mt-1">This may take a moment for large collections</p>
            </div>
          )}

          {result && (
            <div className="flex-1 mt-6 space-y-6 animate-in fade-in slide-in-from-bottom-4">
              <div className={cn(
                "p-4 rounded-lg flex items-center gap-3",
                result.status === 'success' ? "bg-green-500/10 border border-green-500/20" : "bg-orange-500/10 border border-orange-500/20"
              )}>
                {result.status === 'success' ? (
                  <CheckCircle2 className="text-green-500" size={20} />
                ) : (
                  <AlertCircle className="text-orange-500" size={20} />
                )}
                <div>
                  <p className="text-sm font-bold capitalize">{result.status}</p>
                  <p className="text-xs text-[#718096]">{result.message}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 bg-[#14202d] rounded-lg border border-[#1d2a39]">
                  <p className="text-[10px] font-bold text-[#718096] uppercase mb-2">Nodes Ingested</p>
                  <p className="text-2xl font-bold">{Object.values(result.nodes_ingested).reduce((a, b) => a + b, 0).toLocaleString()}</p>
                </div>
                <div className="p-4 bg-[#14202d] rounded-lg border border-[#1d2a39]">
                  <p className="text-[10px] font-bold text-[#718096] uppercase mb-2">Relationships</p>
                  <p className="text-2xl font-bold">{Object.values(result.relationships_ingested).reduce((a, b) => a + b, 0).toLocaleString()}</p>
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-[#465668] mb-3">Breakdown</h3>
                  <div className="space-y-2">
                    {Object.entries(result.nodes_ingested).filter(([_, count]) => count > 0).map(([type, count]) => (
                      <div key={type} className="flex items-center justify-between text-xs p-2 bg-[#0d141e] rounded border border-[#1d2a39]/50">
                        <span className="text-[#aab9c9]">{type}</span>
                        <span className="font-mono text-green-500">{count.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {result.skipped_ace_types.length > 0 && (
                  <div>
                    <h3 className="text-xs font-bold uppercase tracking-wider text-[#465668] mb-2">Skipped ACE Types</h3>
                    <div className="flex flex-wrap gap-2">
                      {result.skipped_ace_types.map(ace => (
                        <span key={ace} className="px-2 py-1 bg-[#1d2a39] rounded text-[10px] text-[#718096]">{ace}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {engagementId && gatStatus && (
            <div className="mt-8 pt-6 border-t border-[#1d2a39]/50">
              <h3 className="text-xs font-bold uppercase tracking-wider text-[#465668] mb-4">Model Training</h3>
              <div className={cn(
                "p-4 rounded-lg border",
                gatStatus.status === 'ready' ? "bg-green-500/10 border-green-500/20" :
                gatStatus.status === 'training' ? "bg-yellow-500/10 border-yellow-500/20" :
                gatStatus.status === 'failed' ? "bg-red-500/10 border-red-500/20" :
                "bg-[#14202d] border-[#1d2a39]"
              )}>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs text-[#718096]">Status</span>
                  <span className={cn(
                    "text-xs font-bold capitalize",
                    gatStatus.status === 'ready' && 'text-green-400',
                    gatStatus.status === 'training' && 'text-yellow-400',
                    gatStatus.status === 'failed' && 'text-red-400'
                  )}>
                    {gatStatus.status || 'unknown'}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-[10px] font-bold text-[#718096] uppercase mb-1">Nodes</p>
                    <p className="text-lg font-bold">{gatStatus.node_count?.toLocaleString() ?? '—'}</p>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold text-[#718096] uppercase mb-1">Edges</p>
                    <p className="text-lg font-bold">{gatStatus.edge_count?.toLocaleString() ?? '—'}</p>
                  </div>
                </div>
                {(gatStatus.trained_at || gatStatus.started_at || gatStatus.completed_at) && (
                  <div className="mt-3 pt-3 border-t border-[#1d2a39]/50 text-xs text-[#718096] space-y-1">
                    {gatStatus.trained_at && (
                      <div className="flex justify-between">
                        <span>Trained at</span>
                        <span className="text-[#aab9c9]">{new Date(gatStatus.trained_at).toLocaleString()}</span>
                      </div>
                    )}
                    {gatStatus.started_at && (
                      <div className="flex justify-between">
                        <span>Started at</span>
                        <span className="text-[#aab9c9]">{new Date(gatStatus.started_at).toLocaleString()}</span>
                      </div>
                    )}
                    {gatStatus.completed_at && (
                      <div className="flex justify-between">
                        <span>Completed at</span>
                        <span className="text-[#aab9c9]">{new Date(gatStatus.completed_at).toLocaleString()}</span>
                      </div>
                    )}
                  </div>
                )}
                {gatStatus.error && (
                  <div className="mt-3 text-xs text-red-400">Error: {gatStatus.error}</div>
                )}
              </div>
            </div>
          )}
        </section>
      </div>

      <section className="panel mt-4 hidden">
        <div className="panel-header">
          <div>
            <h2>Knowledge Base</h2>
            <p>How to use BloodHound data</p>
          </div>
        </div>
        <div className="quick-actions">
          <button onClick={() => {}}>
            <div className="quick-icon cyan"><GitBranch size={19} /></div>
            <span><strong>Map Attack Paths</strong><small>Visualize your security graph</small></span>
            <ChevronRight size={16} />
          </button>
          <button onClick={() => {}}>
            <div className="quick-icon purple"><Search size={19} /></div>
            <span><strong>Query Assets</strong><small>Search for specific identities</small></span>
            <ChevronRight size={16} />
          </button>
          <button onClick={() => {}}>
            <div className="quick-icon blue"><X size={19} /></div>
            <span><strong>Purge Workspace</strong><small>Reset your current engagement</small></span>
            <ChevronRight size={16} />
          </button>
        </div>
      </section>
    </div>
  )
}

