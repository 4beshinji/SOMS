import { motion, AnimatePresence } from 'framer-motion';
import type { Task, TaskReport } from '@soms/types';
import { Spinner } from '@soms/ui';
import TaskCard from './TaskCard';

interface TaskListProps {
  tasks: Task[];
  loading: boolean;
  hasMoreTasks?: boolean;
  acceptedTaskIds: Set<number>;
  onAccept: (taskId: number) => void;
  onComplete: (taskId: number, report?: TaskReport) => void;
  onIgnore: (taskId: number) => void;
  onShowMore?: () => void;
}

export default function TaskList({
  tasks,
  loading,
  hasMoreTasks,
  acceptedTaskIds,
  onAccept,
  onComplete,
  onIgnore,
  onShowMore,
}: TaskListProps) {
  return (
    <main className="max-w-6xl mx-auto px-6 py-8">
      <div className="mb-6">
        <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-2">
          お願い事一覧
        </h2>
        <p className="text-[var(--gray-600)]">
          担当のタスクを確認し、完了したら報告してください。
        </p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <Spinner size="large" className="text-[var(--primary-500)] mx-auto" />
            <p className="text-[var(--gray-600)] mt-4">タスクを読み込み中...</p>
          </div>
        </div>
      ) : tasks.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-[var(--gray-500)] text-lg">現在利用可能なタスクはありません。</p>
          <p className="text-[var(--gray-400)] text-sm mt-2">新しいタスクが追加されるまでお待ちください！</p>
        </div>
      ) : (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5 }}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
        >
          <AnimatePresence>
            {tasks.map((task, index) => (
              <motion.div
                key={task.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ delay: index * 0.1 }}
              >
                <TaskCard
                  task={task}
                  isAccepted={acceptedTaskIds.has(task.id)}
                  onAccept={onAccept}
                  onComplete={onComplete}
                  onIgnore={onIgnore}
                />
              </motion.div>
            ))}
          </AnimatePresence>
        </motion.div>
      )}

      {hasMoreTasks && (
        <div className="text-center mt-6">
          <button
            onClick={onShowMore}
            className="px-6 py-2 text-sm font-medium text-[var(--primary-500)] bg-[var(--primary-50)] border border-[var(--primary-200)] rounded-lg hover:bg-[var(--primary-100)] transition-colors"
          >
            もっと見る
          </button>
        </div>
      )}
    </main>
  );
}
