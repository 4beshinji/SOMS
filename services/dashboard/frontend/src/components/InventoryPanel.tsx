import { memo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchInventoryLiveStatus } from '../api';
import type { InventoryLiveItem } from '@soms/types';

const InventoryPanel = memo(function InventoryPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['inventory-live'],
    queryFn: fetchInventoryLiveStatus,
    refetchInterval: 10000,
    staleTime: 5000,
  });

  const items = data?.items ?? [];
  const lowCount = items.filter(i => i.status === 'low').length;
  const totalWeight = items.reduce(
    (sum, i) => sum + (i.current_weight_g ?? 0),
    0,
  );

  const updatedAgo = data?.updated_at
    ? Math.round((Date.now() / 1000 - data.updated_at))
    : null;

  if (isLoading) {
    return (
      <div className="p-3">
        <p className="text-sm text-[var(--text-muted)] text-center py-4">
          在庫データ読込中...
        </p>
      </div>
    );
  }

  if (items.length === 0) {
    return null; // Don't render panel when no inventory items
  }

  return (
    <div className="p-3 space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider px-1">
          在庫状況
        </h2>
        {lowCount > 0 && (
          <span className="px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-red-600/30 text-red-300">
            {lowCount} low
          </span>
        )}
      </div>

      {/* Items */}
      <div className="space-y-1">
        {items.map((item) => (
          <ItemRow key={`${item.device_id}:${item.item_name}`} item={item} />
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-[10px] text-[var(--text-muted)] px-1 pt-1">
        <span>{totalWeight.toFixed(0)}g total</span>
        {updatedAgo !== null && updatedAgo < 300 && (
          <span>{updatedAgo}s ago</span>
        )}
      </div>
    </div>
  );
});

function ItemRow({ item }: { item: InventoryLiveItem }) {
  const isLow = item.status === 'low';

  return (
    <div
      className={`flex items-center justify-between px-2 py-1.5 rounded text-sm
        ${isLow
          ? 'bg-red-900/20 border border-red-800/30'
          : 'bg-[var(--card-bg)] border border-[var(--border-color)]'
        }`}
    >
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-base flex-shrink-0">
          {isLow ? '\u26a0\ufe0f' : '\u2705'}
        </span>
        <span className="truncate text-[var(--text-primary)]">
          {item.item_name}
        </span>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <span
          className={`font-mono font-bold text-sm
            ${isLow ? 'text-red-400' : 'text-[var(--text-primary)]'}`}
        >
          x{item.quantity}
        </span>
      </div>
    </div>
  );
}

export default InventoryPanel;
