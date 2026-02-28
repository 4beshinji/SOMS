import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getDeviceFunding, getDevices, buyShares, returnShares } from '../api/stakes';
import type { DeviceFundingResponse } from '../api/stakes';
import DeviceTypeBadge from '../components/DeviceTypeBadge';
import ProgressBar from '../components/ProgressBar';

export default function DeviceDetail({ userId }: { userId: number }) {
  const { deviceId } = useParams<{ deviceId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<DeviceFundingResponse | null>(null);
  const [deviceType, setDeviceType] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [buyQty, setBuyQty] = useState('');
  const [returnQty, setReturnQty] = useState('');
  const [actionMsg, setActionMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function loadData() {
    if (!deviceId) return;
    try {
      const d = await getDeviceFunding(deviceId);
      setData(d);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : '読み込みに失敗しました');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!deviceId) return;
      try {
        const [funding, devices] = await Promise.all([
          getDeviceFunding(deviceId),
          getDevices(),
        ]);
        if (cancelled) return;
        setData(funding);
        const dev = devices.find(d => d.device_id === deviceId);
        if (dev) setDeviceType(dev.device_type);
        setError(null);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : '読み込みに失敗しました');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [deviceId]);

  if (!deviceId) return null;

  const myStake = data?.stakeholders.find(s => s.user_id === userId);
  const isOwner = data?.stakeholders.some(s => s.user_id === userId && s.shares === data.total_shares);
  const soldShares = data ? data.total_shares - data.available_shares : 0;
  const soldPct = data ? (soldShares / data.total_shares) * 100 : 0;

  async function handleBuy() {
    const qty = parseInt(buyQty, 10);
    if (!qty || qty <= 0) return;
    setSubmitting(true);
    setActionMsg(null);
    try {
      await buyShares(deviceId!, userId, qty);
      setActionMsg({ type: 'success', text: `${qty} シェアを購入しました` });
      setBuyQty('');
      await loadData();
    } catch (e) {
      setActionMsg({ type: 'error', text: e instanceof Error ? e.message : '購入に失敗しました' });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReturn() {
    const qty = parseInt(returnQty, 10);
    if (!qty || qty <= 0) return;
    setSubmitting(true);
    setActionMsg(null);
    try {
      await returnShares(deviceId!, userId, qty);
      setActionMsg({ type: 'success', text: `${qty} シェアを返却しました` });
      setReturnQty('');
      await loadData();
    } catch (e) {
      setActionMsg({ type: 'error', text: e instanceof Error ? e.message : '返却に失敗しました' });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="p-4 pb-24 space-y-4">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/invest')} className="text-[var(--gray-500)] hover:text-[var(--gray-900)] cursor-pointer" aria-label="戻る">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <h1 className="text-xl font-bold text-[var(--gray-900)] truncate">{deviceId}</h1>
      </div>

      {error && (
        <div className="bg-[var(--error-50)] border border-[var(--error-500)] rounded-xl p-3 text-[var(--error-700)] text-sm">{error}</div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="h-20 bg-[var(--gray-100)] rounded-xl animate-pulse" />)}
        </div>
      ) : data && (
        <>
          <div className="bg-white rounded-xl p-4 space-y-2 elevation-1">
            <div className="flex items-center gap-2">
              {deviceType && <DeviceTypeBadge type={deviceType} />}
              <span className="text-sm text-[var(--gray-500)]">
                {(data.share_price / 1000).toFixed(3)} SOMS/シェア
              </span>
            </div>
            <div className="text-sm text-[var(--gray-500)]">
              推定報酬: <span className="text-[var(--gold-dark)] font-medium">{(data.estimated_reward_per_hour / 1000).toFixed(3)} SOMS/時</span>
            </div>
          </div>

          <div className="bg-white rounded-xl p-4 space-y-3 elevation-1">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-[var(--gray-900)]">ファンディング</span>
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                data.funding_open ? 'bg-[var(--success-50)] text-[var(--success-700)]' : 'bg-[var(--gray-100)] text-[var(--gray-500)]'
              }`}>
                {data.funding_open ? '募集中' : '終了'}
              </span>
            </div>
            <div className="text-sm text-[var(--gray-500)]">
              {soldShares}/{data.total_shares} シェア販売済み &middot; {data.available_shares} 残
            </div>
            <ProgressBar value={soldPct} color={data.funding_open ? 'bg-[var(--primary-500)]' : 'bg-[var(--gray-400)]'} />
          </div>

          <div className="bg-white rounded-xl p-4 space-y-2 elevation-1">
            <h2 className="text-sm font-medium text-[var(--gray-900)] mb-2">出資者</h2>
            {data.stakeholders.length === 0 ? (
              <div className="text-[var(--gray-500)] text-sm">出資者はまだいません</div>
            ) : (
              data.stakeholders.map(s => (
                <div
                  key={s.id}
                  className={`flex items-center justify-between text-sm py-1 ${
                    s.user_id === userId ? 'text-[var(--primary-700)]' : 'text-[var(--gray-700)]'
                  }`}
                >
                  <span>ユーザー #{s.user_id}{s.user_id === userId ? ' (あなた)' : ''}</span>
                  <span>{s.shares} シェア ({s.percentage.toFixed(1)}%)</span>
                </div>
              ))
            )}
          </div>

          {isOwner ? (
            <div className="bg-white rounded-xl p-4 text-center text-sm text-[var(--gray-500)] elevation-1">
              あなたはこのデバイスのオーナーです
            </div>
          ) : (
            <div className="space-y-3">
              {data.funding_open && data.available_shares > 0 && (
                <div className="bg-white rounded-xl p-4 space-y-3 elevation-1">
                  <h2 className="text-sm font-medium text-[var(--gray-900)]">シェアを購入</h2>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      inputMode="numeric"
                      min="1"
                      max={data.available_shares}
                      value={buyQty}
                      onChange={e => setBuyQty(e.target.value)}
                      placeholder="数量"
                      className="flex-1 bg-[var(--gray-100)] border border-[var(--gray-300)] rounded-lg px-3 py-2 text-[var(--gray-900)] text-sm focus:outline-none focus:border-[var(--primary-500)]"
                    />
                    <button
                      onClick={handleBuy}
                      disabled={submitting || !buyQty || parseInt(buyQty) <= 0}
                      className="px-4 py-2 bg-[var(--primary-500)] text-white font-semibold rounded-lg text-sm disabled:opacity-40 cursor-pointer"
                    >
                      購入
                    </button>
                  </div>
                  {buyQty && parseInt(buyQty) > 0 && (
                    <div className="text-xs text-[var(--gray-500)]">
                      費用: {(parseInt(buyQty) * data.share_price / 1000).toFixed(3)} SOMS
                    </div>
                  )}
                </div>
              )}

              {myStake && myStake.shares > 0 && (
                <div className="bg-white rounded-xl p-4 space-y-3 elevation-1">
                  <h2 className="text-sm font-medium text-[var(--gray-900)]">シェアを返却</h2>
                  <div className="text-xs text-[var(--gray-500)] mb-1">
                    所有数: {myStake.shares} シェア
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      inputMode="numeric"
                      min="1"
                      max={myStake.shares}
                      value={returnQty}
                      onChange={e => setReturnQty(e.target.value)}
                      placeholder="数量"
                      className="flex-1 bg-[var(--gray-100)] border border-[var(--gray-300)] rounded-lg px-3 py-2 text-[var(--gray-900)] text-sm focus:outline-none focus:border-[var(--primary-500)]"
                    />
                    <button
                      onClick={handleReturn}
                      disabled={submitting || !returnQty || parseInt(returnQty) <= 0}
                      className="px-4 py-2 bg-[var(--gray-200)] text-[var(--gray-700)] font-semibold rounded-lg text-sm disabled:opacity-40 cursor-pointer"
                    >
                      返却
                    </button>
                  </div>
                  {returnQty && parseInt(returnQty) > 0 && (
                    <div className="text-xs text-[var(--gray-500)]">
                      払い戻し: {(parseInt(returnQty) * data.share_price / 1000).toFixed(3)} SOMS
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {actionMsg && (
            <div className={`rounded-xl p-3 text-sm ${
              actionMsg.type === 'success'
                ? 'bg-[var(--success-50)] border border-[var(--success-500)] text-[var(--success-700)]'
                : 'bg-[var(--error-50)] border border-[var(--error-500)] text-[var(--error-700)]'
            }`}>
              {actionMsg.text}
            </div>
          )}
        </>
      )}
    </div>
  );
}
