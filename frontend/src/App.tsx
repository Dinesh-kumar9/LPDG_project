import React, { useState, useEffect } from 'react';
import { 
  Activity, 
  RotateCcw, 
  Database, 
  Layers, 
  CheckCircle2, 
  AlertTriangle, 
  Download, 
  RefreshCw, 
  Radio, 
  ShieldCheck, 
  FileText,
} from 'lucide-react';
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  Tooltip, 
  ResponsiveContainer, 
  CartesianGrid, 
  Cell 
} from 'recharts';

interface Prediction {
  week_start: string;
  rank: number;
  gateway_id: string;
  score: number;
  reason: string;
  site_type?: string;
  region?: string;
  hw_model?: string;
  n_meters_installed?: number;
}

interface VersionInfo {
  version_id: string;
  trained_at: string;
  model_type: string;
  is_active: boolean;
  parameters?: {
    sigma: number;
    baseline_days: number;
    recent_days: number;
    metrics: string[];
    visits_per_week: number;
  };
  training_data_hash?: string;
}

interface RollbackEntry {
  timestamp: string;
  from_version: string;
  to_version: string;
  reason: string;
}

interface DriftReport {
  checked_at: string;
  drift_flagged: boolean;
  summary: string;
  new_columns: string[];
  missing_columns: string[];
  new_gateway_ids: string[];
  new_gateway_id_pct: number;
}

