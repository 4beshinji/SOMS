import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import type { Task, TaskReport } from '@soms/types';
import { Badge, Spinner } from '@soms/ui';
import { fetchTasks, acceptTask, completeTask } from '../api/tasks';

const REPORT_STATUSES = [
  { value: 'no_issue', label: '問題なし' },
  { value: 'resolved', label: '対応済み' },
  { value: 'needs_followup', label: '要追加対応' },
  { value: 'cannot_resolve', label: '対応不可' },
] as const;

function TaskItem({ task, onAccept, onComplete }: {
  task: Task;
  onAccept: (id: number) => void;
  onComplete: (id: number, report?: TaskReport) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [reportStatus, setReportStatus] = useState('');
  const [reportNote, setReportNote] = useState('');

  const isAccepted = task.assigned_to != null && !task.is_completed;

  const urgencyColor = (task.urgency ?? 2) >= 3
    ? 'error' as const
    : (task.urgency ?? 2) >= 2
      ? 'warning' as const
      : 'success' as const;

  const urgencyLabel = (task.urgency ?? 2) >= 3 ? '高' : (task.urgency ?? 2) >= 2 ? '中' : '低';

  return (
    <motion.div
      layout
      className="bg-white rounded-xl border border-[var(--gray-200)] overflow-hidden"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left p-4 flex items-center gap-3"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Badge variant={urgencyColor} size="small">{urgencyLabel}</Badge>
            {task.is_completed && <Badge variant="success" size="small">完了</Badge>}
            {isAccepted && !task.is_completed && <Badge variant="info" size="small">対応中</Badge>}
          </div>
          <h3 className="font-medium text-[var(--gray-900)] truncate">{task.title}</h3>
          {task.location && (
            <p className="text-xs text-[var(--gray-500)] mt-0.5">{task.location}</p>
          )}
        </div>
        <div className="text-right shrink-0">
          <p className="text-sm font-bold text-[var(--gold-dark)]">{task.bounty_gold} SOMS</p>
          <p className="text-xs text-[var(--gray-500)]">{task.bounty_xp} XP</p>
        </div>
        <svg
          className={`w-5 h-5 text-[var(--gray-400)] transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 space-y-3 border-t border-[var(--gray-100)] pt-3">
              {task.description && (
                <p className="text-sm text-[var(--gray-700)] leading-relaxed">{task.description}</p>
              )}

              {task.is_completed && task.reward_multiplier != null && task.reward_multiplier > 1.0 && (
                <div className="text-xs text-[var(--gold-dark)] bg-yellow-50 border border-yellow-200 rounded-lg px-3 py-1.5">
                  {task.bounty_gold} x {task.reward_multiplier.toFixed(1)}x = <span className="font-bold">{task.reward_adjusted_bounty} SOMS</span>
                </div>
              )}

              {/* Accept button */}
              {!task.is_completed && !isAccepted && (
                <button
                  onClick={(e) => { e.stopPropagation(); onAccept(task.id); }}
                  className="w-full py-3 bg-[var(--primary-500)] text-white font-medium rounded-xl active:scale-[0.98] transition-transform"
                >
                  受諾する
                </button>
              )}

              {/* Complete flow */}
              {!task.is_completed && isAccepted && !showReport && (
                <button
                  onClick={(e) => { e.stopPropagation(); setShowReport(true); }}
                  className="w-full py-3 bg-[var(--success-600)] text-white font-medium rounded-xl active:scale-[0.98] transition-transform"
                >
                  完了報告
                </button>
              )}

              {!task.is_completed && isAccepted && showReport && (
                <div className="space-y-2">
                  <p className="text-sm font-medium text-[var(--gray-700)]">結果を報告</p>
                  <div className="grid grid-cols-2 gap-2">
                    {REPORT_STATUSES.map(s => (
                      <button
                        key={s.value}
                        onClick={() => setReportStatus(s.value)}
                        className={`px-3 py-2 text-sm rounded-lg border transition-colors ${
                          reportStatus === s.value
                            ? 'border-[var(--primary-500)] bg-[var(--primary-50)] text-[var(--primary-700)] font-medium'
                            : 'border-[var(--gray-300)] bg-white text-[var(--gray-600)]'
                        }`}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                  <textarea
                    value={reportNote}
                    onChange={e => setReportNote(e.target.value)}
                    placeholder="詳細を入力..."
                    rows={2}
                    maxLength={500}
                    className="w-full px-3 py-2 text-sm border border-[var(--gray-300)] rounded-lg resize-none focus:outline-none focus:border-[var(--primary-500)]"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => { onComplete(task.id, { status: reportStatus, note: reportNote }); setShowReport(false); }}
                      disabled={!reportStatus}
                      className="flex-1 py-2.5 bg-[var(--primary-500)] text-white font-medium rounded-xl disabled:opacity-50 active:scale-[0.98] transition-transform"
                    >
                      送信
                    </button>
                    <button
                      onClick={() => { setShowReport(false); setReportStatus(''); setReportNote(''); }}
                      className="px-4 py-2.5 text-[var(--gray-600)] border border-[var(--gray-300)] rounded-xl"
                    >
                      戻る
                    </button>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function Tasks() {
  const queryClient = useQueryClient();

  const { data: tasks, isLoading, error, refetch } = useQuery({
    queryKey: ['tasks'],
    queryFn: fetchTasks,
    refetchInterval: 10000,
  });

  const acceptMutation = useMutation({
    mutationFn: acceptTask,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tasks'] }),
  });

  const completeMutation = useMutation({
    mutationFn: completeTask,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tasks'] }),
  });

  const activeTasks = (tasks ?? []).filter(t => !t.is_completed);
  const completedTasks = (tasks ?? []).filter(t => t.is_completed);

  return (
    <div className="min-h-screen bg-[var(--gray-50)] pb-20">
      <div className="px-4 pt-6 pb-4">
        <h1 className="text-xl font-bold text-[var(--gray-900)]">タスク</h1>
        <p className="text-sm text-[var(--gray-500)] mt-1">
          タスクを完了して報酬を受け取りましょう
        </p>
      </div>

      <div className="px-4 space-y-3">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Spinner size="large" className="text-[var(--primary-500)]" />
          </div>
        ) : error ? (
          <div className="text-center py-12">
            <p className="text-[var(--error-700)] font-medium">タスクの取得に失敗しました</p>
            <p className="text-xs text-[var(--gray-400)] mt-1">{error instanceof Error ? error.message : '不明なエラー'}</p>
            <button
              onClick={() => refetch()}
              className="mt-3 text-sm font-medium text-[var(--primary-500)] hover:underline cursor-pointer"
            >
              再試行
            </button>
          </div>
        ) : activeTasks.length === 0 && completedTasks.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-[var(--gray-500)]">現在タスクはありません</p>
            <p className="text-xs text-[var(--gray-400)] mt-1">新しいタスクが追加されるまでお待ちください</p>
          </div>
        ) : (
          <>
            {activeTasks.map(task => (
              <TaskItem
                key={task.id}
                task={task}
                onAccept={(id) => acceptMutation.mutate(id)}
                onComplete={(id, report) => completeMutation.mutate({ taskId: id, report })}
              />
            ))}

            {completedTasks.length > 0 && (
              <>
                <p className="text-xs font-medium text-[var(--gray-500)] uppercase tracking-wider pt-2">完了済み</p>
                {completedTasks.slice(0, 5).map(task => (
                  <TaskItem
                    key={task.id}
                    task={task}
                    onAccept={() => {}}
                    onComplete={() => {}}
                  />
                ))}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
