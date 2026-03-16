import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Spinner } from '@soms/ui';
import type { ShoppingItem, ShoppingItemCreate, PurchaseHistory } from '@soms/types';
import {
  useShoppingItems,
  useShoppingStats,
  useShoppingHistory,
  useRecurringItems,
  useDueItems,
  useCreateShoppingItem,
  useUpdateShoppingItem,
  usePurchaseShoppingItem,
  useDeleteShoppingItem,
  useShareShoppingItems,
} from '../hooks/useShopping';
import type { ShoppingItemUpdate } from '../api/shopping';

// ── Constants ────────────────────────────────────────────────────────

const CATEGORIES = ['食品', '日用品', '消耗品', '飲料', '調味料', '文具', '備品'];

const CATEGORY_COLORS: Record<string, string> = {
  食品: '#4CAF50',
  日用品: '#FF9800',
  消耗品: '#9C27B0',
  飲料: '#2196F3',
  調味料: '#F44336',
  文具: '#03A9F4',
  備品: '#607D8B',
};

const PRIORITY_LABELS: Record<number, { label: string; bg: string; text: string }> = {
  0: { label: '低', bg: 'var(--gray-100)', text: 'var(--gray-600)' },
  1: { label: '通常', bg: 'var(--primary-50)', text: 'var(--primary-700)' },
  2: { label: '高', bg: 'var(--error-50)', text: 'var(--error-600)' },
};

type Tab = 'list' | 'recurring' | 'history';

// ── Add / Edit Form ──────────────────────────────────────────────────

