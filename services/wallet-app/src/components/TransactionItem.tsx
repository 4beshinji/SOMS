import type { LedgerEntry } from '../api/wallet';

const TYPE_LABELS: Record<string, string> = {
  INFRASTRUCTURE_REWARD: 'インフラ報酬',
  TASK_REWARD: 'タスク報酬',
  P2P_TRANSFER: '送金',
  FEE_BURN: '手数料',
  DEMURRAGE_BURN: '減価',
};

interface TransactionItemProps {
  entry: LedgerEntry;
}

export default function TransactionItem({ entry }: TransactionItemProps) {
  const isCredit = entry.entry_type === 'CREDIT';
  const sign = isCredit ? '+' : '-';
  const colorClass = isCredit ? 'text-[var(--success-700)]' : 'text-[var(--error-700)]';
  const label = TYPE_LABELS[entry.transaction_type] || entry.transaction_type;
  const date = new Date(entry.created_at);
  const timeStr = `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`;

  return (
    <div className="flex items-center justify-between py-3 border-b border-[var(--gray-200)] last:border-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-[var(--gray-800)] truncate">{label}</p>
        {entry.description && (
          <p className="text-xs text-[var(--gray-500)] truncate">{entry.description}</p>
        )}
        <p className="text-xs text-[var(--gray-500)]">{timeStr}</p>
      </div>
      <div className={`text-right ml-3 flex-shrink-0 ${colorClass}`}>
        <p className="text-sm font-semibold">{sign}{(Math.abs(entry.amount) / 1000).toFixed(3)}</p>
        <p className="text-xs text-[var(--gray-500)]">{(entry.balance_after / 1000).toFixed(3)}</p>
      </div>
    </div>
  );
}
