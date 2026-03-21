import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { MapPin, Coins, Zap, Circle, AlertCircle, AlertTriangle, QrCode, X, TrendingUp, Clock, Users, Timer } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import { Card, Badge, Button } from '@soms/ui';
import type { Task, TaskReport, ZoneMultiplierInfo } from '@soms/types';

interface TaskCardProps {
    task: Task;
    isAccepted?: boolean;
    zoneMultiplier?: ZoneMultiplierInfo;
    onAccept?: (taskId: number) => void;
    onComplete?: (taskId: number, report?: TaskReport) => void;
    onIgnore?: (taskId: number) => void;
}

const URGENCY_MAP: Record<number, { variant: 'neutral' | 'success' | 'info' | 'warning' | 'error'; icon: React.ReactNode; label: string; pulse?: boolean }> = {
    0: { variant: 'neutral', icon: <Clock size={12} />, label: '延期' },
    1: { variant: 'success', icon: <Circle size={12} />, label: '低' },
    2: { variant: 'info', icon: <Circle size={12} />, label: '通常' },
    3: { variant: 'warning', icon: <AlertCircle size={12} />, label: '高' },
    4: { variant: 'error', icon: <AlertTriangle size={12} />, label: '緊急', pulse: true },
};

const getUrgencyBadge = (urgency: number) => {
    return URGENCY_MAP[urgency] ?? URGENCY_MAP[2];
};

const REPORT_STATUSES = [
    { value: 'no_issue', label: '問題なし' },
    { value: 'resolved', label: '対応済み' },
    { value: 'needs_followup', label: '要追加対応' },
    { value: 'cannot_resolve', label: '対応不可' },
] as const;

