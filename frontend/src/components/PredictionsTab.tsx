import React from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell,
} from 'recharts';
import { Download } from 'lucide-react';
import type { Prediction } from '../types';

// ── Custom bar chart tooltip ───────────────────────────────────────────────────
const CustomTooltip = ({
  active, payload, label,
}: { active?: boolean; payload?: { value: number; payload: { rank: number } }[]; label?: string }) => {
  if (!active || !payload?.length) return null;
  const item = payload[0];
  const rank = item.payload?.rank;
  return (
    <div style={{ background: '#0c1120', border: '1px solid rgba(34,211,238,0.35)', borderRadius: 10, padding: '12px 16px', boxShadow: '0 8px 32px rgba(0,0,0,0.8)', pointerEvents: 'none' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14, marginBottom: 6 }}>
        <span style={{ color: '#cbd5e1', fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          Gateway …{label}
        </span>
        {rank !== undefined && (
          <span style={{ fontSize: 10, fontWeight: 800, padding: '2px 7px', borderRadius: 4, background: rank === 1 ? 'rgba(244,63,94,0.25)' : rank <= 3 ? 'rgba(249,115,22,0.25)' : rank <= 5 ? 'rgba(245,158,11,0.25)' : 'rgba(34,211,238,0.2)', color: rank === 1 ? '#f43f5e' : rank <= 3 ? '#f97316' : rank <= 5 ? '#f59e0b' : '#22d3ee' }}>
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

interface PredictionsTabProps {
  predictions: Prediction[];
  availableWeeks: string[];
  selectedWeek: string;
  onSelectWeek: (week: string) => void;
}

export const PredictionsTab: React.FC<PredictionsTabProps> = ({
  predictions, availableWeeks, selectedWeek, onSelectWeek,
}) => {
  const chartData = predictions.map((p) => ({
    name: p.gateway_id.slice(-6),
    score: p.score,
    rank: p.rank,
  }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Week selector bar */}
      <div className="surface" style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.07em', marginRight: 4 }}>Week:</span>
          {availableWeeks.map((w) => (
            <button key={w} onClick={() => onSelectWeek(w)} style={{ padding: '5px 12px', borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer', border: selectedWeek === w ? '1px solid rgba(34,211,238,0.45)' : '1px solid rgba(255,255,255,0.07)', background: selectedWeek === w ? 'rgba(34,211,238,0.12)' : '#111827', color: selectedWeek === w ? '#22d3ee' : '#94a3b8', transition: 'all 0.15s' }}>
              {w}
            </button>
          ))}
        </div>
        <a href="/api/predictions/download" download="predictions.csv" style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '8px 16px', borderRadius: 9, fontSize: 12, fontWeight: 700, textDecoration: 'none', background: '#111827', border: '1px solid rgba(255,255,255,0.1)', color: '#f0f4ff', transition: 'background 0.15s' }}>
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
          <div className="font-mono" style={{ fontSize: 11, color: '#94a3b8', background: '#0c1120', padding: '5px 10px', borderRadius: 7, border: '1px solid rgba(255,255,255,0.08)' }}>{selectedWeek}</div>
        </div>
        <div style={{ height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
              <XAxis dataKey="name" stroke="rgba(255,255,255,0.0)" tick={{ fill: '#94a3b8', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' }} tickLine={false} axisLine={false} />
              <YAxis stroke="rgba(255,255,255,0.0)" tick={{ fill: '#94a3b8', fontSize: 11 }} tickLine={false} axisLine={false} />
              <Tooltip content={<CustomTooltip />} cursor={false} />
              <Bar dataKey="score" radius={[5, 5, 0, 0]} maxBarSize={36}>
                {chartData.map((entry, idx) => (
                  <Cell key={`cell-${idx}`} fill={entry.rank === 1 ? '#f43f5e' : entry.rank <= 3 ? '#f97316' : entry.rank <= 5 ? '#f59e0b' : '#22d3ee'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div style={{ display: 'flex', gap: 18, marginTop: 12 }}>
          {[{ color: '#f43f5e', label: 'Critical (#1)' }, { color: '#f97316', label: 'High (#2–3)' }, { color: '#f59e0b', label: 'Elevated (#4–5)' }, { color: '#22d3ee', label: 'Monitored (#6–15)' }].map(({ color, label }) => (
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
          <div style={{ fontSize: 14, fontWeight: 700, color: '#f0f4ff' }}>Recommended Site Visits — Ranked 1 to 15</div>
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
              {predictions.map((p) => (
                <tr key={`${p.week_start}-${p.rank}`}>
                  <td>
                    <span className={p.rank === 1 ? 'rank-1' : p.rank <= 3 ? 'rank-top' : 'rank-normal'}>{p.rank}</span>
                  </td>
                  <td><span className="font-mono" style={{ color: '#22d3ee', fontWeight: 600, fontSize: 12 }}>{p.gateway_id}</span></td>
                  <td>
                    <div style={{ fontWeight: 600, color: '#e2e8f0', fontSize: 12 }}>{p.site_type || 'Unknown'}</div>
                    <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{p.region || '—'}</div>
                  </td>
                  <td style={{ color: '#94a3b8', fontSize: 12 }}>{p.hw_model || '—'}</td>
                  <td style={{ color: '#94a3b8', fontSize: 12 }}>{p.n_meters_installed ? `${p.n_meters_installed} m` : '—'}</td>
                  <td><span className="font-mono" style={{ color: '#f59e0b', fontWeight: 800, fontSize: 13 }}>{p.score.toFixed(1)}</span></td>
                  <td style={{ color: '#94a3b8', fontSize: 12, maxWidth: 340, lineHeight: 1.5 }}>{p.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
