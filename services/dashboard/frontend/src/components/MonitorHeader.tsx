import { motion } from 'framer-motion';
import type { SystemStats } from '@soms/types';

interface MonitorHeaderProps {
  systemStats: SystemStats | null;
  isAudioEnabled: boolean;
  onToggleAudio: () => void;
  children?: React.ReactNode;
}

export default function MonitorHeader({ systemStats, isAudioEnabled, onToggleAudio, children }: MonitorHeaderProps) {
  return (
    <header className="bg-white border-b border-[var(--gray-200)] elevation-1">
      <div className="max-w-6xl mx-auto px-6 py-6">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="flex justify-between items-center"
        >
          <div>
            <h1 className="text-4xl font-bold text-[var(--primary-500)]">
              SOMS
            </h1>
            <p className="text-[var(--gray-600)] mt-1">
              共生型オフィス管理システム
            </p>
          </div>

          {/* System Stats */}
          <div className="flex items-center gap-4">
            {systemStats && (
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[var(--gray-100)] border border-[var(--gray-300)]">
                  <span className="text-sm text-[var(--gray-700)]">{systemStats.tasks_completed} 完了</span>
                </div>
                {systemStats.tasks_queued > 0 && (
                  <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[var(--info-50)] border border-[var(--info-border)]">
                    <span className="text-sm font-medium text-[var(--info-700)]">{systemStats.tasks_queued} 待機中</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Extra controls */}
          <div className="flex items-center gap-2">
          {children}
          <button
            onClick={onToggleAudio}
            className={`p-3 rounded-full transition-all duration-300 cursor-pointer touch-action-manipulation min-w-[48px] min-h-[48px] flex items-center justify-center ${isAudioEnabled
              ? 'bg-[var(--primary-100)] text-[var(--primary-600)] shadow-inner'
              : 'bg-[var(--gray-100)] text-[var(--gray-400)]'
            }`}
            aria-label={isAudioEnabled ? "音声をオフにする" : "音声をオンにする"}
          >
            {isAudioEnabled ? (
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 5L6 9H2v6h4l5 4V5z"></path><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 5L6 9H2v6h4l5 4V5z"></path><line x1="23" y1="9" x2="17" y2="15"></line><line x1="17" y1="9" x2="23" y2="15"></line></svg>
            )}
          </button>
          </div>
        </motion.div>
      </div>
    </header>
  );
}
