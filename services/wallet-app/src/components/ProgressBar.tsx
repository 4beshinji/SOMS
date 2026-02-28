export default function ProgressBar({
  value,
  label,
  color = 'bg-[var(--primary-500)]',
}: {
  value: number;
  label?: string;
  color?: string;
}) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div>
      {label && (
        <div className="flex justify-between text-xs text-[var(--gray-500)] mb-1">
          <span>{label}</span>
          <span>{pct.toFixed(0)}%</span>
        </div>
      )}
      <div className="h-2 bg-[var(--gray-200)] rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
