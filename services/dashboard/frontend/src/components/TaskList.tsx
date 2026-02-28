import { motion, AnimatePresence } from 'framer-motion';
import type { Task, TaskReport, ZoneMultiplierInfo } from '@soms/types';
import { Spinner } from '@soms/ui';
import TaskCard from './TaskCard';

interface TaskListProps {
  tasks: Task[];
  loading: boolean;
  acceptedTaskIds: Set<number>;
  zoneMultipliers: Record<string, ZoneMultiplierInfo>;
  onAccept: (taskId: number) => void;
  onComplete: (taskId: number, report?: TaskReport) => void;
  onIgnore: (taskId: number) => void;
}

export default function TaskList({
  tasks,
  loading,
  acceptedTaskIds,
  zoneMultipliers,
  onAccept,
  onComplete,
  onIgnore,
}: TaskListProps) {
  return (
    <main className="max-w-6xl mx-auto px-6 py-8">
      <div className="mb-6">
        <h2 className="text-2xl font-semibold text-[var(--gray-900)] mb-2">
          お願い事一覧
        </h2>
        <p className="text-[var(--gray-600)]">
          タスクを完了して報酬を受け取りましょう。スマホのウォレットアプリで QR コードを読み取ってください。
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
                  zoneMultiplier={task.zone ? zoneMultipliers[task.zone] : undefined}
                  onAccept={onAccept}
                  onComplete={onComplete}
                  onIgnore={onIgnore}
                />
              </motion.div>
            ))}
          </AnimatePresence>
        </motion.div>
      )}
    </main>
  );
}
