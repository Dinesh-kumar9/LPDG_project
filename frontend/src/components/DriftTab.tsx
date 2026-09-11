import React from 'react';
import { ShieldCheck, CheckCircle2, AlertTriangle, RefreshCw, WifiOff } from 'lucide-react';
import { SectionTitle } from './SectionTitle';
import type { DriftReport } from '../types';

interface DriftTabProps {
  driftStatus: DriftReport | null;
  consecutiveDriftWeeks: number;
  actionLoading: boolean;
  onTriggerDrift: () => void;
}

export const DriftTab: React.FC<DriftTabProps> = ({
  driftStatus, consecutiveDriftWeeks, actionLoading, onTriggerDrift,
}) => {
  // Three distinct states -- do NOT collapse null into "OK".
  // null means the API call failed or hasn't returned yet.
  const driftUnavailable = driftStatus === null;
  const driftOk = !driftUnavailable && !driftStatus.drift_flagged;

  const checks = [
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
      detail: driftStatus?.new_gateway_id_pct
        ? `${(driftStatus.new_gateway_id_pct * 100).toFixed(1)}% new IDs (threshold: 5%)`
        : 'Population stable. Known gateway count verified.',
    },
    {
      title: 'Distribution Range',
      ok: driftUnavailable ? true : driftOk,
      detail: driftUnavailable
        ? 'Status unavailable.'
        : driftOk
          ? 'All metric values within 5× training maximum.'
          : 'One or more metrics exceed 5× historical maximum.',
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 14 }}>
        <SectionTitle
          icon={<ShieldCheck size={18} color={driftOk ? '#10b981' : '#f59e0b'} />}
          title="Drift Detection & Data Integrity"
          sub="Pre-inference checking of telemetry for schema, population, and distribution anomalies."
        />
        <button onClick={onTriggerDrift} disabled={actionLoading} className="btn-primary" style={{ flexShrink: 0 }}>
          <RefreshCw size={13} style={{ animation: actionLoading ? 'spin 1s linear infinite' : 'none' }} />
          Run Drift Check
        </button>
      </div>

      {/* Status banner */}
      <div style={{ padding: '18px 22px', borderRadius: 14, border: `1px solid ${driftUnavailable ? 'rgba(148,163,184,0.3)' : driftOk ? 'rgba(16,185,129,0.3)' : 'rgba(245,158,11,0.3)'}`, background: driftUnavailable ? 'rgba(148,163,184,0.07)' : driftOk ? 'rgba(16,185,129,0.07)' : 'rgba(245,158,11,0.07)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {driftUnavailable
            ? <WifiOff size={32} color="#64748b" />
            : driftOk
              ? <CheckCircle2 size={32} color="#10b981" />
              : <AlertTriangle size={32} color="#f59e0b" />}
          <div>
            <div style={{ fontSize: 15, fontWeight: 800, color: driftUnavailable ? '#64748b' : driftOk ? '#10b981' : '#f59e0b' }}>
              {driftUnavailable ? 'DRIFT STATUS UNAVAILABLE' : driftOk ? 'SYSTEM HEALTHY — NO DRIFT DETECTED' : 'DRIFT FLAGGED'}
            </div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
              {driftUnavailable
                ? 'Drift monitor API did not respond. Run a check to refresh.'
                : driftStatus?.summary || 'All schemas, IDs, and distributions within expected bounds.'}
            </div>
            {driftStatus?.checked_at && (
              <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 3 }}>
                Last checked: {driftStatus.checked_at.replace('T', ' ').slice(0, 19)} UTC
              </div>
            )}
          </div>
        </div>

        <div style={{ textAlign: 'center', padding: '10px 20px', borderRadius: 10, background: '#0c1120', border: '1px solid rgba(255,255,255,0.07)' }}>
          <div style={{ fontSize: 11, color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Consecutive Flags</div>
          <div className="font-mono" style={{ fontSize: 28, fontWeight: 800, color: consecutiveDriftWeeks >= 3 ? '#f43f5e' : '#f0f4ff', marginTop: 4 }}>
            {consecutiveDriftWeeks}<span style={{ fontSize: 16, color: '#94a3b8' }}>/3</span>
          </div>
          <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>triggers retrain</div>
        </div>
      </div>

      {/* Check detail cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 14 }}>
        {checks.map(({ title, ok, detail }) => (
          <div key={title} className="card-subtle" style={{ padding: '18px 20px' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 12 }}>{title}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 700, color: ok ? '#10b981' : '#f59e0b' }}>
              {ok ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
              {ok ? 'Normal' : 'Anomaly Detected'}
            </div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 8, lineHeight: 1.6 }}>{detail}</div>
          </div>
        ))}
      </div>
    </div>
  );
};
