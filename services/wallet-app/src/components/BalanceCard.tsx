interface BalanceCardProps {
  balance: number;
  loading?: boolean;
}

export default function BalanceCard({ balance, loading }: BalanceCardProps) {
  const display = (balance / 1000).toFixed(3);

  return (
    <div className="bg-gradient-to-br from-[var(--primary-500)] to-[var(--primary-700)] rounded-2xl p-6 text-white shadow-lg">
      <p className="text-sm opacity-80 mb-1">SOMS 残高</p>
      {loading ? (
        <div className="h-10 w-32 bg-white/20 rounded animate-pulse" />
      ) : (
        <p className="text-4xl font-bold tracking-tight">{display} <span className="text-lg font-medium opacity-80">SOMS</span></p>
      )}
      <p className="text-xs opacity-60 mt-2">1 SOMS = 1,000 ミリ単位</p>
    </div>
  );
}
