import React from 'react';

interface SectionTitleProps {
  icon: React.ReactNode;
  title: string;
  sub?: string;
}

export const SectionTitle: React.FC<SectionTitleProps> = ({ icon, title, sub }) => (
  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 20 }}>
    <div style={{ paddingTop: 2 }}>{icon}</div>
    <div>
      <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#f0f4ff' }}>{title}</h2>
      {sub && <p style={{ margin: '3px 0 0', fontSize: 12, color: '#64748b' }}>{sub}</p>}
    </div>
  </div>
);