function ItemForm({
  initial,
  onClose,
}: {
  initial?: ShoppingItem;
  onClose: () => void;
}) {
  const createMutation = useCreateShoppingItem();
  const updateMutation = useUpdateShoppingItem();
  const isEdit = !!initial;

  const [form, setForm] = useState<ShoppingItemCreate & { is_recurring?: boolean; recurrence_days?: number }>({
    name: initial?.name ?? '',
    category: initial?.category ?? '',
    quantity: initial?.quantity ?? 1,
    unit: initial?.unit ?? '',
    store: initial?.store ?? '',
    price: initial?.price ?? undefined,
    is_recurring: initial?.is_recurring ?? false,
    recurrence_days: initial?.recurrence_days ?? undefined,
    notes: initial?.notes ?? '',
    priority: initial?.priority ?? 1,
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload = {
      ...form,
      category: form.category || undefined,
      unit: form.unit || undefined,
      store: form.store || undefined,
      price: form.price || undefined,
      notes: form.notes || undefined,
      recurrence_days: form.is_recurring ? form.recurrence_days : undefined,
    };
    if (isEdit) {
      updateMutation.mutate(
        { id: initial.id, data: payload as ShoppingItemUpdate },
        { onSuccess: onClose },
      );
    } else {
      createMutation.mutate(payload, { onSuccess: onClose });
    }
  };

  const isPending = createMutation.isPending || updateMutation.isPending;
  const inputClass =
    'w-full px-3 py-1.5 rounded-lg border border-[var(--gray-300)] bg-white text-sm text-[var(--gray-700)] focus:outline-none focus:border-[var(--primary-500)]';
  const labelClass = 'block text-xs font-medium text-[var(--gray-500)] mb-1';

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      className="bg-white rounded-xl elevation-2 p-6 mb-6 overflow-hidden"
    >
      <h3 className="text-base font-semibold text-[var(--gray-900)] mb-4">
        {isEdit ? 'アイテム編集' : 'アイテム追加'}
      </h3>
      <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div>
          <label className={labelClass}>名前 *</label>
          <input
            required
            className={inputClass}
            placeholder="牛乳"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>
        <div>
          <label className={labelClass}>カテゴリ</label>
          <select
            className={inputClass}
            value={form.category ?? ''}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
          >
            <option value="">未分類</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <div>
          <label className={labelClass}>優先度</label>
          <select
            className={inputClass}
            value={form.priority ?? 1}
            onChange={(e) => setForm({ ...form, priority: parseInt(e.target.value) })}
          >
            <option value={0}>低</option>
            <option value={1}>通常</option>
            <option value={2}>高</option>
          </select>
        </div>
        <div>
          <label className={labelClass}>数量</label>
          <input
            type="number"
            min="1"
            className={inputClass}
            value={form.quantity ?? 1}
            onChange={(e) => setForm({ ...form, quantity: parseInt(e.target.value) || 1 })}
          />
        </div>
        <div>
          <label className={labelClass}>単位</label>
          <input
            className={inputClass}
            placeholder="本, kg, 個"
            value={form.unit ?? ''}
            onChange={(e) => setForm({ ...form, unit: e.target.value })}
          />
        </div>
        <div>
          <label className={labelClass}>購入店</label>
          <input
            className={inputClass}
            placeholder="スーパー"
            value={form.store ?? ''}
            onChange={(e) => setForm({ ...form, store: e.target.value })}
          />
        </div>
        <div>
          <label className={labelClass}>価格 (円)</label>
          <input
            type="number"
            min="0"
            className={inputClass}
            value={form.price ?? ''}
            onChange={(e) => setForm({ ...form, price: parseInt(e.target.value) || undefined })}
          />
        </div>
        <div>
          <label className="flex items-center gap-2 cursor-pointer mt-5">
            <input
              type="checkbox"
              checked={form.is_recurring ?? false}
              onChange={(e) => setForm({ ...form, is_recurring: e.target.checked })}
              className="rounded border-[var(--gray-300)]"
            />
            <span className="text-sm text-[var(--gray-700)]">定期購入</span>
          </label>
        </div>
        {form.is_recurring && (
          <div>
            <label className={labelClass}>間隔 (日)</label>
            <input
              type="number"
              min="1"
              className={inputClass}
              value={form.recurrence_days ?? ''}
              onChange={(e) => setForm({ ...form, recurrence_days: parseInt(e.target.value) || undefined })}
            />
          </div>
        )}
        <div className="md:col-span-2 lg:col-span-3">
          <label className={labelClass}>メモ</label>
          <input
            className={inputClass}
            placeholder="朝食用、無脂肪タイプ"
            value={form.notes ?? ''}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
          />
        </div>

        <div className="md:col-span-2 lg:col-span-3 flex gap-3 pt-2">
          <button
            type="submit"
            disabled={isPending}
            className="px-4 py-2 bg-[var(--primary-500)] text-white text-sm rounded-lg font-medium hover:bg-[var(--primary-600)] transition-colors disabled:opacity-50"
          >
            {isPending ? '保存中...' : isEdit ? '更新' : '追加'}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-[var(--gray-100)] text-[var(--gray-700)] text-sm rounded-lg font-medium hover:bg-[var(--gray-200)] transition-colors"
          >
            キャンセル
          </button>
        </div>
      </form>
    </motion.div>
  );
}

// ── Item Card ────────────────────────────────────────────────────────

