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
  TrendingUp,
  Cpu,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from 'recharts';

// ── Types ──────────────────────────────────────────────────────────────────────

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

// ── Custom tooltip ─────────────────────────────────────────────────────────────
const CustomTooltip = ({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: any[];
  label?: string;
}) => {
  if (!active || !payload?.length) return null;
  const item = payload[0];
  const rank = item.payload?.rank;
  return (
    <div
      style={{
        background: '#0c1120',
        border: '1px solid rgba(34,211,238,0.35)',
        borderRadius: 10,
        padding: '12px 16px',
        boxShadow: '0 8px 32px rgba(0,0,0,0.8)',
        pointerEvents: 'none',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14, marginBottom: 6 }}>
        <span style={{ color: '#cbd5e1', fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          Gateway …{label}
        </span>
        {rank !== undefined && (
          <span
            style={{
              fontSize: 10,
              fontWeight: 800,
              padding: '2px 7px',
              borderRadius: 4,
              background:
                rank === 1
                  ? 'rgba(244,63,94,0.25)'
                  : rank <= 3
                  ? 'rgba(249,115,22,0.25)'
                  : rank <= 5
                  ? 'rgba(245,158,11,0.25)'
                  : 'rgba(34,211,238,0.2)',
              color:
                rank === 1
                  ? '#f43f5e'
                  : rank <= 3
                  ? '#f97316'
                  : rank <= 5
                  ? '#f59e0b'
                  : '#22d3ee',
            }}
          >
            Rank #{rank}
          </span>
        )}
      </div>
      <p style={{ color: '#ffffff', fontWeight: 800, fontSize: 19, margin: 0, fontFamily: 'JetBrains Mono, monospace' }}>
        {Number(item.value).toFixed(1)}
        <span style={{ color: '#22d3ee', fontWeight: 600, fontSize: 13, marginLeft: 8 }}>flagged hrs</span>
      </p>
    </div>
  );
};

// ── Stat Card ──────────────────────────────────────────────────────────────────
const StatCard = ({
  icon,
  label,
  value,
  accent = '#22d3ee',
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  accent?: string;
}) => (
  <div className="card-subtle" style={{ padding: '18px 20px', display: 'flex', alignItems: 'center', gap: 14 }}>
    <div
      style={{
        width: 44,
        height: 44,
        borderRadius: 12,
        background: `${accent}18`,
        border: `1px solid ${accent}30`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
      }}
    >
      {icon}
    </div>
    <div>
      <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 15, fontWeight: 800, color: '#f0f4ff' }}>{value}</div>
    </div>
  </div>
);

// ── Section header ─────────────────────────────────────────────────────────────
const SectionTitle = ({ icon, title, sub }: { icon: React.ReactNode; title: string; sub?: string }) => (
  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 20 }}>
    <div style={{ paddingTop: 2 }}>{icon}</div>
    <div>
      <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#f0f4ff' }}>{title}</h2>
      {sub && <p style={{ margin: '3px 0 0', fontSize: 12, color: '#64748b' }}>{sub}</p>}
    </div>
  </div>
);

