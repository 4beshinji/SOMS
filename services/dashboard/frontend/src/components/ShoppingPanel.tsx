import { memo, useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { ShoppingItem } from '@soms/types';
import {
  fetchShopping,
  fetchShoppingStats,
  addShoppingItem,
  purchaseShoppingItem,
  deleteShoppingItem,
  createShoppingShareLink,
} from '../api';

const CATEGORY_COLORS: Record<string, string> = {
  '食品': 'bg-green-600/20 text-green-300',
  '日用品': 'bg-blue-600/20 text-blue-300',
  '消耗品': 'bg-yellow-600/20 text-yellow-300',
  '飲料': 'bg-cyan-600/20 text-cyan-300',
  '調味料': 'bg-orange-600/20 text-orange-300',
  '文具': 'bg-purple-600/20 text-purple-300',
  '備品': 'bg-pink-600/20 text-pink-300',
};

const PRIORITY_STYLES: Record<number, string> = {
  0: 'opacity-60',
  1: '',
  2: 'font-semibold text-red-400',
};

const ShoppingPanel = memo(function ShoppingPanel() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [store, setStore] = useState('');
  const [filterStore, setFilterStore] = useState<string | null>(null);
  const [shareNotice, setShareNotice] = useState(false);

  const itemsQuery = useQuery({
    queryKey: ['shopping'],
    queryFn: fetchShopping,
    refetchInterval: 10000,
    staleTime: 5000,
  });

  const statsQuery = useQuery({
    queryKey: ['shopping-stats'],
    queryFn: fetchShoppingStats,
    refetchInterval: 30000,
    staleTime: 15000,
  });

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['shopping'] });
    queryClient.invalidateQueries({ queryKey: ['shopping-stats'] });
  }, [queryClient]);

  const addMutation = useMutation({
    mutationFn: addShoppingItem,
    onSuccess: invalidate,
  });

  const purchaseMutation = useMutation({
    mutationFn: purchaseShoppingItem,
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteShoppingItem,
    onSuccess: invalidate,
  });

  const handleAdd = useCallback(() => {
    if (!name.trim()) return;
    addMutation.mutate({
      name: name.trim(),
      category: category || undefined,
      store: store || undefined,
    });
    setName('');
    setCategory('');
    setStore('');
    setShowForm(false);
  }, [name, category, store, addMutation]);

  const handleShare = useCallback(async () => {
    try {
      const result = await createShoppingShareLink();
      await navigator.clipboard.writeText(result.share_url);
      setShareNotice(true);
      setTimeout(() => setShareNotice(false), 3000);
    } catch { /* ignore */ }
  }, []);

  const items = itemsQuery.data ?? [];
  const stats = statsQuery.data;
  const pending = items.filter(i => !i.is_purchased);
  const stores = [...new Set(pending.map(i => i.store).filter(Boolean))] as string[];
  const filtered = filterStore ? pending.filter(i => i.store === filterStore) : pending;

  // Group by category
  const grouped = filtered.reduce<Record<string, ShoppingItem[]>>((acc, item) => {
    const cat = item.category || '未分類';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(item);
    return acc;
  }, {});

  return (
    <div className="bg-[var(--gray-800)] rounded-xl border border-[var(--gray-700)] overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--gray-700)] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">🛒</span>
          <span className="text-sm font-semibold text-[var(--gray-100)]">買い物リスト</span>
          {stats && stats.pending_items > 0 && (
            <span className="bg-[var(--primary)] text-white text-[10px] px-1.5 py-0.5 rounded-full font-medium">
              {stats.pending_items}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={handleShare}
            className="p-1.5 rounded hover:bg-[var(--gray-700)] text-[var(--gray-400)] hover:text-[var(--gray-200)] transition-colors"
            title="共有リンク作成"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
            </svg>
          </button>
          <button
            onClick={() => setShowForm(!showForm)}
            className="p-1.5 rounded hover:bg-[var(--gray-700)] text-[var(--gray-400)] hover:text-[var(--gray-200)] transition-colors"
          >
            {showForm ? (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            )}
          </button>
        </div>
      </div>

      <div className="px-4 py-3 space-y-3">
        {/* Share notice */}
        {shareNotice && (
          <div className="text-xs text-[var(--gray-400)] bg-[var(--gray-700)] rounded p-2">
            共有リンクをコピーしました
          </div>
        )}

        {/* Add form */}
        {showForm && (
          <div className="space-y-2 pb-3 border-b border-[var(--gray-700)]">
            <input
              type="text"
              placeholder="アイテム名"
              value={name}
              onChange={e => setName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAdd()}
              className="w-full h-8 px-2 text-xs rounded border border-[var(--gray-600)] bg-[var(--gray-900)] text-[var(--gray-100)] placeholder:text-[var(--gray-500)] focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
            />
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="カテゴリ"
                value={category}
                onChange={e => setCategory(e.target.value)}
                className="flex-1 h-8 px-2 text-xs rounded border border-[var(--gray-600)] bg-[var(--gray-900)] text-[var(--gray-100)] placeholder:text-[var(--gray-500)] focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
              />
              <input
                type="text"
                placeholder="店舗"
                value={store}
                onChange={e => setStore(e.target.value)}
                className="flex-1 h-8 px-2 text-xs rounded border border-[var(--gray-600)] bg-[var(--gray-900)] text-[var(--gray-100)] placeholder:text-[var(--gray-500)] focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
              />
            </div>
            <button
              onClick={handleAdd}
              disabled={!name.trim()}
              className="w-full h-7 text-xs rounded bg-[var(--primary)] text-white hover:opacity-90 disabled:opacity-40 transition-opacity"
            >
              追加
            </button>
          </div>
        )}

        {/* Store filter */}
        {stores.length > 0 && (
          <div className="flex gap-1 flex-wrap">
            <button
              className={`text-[10px] px-2 py-0.5 rounded-full transition-colors ${
                !filterStore
                  ? 'bg-[var(--primary)] text-white'
                  : 'bg-[var(--gray-700)] text-[var(--gray-400)] hover:bg-[var(--gray-600)]'
              }`}
              onClick={() => setFilterStore(null)}
            >
              全店舗
            </button>
            {stores.map(s => (
              <button
                key={s}
                className={`text-[10px] px-2 py-0.5 rounded-full transition-colors ${
                  filterStore === s
                    ? 'bg-[var(--primary)] text-white'
                    : 'bg-[var(--gray-700)] text-[var(--gray-400)] hover:bg-[var(--gray-600)]'
                }`}
                onClick={() => setFilterStore(filterStore === s ? null : s)}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Item groups */}
        {itemsQuery.isLoading ? (
          <p className="text-xs text-[var(--gray-500)] py-4 text-center">読み込み中...</p>
        ) : Object.keys(grouped).length === 0 ? (
          <p className="text-xs text-[var(--gray-500)] py-4 text-center">リストは空です</p>
        ) : (
          Object.entries(grouped).map(([cat, catItems]) => (
            <div key={cat}>
              <div className="flex items-center gap-1.5 mb-1">
                <span
                  className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                    CATEGORY_COLORS[cat] || 'bg-[var(--gray-700)] text-[var(--gray-400)]'
                  }`}
                >
                  {cat}
                </span>
                <span className="text-[10px] text-[var(--gray-500)]">{catItems.length}</span>
              </div>
              {catItems.map(item => (
                <div key={item.id} className="flex items-center gap-2 py-1 group">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5 rounded cursor-pointer accent-[var(--primary)]"
                    checked={false}
                    onChange={() => purchaseMutation.mutate(item.id)}
                  />
                  <span className={`text-xs flex-1 truncate text-[var(--gray-200)] ${PRIORITY_STYLES[item.priority] || ''}`}>
                    {item.name}
                    {item.quantity > 1 && (
                      <span className="text-[var(--gray-500)] ml-1">
                        x{item.quantity}{item.unit || ''}
                      </span>
                    )}
                    {item.quantity === 1 && item.unit && (
                      <span className="text-[var(--gray-500)] ml-1">{item.unit}</span>
                    )}
                  </span>
                  {item.is_recurring && (
                    <span title={`${item.recurrence_days}日ごと`} className="text-[var(--gray-500)]">
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                    </span>
                  )}
                  {item.store && (
                    <span className="text-[9px] text-[var(--gray-500)] bg-[var(--gray-700)] px-1 rounded">
                      {item.store}
                    </span>
                  )}
                  {item.price != null && (
                    <span className="text-[10px] text-[var(--gray-500)]">
                      ¥{item.price.toLocaleString()}
                    </span>
                  )}
                  <button
                    className="opacity-0 group-hover:opacity-100 transition-opacity text-[var(--gray-500)] hover:text-red-400"
                    onClick={() => deleteMutation.mutate(item.id)}
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          ))
        )}

        {/* Stats footer */}
        {stats && stats.total_spent_this_month > 0 && (
          <div className="pt-2 border-t border-[var(--gray-700)] flex justify-between text-[10px] text-[var(--gray-500)]">
            <span>今月の支出</span>
            <span className="font-medium text-[var(--gray-300)]">
              ¥{stats.total_spent_this_month.toLocaleString()}
            </span>
          </div>
        )}
      </div>
    </div>
  );
});

export default ShoppingPanel;