function ShoppingItemCard({
  item,
  index,
  onEdit,
}: {
  item: ShoppingItem;
  index: number;
  onEdit: (item: ShoppingItem) => void;
}) {
  const purchaseMutation = usePurchaseShoppingItem();
  const deleteMutation = useDeleteShoppingItem();
  const pri = PRIORITY_LABELS[item.priority] ?? PRIORITY_LABELS[1];

  const isDue =
    item.is_recurring &&
    item.next_purchase_at &&
    new Date(item.next_purchase_at) <= new Date();

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
      className={`bg-white rounded-xl elevation-2 p-5 ${isDue ? 'ring-2 ring-[var(--error-300)]' : ''}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium"
            style={{ backgroundColor: pri.bg, color: pri.text }}
          >
            {pri.label}
          </span>
          <h4 className="font-semibold text-[var(--gray-900)] text-base truncate">{item.name}</h4>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {isDue && (
            <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-[var(--error-50)] text-[var(--error-600)]">
              期限
            </span>
          )}
          {item.category && (
            <span
              className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium text-white"
              style={{ backgroundColor: CATEGORY_COLORS[item.category] ?? '#9E9E9E' }}
            >
              {item.category}
            </span>
          )}
        </div>
      </div>

      {/* Details */}
      <div className="space-y-1.5 mb-3">
        <div className="flex items-center justify-between">
          <span className="text-xs text-[var(--gray-500)]">数量</span>
          <span className="text-xs text-[var(--gray-700)]">
            {item.quantity}{item.unit ? ` ${item.unit}` : ''}
          </span>
        </div>
        {item.store && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-[var(--gray-500)]">購入店</span>
            <span className="text-xs text-[var(--gray-700)]">{item.store}</span>
          </div>
        )}
        {item.price != null && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-[var(--gray-500)]">価格</span>
            <span className="text-xs text-[var(--gray-700)]">&yen;{item.price.toLocaleString()}</span>
          </div>
        )}
        {item.is_recurring && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-[var(--gray-500)]">定期</span>
            <span className="text-xs text-[var(--gray-700)]">{item.recurrence_days}日ごと</span>
          </div>
        )}
        {item.notes && (
          <div className="pt-1">
            <span className="text-xs text-[var(--gray-500)] italic">{item.notes}</span>
          </div>
        )}
        {item.created_at && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-[var(--gray-500)]">作成者</span>
            <span className="text-xs text-[var(--gray-400)]">
              {item.created_by} / {new Date(item.created_at).toLocaleDateString('ja-JP')}
            </span>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="border-t border-[var(--gray-100)] pt-3 flex items-center justify-between">
        <div className="flex gap-2">
          <button
            onClick={() => purchaseMutation.mutate(item.id)}
            disabled={purchaseMutation.isPending}
            className="text-xs px-2.5 py-1 rounded bg-[var(--success-50)] text-[var(--success-700)] hover:bg-green-100 disabled:opacity-50"
          >
            購入済み
          </button>
          <button
            onClick={() => onEdit(item)}
            className="text-xs px-2.5 py-1 rounded bg-[var(--primary-50)] text-[var(--primary-700)] hover:bg-blue-100"
          >
            編集
          </button>
        </div>
        <button
          onClick={() => {
            if (confirm(`「${item.name}」を削除しますか？`)) {
              deleteMutation.mutate(item.id);
            }
          }}
          disabled={deleteMutation.isPending}
          className="text-xs text-[var(--error-600)] hover:text-[var(--error-700)]"
        >
          削除
        </button>
      </div>
    </motion.div>
  );
}

// ── History Table ────────────────────────────────────────────────────

function HistorySection() {
  const [days, setDays] = useState(30);
  const { data: history, isLoading } = useShoppingHistory(days);

  return (
    <section className="bg-white rounded-xl border border-[var(--gray-200)] overflow-hidden">
      <div className="px-4 py-3 border-b border-[var(--gray-200)] flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--gray-900)]">購入履歴</h2>
        <select
          className="px-2 py-1 text-xs border border-[var(--gray-300)] rounded-lg bg-white text-[var(--gray-700)]"
          value={days}
          onChange={(e) => setDays(parseInt(e.target.value))}
        >
          <option value={7}>7日間</option>
          <option value={30}>30日間</option>
          <option value={90}>90日間</option>
          <option value={365}>1年間</option>
        </select>
      </div>
      {isLoading ? (
        <div className="p-4 text-sm text-[var(--gray-500)]">Loading...</div>
      ) : !history || history.length === 0 ? (
        <div className="p-6 text-center text-sm text-[var(--gray-500)]">購入履歴なし</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--gray-100)]">
                <th className="px-4 py-2 text-left text-xs font-medium text-[var(--gray-500)]">アイテム</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-[var(--gray-500)]">カテゴリ</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-[var(--gray-500)]">店舗</th>
                <th className="px-4 py-2 text-right text-xs font-medium text-[var(--gray-500)]">数量</th>
                <th className="px-4 py-2 text-right text-xs font-medium text-[var(--gray-500)]">価格</th>
                <th className="px-4 py-2 text-right text-xs font-medium text-[var(--gray-500)]">購入日</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--gray-50)]">
              {history.map((h: PurchaseHistory) => (
                <tr key={h.id} className="hover:bg-[var(--gray-50)]">
                  <td className="px-4 py-2 text-[var(--gray-900)]">{h.item_name}</td>
                  <td className="px-4 py-2 text-[var(--gray-600)]">{h.category ?? '-'}</td>
                  <td className="px-4 py-2 text-[var(--gray-600)]">{h.store ?? '-'}</td>
                  <td className="px-4 py-2 text-right text-[var(--gray-700)]">{h.quantity}</td>
                  <td className="px-4 py-2 text-right text-[var(--gray-700)]">
                    {h.price != null ? `\u00a5${h.price.toLocaleString()}` : '-'}
                  </td>
                  <td className="px-4 py-2 text-right text-[var(--gray-500)] text-xs">
                    {new Date(h.purchased_at).toLocaleDateString('ja-JP')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ── Recurring Section ────────────────────────────────────────────────

function RecurringSection() {
  const { data: recurring, isLoading: loadingRecurring } = useRecurringItems();
  const { data: due, isLoading: loadingDue } = useDueItems();
  const purchaseMutation = usePurchaseShoppingItem();

  const dueIds = new Set((due ?? []).map((d) => d.id));

  return (
    <div className="space-y-4">
      {/* Due items alert */}
      {due && due.length > 0 && (
        <div className="bg-[var(--error-50)] border border-[var(--error-200)] rounded-xl p-4">
          <h3 className="text-sm font-semibold text-[var(--error-700)] mb-2">
            期限切れアイテム ({due.length})
          </h3>
          <div className="space-y-2">
            {due.map((item) => (
              <div key={item.id} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-[var(--gray-900)]">{item.name}</span>
                  <span className="text-xs text-[var(--gray-500)]">
                    {item.quantity}{item.unit ? ` ${item.unit}` : ''}
                  </span>
                  {item.store && (
                    <span className="text-xs text-[var(--gray-400)]">@ {item.store}</span>
                  )}
                </div>
                <button
                  onClick={() => purchaseMutation.mutate(item.id)}
                  disabled={purchaseMutation.isPending}
                  className="text-xs px-2 py-1 rounded bg-white text-[var(--success-700)] hover:bg-[var(--success-50)] border border-[var(--success-200)] disabled:opacity-50"
                >
                  購入済み
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* All recurring */}
      <section className="bg-white rounded-xl border border-[var(--gray-200)] overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--gray-200)]">
          <h2 className="text-sm font-semibold text-[var(--gray-900)]">定期購入アイテム</h2>
        </div>
        {loadingRecurring || loadingDue ? (
          <div className="p-4 text-sm text-[var(--gray-500)]">Loading...</div>
        ) : !recurring || recurring.length === 0 ? (
          <div className="p-6 text-center text-sm text-[var(--gray-500)]">定期購入アイテムなし</div>
        ) : (
          <div className="divide-y divide-[var(--gray-100)]">
            {recurring.map((item) => (
              <div
                key={item.id}
                className={`px-4 py-3 flex items-center gap-3 ${dueIds.has(item.id) ? 'bg-[var(--error-50)]' : ''}`}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-[var(--gray-900)] truncate">{item.name}</span>
                    {item.category && (
                      <span
                        className="px-1.5 py-0.5 rounded-full text-xs text-white"
                        style={{ backgroundColor: CATEGORY_COLORS[item.category] ?? '#9E9E9E' }}
                      >
                        {item.category}
                      </span>
                    )}
                    {dueIds.has(item.id) && (
                      <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-[var(--error-100)] text-[var(--error-600)]">
                        期限
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-[var(--gray-500)] mt-0.5">
                    {item.recurrence_days}日ごと
                    {item.next_purchase_at && (
                      <> / 次回: {new Date(item.next_purchase_at).toLocaleDateString('ja-JP')}</>
                    )}
                    {item.store && <> / {item.store}</>}
                  </div>
                </div>
                <span className="text-sm text-[var(--gray-700)]">
                  {item.quantity}{item.unit ? ` ${item.unit}` : ''}
                </span>
                {item.price != null && (
                  <span className="text-xs text-[var(--gray-500)]">&yen;{item.price.toLocaleString()}</span>
                )}
                <button
                  onClick={() => purchaseMutation.mutate(item.id)}
                  disabled={purchaseMutation.isPending}
                  className="text-xs px-2 py-1 rounded bg-[var(--success-50)] text-[var(--success-700)] hover:bg-green-100 disabled:opacity-50"
                >
                  購入済み
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────

export default function ShoppingPage() {
  const [tab, setTab] = useState<Tab>('list');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [storeFilter, setStoreFilter] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingItem, setEditingItem] = useState<ShoppingItem | undefined>();
  const [shareUrl, setShareUrl] = useState<string | null>(null);

  const {
    data: items,
    isLoading,
    isError,
  } = useShoppingItems(categoryFilter || undefined, storeFilter || undefined);

  const { data: stats } = useShoppingStats();
  const { data: due } = useDueItems();
  const shareMutation = useShareShoppingItems();

  // Derive filters from items
  const stores = items ? [...new Set(items.filter((i) => i.store).map((i) => i.store!))].sort() : [];

  const handleEdit = (item: ShoppingItem) => {
    setEditingItem(item);
    setShowForm(true);
  };

  const handleCloseForm = () => {
    setShowForm(false);
    setEditingItem(undefined);
  };

  const handleShare = () => {
    shareMutation.mutate(0, {
      onSuccess: (data) => {
        setShareUrl(data.share_url);
        navigator.clipboard.writeText(data.share_url).catch(() => {});
      },
    });
  };

  const tabClass = (t: Tab) =>
    `px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
      tab === t
        ? 'border-[var(--primary-500)] text-[var(--primary-700)]'
        : 'border-transparent text-[var(--gray-500)] hover:text-[var(--gray-700)]'
    }`;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-[var(--gray-900)]">Shopping</h2>
        <p className="text-sm text-[var(--gray-500)] mt-1">
          買い物リスト管理 &mdash; アイテム追加・購入管理・定期購入・購入履歴
        </p>
      </div>

      {/* Stats overview */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-xl elevation-2 p-4 text-center">
            <div className="text-2xl font-bold text-[var(--gray-900)]">{stats.pending_items}</div>
            <div className="text-xs text-[var(--gray-500)]">未購入</div>
          </div>
          <div className="bg-white rounded-xl elevation-2 p-4 text-center">
            <div className="text-2xl font-bold text-[var(--primary-600)]">{stats.purchased_items}</div>
            <div className="text-xs text-[var(--gray-500)]">購入済み</div>
          </div>
          <div className="bg-white rounded-xl elevation-2 p-4 text-center">
            <div className={`text-2xl font-bold ${(due?.length ?? 0) > 0 ? 'text-[var(--error-600)]' : 'text-[var(--gray-900)]'}`}>
              {due?.length ?? 0}
            </div>
            <div className="text-xs text-[var(--gray-500)]">期限切れ</div>
          </div>
          <div className="bg-white rounded-xl elevation-2 p-4 text-center">
            <div className="text-2xl font-bold text-[var(--gold-dark)]">
              &yen;{(stats.total_spent_this_month ?? 0).toLocaleString()}
            </div>
            <div className="text-xs text-[var(--gray-500)]">今月の支出</div>
          </div>
        </div>
      )}

      {/* Category breakdown */}
      {stats && Object.keys(stats.category_breakdown).length > 0 && (
        <div className="flex flex-wrap gap-2 mb-6">
          {Object.entries(stats.category_breakdown).map(([cat, count]) => (
            <span
              key={cat}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium text-white cursor-pointer hover:opacity-80 transition-opacity"
              style={{ backgroundColor: CATEGORY_COLORS[cat] ?? '#9E9E9E' }}
              onClick={() => setCategoryFilter(categoryFilter === cat ? '' : cat)}
            >
              {cat}: {count}
            </span>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex items-center border-b border-[var(--gray-200)] mb-6">
        <button className={tabClass('list')} onClick={() => setTab('list')}>
          リスト
        </button>
        <button className={tabClass('recurring')} onClick={() => setTab('recurring')}>
          定期購入
          {(due?.length ?? 0) > 0 && (
            <span className="ml-1.5 px-1.5 py-0.5 rounded-full text-xs bg-[var(--error-500)] text-white">
              {due!.length}
            </span>
          )}
        </button>
        <button className={tabClass('history')} onClick={() => setTab('history')}>
          購入履歴
        </button>

        {/* Actions (right side) */}
        <div className="ml-auto flex items-center gap-2">
          {tab === 'list' && (
            <>
              <button
                onClick={handleShare}
                disabled={shareMutation.isPending}
                className="px-3 py-1.5 text-xs font-medium bg-[var(--gray-100)] text-[var(--gray-700)] rounded-lg hover:bg-[var(--gray-200)] transition-colors disabled:opacity-50"
              >
                {shareMutation.isPending ? '生成中...' : '共有リンク'}
              </button>
              <button
                onClick={() => {
                  if (showForm && !editingItem) {
                    handleCloseForm();
                  } else {
                    setEditingItem(undefined);
                    setShowForm(true);
                  }
                }}
                className="px-4 py-1.5 bg-[var(--primary-500)] text-white text-sm rounded-lg font-medium hover:bg-[var(--primary-600)] transition-colors"
              >
                {showForm && !editingItem ? '閉じる' : '+ 追加'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Share URL banner */}
      <AnimatePresence>
        {shareUrl && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mb-4 p-3 bg-[var(--success-50)] border border-[var(--success-200)] rounded-lg flex items-center justify-between overflow-hidden"
          >
            <div className="text-sm text-[var(--success-700)]">
              共有リンクをクリップボードにコピーしました:
              <span className="ml-2 font-mono text-xs break-all">{shareUrl}</span>
            </div>
            <button
              onClick={() => setShareUrl(null)}
              className="text-xs text-[var(--gray-500)] hover:text-[var(--gray-700)] ml-3 flex-shrink-0"
            >
              閉じる
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── List Tab ── */}
      {tab === 'list' && (
        <>
          {/* Add/Edit form */}
          <AnimatePresence>
            {showForm && <ItemForm initial={editingItem} onClose={handleCloseForm} />}
          </AnimatePresence>

          {/* Filters */}
          <div className="flex flex-wrap items-center gap-3 mb-6">
            <div>
              <label className="block text-xs font-medium text-[var(--gray-500)] mb-1">カテゴリ</label>
              <select
                className="px-3 py-1.5 rounded-lg border border-[var(--gray-300)] bg-white text-sm text-[var(--gray-700)] focus:outline-none focus:border-[var(--primary-500)]"
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
              >
                <option value="">すべて</option>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-[var(--gray-500)] mb-1">店舗</label>
              <select
                className="px-3 py-1.5 rounded-lg border border-[var(--gray-300)] bg-white text-sm text-[var(--gray-700)] focus:outline-none focus:border-[var(--primary-500)]"
                value={storeFilter}
                onChange={(e) => setStoreFilter(e.target.value)}
              >
                <option value="">すべて</option>
                {stores.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Loading */}
          {isLoading && (
            <div className="flex items-center justify-center py-16">
              <Spinner size="large" className="text-[var(--primary-500)]" />
            </div>
          )}

          {/* Error */}
          {isError && (
            <div className="text-center py-16 text-[var(--gray-500)]">
              買い物リストの読み込みに失敗しました。
            </div>
          )}

          {/* Empty */}
          {!isLoading && !isError && items && items.length === 0 && (
            <div className="text-center py-16 text-[var(--gray-500)]">
              <p className="text-lg mb-2">買い物リストは空です</p>
              <p className="text-sm">「+ 追加」からアイテムを追加してください。</p>
            </div>
          )}

          {/* Item grid */}
          {!isLoading && !isError && items && items.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {items.map((item, i) => (
                <ShoppingItemCard key={item.id} item={item} index={i} onEdit={handleEdit} />
              ))}
            </div>
          )}
        </>
      )}

      {/* ── Recurring Tab ── */}
      {tab === 'recurring' && <RecurringSection />}

      {/* ── History Tab ── */}
      {tab === 'history' && <HistorySection />}
    </div>
  );
}
