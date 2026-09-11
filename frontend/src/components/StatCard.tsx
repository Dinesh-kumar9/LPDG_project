import React from 'react';

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  accent?: string;
}

export const StatCard: React.FC<StatCardProps> = ({ icon, label, value, accent = '#22d3ee' }) => (
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
