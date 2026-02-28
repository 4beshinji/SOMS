import { clsx } from 'clsx';

export interface TabPillsProps<T extends string> {
  tabs: readonly { value: T; label: string }[];
  active: T;
  onChange: (value: T) => void;
  className?: string;
}

export default function TabPills<T extends string>({
  tabs,
  active,
  onChange,
  className,
}: TabPillsProps<T>) {
  return (
    <div className={clsx('flex gap-1 bg-[var(--gray-100)] p-1 rounded-lg', className)}>
      {tabs.map((tab) => (
        <button
          key={tab.value}
          onClick={() => onChange(tab.value)}
          className={clsx(
            'px-4 py-2 text-sm font-medium rounded-md transition-all cursor-pointer',
            active === tab.value
              ? 'bg-white text-[var(--primary-700)] elevation-1'
              : 'text-[var(--gray-600)] hover:text-[var(--gray-900)]'
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
