/**
 * Dev-only UI preview page — accessible at http://localhost:5173/?preview
 * Shows all @soms/ui components with the updated design tokens.
 */
import { Button, Badge, Spinner } from '@soms/ui';
import { MapPin, Coins, Zap, AlertTriangle } from 'lucide-react';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-12">
      <h2 className="text-sm font-semibold text-[var(--gray-400)] uppercase tracking-widest mb-4 border-b border-[var(--gray-200)] pb-2">
        {title}
      </h2>
      {children}
    </div>
  );
}

/** タスクカードの中身（インタラクションなし・見た目のみ） */
function MockTaskContent() {
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <h3 className="text-2xl font-semibold text-[var(--gray-900)] mb-1">
            会議室Bの冷房が効きすぎている
          </h3>
          <div className="flex items-center gap-1 text-sm text-[var(--gray-600)]">
            <MapPin size={14} />
            <span>会議室B / 3F</span>
          </div>
        </div>
        <Badge variant="error" icon={<AlertTriangle size={12} />}>高優先度</Badge>
      </div>

      <p className="text-[var(--gray-700)] leading-relaxed">
        センサーが室温18℃を検知。在室者から寒さの報告あり。空調リモコンで温度を22℃に設定してください。
      </p>

      <div className="flex items-center gap-3 flex-wrap">
        <Badge variant="gold" icon={<Coins size={14} />}>2,500 SOMS</Badge>
        <Badge variant="xp" icon={<Zap size={14} />}>80 システム活動値</Badge>
      </div>

      <div className="flex gap-2 pt-2">
        <Button variant="primary" size="medium" className="flex-1">受諾</Button>
        <Button variant="ghost" size="medium">無視</Button>
      </div>
    </div>
  );
}

const PADDING_OPTIONS = [
  { label: 'A', padding: 'p-4',  px: '16px', note: '現在より狭い' },
  { label: 'B', padding: 'p-6',  px: '24px', note: '現在 (medium)' },
  { label: 'C', padding: 'p-8',  px: '32px', note: 'ゆとりあり' },
  { label: 'D', padding: 'p-10', px: '40px', note: '広め' },
] as const;

