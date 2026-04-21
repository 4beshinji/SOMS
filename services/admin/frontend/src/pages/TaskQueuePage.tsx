import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchTaskQueue, fetchTaskStats, dispatchTask, fetchAdminTasks, completeAdminTask } from '../api/tasks';

const URGENCY_LABELS: Record<number, { label: string; style: string }> = {
  0: { label: '延期', style: 'bg-[var(--gray-100)] text-[var(--gray-600)]' },
  1: { label: '低', style: 'bg-[var(--success-50)] text-[var(--success-700)]' },
  2: { label: '通常', style: 'bg-[var(--info-50)] text-[var(--info-700)]' },
  3: { label: '高', style: 'bg-[var(--warning-50)] text-[var(--warning-700)]' },
  4: { label: '緊急', style: 'bg-[var(--error-50)] text-[var(--error-700)]' },
};

export default function TaskQueuePage() {
  const queryClient = useQueryClient();

  const queueQuery = useQuery({
    queryKey: ['task-queue'],
    queryFn: fetchTaskQueue,
    refetchInterval: 10000,
  });

  const statsQuery = useQuery({
    queryKey: ['task-stats'],
    queryFn: fetchTaskStats,
    refetchInterval: 10000,
  });

  const adminQuery = useQuery({
    queryKey: ['admin-tasks'],
    queryFn: fetchAdminTasks,
    refetchInterval: 10000,
  });

  const dispatchMutation = useMutation({
    mutationFn: dispatchTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['task-queue'] });
      queryClient.invalidateQueries({ queryKey: ['task-stats'] });
    },
  });

  const completeMutation = useMutation({
    mutationFn: completeAdminTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-tasks'] });
      queryClient.invalidateQueries({ queryKey: ['task-stats'] });
    },
  });

  const stats = statsQuery.data;
  const queue = queueQuery.data ?? [];
  const adminTasks = (adminQuery.data ?? []).filter((t) => !t.is_completed);

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-[var(--gray-900)]">Task Queue</h1>

      {/* Stats summary */}
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: 'Active', value: stats.tasks_active, style: 'text-[var(--primary-700)]' },
            { label: 'Queued', value: stats.tasks_queued, style: 'text-[var(--info-700)]' },
            { label: 'Completed', value: stats.tasks_completed, style: 'text-[var(--success-700)]' },
            { label: 'Last Hour', value: stats.tasks_completed_last_hour, style: 'text-[var(--gold-dark)]' },
          ].map((s) => (
            <div key={s.label} className="bg-white rounded-xl border border-[var(--gray-200)] p-4 text-center">
              <p className="text-xs text-[var(--gray-500)]">{s.label}</p>
              <p className={`text-2xl font-bold ${s.style}`}>{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Admin tasks */}
      <section className="bg-white rounded-xl border border-[var(--gray-200)] overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--gray-200)]">
          <h2 className="text-sm font-semibold text-[var(--gray-900)]">
            管理者タスク ({adminTasks.length})
          </h2>
        </div>
        <div className="divide-y divide-[var(--gray-100)]">
          {adminQuery.isLoading ? (
            <div className="p-4 text-sm text-[var(--gray-500)]">Loading...</div>
          ) : adminTasks.length === 0 ? (
            <div className="p-4 text-sm text-[var(--gray-500)]">管理者向けタスクはありません</div>
          ) : (
            adminTasks.map((task) => {
              const u = URGENCY_LABELS[task.urgency] ?? URGENCY_LABELS[2];
              return (
                <div key={task.id} className="px-4 py-3 flex items-center gap-3">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${u.style}`}>
                    {u.label}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-[var(--gray-900)] truncate">{task.title}</p>
                    <p className="text-xs text-[var(--gray-500)] truncate">{task.description}</p>
                  </div>
                  <span className="text-xs text-[var(--gray-500)]">{task.zone || '-'}</span>
                  {task.skill_level && (
                    <span className="px-1.5 py-0.5 rounded bg-[var(--gray-100)] text-xs text-[var(--gray-700)]">{task.skill_level}</span>
                  )}
                  <span className="text-xs text-[var(--gray-400)]">
                    {new Date(task.created_at).toLocaleString('ja-JP', { hour: '2-digit', minute: '2-digit', month: 'numeric', day: 'numeric' })}
                  </span>
                  <button
                    onClick={() => completeMutation.mutate(task.id)}
                    disabled={completeMutation.isPending}
                    className="px-3 py-1.5 text-xs font-medium bg-[var(--success-500)] text-white rounded-lg hover:bg-[var(--success-600)] disabled:opacity-40 transition-colors"
                  >
                    完了
                  </button>
                </div>
              );
            })
          )}
        </div>
      </section>

      {/* Queue table */}
      <section className="bg-white rounded-xl border border-[var(--gray-200)] overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--gray-200)]">
          <h2 className="text-sm font-semibold text-[var(--gray-900)]">
            Queued Tasks ({queue.length})
          </h2>
        </div>
        <div className="divide-y divide-[var(--gray-100)]">
          {queueQuery.isLoading ? (
            <div className="p-4 text-sm text-[var(--gray-500)]">Loading...</div>
          ) : queue.length === 0 ? (
            <div className="p-4 text-sm text-[var(--gray-500)]">No tasks in queue</div>
          ) : (
            queue.map((task) => {
              const u = URGENCY_LABELS[task.urgency] ?? URGENCY_LABELS[2];
              return (
                <div key={task.id} className="px-4 py-3 flex items-center gap-3">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${u.style}`}>
                    {u.label}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-[var(--gray-900)] truncate">{task.title}</p>
                    <p className="text-xs text-[var(--gray-500)] truncate">{task.description}</p>
                  </div>
                  <span className="text-xs text-[var(--gray-500)]">{task.zone || '-'}</span>
                  {task.skill_level && (
                    <span className="px-1.5 py-0.5 rounded bg-[var(--gray-100)] text-xs text-[var(--gray-700)]">{task.skill_level}</span>
                  )}
                  <span className="text-xs text-[var(--gray-400)]">
                    {new Date(task.created_at).toLocaleString('ja-JP', { hour: '2-digit', minute: '2-digit', month: 'numeric', day: 'numeric' })}
                  </span>
                  <button
                    onClick={() => dispatchMutation.mutate(task.id)}
                    disabled={dispatchMutation.isPending}
                    className="px-3 py-1.5 text-xs font-medium bg-[var(--primary-500)] text-white rounded-lg hover:bg-[var(--primary-600)] disabled:opacity-40 transition-colors"
                  >
                    Dispatch
                  </button>
                </div>
              );
            })
          )}
        </div>
      </section>
    </div>
  );
}
