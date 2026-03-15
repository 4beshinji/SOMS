import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchRejectionStatus,
  clearRejectionStock,
  fetchAcceptanceStatus,
  clearAcceptanceStock,
  fetchCurrencyUnitStatus,
  clearCurrencyUnitStock,
  type StockStatus,
  type CurrencyUnitStatus,
} from '../api/voice';

function StockCard({
  title,
  data,
  isLoading,
  isError,
  onRegenerate,
  isRegenerating,
  samples,
}: {
  title: string;
  data: StockStatus | CurrencyUnitStatus | undefined;
  isLoading: boolean;
  isError: boolean;
  onRegenerate: () => void;
  isRegenerating: boolean;
  samples?: string[];
}) {
  const pct = data ? (data.count / data.max) * 100 : 0;
  const barColor = pct > 50 ? 'bg-[var(--success-500)]' : pct > 20 ? 'bg-[var(--warning-500)]' : 'bg-[var(--error-500)]';

  return (
    <div className="bg-white rounded-xl border border-[var(--gray-200)] p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--gray-900)]">{title}</h3>
        {data?.generating && (
          <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-[var(--info-50)] text-[var(--info-700)] animate-pulse">
            Generating...
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="h-12 bg-[var(--gray-100)] rounded animate-pulse" />
      ) : isError ? (
        <p className="text-sm text-[var(--error-600)]">Service unavailable</p>
      ) : data ? (
        <>
          <div className="flex items-end gap-2">
            <span className="text-3xl font-bold text-[var(--gray-900)]">{data.count}</span>
            <span className="text-sm text-[var(--gray-500)] mb-1">/ {data.max}</span>
          </div>
          <div className="w-full h-2 bg-[var(--gray-100)] rounded-full overflow-hidden">
            <div className={`h-full ${barColor} rounded-full transition-all`} style={{ width: `${pct}%` }} />
          </div>
          {samples && samples.length > 0 && (
            <div className="text-xs text-[var(--gray-500)] space-y-0.5">
              <p className="font-medium">Samples:</p>
              {samples.slice(0, 3).map((s, i) => (
                <p key={i} className="truncate">{s}</p>
              ))}
            </div>
          )}
          <button
            onClick={onRegenerate}
            disabled={isRegenerating}
            className="w-full py-2 text-xs font-medium border border-[var(--gray-300)] rounded-lg hover:bg-[var(--gray-50)] disabled:opacity-40 transition-colors"
          >
            {isRegenerating ? 'Clearing...' : 'Clear & Regenerate'}
          </button>
        </>
      ) : null}
    </div>
  );
}

export default function VoicePage() {
  const queryClient = useQueryClient();

  const rejectionQuery = useQuery({
    queryKey: ['voice-rejection'],
    queryFn: fetchRejectionStatus,
    refetchInterval: 15000,
    retry: 1,
  });

  const acceptanceQuery = useQuery({
    queryKey: ['voice-acceptance'],
    queryFn: fetchAcceptanceStatus,
    refetchInterval: 15000,
    retry: 1,
  });

  const currencyQuery = useQuery({
    queryKey: ['voice-currency'],
    queryFn: fetchCurrencyUnitStatus,
    refetchInterval: 15000,
    retry: 1,
  });

  const rejectionClear = useMutation({
    mutationFn: clearRejectionStock,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['voice-rejection'] }),
  });

  const acceptanceClear = useMutation({
    mutationFn: clearAcceptanceStock,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['voice-acceptance'] }),
  });

  const currencyClear = useMutation({
    mutationFn: clearCurrencyUnitStock,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['voice-currency'] }),
  });

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-[var(--gray-900)]">Voice Management</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StockCard
          title="Rejection Stock"
          data={rejectionQuery.data}
          isLoading={rejectionQuery.isLoading}
          isError={rejectionQuery.isError}
          onRegenerate={() => rejectionClear.mutate()}
          isRegenerating={rejectionClear.isPending}
        />
        <StockCard
          title="Acceptance Stock"
          data={acceptanceQuery.data}
          isLoading={acceptanceQuery.isLoading}
          isError={acceptanceQuery.isError}
          onRegenerate={() => acceptanceClear.mutate()}
          isRegenerating={acceptanceClear.isPending}
        />
        <StockCard
          title="Currency Units"
          data={currencyQuery.data}
          isLoading={currencyQuery.isLoading}
          isError={currencyQuery.isError}
          onRegenerate={() => currencyClear.mutate()}
          isRegenerating={currencyClear.isPending}
          samples={(currencyQuery.data as CurrencyUnitStatus)?.sample}
        />
      </div>
    </div>
  );
}
