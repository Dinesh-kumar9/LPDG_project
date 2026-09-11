import React from 'react';
import { Database, CheckCircle2, Cpu, TrendingUp } from 'lucide-react';
import { StatCard } from './StatCard';
import { SectionTitle } from './SectionTitle';
import type { VersionInfo, RollbackEntry } from '../types';

interface RegistryTabProps {
  versions: VersionInfo[];
  activeVersion: string;
  rollbackLogs: RollbackEntry[];
}

export const RegistryTab: React.FC<RegistryTabProps> = ({ versions, activeVersion, rollbackLogs }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
    <SectionTitle
      icon={<Database size={18} color="#22d3ee" />}
      title="Model Registry & Versions"
      sub="Versioned JSON artifacts with content signatures and deterministic scoring parameters."
    />

    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
      <StatCard icon={<Database size={20} color="#22d3ee" />} label="Registered Versions" value={versions.length} accent="#22d3ee" />
      <StatCard
        icon={<CheckCircle2 size={20} color="#10b981" />}
        label="Active Production"
        value={<span className="font-mono" style={{ fontSize: 13, color: '#10b981' }}>{activeVersion || '—'}</span>}
        accent="#10b981"
      />
      <StatCard icon={<Cpu size={20} color="#6366f1" />} label="Scoring Architecture" value={<span style={{ fontSize: 13 }}>Rule-based 3σ Anomaly</span>} accent="#6366f1" />
      <StatCard icon={<TrendingUp size={20} color="#f59e0b" />} label="Rollback Events" value={rollbackLogs.length} accent="#f59e0b" />
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
            {versions.map((v) => (
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
                <td><span className="font-mono" style={{ color: '#22d3ee', fontWeight: 700, fontSize: 12 }}>{v.version_id}</span></td>
                <td style={{ color: '#94a3b8', fontSize: 12 }}>{v.trained_at?.slice(0, 10)}</td>
                <td style={{ color: '#94a3b8', fontSize: 12 }}>{v.model_type}</td>
                <td><span className="font-mono" style={{ color: '#94a3b8', fontSize: 11 }}>σ={v.parameters?.sigma ?? 3.0}  ·  {v.parameters?.baseline_days ?? 28}d</span></td>
                <td><span className="font-mono" style={{ color: '#94a3b8', fontSize: 11 }}>{v.training_data_hash?.slice(0, 18)}…</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  </div>
);
