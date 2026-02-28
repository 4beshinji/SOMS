import { useState, useEffect } from 'react';
import { sendTransfer, previewFee, type TransferFeeInfo } from '../api/wallet';

interface SendProps {
  userId: number;
}

export default function Send({ userId }: SendProps) {
  const [toUserId, setToUserId] = useState('');
  const [amount, setAmount] = useState('');
  const [description, setDescription] = useState('');
  const [fee, setFee] = useState<TransferFeeInfo | null>(null);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);

  useEffect(() => {
    const millis = Math.floor(parseFloat(amount || '0') * 1000);
    if (millis <= 0) {
      setFee(null);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const f = await previewFee(millis);
        setFee(f);
      } catch {
        setFee(null);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [amount]);

  const handleSend = async () => {
    const millis = Math.floor(parseFloat(amount) * 1000);
    const to = parseInt(toUserId, 10);
    if (isNaN(to) || millis <= 0) return;

    setSending(true);
    setResult(null);
    try {
      await sendTransfer(userId, to, millis, description || undefined);
      setResult({ success: true, message: `ユーザー #${to} に ${(millis / 1000).toFixed(3)} SOMS を送金しました` });
      setToUserId('');
      setAmount('');
      setDescription('');
      setFee(null);
    } catch (e) {
      setResult({ success: false, message: e instanceof Error ? e.message : '送金に失敗しました' });
    } finally {
      setSending(false);
    }
  };

  const millis = Math.floor(parseFloat(amount || '0') * 1000);
  const canSend = parseInt(toUserId) > 0 && millis > 0 && !sending && !fee?.below_minimum;

  return (
    <div className="p-4 pb-24 space-y-6">
      <h1 className="text-xl font-bold text-[var(--gray-900)]">送金</h1>

      <div className="space-y-4">
        <div>
          <label className="block text-sm text-[var(--gray-500)] mb-1">送信先ユーザーID</label>
          <input
            type="number"
            inputMode="numeric"
            value={toUserId}
            onChange={e => setToUserId(e.target.value)}
            placeholder="例: 2"
            className="w-full bg-[var(--gray-100)] border border-[var(--gray-300)] rounded-xl px-4 py-3 text-[var(--gray-900)] placeholder-[var(--gray-400)] focus:outline-none focus:border-[var(--primary-500)] focus:ring-2 focus:ring-[var(--primary-500)]"
          />
        </div>

        <div>
          <label className="block text-sm text-[var(--gray-500)] mb-1">金額 (SOMS)</label>
          <input
            type="number"
            inputMode="decimal"
            step="0.001"
            min="0"
            value={amount}
            onChange={e => setAmount(e.target.value)}
            placeholder="0.000"
            className="w-full bg-[var(--gray-100)] border border-[var(--gray-300)] rounded-xl px-4 py-3 text-[var(--gray-900)] text-2xl font-bold placeholder-[var(--gray-400)] focus:outline-none focus:border-[var(--primary-500)] focus:ring-2 focus:ring-[var(--primary-500)]"
          />
        </div>

        <div>
          <label className="block text-sm text-[var(--gray-500)] mb-1">メモ（任意）</label>
          <input
            type="text"
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="何のための送金ですか？"
            maxLength={100}
            className="w-full bg-[var(--gray-100)] border border-[var(--gray-300)] rounded-xl px-4 py-3 text-[var(--gray-900)] placeholder-[var(--gray-400)] focus:outline-none focus:border-[var(--primary-500)] focus:ring-2 focus:ring-[var(--primary-500)]"
          />
        </div>
      </div>

      {fee && (
        <div className="bg-white rounded-xl p-4 space-y-2 text-sm elevation-1">
          <div className="flex justify-between text-[var(--gray-500)]">
            <span>手数料 ({(fee.fee_rate * 100).toFixed(0)}%)</span>
            <span className="text-[var(--error-700)]">-{(fee.fee_amount / 1000).toFixed(3)}</span>
          </div>
          <div className="flex justify-between text-[var(--gray-800)] font-semibold">
            <span>受取額</span>
            <span className="text-[var(--success-700)]">{(fee.net_amount / 1000).toFixed(3)}</span>
          </div>
          {fee.below_minimum && (
            <p className="text-[var(--error-700)] text-xs">
              最低送金額 ({(fee.min_transfer / 1000).toFixed(3)} SOMS) に達していません
            </p>
          )}
        </div>
      )}

      {result && (
        <div className={`rounded-lg p-3 text-sm ${
          result.success ? 'bg-[var(--success-50)] border border-[var(--success-500)] text-[var(--success-700)]' :
          'bg-[var(--error-50)] border border-[var(--error-500)] text-[var(--error-700)]'
        }`}>
          {result.message}
        </div>
      )}

      <button
        onClick={handleSend}
        disabled={!canSend}
        className="w-full py-3 bg-[var(--primary-500)] hover:bg-[var(--primary-700)] text-white font-semibold rounded-xl disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
      >
        {sending ? '送信中...' : '送金'}
      </button>
    </div>
  );
}