export default function UIPreview() {
  return (
    <div className="min-h-screen bg-[var(--gray-50)] p-8">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold text-[var(--gray-900)] mb-2">SOMS UI Preview</h1>
        <p className="text-[var(--gray-500)] mb-10">Design token brushup — Linear/Notion inspired</p>

        {/* ===== タスクカード padding 比較 ===== */}
        <Section title="タスクカード margin 比較 — どれが良いですか？">
          <div className="space-y-6">
            {PADDING_OPTIONS.map(({ label, padding, px, note }) => (
              <div key={label}>
                {/* ラベル */}
                <div className="flex items-baseline gap-3 mb-2">
                  <span className="text-lg font-bold text-[var(--primary-500)]">選択肢 {label}</span>
                  <span className="text-sm font-mono text-[var(--gray-500)]">{padding} = {px}</span>
                  <span className="text-sm text-[var(--gray-400)]">{note}</span>
                </div>
                {/* カード */}
                <div className={`bg-white rounded-xl border border-[var(--gray-100)] elevation-2 ${padding}`}>
                  <MockTaskContent />
                </div>
              </div>
            ))}
          </div>
        </Section>

        {/* ===== Primary Colors ===== */}
        <Section title="Primary Colors (Indigo)">
          <div className="flex gap-3 flex-wrap">
            {['50','100','300','500','700','900'].map(shade => (
              <div key={shade} className="text-center">
                <div
                  className="w-14 h-14 rounded-lg mb-1 border border-[var(--gray-200)]"
                  style={{ backgroundColor: `var(--primary-${shade})` }}
                />
                <span className="text-xs text-[var(--gray-500)]">{shade}</span>
              </div>
            ))}
          </div>
        </Section>

        {/* ===== Gray Scale ===== */}
        <Section title="Gray Scale (Slate)">
          <div className="flex gap-3 flex-wrap">
            {['50','100','200','300','400','500','600','700','800','900'].map(shade => (
              <div key={shade} className="text-center">
                <div
                  className="w-14 h-14 rounded-lg mb-1 border border-[var(--gray-200)]"
                  style={{ backgroundColor: `var(--gray-${shade})` }}
                />
                <span className="text-xs text-[var(--gray-500)]">{shade}</span>
              </div>
            ))}
          </div>
        </Section>

        {/* ===== Buttons ===== */}
        <Section title="Buttons">
          <div className="flex flex-wrap gap-3 items-center mb-3">
            <Button variant="primary">Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="danger">Danger</Button>
            <Button variant="primary" loading>Loading</Button>
            <Button variant="primary" disabled>Disabled</Button>
          </div>
          <div className="flex flex-wrap gap-3 items-center">
            <Button variant="primary" size="small">Small</Button>
            <Button variant="primary" size="medium">Medium</Button>
            <Button variant="primary" size="large">Large</Button>
          </div>
        </Section>

        {/* ===== Badges ===== */}
        <Section title="Badges — 全バリアント">
          {/* サイズ比較 */}
          <p className="text-xs font-semibold text-[var(--gray-400)] uppercase tracking-wider mb-2">medium (デフォルト)</p>
          <div className="flex flex-wrap gap-3 items-center mb-4">
            <Badge variant="success">完了</Badge>
            <Badge variant="warning">警告</Badge>
            <Badge variant="error">エラー</Badge>
            <Badge variant="info">情報</Badge>
            <Badge variant="gold">1,200 SOMS</Badge>
            <Badge variant="xp">XP +50</Badge>
            <Badge variant="neutral">ニュートラル</Badge>
          </div>
          <p className="text-xs font-semibold text-[var(--gray-400)] uppercase tracking-wider mb-2">small</p>
          <div className="flex flex-wrap gap-3 items-center mb-6">
            <Badge variant="success" size="small">完了</Badge>
            <Badge variant="warning" size="small">警告</Badge>
            <Badge variant="error" size="small">エラー</Badge>
            <Badge variant="info" size="small">情報</Badge>
            <Badge variant="gold" size="small">1,200 SOMS</Badge>
            <Badge variant="xp" size="small">XP +50</Badge>
            <Badge variant="neutral" size="small">ニュートラル</Badge>
          </div>

          {/* small フォントサイズ比較 */}
          <p className="text-xs font-semibold text-[var(--gray-400)] uppercase tracking-wider mb-2">
            small — フォントサイズ比較
          </p>
          <div className="flex flex-wrap gap-6 items-end mb-6">
            {([4, 5, 6] as const).map(px => (
              <div key={px} className="flex flex-col items-center gap-1">
                <span
                  className="inline-flex items-center px-[9px] py-px font-medium rounded-[6px] bg-[var(--error-50)] text-[var(--error-700)] border border-[var(--error-border)]"
                  style={{ fontSize: `${px}px` }}
                >
                  高優先度
                </span>
                <span className="text-xs text-[var(--gray-400)]">{px}px</span>
              </div>
            ))}
          </div>

          {/* border opacity 確認 — カード内コーナー配置 */}
          <p className="text-xs font-semibold text-[var(--gray-400)] uppercase tracking-wider mb-2">
            カード内コーナー配置（border opacity 確認）
          </p>
          <div className="grid grid-cols-2 gap-4">
            {(
              [
                ['success', '完了', '正常に終了しました。'],
                ['warning', '要確認', '設定値が閾値に近づいています。'],
                ['error', '高優先度', '即時対応が必要なアラートです。'],
                ['info', '情報', 'バックグラウンドで処理中です。'],
              ] as const
            ).map(([variant, label, desc]) => (
              <div
                key={variant}
                className="bg-white rounded-xl border border-[var(--gray-100)] elevation-1 p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm text-[var(--gray-700)] leading-relaxed flex-1">{desc}</p>
                  <Badge variant={variant} size="small">{label}</Badge>
                </div>
              </div>
            ))}
          </div>
        </Section>

        {/* ===== Shadows ===== */}
        <Section title="Shadows (soft &amp; wide-spread)">
          <div className="grid grid-cols-4 gap-4">
            {(['elevation-1','elevation-2','elevation-3','elevation-4'] as const).map(e => (
              <div key={e} className={`bg-white rounded-xl p-5 ${e} border border-[var(--gray-100)]`}>
                <p className="text-sm font-medium text-[var(--gray-700)]">{e}</p>
              </div>
            ))}
          </div>
        </Section>

        {/* ===== Border Radius ===== */}
        <Section title="Border Radius">
          <div className="flex gap-6 items-end">
            {[
              ['sm', 'rounded-[var(--radius-sm)]', '6px'],
              ['md', 'rounded-[var(--radius-md)]', '10px'],
              ['lg', 'rounded-[var(--radius-lg)]', '14px'],
              ['xl', 'rounded-[var(--radius-xl)]', '18px'],
            ].map(([label, cls, size]) => (
              <div key={label} className="text-center">
                <div className={`w-16 h-16 bg-[var(--primary-100)] border-2 border-[var(--primary-300)] ${cls}`} />
                <p className="text-xs text-[var(--gray-600)] mt-1 font-medium">{label}</p>
                <p className="text-xs text-[var(--gray-400)]">{size}</p>
              </div>
            ))}
          </div>
        </Section>

        {/* ===== Spinner ===== */}
        <Section title="Spinner">
          <div className="flex gap-6 items-center">
            <Spinner size="small" />
            <Spinner size="medium" />
            <Spinner size="large" />
          </div>
        </Section>
      </div>
    </div>
  );
}
