import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Spinner } from '@soms/ui';
import type { InventoryItem, InventoryItemCreate } from '@soms/types';
import {
  useInventoryItems,
  useCreateInventoryItem,
  useUpdateInventoryItem,
  useDeleteInventoryItem,
} from '../hooks/useInventory';

// ── Category config ─────────────────────────────────────────────────

const CATEGORY_COLORS: Record<string, string> = {
  飲料: '#2196F3',
  食品: '#4CAF50',
  日用品: '#FF9800',
  消耗品: '#9C27B0',
  調味料: '#F44336',
  文具: '#03A9F4',
  備品: '#607D8B',
};

function categoryColor(cat?: string | null): string {
  if (!cat) return '#9E9E9E';
  return CATEGORY_COLORS[cat] ?? '#9E9E9E';
}

// ── Stock level helpers ─────────────────────────────────────────────

function stockBadge(item: InventoryItem) {
  // We don't have live weight data here, so show threshold config
  return {
    label: `閾値: ${item.min_threshold}`,
    bg: 'var(--gray-100)',
    text: 'var(--gray-600)',
  };
}

// ── Add Item Form ───────────────────────────────────────────────────

function AddItemForm({ onClose }: { onClose: () => void }) {
  const createMutation = useCreateInventoryItem();
  const [form, setForm] = useState<InventoryItemCreate>({
    device_id: '',
    channel: 'weight',
    zone: '',
    item_name: '',
    category: '',
    unit_weight_g: 0,
    tare_weight_g: 0,
    min_threshold: 2,
    reorder_quantity: 1,
    store: '',
    price: undefined,
    barcode: '',
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: InventoryItemCreate = {
      ...form,
      category: form.category || undefined,
      store: form.store || undefined,
      barcode: form.barcode || undefined,
      price: form.price || undefined,
    };
    createMutation.mutate(payload, { onSuccess: onClose });
  };

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
        在庫アイテム追加
      </h3>
      <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div>
          <label className={labelClass}>デバイスID *</label>
          <input
            required
            className={inputClass}
            placeholder="shelf_01"
            value={form.device_id}
            onChange={(e) => setForm({ ...form, device_id: e.target.value })}
          />
        </div>
        <div>
          <label className={labelClass}>チャンネル</label>
          <input
            className={inputClass}
            placeholder="weight"
            value={form.channel ?? 'weight'}
            onChange={(e) => setForm({ ...form, channel: e.target.value })}
          />
        </div>
        <div>
          <label className={labelClass}>ゾーン *</label>
          <input
            required
            className={inputClass}
            placeholder="kitchen"
            value={form.zone}
            onChange={(e) => setForm({ ...form, zone: e.target.value })}
          />
        </div>
        <div>
          <label className={labelClass}>アイテム名 *</label>
          <input
            required
            className={inputClass}
            placeholder="コーヒー豆"
            value={form.item_name}
            onChange={(e) => setForm({ ...form, item_name: e.target.value })}
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
            {Object.keys(CATEGORY_COLORS).map((cat) => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
          </select>
        </div>
        <div>
          <label className={labelClass}>単位重量 (g) *</label>
          <input
            required
            type="number"
            step="0.1"
            min="0"
            className={inputClass}
            value={form.unit_weight_g || ''}
            onChange={(e) => setForm({ ...form, unit_weight_g: parseFloat(e.target.value) || 0 })}
          />
        </div>
        <div>
          <label className={labelClass}>風袋重量 (g)</label>
          <input
            type="number"
            step="0.1"
            min="0"
            className={inputClass}
            value={form.tare_weight_g || ''}
            onChange={(e) => setForm({ ...form, tare_weight_g: parseFloat(e.target.value) || 0 })}
          />
        </div>
        <div>
          <label className={labelClass}>最低閾値</label>
          <input
            type="number"
            min="0"
            className={inputClass}
            value={form.min_threshold ?? 2}
            onChange={(e) => setForm({ ...form, min_threshold: parseInt(e.target.value) || 0 })}
          />
        </div>
        <div>
          <label className={labelClass}>再注文数量</label>
          <input
            type="number"
            min="1"
            className={inputClass}
            value={form.reorder_quantity ?? 1}
            onChange={(e) => setForm({ ...form, reorder_quantity: parseInt(e.target.value) || 1 })}
          />
        </div>
        <div>
          <label className={labelClass}>購入店</label>
          <input
            className={inputClass}
            placeholder="カルディ"
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
          <label className={labelClass}>バーコード</label>
          <input
            className={inputClass}
            placeholder="4901234567890"
            value={form.barcode ?? ''}
            onChange={(e) => setForm({ ...form, barcode: e.target.value })}
          />
        </div>

        <div className="md:col-span-2 lg:col-span-3 flex gap-3 pt-2">
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="px-4 py-2 bg-[var(--primary-500)] text-white text-sm rounded-lg font-medium hover:bg-[var(--primary-600)] transition-colors disabled:opacity-50"
          >
            {createMutation.isPending ? '作成中...' : '追加'}
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

// ── Item Card ───────────────────────────────────────────────────────

function InventoryItemCard({
  item,
  index,
}: {
  item: InventoryItem;
  index: number;
}) {
  const updateMutation = useUpdateInventoryItem();
  const deleteMutation = useDeleteInventoryItem();
  const [editing, setEditing] = useState(false);
  const [editThreshold, setEditThreshold] = useState(item.min_threshold);
  const [editReorder, setEditReorder] = useState(item.reorder_quantity);

  const badge = stockBadge(item);

  const handleSave = () => {
    updateMutation.mutate(
      { id: item.id, data: { min_threshold: editThreshold, reorder_quantity: editReorder } },
      { onSuccess: () => setEditing(false) },
    );
  };

  const toggleActive = () => {
    updateMutation.mutate({ id: item.id, data: { is_active: !item.is_active } });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
      className={`bg-white rounded-xl elevation-2 p-5 ${!item.is_active ? 'opacity-50' : ''}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className="w-2.5 h-2.5 rounded-full flex-shrink-0"
            style={{ backgroundColor: item.is_active ? '#4CAF50' : '#9E9E9E' }}
          />
          <h4 className="font-semibold text-[var(--gray-900)] text-base truncate">
            {item.item_name}
          </h4>
        </div>
        {item.category && (
          <span
            className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium text-white flex-shrink-0"
            style={{ backgroundColor: categoryColor(item.category) }}
          >
            {item.category}
          </span>
        )}
      </div>

      {/* Device info */}
      <div className="space-y-1.5 mb-3">
        <div className="flex items-center justify-between">
          <span className="text-xs text-[var(--gray-500)]">デバイス</span>
          <span className="text-xs font-mono text-[var(--gray-700)]">
            {item.device_id}:{item.channel}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-[var(--gray-500)]">ゾーン</span>
          <span className="text-xs text-[var(--gray-700)]">{item.zone}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-[var(--gray-500)]">単位重量</span>
          <span className="text-xs text-[var(--gray-700)]">{item.unit_weight_g}g</span>
        </div>
        {item.tare_weight_g > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-[var(--gray-500)]">風袋</span>
            <span className="text-xs text-[var(--gray-700)]">{item.tare_weight_g}g</span>
          </div>
        )}
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
        {item.barcode && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-[var(--gray-500)]">バーコード</span>
            <span className="text-xs font-mono text-[var(--gray-700)]">{item.barcode}</span>
          </div>
        )}
      </div>

      {/* Threshold config */}
      <div className="border-t border-[var(--gray-100)] pt-3 mb-3">
        {editing ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <label className="text-xs text-[var(--gray-500)] w-16">閾値</label>
              <input
                type="number"
                min="0"
                className="w-20 px-2 py-1 rounded border border-[var(--gray-300)] text-xs"
                value={editThreshold}
                onChange={(e) => setEditThreshold(parseInt(e.target.value) || 0)}
              />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs text-[var(--gray-500)] w-16">再注文</label>
              <input
                type="number"
                min="1"
                className="w-20 px-2 py-1 rounded border border-[var(--gray-300)] text-xs"
                value={editReorder}
                onChange={(e) => setEditReorder(parseInt(e.target.value) || 1)}
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleSave}
                disabled={updateMutation.isPending}
                className="text-xs px-2 py-1 bg-[var(--primary-500)] text-white rounded hover:bg-[var(--primary-600)]"
              >
                保存
              </button>
              <button
                onClick={() => setEditing(false)}
                className="text-xs px-2 py-1 text-[var(--gray-600)] hover:text-[var(--gray-800)]"
              >
                取消
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <span
              className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium"
              style={{ backgroundColor: badge.bg, color: badge.text }}
            >
              {badge.label} / 再注文: {item.reorder_quantity}
            </span>
            <button
              onClick={() => {
                setEditThreshold(item.min_threshold);
                setEditReorder(item.reorder_quantity);
                setEditing(true);
              }}
              className="text-xs text-[var(--primary-600)] hover:text-[var(--primary-700)]"
            >
              編集
            </button>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between">
        <button
          onClick={toggleActive}
          disabled={updateMutation.isPending}
          className={`text-xs px-2 py-1 rounded ${
            item.is_active
              ? 'text-[var(--warning-700)] bg-[var(--warning-50)] hover:bg-orange-100'
              : 'text-[var(--primary-600)] bg-[var(--primary-50)] hover:bg-blue-100'
          }`}
        >
          {item.is_active ? '無効化' : '有効化'}
        </button>
        <button
          onClick={() => {
            if (confirm(`「${item.item_name}」を削除しますか？`)) {
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

// ── Main Page ───────────────────────────────────────────────────────

export default function InventoryPage() {
  const [zoneFilter, setZoneFilter] = useState<string>('');
  const [showInactive, setShowInactive] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);

  const {
    data: items,
    isLoading,
    isError,
  } = useInventoryItems(zoneFilter || undefined, !showInactive);

  // Derive zone list from items
  const zones = items
    ? [...new Set(items.map((i) => i.zone))].sort()
    : [];

  // Group by zone
  const grouped = (items ?? []).reduce<Record<string, InventoryItem[]>>((acc, item) => {
    if (!acc[item.zone]) acc[item.zone] = [];
    acc[item.zone].push(item);
    return acc;
  }, {});

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-[var(--gray-900)]">Inventory</h2>
        <p className="text-sm text-[var(--gray-500)] mt-1">
          棚センサーとアイテムのマッピング管理
        </p>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <div>
          <label className="block text-xs font-medium text-[var(--gray-500)] mb-1">Zone</label>
          <select
            className="px-3 py-1.5 rounded-lg border border-[var(--gray-300)] bg-white text-sm text-[var(--gray-700)] focus:outline-none focus:border-[var(--primary-500)]"
            value={zoneFilter}
            onChange={(e) => setZoneFilter(e.target.value)}
          >
            <option value="">All zones</option>
            {zones.map((z) => (
              <option key={z} value={z}>{z}</option>
            ))}
          </select>
        </div>

        <div className="flex items-end gap-3">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
              className="rounded border-[var(--gray-300)]"
            />
            <span className="text-sm text-[var(--gray-600)]">無効アイテムも表示</span>
          </label>
        </div>

        <div className="ml-auto">
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="px-4 py-2 bg-[var(--primary-500)] text-white text-sm rounded-lg font-medium hover:bg-[var(--primary-600)] transition-colors"
          >
            {showAddForm ? '閉じる' : '+ アイテム追加'}
          </button>
        </div>
      </div>

      {/* Add form */}
      <AnimatePresence>
        {showAddForm && <AddItemForm onClose={() => setShowAddForm(false)} />}
      </AnimatePresence>

      {/* Summary stats */}
      {items && items.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-xl elevation-2 p-4 text-center">
            <div className="text-2xl font-bold text-[var(--gray-900)]">{items.length}</div>
            <div className="text-xs text-[var(--gray-500)]">登録アイテム</div>
          </div>
          <div className="bg-white rounded-xl elevation-2 p-4 text-center">
            <div className="text-2xl font-bold text-[var(--primary-600)]">
              {items.filter((i) => i.is_active).length}
            </div>
            <div className="text-xs text-[var(--gray-500)]">有効</div>
          </div>
          <div className="bg-white rounded-xl elevation-2 p-4 text-center">
            <div className="text-2xl font-bold text-[var(--gray-900)]">
              {new Set(items.map((i) => i.zone)).size}
            </div>
            <div className="text-xs text-[var(--gray-500)]">ゾーン数</div>
          </div>
          <div className="bg-white rounded-xl elevation-2 p-4 text-center">
            <div className="text-2xl font-bold text-[var(--gray-900)]">
              {new Set(items.filter((i) => i.category).map((i) => i.category)).size}
            </div>
            <div className="text-xs text-[var(--gray-500)]">カテゴリ数</div>
          </div>
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-16">
          <Spinner size="large" className="text-[var(--primary-500)]" />
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="text-center py-16 text-[var(--gray-500)]">
          在庫データの読み込みに失敗しました。
        </div>
      )}

      {/* Empty */}
      {!isLoading && !isError && items && items.length === 0 && (
        <div className="text-center py-16 text-[var(--gray-500)]">
          <p className="text-lg mb-2">在庫アイテムが登録されていません</p>
          <p className="text-sm">「+ アイテム追加」から棚センサーとアイテムのマッピングを作成してください。</p>
        </div>
      )}

      {/* Item grid grouped by zone */}
      {!isLoading && !isError && items && items.length > 0 && (
        <div className="space-y-8">
          {Object.entries(grouped)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([zone, zoneItems]) => (
              <div key={zone}>
                <h3 className="text-sm font-medium text-[var(--gray-500)] uppercase tracking-wider mb-3">
                  {zone}
                  <span className="ml-2 text-[var(--gray-400)]">({zoneItems.length})</span>
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {zoneItems.map((item, i) => (
                    <InventoryItemCard key={item.id} item={item} index={i} />
                  ))}
                </div>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
