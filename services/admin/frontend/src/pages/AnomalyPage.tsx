import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchAnomalyHealth,
  fetchAnomalyModels,
  fetchAnomalyDetections,
  triggerTraining,
} from '../api/anomaly';

const SEVERITY_STYLES: Record<string, string> = {
  normal: 'bg-[var(--success-50)] text-[var(--success-700)]',
  warning: 'bg-[var(--warning-50)] text-[var(--warning-700)]',
  critical: 'bg-[var(--error-50)] text-[var(--error-700)]',
};

export default function AnomalyPage() {
  const queryClient = useQueryClient();
  const [filterZone, setFilterZone] = useState('');
  const [filterSeverity, setFilterSeverity] = useState('');
  const [filterHours, setFilterHours] = useState(24);

  const healthQuery = useQuery({
    queryKey: ['anomaly-health'],
    queryFn: fetchAnomalyHealth,
    refetchInterval: 30000,
    retry: 1,
  });

  const modelsQuery = useQuery({
    queryKey: ['anomaly-models'],
    queryFn: fetchAnomalyModels,
    refetchInterval: 60000,
    retry: 1,
  });

  const detectionsQuery = useQuery({
    queryKey: ['anomaly-detections', filterZone, filterSeverity, filterHours],
    queryFn: () =>
      fetchAnomalyDetections({
        zone: filterZone || undefined,
        severity: filterSeverity || undefined,
        hours: filterHours,
      }),
    refetchInterval: 30000,
    retry: 1,
  });

  const trainMutation = useMutation({
    mutationFn: (zone?: string) => triggerTraining(zone),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['anomaly-models'] }),
  });

  const isOnline = healthQuery.isSuccess;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-[var(--gray-900)]">Anomaly Detection</h1>
        <div className="flex items-center gap-2">
          <span className={`w-2.5 h-2.5 rounded-full ${isOnline ? 'bg-[var(--success-500)]' : 'bg-[var(--error-500)]'}`} />
          <span className="text-sm text-[var(--gray-600)]">{isOnline ? 'Online' : 'Offline'}</span>
        </div>
      </div>

      {/* Model Status */}
      <section className="bg-white rounded-xl border border-[var(--gray-200)] overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--gray-200)] flex items-center justify-between">
          <h2 className="text-sm font-semibold text-[var(--gray-900)]">Models</h2>
          <button
            onClick={() => trainMutation.mutate(undefined)}
            disabled={trainMutation.isPending || !isOnline}
            className="px-3 py-1.5 text-xs font-medium bg-[var(--primary-500)] text-white rounded-lg hover:bg-[var(--primary-600)] disabled:opacity-40 transition-colors"
          >
            {trainMutation.isPending ? 'Training...' : 'Train All'}
          </button>
        </div>
        <div className="divide-y divide-[var(--gray-100)]">
          {modelsQuery.isLoading ? (
            <div className="p-4 text-sm text-[var(--gray-500)]">Loading...</div>
          ) : modelsQuery.isError ? (
            <div className="p-4 text-sm text-[var(--error-600)]">Service unavailable</div>
          ) : (modelsQuery.data ?? []).length === 0 ? (
            <div className="p-4 text-sm text-[var(--gray-500)]">No models trained yet</div>
          ) : (
            (modelsQuery.data ?? []).map((m) => (
              <div key={m.id} className="px-4 py-3 flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-[var(--gray-900)]">{m.zone}</span>
                  <span className="text-xs text-[var(--gray-500)] ml-2">{m.arch}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-[var(--gray-500)]">val_loss: {m.val_loss.toFixed(4)}</span>
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${m.is_active ? 'bg-[var(--success-50)] text-[var(--success-700)]' : 'bg-[var(--gray-100)] text-[var(--gray-500)]'}`}>
                    {m.is_active ? 'Active' : 'Inactive'}
                  </span>
                  <button
                    onClick={() => trainMutation.mutate(m.zone)}
                    disabled={trainMutation.isPending}
                    className="text-xs text-[var(--primary-500)] hover:text-[var(--primary-700)]"
                  >
                    Retrain
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      {/* Detections */}
      <section className="bg-white rounded-xl border border-[var(--gray-200)] overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--gray-200)]">
          <h2 className="text-sm font-semibold text-[var(--gray-900)] mb-2">Recent Anomalies</h2>
          <div className="flex gap-2 flex-wrap">
            <input
              type="text"
              placeholder="Zone"
              value={filterZone}
              onChange={(e) => setFilterZone(e.target.value)}
              className="h-8 px-2 text-xs border border-[var(--gray-300)] rounded-lg focus:outline-none focus:border-[var(--primary-500)]"
            />
            <select
              value={filterSeverity}
              onChange={(e) => setFilterSeverity(e.target.value)}
              className="h-8 px-2 text-xs border border-[var(--gray-300)] rounded-lg focus:outline-none focus:border-[var(--primary-500)]"
            >
              <option value="">All Severity</option>
              <option value="warning">Warning</option>
              <option value="critical">Critical</option>
            </select>
            <select
              value={filterHours}
              onChange={(e) => setFilterHours(Number(e.target.value))}
              className="h-8 px-2 text-xs border border-[var(--gray-300)] rounded-lg focus:outline-none focus:border-[var(--primary-500)]"
            >
              <option value={6}>Last 6h</option>
              <option value={24}>Last 24h</option>
              <option value={72}>Last 3d</option>
              <option value={168}>Last 7d</option>
            </select>
          </div>
        </div>
        <div className="divide-y divide-[var(--gray-100)] max-h-[500px] overflow-y-auto">
          {detectionsQuery.isLoading ? (
            <div className="p-4 text-sm text-[var(--gray-500)]">Loading...</div>
          ) : detectionsQuery.isError ? (
            <div className="p-4 text-sm text-[var(--error-600)]">Service unavailable</div>
          ) : (detectionsQuery.data ?? []).length === 0 ? (
            <div className="p-4 text-sm text-[var(--gray-500)]">No anomalies detected</div>
          ) : (
            (detectionsQuery.data ?? []).map((d) => (
              <div key={d.id} className="px-4 py-2 flex items-center gap-3 text-sm">
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${SEVERITY_STYLES[d.severity] ?? SEVERITY_STYLES.normal}`}>
                  {d.severity}
                </span>
                <span className="text-[var(--gray-900)] font-medium">{d.zone}</span>
                <span className="text-[var(--gray-500)]">{d.channel}</span>
                <span className="text-[var(--gray-500)] ml-auto">
                  score: {d.score.toFixed(2)} | predicted: {d.predicted.toFixed(1)} | actual: {d.actual.toFixed(1)}
                </span>
                <span className="text-xs text-[var(--gray-400)]">
                  {new Date(d.created_at).toLocaleString('ja-JP', { hour: '2-digit', minute: '2-digit', month: 'numeric', day: 'numeric' })}
                </span>
              </div>
            ))
          )}
        </div>
      </section>

      {trainMutation.isSuccess && (
        <div className="bg-[var(--success-50)] border border-[var(--success-border)] rounded-lg p-3 text-sm text-[var(--success-700)]">
          Training triggered successfully
        </div>
      )}
    </div>
  );
}