const TaskCard = React.memo(function TaskCard({ task, isAccepted, zoneMultiplier, onAccept, onComplete, onIgnore }: TaskCardProps) {
    const urgencyBadge = getUrgencyBadge(task.urgency ?? 2);
    const [showReport, setShowReport] = useState(false);
    const [reportStatus, setReportStatus] = useState('');
    const [reportNote, setReportNote] = useState('');
    const [showQR, setShowQR] = useState(false);

    return (
        <Card elevation={2} padding="medium" hoverable>
            <div className="space-y-4">
                {/* Header with title and urgency */}
                <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                        <h3 className="text-2xl font-semibold text-[var(--gray-900)] mb-1">
                            {task.title}
                        </h3>
                        {task.location && (
                            <div className="flex items-center gap-1 text-sm text-[var(--gray-600)]">
                                <MapPin size={14} />
                                <span>{task.location}</span>
                            </div>
                        )}
                    </div>
                    <Badge variant={urgencyBadge.variant} icon={urgencyBadge.icon} className={urgencyBadge.pulse ? 'animate-pulse' : ''}>
                        {urgencyBadge.label}
                    </Badge>
                </div>

                {/* Description */}
                {task.description && (
                    <p className="text-[var(--gray-700)] leading-relaxed">
                        {task.description}
                    </p>
                )}

                {/* Task metadata */}
                {(task.estimated_duration || task.min_people_required || task.expires_at) && (
                    <div className="flex items-center gap-3 flex-wrap text-xs text-[var(--gray-500)]">
                        {task.estimated_duration != null && (
                            <span className="flex items-center gap-1">
                                <Timer size={12} />
                                ~{task.estimated_duration}分
                            </span>
                        )}
                        {task.min_people_required != null && task.min_people_required > 1 && (
                            <span className="flex items-center gap-1">
                                <Users size={12} />
                                {task.min_people_required}人以上
                            </span>
                        )}
                        {task.expires_at && !task.is_completed && (() => {
                            const remaining = Math.max(0, Math.floor((new Date(task.expires_at).getTime() - Date.now()) / 60000));
                            if (remaining <= 0) return <span className="text-[var(--error-700)]">期限切れ</span>;
                            if (remaining < 60) return <span className="flex items-center gap-1 text-[var(--warning-700)]"><Clock size={12} />残り{remaining}分</span>;
                            const hours = Math.floor(remaining / 60);
                            return <span className="flex items-center gap-1"><Clock size={12} />残り{hours}時間</span>;
                        })()}
                    </div>
                )}

                <div className="flex items-center gap-3 flex-wrap">
                    <Badge variant="gold" icon={<Coins size={14} />}>
                        {task.bounty_gold} SOMS
                    </Badge>
                    <Badge variant="xp" icon={<Zap size={14} />}>
                        {task.bounty_xp} システム活動値
                    </Badge>
                </div>

                {/* Reward multiplier display */}
                {task.is_completed && task.reward_multiplier != null && task.reward_multiplier > 1.0 && (
                    <div className="flex items-center gap-1.5 text-sm text-[var(--gold-dark)] bg-gradient-to-r from-yellow-50 to-amber-50 border border-yellow-200 rounded-lg px-3 py-1.5">
                        <TrendingUp size={14} />
                        <span>
                            {task.bounty_gold} x {task.reward_multiplier.toFixed(1)}x = <span className="font-bold">{task.reward_adjusted_bounty} SOMS</span>
                        </span>
                    </div>
                )}
                {!task.is_completed && zoneMultiplier && zoneMultiplier.multiplier > 1.0 && (
                    <div className="flex items-center gap-1.5 text-xs text-[var(--gold-dark)] bg-gradient-to-r from-yellow-50 to-amber-50 border border-yellow-200 rounded-lg px-2.5 py-1">
                        <TrendingUp size={12} />
                        <span>
                            ゾーンボーナス {zoneMultiplier.multiplier.toFixed(1)}x ({zoneMultiplier.device_count} devices, avg {zoneMultiplier.avg_xp} XP)
                        </span>
                    </div>
                )}

                {/* Actions */}
                {!task.is_completed && !isAccepted && (
                    <motion.div
                        className="flex gap-2 pt-2"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.1 }}
                    >
                        <Button
                            variant="primary"
                            size="medium"
                            onClick={() => onAccept?.(task.id)}
                            className="flex-1"
                        >
                            受諾
                        </Button>
                        <Button
                            variant="ghost"
                            size="medium"
                            onClick={() => onIgnore?.(task.id)}
                        >
                            無視
                        </Button>
                    </motion.div>
                )}

                {!task.is_completed && isAccepted && !showReport && (
                    <motion.div
                        className="flex gap-2 pt-2"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.1 }}
                    >
                        <Badge variant="info" size="medium">
                            対応中
                        </Badge>
                        <Button
                            variant="secondary"
                            size="medium"
                            onClick={() => setShowReport(true)}
                            className="flex-1"
                        >
                            完了
                        </Button>
                    </motion.div>
                )}

                {!task.is_completed && isAccepted && showReport && (
                    <motion.div
                        className="pt-2 space-y-3"
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        transition={{ duration: 0.2 }}
                    >
                        <p className="text-sm font-medium text-[var(--gray-700)]">結果を報告</p>
                        <div className="grid grid-cols-2 gap-2">
                            {REPORT_STATUSES.map(s => (
                                <button
                                    key={s.value}
                                    onClick={() => setReportStatus(s.value)}
                                    className={`px-3 py-2 text-sm rounded-lg border transition-colors ${
                                        reportStatus === s.value
                                            ? 'border-[var(--primary-500)] bg-[var(--primary-50)] text-[var(--primary-700)] font-medium'
                                            : 'border-[var(--gray-300)] bg-white text-[var(--gray-600)] hover:border-[var(--gray-400)]'
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
                            <Button
                                variant="primary"
                                size="medium"
                                onClick={() => onComplete?.(task.id, { status: reportStatus, note: reportNote })}
                                className="flex-1"
                                disabled={!reportStatus}
                            >
                                送信
                            </Button>
                            <Button
                                variant="ghost"
                                size="medium"
                                onClick={() => {
                                    setShowReport(false);
                                    setReportStatus('');
                                    setReportNote('');
                                }}
                            >
                                戻る
                            </Button>
                        </div>
                    </motion.div>
                )}

                {task.is_completed && (
                    <div className="pt-2 flex items-center gap-2">
                        <Badge variant="success" size="medium">
                            ✓ 完了済み
                        </Badge>
                        {task.bounty_gold > 0 && (
                            <Button
                                variant="secondary"
                                size="small"
                                onClick={() => setShowQR(true)}
                                className="flex items-center gap-1"
                                aria-label="QRコードを表示して報酬を受け取る"
                            >
                                <QrCode size={14} />
                                QR で報酬を受け取る
                            </Button>
                        )}
                    </div>
                )}
            </div>

            {/* QR Reward Modal */}
            <AnimatePresence>
                {showQR && (
                    <motion.div
                        className="fixed inset-0 bg-black/80 flex items-center justify-center z-50"
                        role="dialog"
                        aria-modal="true"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={() => setShowQR(false)}
                    >
                        <motion.div
                            className="relative bg-white p-8 rounded-2xl text-center max-w-sm mx-4"
                            initial={{ scale: 0.8, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.8, opacity: 0 }}
                            onClick={(e: React.MouseEvent) => e.stopPropagation()}
                        >
                            <button
                                onClick={() => setShowQR(false)}
                                className="absolute top-3 right-3 text-[var(--gray-400)] hover:text-[var(--gray-600)]"
                                aria-label="QRモーダルを閉じる"
                            >
                                <X size={20} />
                            </button>
                            <QRCodeSVG
                                value={`soms://reward?task_id=${task.id}&amount=${task.reward_adjusted_bounty ?? task.bounty_gold}`}
                                size={280}
                                level="M"
                            />
                            <p className="mt-4 text-lg font-bold text-[var(--gray-900)]">
                                スマホで読み取ってください
                            </p>
                            <div className="mt-2 flex items-center justify-center gap-1 text-[var(--gold-dark)]">
                                <Coins size={18} />
                                <span className="text-xl font-bold">{task.reward_adjusted_bounty ?? task.bounty_gold} SOMS</span>
                            </div>
                            {task.reward_multiplier != null && task.reward_multiplier > 1.0 && (
                                <p className="text-xs text-[var(--gray-500)] mt-1">
                                    {task.bounty_gold} x {task.reward_multiplier.toFixed(1)}x multiplier
                                </p>
                            )}
                            <p className="text-sm text-[var(--gray-500)] mt-2">
                                {task.title}
                            </p>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </Card>
    );
});

export default TaskCard;
