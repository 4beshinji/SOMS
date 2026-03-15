import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchRewardRates,
  updateRewardRate,
  fetchSupply,
  triggerDemurrage,
  fetchPools,
  createPool,
  contributeToPool,
  activatePool,
  type RewardRate,
  type FundingPool,
} from '../api/economy';

function RewardRatesSection() {
  const queryClient = useQueryClient();
  const [editingType, setEditingType] = useState<string | null>(null);
  const [editRate, setEditRate] = useState('');

  const ratesQuery = useQuery({
    queryKey: ['reward-rates'],
    queryFn: fetchRewardRates,
    refetchInterval: 30000,
  });

  const updateMutation = useMutation({
    mutationFn: ({ deviceType, rate }: { deviceType: string; rate: number }) =>
      updateRewardRate(deviceType, rate),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reward-rates'] });
      setEditingType(null);
    },
  });

  const rates = ratesQuery.data ?? [];

  return (
    <section className="bg-white rounded-xl border border-[var(--gray-200)] overflow-hidden">
      <div className="px-4 py-3 border-b border-[var(--gray-200)]">
        <h2 className="text-sm font-semibold text-[var(--gray-900)]">Reward Rates</h2>
      </div>
      <div className="divide-y divide-[var(--gray-100)]">
        {ratesQuery.isLoading ? (
          <div className="p-4 text-sm text-[var(--gray-500)]">Loading...</div>
        ) : rates.length === 0 ? (
          <div className="p-4 text-sm text-[var(--gray-500)]">No reward rates configured</div>
        ) : (
          rates.map((r: RewardRate) => (
            <div key={r.device_type} className="px-4 py-3 flex items-center gap-3">
              <span className="text-sm font-medium text-[var(--gray-900)] flex-1">{r.device_type}</span>
              {editingType === r.device_type ? (
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    step="0.1"
                    value={editRate}
                    onChange={(e) => setEditRate(e.target.value)}
                    className="w-24 h-8 px-2 text-xs border border-[var(--gray-300)] rounded-lg"
                  />
                  <button
                    onClick={() => updateMutation.mutate({ deviceType: r.device_type, rate: parseFloat(editRate) })}
                    disabled={updateMutation.isPending}
                    className="px-2 py-1 text-xs bg-[var(--primary-500)] text-white rounded"
                  >
                    Save
                  </button>
                  <button onClick={() => setEditingType(null)} className="px-2 py-1 text-xs text-[var(--gray-500)]">
                    Cancel
                  </button>
                </div>
              ) : (
                <>
                  <span className="text-sm text-[var(--gray-600)]">{r.base_rate}</span>
                  <button
                    onClick={() => { setEditingType(r.device_type); setEditRate(String(r.base_rate)); }}
                    className="text-xs text-[var(--primary-500)] hover:text-[var(--primary-700)]"
                  >
                    Edit
                  </button>
                </>
              )}
            </div>
          ))
        )}
      </div>
    </section>
  );
}

