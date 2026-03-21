import { authFetch } from '@soms/auth';

export interface AnomalyModel {
  id: number;
  zone: string;
  arch: string;
  val_loss: number;
  is_active: boolean;
  created_at: string;
}

export interface AnomalyDetection {
  id: number;
  zone: string;
  channel: string;
  score: number;
  predicted: number;
  actual: number;
  severity: string;
  source: string;
  created_at: string;
}

export async function fetchAnomalyHealth(): Promise<{ status: string }> {
  const res = await authFetch('/api/anomaly/health');
  if (!res.ok) throw new Error('Anomaly service unreachable');
  return res.json();
}

export async function fetchAnomalyModels(): Promise<AnomalyModel[]> {
  const res = await authFetch('/api/anomaly/models');
  if (!res.ok) throw new Error('Failed to fetch anomaly models');
  const data = await res.json();
  const models = data.models ?? data;
  if (Array.isArray(models)) return models;
  return Object.values(models);
}

export async function fetchAnomalyDetections(params?: {
  zone?: string;
  channel?: string;
  severity?: string;
  hours?: number;
}): Promise<AnomalyDetection[]> {
  const qs = new URLSearchParams();
  if (params?.zone) qs.set('zone', params.zone);
  if (params?.channel) qs.set('channel', params.channel);
  if (params?.severity) qs.set('severity', params.severity);
  if (params?.hours) qs.set('hours', String(params.hours));
  const res = await authFetch(`/api/anomaly/admin/anomalies?${qs}`);
  if (!res.ok) throw new Error('Failed to fetch anomaly detections');
  const data = await res.json();
  return data.detections ?? data;
}

export async function triggerTraining(zone?: string): Promise<{ message: string }> {
  const res = await authFetch('/api/anomaly/admin/train', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(zone ? { zone } : {}),
  });
  if (!res.ok) throw new Error('Failed to trigger training');
  return res.json();
}
