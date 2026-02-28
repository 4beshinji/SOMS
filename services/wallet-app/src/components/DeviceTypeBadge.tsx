const COLORS: Record<string, string> = {
  llm_node: 'bg-purple-100 text-purple-700',
  sensor_node: 'bg-cyan-100 text-cyan-700',
  hub: 'bg-yellow-100 text-yellow-700',
  relay_node: 'bg-emerald-100 text-emerald-700',
  remote_node: 'bg-[var(--gray-100)] text-[var(--gray-700)]',
};

const TYPE_LABELS: Record<string, string> = {
  llm_node: 'LLM',
  sensor_node: 'センサー',
  hub: 'ハブ',
  relay_node: 'リレー',
  remote_node: 'リモート',
};

export default function DeviceTypeBadge({ type }: { type: string }) {
  const color = COLORS[type] || COLORS.remote_node;
  const label = TYPE_LABELS[type] || type.replace('_', ' ');
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {label}
    </span>
  );
}