function PoolsSection() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newGoal, setNewGoal] = useState('');
  const [contributePoolId, setContributePoolId] = useState<number | null>(null);
  const [contributeUserId, setContributeUserId] = useState('');
  const [contributeAmount, setContributeAmount] = useState('');
  const [activatePoolId, setActivatePoolId] = useState<number | null>(null);
  const [activateDeviceId, setActivateDeviceId] = useState('');

  const poolsQuery = useQuery({
    queryKey: ['pools'],
    queryFn: fetchPools,
    refetchInterval: 30000,
  });

  const createMutation = useMutation({
    mutationFn: () => createPool(newTitle, parseInt(newGoal)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pools'] });
      setShowCreate(false);
      setNewTitle('');
      setNewGoal('');
    },
  });

  const contributeMutation = useMutation({
    mutationFn: () => contributeToPool(contributePoolId!, parseInt(contributeUserId), parseInt(contributeAmount)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pools'] });
      setContributePoolId(null);
    },
  });

  const activateMutation = useMutation({
    mutationFn: () => activatePool(activatePoolId!, activateDeviceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pools'] });
      setActivatePoolId(null);
    },
  });

  const pools = poolsQuery.data ?? [];

  const STATUS_STYLES: Record<string, string> = {
    open: 'bg-[var(--info-50)] text-[var(--info-700)]',
    funded: 'bg-[var(--success-50)] text-[var(--success-700)]',
    active: 'bg-[var(--primary-50)] text-[var(--primary-700)]',
    closed: 'bg-[var(--gray-100)] text-[var(--gray-500)]',
  };

  return (
    <section className="bg-white rounded-xl border border-[var(--gray-200)] overflow-hidden">
      <div className="px-4 py-3 border-b border-[var(--gray-200)] flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--gray-900)]">Funding Pools</h2>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="px-3 py-1.5 text-xs font-medium bg-[var(--primary-500)] text-white rounded-lg hover:bg-[var(--primary-600)] transition-colors"
        >
          Create Pool
        </button>
      </div>

      {showCreate && (
        <div className="px-4 py-3 border-b border-[var(--gray-200)] flex gap-2 items-end">
          <div className="flex-1">
            <label className="text-xs text-[var(--gray-500)]">Title</label>
            <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} className="w-full h-8 px-2 text-xs border border-[var(--gray-300)] rounded-lg" />
          </div>
          <div className="w-32">
            <label className="text-xs text-[var(--gray-500)]">Goal (JPY)</label>
            <input type="number" value={newGoal} onChange={(e) => setNewGoal(e.target.value)} className="w-full h-8 px-2 text-xs border border-[var(--gray-300)] rounded-lg" />
          </div>
          <button
            onClick={() => createMutation.mutate()}
            disabled={!newTitle || !newGoal || createMutation.isPending}
            className="px-3 h-8 text-xs font-medium bg-[var(--primary-500)] text-white rounded-lg disabled:opacity-40"
          >
            Create
          </button>
        </div>
      )}

      <div className="divide-y divide-[var(--gray-100)]">
        {poolsQuery.isLoading ? (
          <div className="p-4 text-sm text-[var(--gray-500)]">Loading...</div>
        ) : pools.length === 0 ? (
          <div className="p-4 text-sm text-[var(--gray-500)]">No funding pools</div>
        ) : (
          pools.map((p: FundingPool) => (
            <div key={p.id} className="px-4 py-3 space-y-2">
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-[var(--gray-900)] flex-1">{p.title}</span>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_STYLES[p.status] ?? STATUS_STYLES.closed}`}>
                  {p.status}
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs text-[var(--gray-500)]">
                <span>{p.progress_pct.toFixed(0)}%</span>
                <div className="flex-1 h-1.5 bg-[var(--gray-100)] rounded-full overflow-hidden">
                  <div className="h-full bg-[var(--primary-500)] rounded-full" style={{ width: `${Math.min(100, p.progress_pct)}%` }} />
                </div>
                <span>¥{p.raised_jpy.toLocaleString()} / ¥{p.goal_jpy.toLocaleString()}</span>
              </div>
              <div className="flex gap-2">
                {p.status === 'open' && (
                  contributePoolId === p.id ? (
                    <div className="flex gap-1 items-center">
                      <input type="number" placeholder="User ID" value={contributeUserId} onChange={(e) => setContributeUserId(e.target.value)} className="w-20 h-7 px-1 text-xs border border-[var(--gray-300)] rounded" />
                      <input type="number" placeholder="JPY" value={contributeAmount} onChange={(e) => setContributeAmount(e.target.value)} className="w-20 h-7 px-1 text-xs border border-[var(--gray-300)] rounded" />
                      <button onClick={() => contributeMutation.mutate()} disabled={contributeMutation.isPending} className="px-2 h-7 text-xs bg-[var(--primary-500)] text-white rounded disabled:opacity-40">Add</button>
                      <button onClick={() => setContributePoolId(null)} className="px-2 h-7 text-xs text-[var(--gray-500)]">Cancel</button>
                    </div>
                  ) : (
                    <button onClick={() => setContributePoolId(p.id)} className="text-xs text-[var(--primary-500)]">+ Contribute</button>
                  )
                )}
                {p.status === 'funded' && (
                  activatePoolId === p.id ? (
                    <div className="flex gap-1 items-center">
                      <input placeholder="Device ID" value={activateDeviceId} onChange={(e) => setActivateDeviceId(e.target.value)} className="w-32 h-7 px-1 text-xs border border-[var(--gray-300)] rounded" />
                      <button onClick={() => activateMutation.mutate()} disabled={activateMutation.isPending} className="px-2 h-7 text-xs bg-[var(--success-500)] text-white rounded disabled:opacity-40">Activate</button>
                      <button onClick={() => setActivatePoolId(null)} className="px-2 h-7 text-xs text-[var(--gray-500)]">Cancel</button>
                    </div>
                  ) : (
                    <button onClick={() => setActivatePoolId(p.id)} className="text-xs text-[var(--success-700)]">Activate</button>
                  )
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

export default function EconomyPage() {
  const queryClient = useQueryClient();

  const supplyQuery = useQuery({
    queryKey: ['supply'],
    queryFn: fetchSupply,
    refetchInterval: 30000,
  });

  const demurrageMutation = useMutation({
    mutationFn: triggerDemurrage,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['supply'] }),
  });

  const supply = supplyQuery.data;

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-[var(--gray-900)]">Economy</h1>

      {/* Supply overview */}
      {supply && (
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: 'Total Issued', value: `${(supply.total_issued / 1000).toFixed(1)} SOMS`, style: 'text-[var(--gray-700)]' },
            { label: 'Total Burned', value: `${(supply.total_burned / 1000).toFixed(1)} SOMS`, style: 'text-[var(--error-700)]' },
            { label: 'Circulating', value: `${(supply.circulating / 1000).toFixed(1)} SOMS`, style: 'text-[var(--gold-dark)]' },
          ].map((s) => (
            <div key={s.label} className="bg-white rounded-xl border border-[var(--gray-200)] p-4 text-center">
              <p className="text-xs text-[var(--gray-500)]">{s.label}</p>
              <p className={`text-xl font-bold ${s.style}`}>{s.value}</p>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <button
          onClick={() => demurrageMutation.mutate()}
          disabled={demurrageMutation.isPending}
          className="px-4 py-2 text-sm font-medium border border-[var(--warning-border)] bg-[var(--warning-50)] text-[var(--warning-700)] rounded-lg hover:bg-[var(--warning-100)] disabled:opacity-40 transition-colors"
        >
          {demurrageMutation.isPending ? 'Processing...' : 'Trigger Demurrage'}
        </button>
      </div>

      <RewardRatesSection />
      <PoolsSection />
    </div>
  );
}
