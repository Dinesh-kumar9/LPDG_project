// ── API client — single source of truth for all backend calls ─────────────────
// Base URL is empty string so calls are relative to the host that serves the
// frontend (FastAPI mounts the built dist/ at "/", so /api/* routes resolve
// correctly in both dev-proxy and production-Docker scenarios).

import type { DriftReport, Prediction, RollbackEntry, VersionInfo } from '../types';

const BASE = '';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail: string }).detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

// ── Registry ─────────────────────────────────────────────────────────────────

export interface RegistryResponse {
  active_version: string;
  total_versions: number;
  versions: VersionInfo[];
}

export const fetchRegistry = () => get<RegistryResponse>('/api/registry');

// ── Predictions ───────────────────────────────────────────────────────────────

export interface PredictionsResponse {
  total_rows: number;
  available_weeks: string[];
  selected_week: string | null;
  predictions: Prediction[];
}

export const fetchPredictions = (week?: string) =>
  get<PredictionsResponse>(`/api/predictions${week ? `?week_start=${week}` : ''}`);

// ── Drift ─────────────────────────────────────────────────────────────────────

export interface DriftStatusResponse {
  consecutive_flagged_weeks: number;
  retrain_recommended: boolean;
  total_reports: number;
  latest_report: DriftReport | null;
}

export const fetchDriftStatus = () => get<DriftStatusResponse>('/api/drift/status');

export const triggerDriftCheck = () =>
  post<{ status: string; report: DriftReport }>('/api/drift/run');

// ── Rollback ──────────────────────────────────────────────────────────────────

export interface RollbackLogResponse {
  total_entries: number;
  logs: RollbackEntry[];
}

export const fetchRollbackLog = () => get<RollbackLogResponse>('/api/rollback/log');

export const executeRollback = (to_version: string, reason: string) =>
  post<{ status: string; from_version: string; to_version: string }>('/api/rollback/execute', {
    to_version,
    reason,
  });

export const verifyRollback = (version_id?: string) =>
  post<{
    version_id: string;
    verified: boolean;
    status: string;
    sigma: number;
    intentionally_broken: boolean;
    note: string;
  }>(
    `/api/rollback/verify${version_id ? `?version_id=${version_id}` : ''}`
  );

