// ── Shared TypeScript types for LPDG Gateway Dashboard ────────────────────────

export interface Prediction {
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

export interface VersionInfo {
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

export interface RollbackEntry {
  timestamp: string;
  from_version: string;
  to_version: string;
  reason: string;
}

export interface DriftReport {
  checked_at: string;
  drift_flagged: boolean;
  summary: string;
  new_columns: string[];
  missing_columns: string[];
  new_gateway_ids: string[];
  new_gateway_id_pct: number;
}

export interface ActionFeedback {
  type: 'success' | 'error' | 'warning';
  message: string;
}

