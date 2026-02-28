import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getWallet, getHistory, getSupply, type Wallet, type LedgerEntry, type SupplyStats } from '../api/wallet';
import BalanceCard from '../components/BalanceCard';
import TransactionItem from '../components/TransactionItem';

interface HomeProps {
  userId: number;
}

export default function Home({ userId }: HomeProps) {
  const navigate = useNavigate();
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [recent, setRecent] = useState<LedgerEntry[]>([]);
  const [supply, setSupply] = useState<SupplyStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [w, h, s] = await Promise.all([
        getWallet(userId),
        getHistory(userId, 10),
        getSupply(),
      ]);
      setWallet(w);
      setRecent(h);
      setSupply(s);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : '読み込みに失敗しました');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [w, h, s] = await Promise.all([
          getWallet(userId),
          getHistory(userId, 10),
          getSupply(),
        ]);
        if (cancelled) return;
        setWallet(w);
        setRecent(h);
        setSupply(s);
        setError(null);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : '読み込みに失敗しました');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    const interval = setInterval(load, 15000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [userId]);

  const recentRewards = recent.filter(
    e => e.transaction_type === 'TASK_REWARD' && e.entry_type === 'CREDIT'
  );

  return (
    <div className="p-4 pb-24 space-y-6">
      <BalanceCard balance={wallet?.balance ?? 0} loading={loading} />

      {/* QR Scan Button */}
      <button
        onClick={() => navigate('/scan')}
        className="w-full py-3 bg-[var(--primary-500)] hover:bg-[var(--primary-700)] text-white font-semibold rounded-xl flex items-center justify-center gap-2 transition-colors cursor-pointer"
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm12 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z" />
        </svg>
        QR スキャンで報酬を受け取る
      </button>

      {error && (
        <div className="bg-[var(--error-50)] border border-[var(--error-500)] rounded-xl p-4 text-center">
          <p className="text-sm font-medium text-[var(--error-700)]">接続エラー</p>
          <p className="text-xs text-[var(--error-600)] mt-1">{error}</p>
          <button
            onClick={loadData}
            className="mt-3 text-sm font-medium text-[var(--primary-500)] hover:underline cursor-pointer"
          >
            再試行
          </button>
        </div>
      )}

      {supply && (
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-white rounded-xl p-3 text-center elevation-1">
            <p className="text-xs text-[var(--gray-500)]">発行</p>
            <p className="text-sm font-semibold text-[var(--gray-700)]">{(supply.total_issued / 1000).toFixed(1)}</p>
          </div>
          <div className="bg-white rounded-xl p-3 text-center elevation-1">
            <p className="text-xs text-[var(--gray-500)]">焼却</p>
            <p className="text-sm font-semibold text-[var(--error-700)]">{(supply.total_burned / 1000).toFixed(1)}</p>
          </div>
          <div className="bg-white rounded-xl p-3 text-center elevation-1">
            <p className="text-xs text-[var(--gray-500)]">流通</p>
            <p className="text-sm font-semibold text-[var(--gold-dark)]">{(supply.circulating / 1000).toFixed(1)}</p>
          </div>
        </div>
      )}

      {recentRewards.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-lg font-semibold text-[var(--gray-900)]">タスク報酬</h2>
          {recentRewards.map(r => {
            const date = new Date(r.created_at);
            const timeStr = `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`;
            return (
              <div key={r.id} className="bg-gradient-to-r from-yellow-50 to-amber-50 border border-yellow-200 rounded-xl p-3 flex items-center justify-between">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-[var(--gold-dark)] truncate">
                    {r.description || 'タスク報酬'}
                  </p>
                  <p className="text-xs text-[var(--gray-500)]">{timeStr}</p>
                </div>
                <p className="text-lg font-bold text-[var(--gold-dark)] ml-3">
                  +{(r.amount / 1000).toFixed(3)}
                </p>
              </div>
            );
          })}
        </div>
      )}

      <div>
        <h2 className="text-lg font-semibold text-[var(--gray-900)] mb-2">最近の取引</h2>
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-14 bg-[var(--gray-100)] rounded-lg animate-pulse" />
            ))}
          </div>
        ) : recent.length === 0 ? (
          <p className="text-[var(--gray-500)] text-sm">取引はありません</p>
        ) : (
          <div className="bg-white rounded-xl px-4 elevation-1">
            {recent.map(entry => (
              <TransactionItem key={entry.id} entry={entry} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
