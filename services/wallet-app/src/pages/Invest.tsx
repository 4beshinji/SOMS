import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getPortfolio, getDevices, getPools } from '../api/stakes';
import type { PortfolioResponse, Device, PoolListItem } from '../api/stakes';
import DeviceTypeBadge from '../components/DeviceTypeBadge';
import ProgressBar from '../components/ProgressBar';

type Tab = 'portfolio' | 'devices' | 'pools';

export default function Invest({ userId }: { userId: number }) {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('portfolio');
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [pools, setPools] = useState<PoolListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [p, d, pl] = await Promise.all([
          getPortfolio(userId),
          getDevices(),
          getPools(),
        ]);
        if (cancelled) return;
        setPortfolio(p);
        setDevices(d);
        setPools(pl);
        setError(null);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : '読み込みに失敗しました');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    const interval = setInterval(load, 30000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [userId]);

  const tabClass = (t: Tab) =>
    `px-4 py-1.5 rounded-full text-sm font-medium transition-colors cursor-pointer ${
      tab === t ? 'bg-[var(--primary-500)] text-white' : 'bg-[var(--gray-100)] text-[var(--gray-500)]'
    }`;

  return (
    <div className="p-4 pb-24 space-y-4">
      <h1 className="text-xl font-bold text-[var(--gray-900)]">投資</h1>

      <div className="flex gap-2">
        <button className={tabClass('portfolio')} onClick={() => setTab('portfolio')}>ポートフォリオ</button>
        <button className={tabClass('devices')} onClick={() => setTab('devices')}>デバイス</button>
        <button className={tabClass('pools')} onClick={() => setTab('pools')}>プール</button>
      </div>

      {error && (
        <div className="bg-[var(--error-50)] border border-[var(--error-500)] rounded-xl p-3 text-[var(--error-700)] text-sm">{error}</div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="h-20 bg-[var(--gray-100)] rounded-xl animate-pulse" />)}
        </div>
      ) : (
        <>
          {tab === 'portfolio' && <PortfolioTab portfolio={portfolio} navigate={navigate} />}
          {tab === 'devices' && <DevicesTab devices={devices} navigate={navigate} />}
          {tab === 'pools' && <PoolsTab pools={pools} />}
        </>
      )}
    </div>
  );
}

function PortfolioTab({
  portfolio,
  navigate,
}: {
  portfolio: PortfolioResponse | null;
  navigate: ReturnType<typeof useNavigate>;
}) {
  if (!portfolio || portfolio.stakes.length === 0) {
    return <div className="text-[var(--gray-500)] text-center py-12">まだデバイスシェアを所有していません</div>;
  }

  return (
    <div className="space-y-3">
      <div className="bg-gradient-to-r from-[var(--primary-50)] to-blue-50 rounded-xl p-4 border border-[var(--primary-100)]">
        <div className="text-xs text-[var(--gray-500)]">推定報酬合計</div>
        <div className="text-2xl font-bold text-[var(--primary-700)]">
          {(portfolio.total_estimated_reward_per_hour / 1000).toFixed(3)}
          <span className="text-sm text-[var(--gray-500)] ml-1">SOMS/時</span>
        </div>
      </div>

      {portfolio.stakes.map(s => (
        <button
          key={s.device_id}
          onClick={() => navigate(`/invest/device/${s.device_id}`)}
          className="w-full bg-white rounded-xl p-3 text-left elevation-1 cursor-pointer"
        >
          <div className="flex items-center justify-between mb-1">
            <span className="font-medium text-[var(--gray-900)] truncate mr-2">{s.device_id}</span>
            <DeviceTypeBadge type={s.device_type} />
          </div>
          <div className="flex items-center justify-between text-sm text-[var(--gray-500)]">
            <span>{s.shares}/{s.total_shares} シェア ({s.percentage.toFixed(1)}%)</span>
            <span className="text-[var(--gold-dark)]">{(s.estimated_reward_per_hour / 1000).toFixed(3)}/時</span>
          </div>
        </button>
      ))}
    </div>
  );
}

function DevicesTab({
  devices,
  navigate,
}: {
  devices: Device[];
  navigate: ReturnType<typeof useNavigate>;
}) {
  if (devices.length === 0) {
    return <div className="text-[var(--gray-500)] text-center py-12">登録デバイスなし</div>;
  }

  const sorted = [...devices].sort((a, b) => {
    if (a.funding_open !== b.funding_open) return a.funding_open ? -1 : 1;
    return a.device_id.localeCompare(b.device_id);
  });

  return (
    <div className="space-y-3">
      {sorted.map(d => (
        <button
          key={d.id}
          onClick={() => navigate(`/invest/device/${d.device_id}`)}
          className="w-full bg-white rounded-xl p-3 text-left elevation-1 cursor-pointer"
        >
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-2 min-w-0">
              <span className="font-medium text-[var(--gray-900)] truncate">{d.display_name || d.device_id}</span>
              <DeviceTypeBadge type={d.device_type} />
            </div>
            {d.funding_open && (
              <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-[var(--success-50)] text-[var(--success-700)] shrink-0">
                募集中
              </span>
            )}
          </div>
          <div className="flex items-center justify-between text-sm text-[var(--gray-500)]">
            <span>{d.available_shares}/{d.total_shares} 残</span>
            <span>{(d.share_price / 1000).toFixed(3)} SOMS/シェア</span>
          </div>
        </button>
      ))}
    </div>
  );
}

const STATUS_COLORS: Record<string, string> = {
  open: 'bg-[var(--success-50)] text-[var(--success-700)]',
  funded: 'bg-gradient-to-r from-yellow-100 to-amber-100 text-[var(--gold-dark)]',
  active: 'bg-[var(--info-50)] text-[var(--info-700)]',
  closed: 'bg-[var(--gray-100)] text-[var(--gray-500)]',
};

const STATUS_LABELS: Record<string, string> = {
  open: '募集中',
  funded: '調達完了',
  active: '稼働中',
  closed: '終了',
};

function PoolsTab({ pools }: { pools: PoolListItem[] }) {
  if (pools.length === 0) {
    return <div className="text-[var(--gray-500)] text-center py-12">プールなし</div>;
  }

  return (
    <div className="space-y-3">
      {pools.map(p => {
        const date = new Date(p.created_at);
        const dateStr = `${date.getMonth() + 1}/${date.getDate()}`;
        return (
          <div key={p.id} className="bg-white rounded-xl p-3 space-y-2 elevation-1">
            <div className="flex items-center justify-between">
              <span className="font-medium text-[var(--gray-900)]">{p.title}</span>
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[p.status] || STATUS_COLORS.closed}`}>
                {STATUS_LABELS[p.status] || p.status}
              </span>
            </div>
            <ProgressBar
              value={p.progress_pct}
              label={`\u00a5${p.raised_jpy.toLocaleString()} / \u00a5${p.goal_jpy.toLocaleString()}`}
            />
            <div className="text-xs text-[var(--gray-500)] text-right">{dateStr}</div>
          </div>
        );
      })}
    </div>
  );
}
