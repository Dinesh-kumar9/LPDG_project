import React from 'react';
import { RotateCcw, ShieldCheck, FileText } from 'lucide-react';
import { SectionTitle } from './SectionTitle';
import type { VersionInfo, RollbackEntry } from '../types';

interface RollbackTabProps {
  versions: VersionInfo[];
  rollbackLogs: RollbackEntry[];
  targetVersion: string;
  rollbackReason: string;
  actionLoading: boolean;
  onTargetChange: (v: string) => void;
  onReasonChange: (v: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  onVerify: () => void;
}

export const RollbackTab: React.FC<RollbackTabProps> = ({
  versions, rollbackLogs, targetVersion, rollbackReason,
  actionLoading, onTargetChange, onReasonChange, onSubmit, onVerify,
}) => (
  <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 20 }}>
    {/* Action form */}
    <div className="surface" style={{ padding: '24px 22px', display: 'flex', flexDirection: 'column', gap: 18 }}>
      <SectionTitle
        icon={<RotateCcw size={17} color="#22d3ee" />}
        title="Rollback Controller"
        sub="Zero-downtime version swaps with cryptographic verification."
      />

      <form onSubmit={onSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#94a3b8', marginBottom: 7 }}>Target Version</label>
          <select value={targetVersion} onChange={(e) => onTargetChange(e.target.value)} className="field font-mono" required>
            <option value="">— Select version —</option>
            {versions.map((v) => (
              <option key={v.version_id} value={v.version_id}>
                {v.version_id}{v.is_active ? ' (ACTIVE)' : ''}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#94a3b8', marginBottom: 7 }}>Audit Reason</label>
          <textarea
            value={rollbackReason}
            onChange={(e) => onReasonChange(e.target.value)}
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
          <button type="button" onClick={onVerify} disabled={actionLoading} className="btn-ghost">
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
                  <td><span className="font-mono" style={{ color: '#64748b', fontSize: 11 }}>{log.timestamp?.replace('T', ' ').slice(0, 19)}</span></td>
                  <td><span className="font-mono" style={{ color: '#f43f5e', fontWeight: 600, fontSize: 12 }}>{log.from_version}</span></td>
                  <td><span className="font-mono" style={{ color: '#10b981', fontWeight: 700, fontSize: 12 }}>{log.to_version}</span></td>
                  <td style={{ color: '#94a3b8', fontSize: 12, lineHeight: 1.5 }}>{log.reason}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  </div>
);