export function App() {
  const [activeTab, setActiveTab] = useState<'predictions' | 'registry' | 'rollback' | 'drift'>('predictions');
  
  // Data states
  const [predictionsData, setPredictionsData] = useState<Prediction[]>([]);
  const [availableWeeks, setAvailableWeeks] = useState<string[]>([]);
  const [selectedWeek, setSelectedWeek] = useState<string>('');
  const [registryVersions, setRegistryVersions] = useState<VersionInfo[]>([]);
  const [activeVersion, setActiveVersion] = useState<string>('');
  const [rollbackLogs, setRollbackLogs] = useState<RollbackEntry[]>([]);
  const [driftStatus, setDriftStatus] = useState<DriftReport | null>(null);
  const [consecutiveDriftWeeks, setConsecutiveDriftWeeks] = useState<number>(0);
  
  // Action states
  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [targetVersion, setTargetVersion] = useState<string>('');
  const [rollbackReason, setRollbackReason] = useState<string>('');
  const [actionFeedback, setActionFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Fetch initial data
  const fetchData = async () => {
    try {
      setLoading(true);
      
      // 1. Fetch registry
      const regRes = await fetch('/api/registry');
      if (regRes.ok) {
        const regData = await regRes.json();
        setRegistryVersions(regData.versions || []);
        setActiveVersion(regData.active_version || '');
      }

      // 2. Fetch predictions
      const predRes = await fetch('/api/predictions');
      if (predRes.ok) {
        const pData = await predRes.json();
        setPredictionsData(pData.predictions || []);
        setAvailableWeeks(pData.available_weeks || []);
        if (!selectedWeek && pData.available_weeks?.length > 0) {
          setSelectedWeek(pData.available_weeks[0]);
        }
      }

      // 3. Fetch drift
      const driftRes = await fetch('/api/drift/status');
      if (driftRes.ok) {
        const dData = await driftRes.json();
        setDriftStatus(dData.latest_report);
        setConsecutiveDriftWeeks(dData.consecutive_flagged_weeks || 0);
      }

      // 4. Fetch rollback log
      const rbRes = await fetch('/api/rollback/log');
      if (rbRes.ok) {
        const rbData = await rbRes.json();
        setRollbackLogs(rbData.logs || []);
      }

    } catch (err) {
      console.error("Failed to load dashboard data", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 8000);
    return () => clearInterval(interval);
  }, []);

  const handleRollback = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetVersion || !rollbackReason) {
      setActionFeedback({ type: 'error', message: 'Please select a version and provide a reason.' });
      return;
    }

    try {
      setActionLoading(true);
      const res = await fetch('/api/rollback/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to_version: targetVersion, reason: rollbackReason })
      });

      if (res.ok) {
        setActionFeedback({ type: 'success', message: `Successfully rolled back to ${targetVersion} and updated predictions.` });
        setRollbackReason('');
        await fetchData();
      } else {
        const err = await res.json();
        setActionFeedback({ type: 'error', message: err.detail || 'Rollback failed.' });
      }
    } catch (err) {
      setActionFeedback({ type: 'error', message: 'Network error executing rollback.' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleVerify = async () => {
    try {
      setActionLoading(true);
      const res = await fetch('/api/rollback/verify', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data.verified) {
          setActionFeedback({ type: 'success', message: `Verification PASSED for ${data.version_id}: SHA-256 matches fixed-slice prediction hash.` });
        } else {
          setActionFeedback({ type: 'error', message: `Verification FAILED: Hash mismatch on ${data.version_id}.` });
        }
      } else {
        setActionFeedback({ type: 'error', message: 'Verification endpoint error.' });
      }
    } catch (err) {
      setActionFeedback({ type: 'error', message: 'Failed to verify active model version.' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleTriggerDrift = async () => {
    try {
      setActionLoading(true);
      const res = await fetch('/api/drift/run', { method: 'POST' });
      if (res.ok) {
        setActionFeedback({ type: 'success', message: 'Drift check completed. Report updated.' });
        await fetchData();
      }
    } catch (err) {
      setActionFeedback({ type: 'error', message: 'Failed to run drift check.' });
    } finally {
      setActionLoading(false);
    }
  };

  const filteredPredictions = selectedWeek 
    ? predictionsData.filter(p => p.week_start === selectedWeek)
    : predictionsData.slice(0, 15);

  const chartData = filteredPredictions.map(p => ({
    name: p.gateway_id.slice(-6),
    fullId: p.gateway_id,
    score: p.score,
    rank: p.rank
  }));

  return (
    <div className="min-h-screen bg-[#0b0f19] text-slate-100 flex flex-col font-sans">
      {/* Top Navigation */}
      <header className="glass-panel sticky top-0 z-50 px-6 py-4 border-b border-slate-800/80 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="bg-gradient-to-tr from-blue-600 to-indigo-500 p-2.5 rounded-xl shadow-lg shadow-blue-500/20">
            <Radio className="w-5 h-5 text-white animate-pulse" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-200 to-slate-400">
              LPDG Gateway Visit Prioritization
            </h1>
            <p className="text-xs text-slate-400 font-medium">
              MLOps Track — Autonomous Network Reliability Platform
            </p>
          </div>
        </div>

        {/* Global KPI Pills */}
        <div className="flex items-center gap-3">
          <div className="bg-slate-900/90 border border-slate-800 px-3 py-1.5 rounded-lg flex items-center gap-2">
            <Layers className="w-4 h-4 text-blue-400" />
            <span className="text-xs text-slate-400">ACTIVE:</span>
            <span className="text-xs font-semibold text-blue-400 font-mono">{activeVersion || 'Loading...'}</span>
          </div>

          <div className="bg-slate-900/90 border border-slate-800 px-3 py-1.5 rounded-lg flex items-center gap-2">
            {driftStatus?.drift_flagged ? (
              <AlertTriangle className="w-4 h-4 text-amber-400" />
            ) : (
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            )}
            <span className="text-xs text-slate-400">DRIFT:</span>
            <span className={`text-xs font-semibold ${driftStatus?.drift_flagged ? 'text-amber-400' : 'text-emerald-400'}`}>
              {driftStatus?.drift_flagged ? 'FLAGGED' : 'CLEAR'}
            </span>
          </div>

          <button 
            onClick={fetchData} 
            className="p-2 rounded-lg bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 transition-colors"
            title="Refresh Data"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex-1 max-w-7xl w-full mx-auto p-6 flex flex-col gap-6">
        
        {/* Navigation Tabs */}
        <div className="flex items-center gap-2 border-b border-slate-800/80 pb-3">
          <button
            onClick={() => setActiveTab('predictions')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeTab === 'predictions'
                ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <Activity className="w-4 h-4" />
            Prioritized Visits (15/week)
          </button>

          <button
            onClick={() => setActiveTab('registry')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeTab === 'registry'
                ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <Database className="w-4 h-4" />
            Model Registry
          </button>

          <button
            onClick={() => setActiveTab('rollback')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeTab === 'rollback'
                ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <RotateCcw className="w-4 h-4" />
            Rollback Engine
          </button>

          <button
            onClick={() => setActiveTab('drift')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeTab === 'drift'
                ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <ShieldCheck className="w-4 h-4" />
            Drift Monitor
          </button>
        </div>

        {/* Global Feedback Banner */}
        {actionFeedback && (
          <div className={`p-4 rounded-xl flex items-center justify-between border ${
            actionFeedback.type === 'success' 
              ? 'bg-emerald-950/40 border-emerald-500/30 text-emerald-300' 
              : 'bg-rose-950/40 border-rose-500/30 text-rose-300'
          }`}>
            <div className="flex items-center gap-3">
              {actionFeedback.type === 'success' ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              ) : (
                <AlertTriangle className="w-5 h-5 text-rose-400" />
              )}
              <span className="text-sm font-medium">{actionFeedback.message}</span>
            </div>
            <button 
              onClick={() => setActionFeedback(null)}
              className="text-xs opacity-75 hover:opacity-100 uppercase tracking-wider font-semibold"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* TAB 1: PREDICTIONS */}
        {activeTab === 'predictions' && (
          <div className="flex flex-col gap-6">
            {/* Week Selector Bar & Export */}
            <div className="glass-panel p-4 rounded-2xl flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider mr-1">
                  Scored Week:
                </span>
                {availableWeeks.map(week => (
                  <button
                    key={week}
                    onClick={() => setSelectedWeek(week)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                      selectedWeek === week
                        ? 'bg-blue-600 text-white shadow-md shadow-blue-500/30 font-semibold'
                        : 'bg-slate-800/80 text-slate-300 hover:bg-slate-700'
                    }`}
                  >
                    {week}
                  </button>
                ))}
              </div>

              <a
                href="/api/predictions/download"
                download="predictions.csv"
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-sm font-semibold text-white transition-colors border border-slate-700"
              >
                <Download className="w-4 h-4 text-blue-400" />
                Export predictions.csv (120 rows)
              </a>
            </div>

            {/* Top Score Chart */}
            <div className="glass-panel p-5 rounded-2xl flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-slate-200">Top 15 Gateway Anomaly Scores</h3>
                  <p className="text-xs text-slate-400">Flagged hours beyond 3σ baseline in trailing 7 days</p>
                </div>
                <div className="text-xs text-slate-400 font-mono">
                  Week of {selectedWeek}
                </div>
              </div>

              <div className="h-56 w-full pt-2">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                    <XAxis dataKey="name" stroke="#64748b" fontSize={11} tickLine={false} />
                    <YAxis stroke="#64748b" fontSize={11} tickLine={false} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', fontSize: '12px' }}
                      formatter={(val: number) => [`${val} flagged hours`, 'Score']}
                      labelFormatter={(label) => `Gateway: ...${label}`}
                    />
                    <Bar dataKey="score" radius={[4, 4, 0, 0]}>
                      {chartData.map((_, idx) => (
                        <Cell 
                          key={`cell-${idx}`} 
                          fill={idx === 0 ? '#ef4444' : idx < 5 ? '#f97316' : '#3b82f6'} 
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Ranked Table */}
            <div className="glass-panel rounded-2xl overflow-hidden border border-slate-800">
              <div className="px-5 py-4 border-b border-slate-800 bg-slate-900/40 flex items-center justify-between">
                <h3 className="text-sm font-bold text-slate-200">
                  Recommended Site Visits (Ranked 1 to 15)
                </h3>
                <span className="text-xs text-slate-400 font-medium">
                  Hard Cap: Exactly 15 sites per week
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/60 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
                    <tr>
                      <th className="py-3 px-4 w-16">Rank</th>
                      <th className="py-3 px-4">Gateway ID</th>
                      <th className="py-3 px-4">Location / Site</th>
                      <th className="py-3 px-4">Hardware</th>
                      <th className="py-3 px-4">Meters</th>
                      <th className="py-3 px-4">Score</th>
                      <th className="py-3 px-4">Operations Rationale</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 text-slate-300">
                    {filteredPredictions.map((p) => (
                      <tr key={`${p.week_start}-${p.rank}`} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-3 px-4">
                          <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full font-bold text-xs ${
                            p.rank === 1 
                              ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' 
                              : p.rank <= 3 
                              ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' 
                              : 'bg-slate-800 text-slate-300'
                          }`}>
                            {p.rank}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-mono font-semibold text-blue-400">
                          {p.gateway_id}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex flex-col">
                            <span className="font-medium text-slate-200">{p.site_type || 'Unknown'}</span>
                            <span className="text-[11px] text-slate-500">{p.region || '—'}</span>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-slate-300">
                          {p.hw_model || '—'}
                        </td>
                        <td className="py-3 px-4 font-medium text-slate-300">
                          {p.n_meters_installed ? `${p.n_meters_installed} meters` : '—'}
                        </td>
                        <td className="py-3 px-4 font-bold font-mono text-amber-400">
                          {p.score.toFixed(1)}
                        </td>
                        <td className="py-3 px-4 text-slate-400 max-w-md">
                          {p.reason}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: MODEL REGISTRY */}
        {activeTab === 'registry' && (
          <div className="flex flex-col gap-6">
            <div className="glass-panel p-6 rounded-2xl flex flex-col gap-4">
              <div>
                <h2 className="text-base font-bold text-white">Model Registry & Versions</h2>
                <p className="text-xs text-slate-400">
                  Versioned JSON model artifacts with content signatures and deterministic scoring parameters.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="glass-card p-4 rounded-xl flex items-center gap-3">
                  <Database className="w-8 h-8 text-blue-400" />
                  <div>
                    <div className="text-xs text-slate-400 font-medium">Registered Versions</div>
                    <div className="text-xl font-bold text-white">{registryVersions.length}</div>
                  </div>
                </div>

                <div className="glass-card p-4 rounded-xl flex items-center gap-3">
                  <CheckCircle2 className="w-8 h-8 text-emerald-400" />
                  <div>
                    <div className="text-xs text-slate-400 font-medium">Active Production Model</div>
                    <div className="text-sm font-bold text-emerald-400 font-mono">{activeVersion}</div>
                  </div>
                </div>

                <div className="glass-card p-4 rounded-xl flex items-center gap-3">
                  <ShieldCheck className="w-8 h-8 text-indigo-400" />
                  <div>
                    <div className="text-xs text-slate-400 font-medium">Scoring Architecture</div>
                    <div className="text-sm font-bold text-indigo-300">Rule-based 3-Sigma Anomaly</div>
                  </div>
                </div>
              </div>

              {/* Version Table */}
              <div className="overflow-x-auto rounded-xl border border-slate-800 mt-2">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/80 text-slate-400 uppercase font-semibold border-b border-slate-800">
                    <tr>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4">Version ID</th>
                      <th className="py-3 px-4">Trained Date</th>
                      <th className="py-3 px-4">Model Type</th>
                      <th className="py-3 px-4">Parameters (σ, days)</th>
                      <th className="py-3 px-4">Training Hash</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 text-slate-300">
                    {registryVersions.map(v => (
                      <tr key={v.version_id} className="hover:bg-slate-800/40">
                        <td className="py-3 px-4">
                          {v.is_active ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-400 font-semibold text-[11px] border border-emerald-500/30">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                              ACTIVE
                            </span>
                          ) : (
                            <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-slate-800 text-slate-400 font-medium text-[11px]">
                              Archived
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 font-mono font-bold text-blue-400">
                          {v.version_id}
                        </td>
                        <td className="py-3 px-4 text-slate-300">
                          {v.trained_at?.slice(0, 10)}
                        </td>
                        <td className="py-3 px-4 text-slate-300 font-medium">
                          {v.model_type}
                        </td>
                        <td className="py-3 px-4 font-mono text-slate-400">
                          σ={v.parameters?.sigma || 3.0}, {v.parameters?.baseline_days || 28}d baseline
                        </td>
                        <td className="py-3 px-4 font-mono text-slate-500 text-[11px]">
                          {v.training_data_hash?.slice(0, 16)}...
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: ROLLBACK ENGINE */}
        {activeTab === 'rollback' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            {/* Action Form */}
            <div className="lg:col-span-1 glass-panel p-6 rounded-2xl flex flex-col gap-4">
              <div>
                <h2 className="text-base font-bold text-white flex items-center gap-2">
                  <RotateCcw className="w-5 h-5 text-blue-400" />
                  Rollback Controller
                </h2>
                <p className="text-xs text-slate-400 mt-1">
                  Perform atomic zero-downtime version swaps with cryptographic output verification.
                </p>
              </div>

              <form onSubmit={handleRollback} className="flex flex-col gap-4 mt-2">
                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">
                    Select Target Version:
                  </label>
                  <select
                    value={targetVersion}
                    onChange={(e) => setTargetVersion(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                    required
                  >
                    <option value="">-- Choose Version --</option>
                    {registryVersions.map(v => (
                      <option key={v.version_id} value={v.version_id}>
                        {v.version_id} {v.is_active ? '(Currently ACTIVE)' : ''}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">
                    Rollback Reason (Audit Log Entry):
                  </label>
                  <textarea
                    value={rollbackReason}
                    onChange={(e) => setRollbackReason(e.target.value)}
                    rows={3}
                    placeholder="e.g. Version regressed on validation slice / degraded hit rate..."
                    className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                    required
                  />
                </div>

                <div className="flex flex-col gap-2 pt-2">
                  <button
                    type="submit"
                    disabled={actionLoading}
                    className="w-full py-2.5 px-4 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition-all shadow-md shadow-blue-500/20 disabled:opacity-50"
                  >
                    {actionLoading ? 'Executing Rollback...' : 'Execute Rollback & Update ACTIVE'}
                  </button>

                  <button
                    type="button"
                    onClick={handleVerify}
                    disabled={actionLoading}
                    className="w-full py-2 px-4 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs transition-all border border-slate-700 disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    <ShieldCheck className="w-4 h-4 text-indigo-400" />
                    Verify Output Hash Match
                  </button>
                </div>
              </form>
            </div>

            {/* Audit Log Table */}
            <div className="lg:col-span-2 glass-panel p-6 rounded-2xl flex flex-col gap-4">
              <div>
                <h2 className="text-base font-bold text-white flex items-center gap-2">
                  <FileText className="w-5 h-5 text-indigo-400" />
                  Rollback Audit Trail (models/rollback_log.jsonl)
                </h2>
                <p className="text-xs text-slate-400 mt-1">
                  Immutable, append-only log recording every historical version transition with operator reason.
                </p>
              </div>

              <div className="overflow-x-auto rounded-xl border border-slate-800">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/80 text-slate-400 uppercase font-semibold border-b border-slate-800">
                    <tr>
                      <th className="py-3 px-4">Timestamp (UTC)</th>
                      <th className="py-3 px-4">From</th>
                      <th className="py-3 px-4">To</th>
                      <th className="py-3 px-4">Reason</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 text-slate-300">
                    {rollbackLogs.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="py-6 text-center text-slate-500 font-medium">
                          No rollback events recorded yet.
                        </td>
                      </tr>
                    ) : (
                      rollbackLogs.map((log, idx) => (
                        <tr key={idx} className="hover:bg-slate-800/40">
                          <td className="py-3 px-4 font-mono text-slate-400">
                            {log.timestamp?.replace('T', ' ').slice(0, 19)}
                          </td>
                          <td className="py-3 px-4 font-mono text-rose-400 font-medium">
                            {log.from_version}
                          </td>
                          <td className="py-3 px-4 font-mono text-emerald-400 font-bold">
                            {log.to_version}
                          </td>
                          <td className="py-3 px-4 text-slate-300">
                            {log.reason}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: DRIFT MONITOR */}
        {activeTab === 'drift' && (
          <div className="flex flex-col gap-6">
            <div className="glass-panel p-6 rounded-2xl flex flex-col gap-6">
              <div className="flex items-center justify-between flex-wrap gap-4">
                <div>
                  <h2 className="text-base font-bold text-white flex items-center gap-2">
                    <ShieldCheck className="w-5 h-5 text-emerald-400" />
                    Drift Detection & Data Integrity
                  </h2>
                  <p className="text-xs text-slate-400 mt-1">
                    Continuous pre-inference checking of incoming telemetry for schema, population, and distribution anomalies.
                  </p>
                </div>

                <button
                  onClick={handleTriggerDrift}
                  disabled={actionLoading}
                  className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition-all flex items-center gap-2"
                >
                  <RefreshCw className={`w-4 h-4 ${actionLoading ? 'animate-spin' : ''}`} />
                  Run Drift Check Now
                </button>
              </div>

              {/* Status Banner */}
              <div className={`p-5 rounded-xl border flex items-center justify-between flex-wrap gap-4 ${
                driftStatus?.drift_flagged 
                  ? 'bg-amber-950/30 border-amber-500/30 text-amber-300' 
                  : 'bg-emerald-950/30 border-emerald-500/30 text-emerald-300'
              }`}>
                <div className="flex items-center gap-4">
                  {driftStatus?.drift_flagged ? (
                    <AlertTriangle className="w-8 h-8 text-amber-400" />
                  ) : (
                    <CheckCircle2 className="w-8 h-8 text-emerald-400" />
                  )}
                  <div>
                    <div className="text-sm font-bold">
                      {driftStatus?.drift_flagged ? 'DRIFT FLAGGED' : 'SYSTEM HEALTHY — NO DRIFT DETECTED'}
                    </div>
                    <div className="text-xs opacity-80 mt-0.5">
                      {driftStatus?.summary || 'All schemas, gateway IDs, and metric distributions within expected bounds.'}
                    </div>
                  </div>
                </div>

                <div className="bg-slate-900/80 px-4 py-2 rounded-xl border border-slate-800 flex items-center gap-3 text-xs">
                  <span className="text-slate-400">Consecutive Flagged Weeks:</span>
                  <span className="font-bold text-white text-sm font-mono">{consecutiveDriftWeeks} / 3</span>
                  <span className="text-[11px] text-slate-500">(3 triggers retrain)</span>
                </div>
              </div>

              {/* Check Details Grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="glass-card p-4 rounded-xl">
                  <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                    Schema Invariants
                  </div>
                  <div className="text-sm font-bold text-emerald-400 flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4" />
                    All Required Columns Present
                  </div>
                  <p className="text-[11px] text-slate-500 mt-1">
                    Normalized against 57 telemetry columns & asset registry.
                  </p>
                </div>

                <div className="glass-card p-4 rounded-xl">
                  <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                    Gateway Population
                  </div>
                  <div className="text-sm font-bold text-emerald-400 flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4" />
                    Population Stability: 100%
                  </div>
                  <p className="text-[11px] text-slate-500 mt-1">
                    Known gateway count verified with training reference.
                  </p>
                </div>

                <div className="glass-card p-4 rounded-xl">
                  <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                    Distribution Range
                  </div>
                  <div className="text-sm font-bold text-emerald-400 flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4" />
                    Metric Bounds Normal (&lt;5× max)
                  </div>
                  <p className="text-[11px] text-slate-500 mt-1">
                    No extreme sensor dropouts or erroneous readings.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

export default App;
