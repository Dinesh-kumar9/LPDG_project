import React, { useState, useEffect } from 'react';
import { Activity, RotateCcw, Database, Layers, CheckCircle2, AlertTriangle, RefreshCw, Radio, ShieldCheck } from 'lucide-react';

import {
  fetchRegistry, fetchPredictions, fetchDriftStatus,
  fetchRollbackLog, executeRollback, verifyRollback, triggerDriftCheck,
} from './api/client';
import type { Prediction, VersionInfo, RollbackEntry, DriftReport, ActionFeedback } from './types';
import { PredictionsTab } from './components/PredictionsTab';
import { RegistryTab } from './components/RegistryTab';
import { RollbackTab } from './components/RollbackTab';
import { DriftTab } from './components/DriftTab';

type Tab = 'predictions' | 'registry' | 'rollback' | 'drift';

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'predictions', label: 'Prioritized Visits', icon: <Activity size={14} /> },
  { id: 'registry',    label: 'Model Registry',     icon: <Database size={14} /> },
  { id: 'rollback',    label: 'Rollback Engine',    icon: <RotateCcw size={14} /> },
  { id: 'drift',       label: 'Drift Monitor',      icon: <ShieldCheck size={14} /> },
];

export function App() {
  const [activeTab, setActiveTab] = useState<Tab>('predictions');

  // ── Data state ─────────────────────────────────────────────────────────────
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [availableWeeks, setAvailableWeeks] = useState<string[]>([]);
  const [selectedWeek, setSelectedWeek] = useState<string>('');
  const [versions, setVersions] = useState<VersionInfo[]>([]);
  const [activeVersion, setActiveVersion] = useState<string>('');
  const [rollbackLogs, setRollbackLogs] = useState<RollbackEntry[]>([]);
  const [driftStatus, setDriftStatus] = useState<DriftReport | null>(null);
  const [consecutiveDriftWeeks, setConsecutiveDriftWeeks] = useState<number>(0);

  // ── UI state ───────────────────────────────────────────────────────────────
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [feedback, setFeedback] = useState<ActionFeedback | null>(null);
  const [targetVersion, setTargetVersion] = useState('');
  const [rollbackReason, setRollbackReason] = useState('');

  // ── Data fetch ─────────────────────────────────────────────────────────────
  const fetchAll = async () => {
    setLoading(true);
    const [reg, pred, drift, rb] = await Promise.allSettled([
      fetchRegistry(), fetchPredictions(), fetchDriftStatus(), fetchRollbackLog(),
    ]);
    if (reg.status === 'fulfilled') {
      setVersions(reg.value.versions ?? []);
      setActiveVersion(reg.value.active_version ?? '');
    }
    if (pred.status === 'fulfilled') {
      setPredictions(pred.value.predictions ?? []);
      setAvailableWeeks(pred.value.available_weeks ?? []);
      if (!selectedWeek && pred.value.available_weeks?.length) setSelectedWeek(pred.value.available_weeks[0]);
    }
    if (drift.status === 'fulfilled') {
      setDriftStatus(drift.value.latest_report);
      setConsecutiveDriftWeeks(drift.value.consecutive_flagged_weeks ?? 0);
    }
    if (rb.status === 'fulfilled') setRollbackLogs(rb.value.logs ?? []);
    setLoading(false);
  };

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 10_000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filteredPredictions = selectedWeek
    ? predictions.filter((p) => p.week_start === selectedWeek)
    : predictions.slice(0, 15);

  // ── Actions ────────────────────────────────────────────────────────────────
  const handleRollback = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetVersion || !rollbackReason) { setFeedback({ type: 'error', message: 'Select a version and provide an audit reason.' }); return; }
    setActionLoading(true);
    try {
      await executeRollback(targetVersion, rollbackReason);
      setFeedback({ type: 'success', message: `Rolled back to ${targetVersion}. ACTIVE pointer updated.` });
      setRollbackReason('');
      await fetchAll();
    } catch (err) {
      setFeedback({ type: 'error', message: (err as Error).message || 'Rollback failed.' });
    } finally { setActionLoading(false); }
  };

  const handleVerify = async () => {
    setActionLoading(true);
    try {
      const data = await verifyRollback();
      setFeedback(data.verified
        ? { type: 'success', message: `PASS — ${data.version_id} SHA-256 matches fixed-slice hash.` }
        : { type: 'error', message: `FAIL — Hash mismatch on ${data.version_id}.` });
    } catch (err) {
      setFeedback({ type: 'error', message: (err as Error).message || 'Verification error.' });
    } finally { setActionLoading(false); }
  };

  const handleTriggerDrift = async () => {
    setActionLoading(true);
    try {
      await triggerDriftCheck();
      setFeedback({ type: 'success', message: 'Drift check complete. Report updated.' });
      await fetchAll();
    } catch (err) {
      setFeedback({ type: 'error', message: (err as Error).message || 'Failed to run drift check.' });
    } finally { setActionLoading(false); }
  };

  const driftOk = !driftStatus?.drift_flagged;

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{ minHeight: '100vh', background: '#06080f', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <header style={{ position: 'sticky', top: 0, zIndex: 50, background: 'rgba(6,8,15,0.9)', backdropFilter: 'blur(16px)', borderBottom: '1px solid rgba(255,255,255,0.07)', padding: '14px 28px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ width: 38, height: 38, borderRadius: 10, background: 'linear-gradient(135deg, #22d3ee, #3b82f6)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 18px rgba(34,211,238,0.3)' }}>
            <Radio size={18} color="#fff" />
          </div>
          <div>
            <div className="gradient-text" style={{ fontSize: 15, fontWeight: 800, letterSpacing: '-0.01em' }}>LPDG Gateway Prioritization</div>
            <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 1, fontWeight: 500 }}>MLOps Track · Autonomous Network Reliability Platform</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 14px', borderRadius: 10, background: '#0c1120', border: '1px solid rgba(255,255,255,0.08)', fontSize: 12, color: '#94a3b8' }}>
            <Layers size={13} color="#22d3ee" />
            <span>ACTIVE</span>
            <span className="font-mono" style={{ color: '#22d3ee', fontWeight: 600, fontSize: 11 }}>{activeVersion || '…'}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 14px', borderRadius: 10, background: '#0c1120', border: '1px solid rgba(255,255,255,0.08)', fontSize: 12, color: '#94a3b8' }}>
            {driftOk ? <CheckCircle2 size={13} color="#10b981" /> : <AlertTriangle size={13} color="#f59e0b" />}
            <span>DRIFT</span>
            <span style={{ color: driftOk ? '#10b981' : '#f59e0b', fontWeight: 700, fontSize: 11 }}>{driftOk ? 'CLEAR' : 'FLAGGED'}</span>
          </div>
          <button onClick={fetchAll} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 34, height: 34, borderRadius: 9, background: '#0c1120', border: '1px solid rgba(255,255,255,0.08)', cursor: 'pointer', color: '#94a3b8' }} title="Refresh">
            <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
          </button>
        </div>
      </header>

      {/* Main */}
      <main style={{ flex: 1, maxWidth: 1320, width: '100%', margin: '0 auto', padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Tabs */}
        <div style={{ display: 'flex', gap: 6, borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: 16 }}>
          {TABS.map((t) => {
            const active = activeTab === t.id;
            return (
              <button key={t.id} onClick={() => setActiveTab(t.id)} style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '8px 16px', borderRadius: 9, fontSize: 13, fontWeight: 600, cursor: 'pointer', border: active ? '1px solid rgba(34,211,238,0.3)' : '1px solid transparent', background: active ? 'rgba(34,211,238,0.08)' : 'transparent', color: active ? '#22d3ee' : '#64748b', transition: 'all 0.15s' }}>
                {t.icon}{t.label}
              </button>
            );
          })}
        </div>

        {/* Feedback banner */}
        {feedback && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 18px', borderRadius: 12, fontSize: 13, fontWeight: 500, background: feedback.type === 'success' ? 'rgba(16,185,129,0.1)' : 'rgba(244,63,94,0.1)', border: `1px solid ${feedback.type === 'success' ? 'rgba(16,185,129,0.3)' : 'rgba(244,63,94,0.3)'}`, color: feedback.type === 'success' ? '#10b981' : '#f43f5e' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {feedback.type === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
              {feedback.message}
            </div>
            <button onClick={() => setFeedback(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', fontSize: 11, opacity: 0.7, fontWeight: 600, letterSpacing: '0.05em' }}>DISMISS</button>
          </div>
        )}

        {/* Tab views */}
        {activeTab === 'predictions' && <PredictionsTab predictions={filteredPredictions} availableWeeks={availableWeeks} selectedWeek={selectedWeek} onSelectWeek={setSelectedWeek} />}
        {activeTab === 'registry'    && <RegistryTab versions={versions} activeVersion={activeVersion} rollbackLogs={rollbackLogs} />}
        {activeTab === 'rollback'    && <RollbackTab versions={versions} rollbackLogs={rollbackLogs} targetVersion={targetVersion} rollbackReason={rollbackReason} actionLoading={actionLoading} onTargetChange={setTargetVersion} onReasonChange={setRollbackReason} onSubmit={handleRollback} onVerify={handleVerify} />}
        {activeTab === 'drift'       && <DriftTab driftStatus={driftStatus} consecutiveDriftWeeks={consecutiveDriftWeeks} actionLoading={actionLoading} onTriggerDrift={handleTriggerDrift} />}
      </main>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
      `}</style>
    </div>
  );
}
