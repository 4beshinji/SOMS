import { useQuery } from '@tanstack/react-query';
import { fetchAuditFeed } from '../api/tasks';

const ACTION_STYLES: Record<string, string> = {
  created: 'bg-[var(--info-50)] text-[var(--info-700)]',
  accepted: 'bg-[var(--primary-50)] text-[var(--primary-700)]',
  dispatched: 'bg-[var(--warning-50)] text-[var(--warning-700)]',
  completed: 'bg-[var(--success-50)] text-[var(--success-700)]',
};

export default function ActivityPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['audit-feed'],
    queryFn: () => fetchAuditFeed(200),
    refetchInterval: 15000,
  });

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-[var(--gray-900)]">Task Activity</h1>
        <p className="text-sm text-[var(--gray-500)]">Lifecycle audit trail (created / accepted / dispatched / completed).</p>
      </div>

      {isLoading ? (
        <p className="text-sm text-[var(--gray-500)]">Loading...</p>
      ) : isError || !data ? (
        <p className="text-sm text-[var(--error-600)]">Failed to load audit feed.</p>
      ) : data.length === 0 ? (
        <p className="text-sm text-[var(--gray-500)]">No activity yet.</p>
      ) : (
        <div className="bg-white rounded-xl border border-[var(--gray-200)] overflow-hidden divide-y divide-[var(--gray-100)]">
          {data.map((entry) => {
            const style = ACTION_STYLES[entry.action] ?? 'bg-[var(--gray-100)] text-[var(--gray-700)]';
            return (
              <div key={entry.id} className="px-4 py-3 flex items-center gap-3 text-sm">
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${style}`}>
                  {entry.action}
                </span>
                <span className="text-[var(--gray-700)] font-medium">task #{entry.task_id}</span>
                {entry.actor_user_id !== null && (
                  <span className="text-xs text-[var(--gray-500)]">by user {entry.actor_user_id}</span>
                )}
                {entry.notes && (
                  <span className="text-xs text-[var(--gray-500)] truncate flex-1">note: {entry.notes}</span>
                )}
                <span className="text-xs text-[var(--gray-400)] ml-auto">
                  {new Date(entry.timestamp).toLocaleString('ja-JP', {
                    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
                  })}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