// ── Main App ───────────────────────────────────────────────────────────────────
export function App() {
  const [activeTab, setActiveTab] = useState<'predictions' | 'registry' | 'rollback' | 'drift'>('predictions');

  const [predictionsData, setPredictionsData] = useState<Prediction[]>([]);
  const [availableWeeks, setAvailableWeeks] = useState<string[]>([]);
  const [selectedWeek, setSelectedWeek] = useState<string>('');
  const [registryVersions, setRegistryVersions] = useState<VersionInfo[]>([]);
  const [activeVersion, setActiveVersion] = useState<string>('');
  const [rollbackLogs, setRollbackLogs] = useState<RollbackEntry[]>([]);
  const [driftStatus, setDriftStatus] = useState<DriftReport | null>(null);
  const [consecutiveDriftWeeks, setConsecutiveDriftWeeks] = useState<number>(0);

  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [targetVersion, setTargetVersion] = useState<string>('');
  const [rollbackReason, setRollbackReason] = useState<string>('');
  const [actionFeedback, setActionFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [regRes, predRes, driftRes, rbRes] = await Promise.allSettled([
        fetch('/api/registry'),
        fetch('/api/predictions'),
        fetch('/api/drift/status'),
        fetch('/api/rollback/log'),
      ]);

      if (regRes.status === 'fulfilled' && regRes.value.ok) {
        const d = await regRes.value.json();
        setRegistryVersions(d.versions || []);
        setActiveVersion(d.active_version || '');
      }
      if (predRes.status === 'fulfilled' && predRes.value.ok) {
        const d = await predRes.value.json();
        setPredictionsData(d.predictions || []);
        setAvailableWeeks(d.available_weeks || []);
        if (!selectedWeek && d.available_weeks?.length > 0) setSelectedWeek(d.available_weeks[0]);
      }
      if (driftRes.status === 'fulfilled' && driftRes.value.ok) {
        const d = await driftRes.value.json();
        setDriftStatus(d.latest_report);
        setConsecutiveDriftWeeks(d.consecutive_flagged_weeks || 0);
      }
      if (rbRes.status === 'fulfilled' && rbRes.value.ok) {
        const d = await rbRes.value.json();
        setRollbackLogs(d.logs || []);
      }
    } catch (err) {
      console.error('Failed to load dashboard data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRollback = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetVersion || !rollbackReason) {
      setActionFeedback({ type: 'error', message: 'Select a version and provide an audit reason.' });
      return;
    }
    try {
      setActionLoading(true);
      const res = await fetch('/api/rollback/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to_version: targetVersion, reason: rollbackReason }),
      });
      if (res.ok) {
        setActionFeedback({ type: 'success', message: `Rolled back to ${targetVersion}. ACTIVE pointer updated.` });
        setRollbackReason('');
        await fetchData();
      } else {
        const err = await res.json();
        setActionFeedback({ type: 'error', message: err.detail || 'Rollback failed.' });
      }
    } catch {
      setActionFeedback({ type: 'error', message: 'Network error during rollback.' });
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
        setActionFeedback(
          data.verified
            ? { type: 'success', message: `PASS — ${data.version_id} SHA-256 matches fixed-slice hash.` }
            : { type: 'error', message: `FAIL — Hash mismatch on ${data.version_id}.` }
        );
      } else {
        setActionFeedback({ type: 'error', message: 'Verification endpoint error.' });
      }
    } catch {
      setActionFeedback({ type: 'error', message: 'Could not reach verification endpoint.' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleTriggerDrift = async () => {
    try {
      setActionLoading(true);
      const res = await fetch('/api/drift/run', { method: 'POST' });
      if (res.ok) {
        setActionFeedback({ type: 'success', message: 'Drift check complete. Report updated.' });
        await fetchData();
      }
    } catch {
      setActionFeedback({ type: 'error', message: 'Failed to run drift check.' });
    } finally {
      setActionLoading(false);
    }
  };

  const filteredPredictions = selectedWeek
    ? predictionsData.filter((p) => p.week_start === selectedWeek)
    : predictionsData.slice(0, 15);

  const chartData = filteredPredictions.map((p) => ({
    name: p.gateway_id.slice(-6),
    score: p.score,
    rank: p.rank,
    full_id: p.gateway_id,
  }));

  // ── Tab config ───────────────────────────────────────────────────────────────
  const TABS = [
    { id: 'predictions', label: 'Prioritized Visits', icon: <Activity size={14} /> },
    { id: 'registry',    label: 'Model Registry',     icon: <Database size={14} /> },
    { id: 'rollback',    label: 'Rollback Engine',    icon: <RotateCcw size={14} /> },
    { id: 'drift',       label: 'Drift Monitor',      icon: <ShieldCheck size={14} /> },
  ] as const;

  // ── Styles ───────────────────────────────────────────────────────────────────
  const S = {
    wrap: {
      minHeight: '100vh',
      background: '#06080f',
      display: 'flex',
      flexDirection: 'column' as const,
    },
    header: {
      position: 'sticky' as const,
      top: 0,
      zIndex: 50,
      background: 'rgba(6,8,15,0.9)',
      backdropFilter: 'blur(16px)',
      borderBottom: '1px solid rgba(255,255,255,0.07)',
      padding: '14px 28px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    pill: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      padding: '7px 14px',
      borderRadius: 10,
      background: '#0c1120',
      border: '1px solid rgba(255,255,255,0.08)',
      fontSize: 12,
      color: '#94a3b8',
    },
    main: {
      flex: 1,
      maxWidth: 1320,
      width: '100%',
      margin: '0 auto',
      padding: '24px 28px',
      display: 'flex',
      flexDirection: 'column' as const,
      gap: 20,
    },
  };

  const driftOk = !driftStatus?.drift_flagged;

  return (
    <div style={S.wrap}>
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header style={S.header}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          {/* Logo mark */}
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: 10,
              background: 'linear-gradient(135deg, #22d3ee, #3b82f6)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 18px rgba(34,211,238,0.3)',
            }}
          >
            <Radio size={18} color="#fff" />
          </div>
          <div>
            <div className="gradient-text" style={{ fontSize: 15, fontWeight: 800, letterSpacing: '-0.01em' }}>
              LPDG Gateway Prioritization
            </div>
            <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 1, fontWeight: 500 }}>
              MLOps Track · Autonomous Network Reliability Platform
            </div>
          </div>
        </div>

        {/* Right pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={S.pill}>
            <Layers size={13} color="#22d3ee" />
            <span style={{ color: '#94a3b8' }}>ACTIVE</span>
            <span className="font-mono" style={{ color: '#22d3ee', fontWeight: 600, fontSize: 11 }}>
              {activeVersion || '…'}
            </span>
          </div>

          <div style={S.pill}>
            {driftOk
              ? <CheckCircle2 size={13} color="#10b981" />
              : <AlertTriangle size={13} color="#f59e0b" />}
            <span style={{ color: '#94a3b8' }}>DRIFT</span>
            <span style={{ color: driftOk ? '#10b981' : '#f59e0b', fontWeight: 700, fontSize: 11 }}>
              {driftOk ? 'CLEAR' : 'FLAGGED'}
            </span>
          </div>

          <button
            onClick={fetchData}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 34,
              height: 34,
              borderRadius: 9,
              background: '#0c1120',
              border: '1px solid rgba(255,255,255,0.08)',
              cursor: 'pointer',
              color: '#94a3b8',
            }}
            title="Refresh"
          >
            <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
          </button>
        </div>
      </header>

      {/* ── Main ───────────────────────────────────────────────────────────── */}
      <main style={S.main}>
        {/* Tabs */}
        <div style={{ display: 'flex', gap: 6, borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: 16 }}>
          {TABS.map((t) => {
            const active = activeTab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 7,
                  padding: '8px 16px',
                  borderRadius: 9,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                  border: active ? '1px solid rgba(34,211,238,0.3)' : '1px solid transparent',
                  background: active ? 'rgba(34,211,238,0.08)' : 'transparent',
                  color: active ? '#22d3ee' : '#64748b',
                  transition: 'all 0.15s',
                }}
              >
                {t.icon}
                {t.label}
              </button>
            );
          })}
        </div>

        {/* Feedback Banner */}
        {actionFeedback && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '12px 18px',
              borderRadius: 12,
              fontSize: 13,
              fontWeight: 500,
              background: actionFeedback.type === 'success' ? 'rgba(16,185,129,0.1)' : 'rgba(244,63,94,0.1)',
              border: `1px solid ${actionFeedback.type === 'success' ? 'rgba(16,185,129,0.3)' : 'rgba(244,63,94,0.3)'}`,
              color: actionFeedback.type === 'success' ? '#10b981' : '#f43f5e',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {actionFeedback.type === 'success'
                ? <CheckCircle2 size={16} />
                : <AlertTriangle size={16} />}
              {actionFeedback.message}
            </div>
            <button
              onClick={() => setActionFeedback(null)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', fontSize: 11, opacity: 0.7, fontWeight: 600, letterSpacing: '0.05em' }}
            >
              DISMISS
            </button>
          </div>
        )}

        {/* ── TAB 1: PREDICTIONS ─────────────────────────────────────────── */}
        {activeTab === 'predictions' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Week selector */}
            <div className="surface" style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.07em', marginRight: 4 }}>
                  Week:
                </span>
                {availableWeeks.map((w) => (
                  <button
                    key={w}
                    onClick={() => setSelectedWeek(w)}
                    style={{
                      padding: '5px 12px',
                      borderRadius: 8,
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: 'pointer',
                      border: selectedWeek === w ? '1px solid rgba(34,211,238,0.45)' : '1px solid rgba(255,255,255,0.07)',
                      background: selectedWeek === w ? 'rgba(34,211,238,0.12)' : '#111827',
                      color: selectedWeek === w ? '#22d3ee' : '#94a3b8',
                      transition: 'all 0.15s',
                    }}
                  >
                    {w}
                  </button>
                ))}
              </div>

              <a
                href="/api/predictions/download"
                download="predictions.csv"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 7,
                  padding: '8px 16px',
                  borderRadius: 9,
                  fontSize: 12,
                  fontWeight: 700,
                  textDecoration: 'none',
                  background: '#111827',
                  border: '1px solid rgba(255,255,255,0.1)',
                  color: '#f0f4ff',
                  transition: 'background 0.15s',
                }}
              >
                <Download size={13} color="#22d3ee" />
                Export predictions.csv
              </a>
            </div>

            {/* Bar chart */}
            <div className="surface" style={{ padding: '20px 22px' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 18 }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#f0f4ff' }}>Top 15 Gateway Anomaly Scores</div>
                  <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 3 }}>Flagged hours beyond 3σ baseline · trailing 7 days</div>
                </div>
                <div className="font-mono" style={{ fontSize: 11, color: '#94a3b8', background: '#0c1120', padding: '5px 10px', borderRadius: 7, border: '1px solid rgba(255,255,255,0.08)' }}>
                  {selectedWeek}
                </div>
              </div>

              <div style={{ height: 220 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                    <XAxis
                      dataKey="name"
                      stroke="rgba(255,255,255,0.0)"
                      tick={{ fill: '#94a3b8', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <YAxis
                      stroke="rgba(255,255,255,0.0)"
                      tick={{ fill: '#94a3b8', fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <Tooltip
                      content={<CustomTooltip />}
                      cursor={false}
                      contentStyle={{
                        backgroundColor: '#0c1120',
                        borderColor: 'rgba(34, 211, 238, 0.35)',
                        borderRadius: 10,
                        boxShadow: '0 8px 32px rgba(0,0,0,0.8)',
                        color: '#ffffff',
                      }}
                      itemStyle={{
                        color: '#22d3ee',
                        fontWeight: 700,
                        fontSize: 14,
                      }}
                      labelStyle={{
                        color: '#cbd5e1',
                        fontWeight: 700,
                        fontSize: 12,
                      }}
                      formatter={(val: number) => [`${val.toFixed(1)} flagged hrs`, 'Score']}
                      labelFormatter={(label) => `Gateway …${label}`}
                    />
                    <Bar dataKey="score" radius={[5, 5, 0, 0]} maxBarSize={36}>
                      {chartData.map((entry, idx) => (
                        <Cell
                          key={`cell-${idx}`}
                          fill={
                            entry.rank === 1
                              ? '#f43f5e'
                              : entry.rank <= 3
                              ? '#f97316'
                              : entry.rank <= 5
                              ? '#f59e0b'
                              : '#22d3ee'
                          }
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Legend */}
              <div style={{ display: 'flex', gap: 18, marginTop: 12 }}>
                {[
                  { color: '#f43f5e', label: 'Critical (#1)' },
                  { color: '#f97316', label: 'High (#2–3)' },
                  { color: '#f59e0b', label: 'Elevated (#4–5)' },
                  { color: '#22d3ee', label: 'Monitored (#6–15)' },
                ].map(({ color, label }) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ width: 10, height: 10, borderRadius: 3, background: color }} />
                    <span style={{ fontSize: 11, color: '#94a3b8', fontWeight: 500 }}>{label}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Ranked table */}
            <div className="surface" style={{ overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: '#f0f4ff' }}>
                  Recommended Site Visits — Ranked 1 to 15
                </div>
                <div style={{ fontSize: 11, color: '#94a3b8', fontWeight: 600 }}>Hard cap: exactly 15 visits / week</div>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th style={{ width: 56 }}>Rank</th>
                      <th>Gateway ID</th>
                      <th>Site / Region</th>
                      <th>Hardware</th>
                      <th>Meters</th>
                      <th>Score</th>
                      <th>Operational Rationale</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPredictions.map((p) => (
                      <tr key={`${p.week_start}-${p.rank}`}>
                        <td>
                          <span className={p.rank === 1 ? 'rank-1' : p.rank <= 3 ? 'rank-top' : 'rank-normal'}>
                            {p.rank}
                          </span>
                        </td>
                        <td>
                          <span className="font-mono" style={{ color: '#22d3ee', fontWeight: 600, fontSize: 12 }}>
                            {p.gateway_id}
                          </span>
                        </td>
                        <td>
                          <div style={{ fontWeight: 600, color: '#e2e8f0', fontSize: 12 }}>{p.site_type || 'Unknown'}</div>
                          <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{p.region || '—'}</div>
                        </td>
                        <td style={{ color: '#94a3b8', fontSize: 12 }}>{p.hw_model || '—'}</td>
                        <td style={{ color: '#94a3b8', fontSize: 12 }}>
                          {p.n_meters_installed ? `${p.n_meters_installed} m` : '—'}
                        </td>
                        <td>
                          <span className="font-mono" style={{ color: '#f59e0b', fontWeight: 800, fontSize: 13 }}>
                            {p.score.toFixed(1)}
                          </span>
                        </td>
                        <td style={{ color: '#94a3b8', fontSize: 12, maxWidth: 340, lineHeight: 1.5 }}>{p.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ── TAB 2: MODEL REGISTRY ──────────────────────────────────────── */}
        {activeTab === 'registry' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <SectionTitle
              icon={<Database size={18} color="#22d3ee" />}
              title="Model Registry & Versions"
              sub="Versioned JSON artifacts with content signatures and deterministic scoring parameters."
            />

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
              <StatCard
                icon={<Database size={20} color="#22d3ee" />}
                label="Registered Versions"
                value={registryVersions.length}
                accent="#22d3ee"
              />
              <StatCard
                icon={<CheckCircle2 size={20} color="#10b981" />}
                label="Active Production"
                value={
                  <span className="font-mono" style={{ fontSize: 13, color: '#10b981' }}>
                    {activeVersion || '—'}
                  </span>
                }
                accent="#10b981"
              />
              <StatCard
                icon={<Cpu size={20} color="#6366f1" />}
                label="Scoring Architecture"
                value={<span style={{ fontSize: 13 }}>Rule-based 3σ Anomaly</span>}
                accent="#6366f1"
              />
              <StatCard
                icon={<TrendingUp size={20} color="#f59e0b" />}
                label="Rollback Events"
                value={rollbackLogs.length}
                accent="#f59e0b"
              />
            </div>

            <div className="surface" style={{ overflow: 'hidden' }}>
              <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#f0f4ff' }}>All Registered Versions</div>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Status</th>
                      <th>Version ID</th>
                      <th>Trained</th>
                      <th>Model Type</th>
                      <th>σ / Window</th>
                      <th>Training Hash</th>
                    </tr>
                  </thead>
                  <tbody>
                    {registryVersions.map((v) => (
                      <tr key={v.version_id}>
                        <td>
                          {v.is_active ? (
                            <span className="badge-active">
                              <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10b981', display: 'inline-block', animation: 'pulse 2s infinite' }} />
                              ACTIVE
                            </span>
                          ) : (
                            <span className="badge-archived">Archived</span>
                          )}
                        </td>
                        <td>
                          <span className="font-mono" style={{ color: '#22d3ee', fontWeight: 700, fontSize: 12 }}>
                            {v.version_id}
                          </span>
                        </td>
                        <td style={{ color: '#94a3b8', fontSize: 12 }}>{v.trained_at?.slice(0, 10)}</td>
                        <td style={{ color: '#94a3b8', fontSize: 12 }}>{v.model_type}</td>
                        <td>
                          <span className="font-mono" style={{ color: '#94a3b8', fontSize: 11 }}>
                            σ={v.parameters?.sigma ?? 3.0}  ·  {v.parameters?.baseline_days ?? 28}d
                          </span>
                        </td>
                        <td>
                          <span className="font-mono" style={{ color: '#94a3b8', fontSize: 11 }}>
                            {v.training_data_hash?.slice(0, 18)}…
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ── TAB 3: ROLLBACK ENGINE ─────────────────────────────────────── */}
        {activeTab === 'rollback' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 20 }}>
            {/* Action form */}
            <div className="surface" style={{ padding: '24px 22px', display: 'flex', flexDirection: 'column', gap: 18 }}>
              <SectionTitle
                icon={<RotateCcw size={17} color="#22d3ee" />}
                title="Rollback Controller"
                sub="Zero-downtime version swaps with cryptographic verification."
              />

              <form onSubmit={handleRollback} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#94a3b8', marginBottom: 7 }}>
                    Target Version
                  </label>
                  <select
                    value={targetVersion}
                    onChange={(e) => setTargetVersion(e.target.value)}
                    className="field font-mono"
                    required
                  >
                    <option value="">— Select version —</option>
                    {registryVersions.map((v) => (
                      <option key={v.version_id} value={v.version_id}>
                        {v.version_id}{v.is_active ? ' (ACTIVE)' : ''}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#94a3b8', marginBottom: 7 }}>
                    Audit Reason
                  </label>
                  <textarea
                    value={rollbackReason}
                    onChange={(e) => setRollbackReason(e.target.value)}
                    rows={3}
                    placeholder="e.g. v2 regressed on validation slice — hit rate dropped 8 pp"
                    className="field"
                    required
                  />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 9, paddingTop: 4 }}>
                  <button type="submit" disabled={actionLoading} className="btn-primary">
                    {actionLoading ? 'Executing…' : 'Execute Rollback'}
                  </button>
                  <button type="button" onClick={handleVerify} disabled={actionLoading} className="btn-ghost">
                    <ShieldCheck size={14} color="#6366f1" />
                    Verify Hash Match
                  </button>
                </div>
              </form>
            </div>

            {/* Audit log */}
            <div className="surface" style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              <div style={{ padding: '18px 22px', borderBottom: '1px solid rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', gap: 10 }}>
                <FileText size={16} color="#6366f1" />
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#f0f4ff' }}>Rollback Audit Trail</div>
                  <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>models/rollback_log.jsonl — append-only</div>
                </div>
              </div>
              <div style={{ overflowX: 'auto', flex: 1 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Timestamp (UTC)</th>
                      <th>From</th>
                      <th>To</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rollbackLogs.length === 0 ? (
                      <tr>
                        <td colSpan={4} style={{ textAlign: 'center', color: '#94a3b8', padding: '32px 0', fontStyle: 'italic' }}>
                          No rollback events recorded yet.
                        </td>
                      </tr>
                    ) : (
                      rollbackLogs.map((log, idx) => (
                        <tr key={idx}>
                          <td>
                            <span className="font-mono" style={{ color: '#64748b', fontSize: 11 }}>
                              {log.timestamp?.replace('T', ' ').slice(0, 19)}
                            </span>
                          </td>
                          <td>
                            <span className="font-mono" style={{ color: '#f43f5e', fontWeight: 600, fontSize: 12 }}>
                              {log.from_version}
                            </span>
                          </td>
                          <td>
                            <span className="font-mono" style={{ color: '#10b981', fontWeight: 700, fontSize: 12 }}>
                              {log.to_version}
                            </span>
                          </td>
                          <td style={{ color: '#94a3b8', fontSize: 12, lineHeight: 1.5 }}>{log.reason}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ── TAB 4: DRIFT MONITOR ───────────────────────────────────────── */}
        {activeTab === 'drift' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 14 }}>
              <SectionTitle
                icon={<ShieldCheck size={18} color={driftOk ? '#10b981' : '#f59e0b'} />}
                title="Drift Detection & Data Integrity"
                sub="Pre-inference checking of telemetry for schema, population, and distribution anomalies."
              />
              <button onClick={handleTriggerDrift} disabled={actionLoading} className="btn-primary" style={{ flexShrink: 0 }}>
                <RefreshCw size={13} style={{ animation: actionLoading ? 'spin 1s linear infinite' : 'none' }} />
                Run Drift Check
              </button>
            </div>

            {/* Status banner */}
            <div
              style={{
                padding: '18px 22px',
                borderRadius: 14,
                border: `1px solid ${driftOk ? 'rgba(16,185,129,0.3)' : 'rgba(245,158,11,0.3)'}`,
                background: driftOk ? 'rgba(16,185,129,0.07)' : 'rgba(245,158,11,0.07)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 14,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                {driftOk
                  ? <CheckCircle2 size={32} color="#10b981" />
                  : <AlertTriangle size={32} color="#f59e0b" />}
                <div>
                  <div style={{ fontSize: 15, fontWeight: 800, color: driftOk ? '#10b981' : '#f59e0b' }}>
                    {driftOk ? 'SYSTEM HEALTHY — NO DRIFT DETECTED' : 'DRIFT FLAGGED'}
                  </div>
                  <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                    {driftStatus?.summary || 'All schemas, IDs, and distributions within expected bounds.'}
                  </div>
                  {driftStatus?.checked_at && (
                    <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 3 }}>
                      Last checked: {driftStatus.checked_at.replace('T', ' ').slice(0, 19)} UTC
                    </div>
                  )}
                </div>
              </div>

              <div style={{ textAlign: 'center', padding: '10px 20px', borderRadius: 10, background: '#0c1120', border: '1px solid rgba(255,255,255,0.07)' }}>
                <div style={{ fontSize: 11, color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  Consecutive Flags
                </div>
                <div className="font-mono" style={{ fontSize: 28, fontWeight: 800, color: consecutiveDriftWeeks >= 3 ? '#f43f5e' : '#f0f4ff', marginTop: 4 }}>
                  {consecutiveDriftWeeks}<span style={{ fontSize: 16, color: '#94a3b8' }}>/3</span>
                </div>
                <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>triggers retrain</div>
              </div>
            </div>

            {/* Check detail cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 14 }}>
              {[
                {
                  title: 'Schema Invariants',
                  ok: !driftStatus?.missing_columns?.length && !driftStatus?.new_columns?.length,
                  detail: driftStatus?.missing_columns?.length
                    ? `Missing: ${driftStatus.missing_columns.join(', ')}`
                    : 'All 57 telemetry columns present.',
                },
                {
                  title: 'Gateway Population',
                  ok: (driftStatus?.new_gateway_id_pct ?? 0) < 0.05,
                  detail:
                    driftStatus?.new_gateway_id_pct
                      ? `${(driftStatus.new_gateway_id_pct * 100).toFixed(1)}% new IDs (threshold: 5%)`
                      : 'Population stable. Known gateway count verified.',
                },
                {
                  title: 'Distribution Range',
                  ok: driftOk,
                  detail: driftOk
                    ? 'All metric values within 5× training maximum.'
                    : 'One or more metrics exceed 5× historical maximum.',
                },
              ].map(({ title, ok, detail }) => (
                <div key={title} className="card-subtle" style={{ padding: '18px 20px' }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 12 }}>
                    {title}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 700, color: ok ? '#10b981' : '#f59e0b' }}>
                    {ok ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
                    {ok ? 'Normal' : 'Anomaly Detected'}
                  </div>
                  <div style={{ fontSize: 12, color: '#64748b', marginTop: 8, lineHeight: 1.6 }}>{detail}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
      `}</style>
    </div>
  );
}
