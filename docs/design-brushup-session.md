# Design Brushup Session Notes (2026-03-01)

## 目標
`packages/ui/` のデザイントークンとコンポーネントを Linear/Notion 風に刷新。
アプリ固有ファイルは変更しない。コンポーネント API に破壊的変更なし。

---

## 変更済みファイル

### `packages/ui/src/tokens.css`
| トークン | 変更前 | 変更後 |
|---------|--------|--------|
| Gray scale | Material neutral gray | Tailwind Slate (blue-tinted) |
| Primary | MD3 blue `#2196F3` | Indigo `#6366F1` |
| `--primary-300` | (なし) | `#A5B4FC` 追加 (Button.tsx で使用) |
| Shadows | 硬めの影 | ソフト・広がり系 (opacity 低め) |
| Border radius | 4/8/12/16px | 6/10/14/18px |
| `body line-height` | 1.5 | 1.6 |

### `packages/ui/src/Card.tsx`
- `elevation` デフォルト: 2 → **1**
- `baseStyles`: `border border-[var(--gray-100)]` 追加
- hoverable translate: `-translate-y-1` → `-translate-y-0.5`

### `packages/ui/src/Button.tsx`
- `baseStyles`: `gap-2` 追加
- `secondary` variant: `border-2 border-[primary-500]` → `border border-[primary-300]`、text `primary-700` に

### `packages/ui/src/Badge.tsx`
- `success/warning/error/info`: border `border-[color-500]` → `border-[color-500]/40`
- `neutral`: text `gray-700` → `gray-600`、border `gray-300` → `gray-200`

---

## インフラ修正

### `infra/mosquitto/acl`
```diff
  user soms
  topic readwrite #
+ topic read $SYS/#
```
理由: `mosquitto_sub -t '$SYS/broker/version'` healthcheck が ACL でブロックされ soms-mqtt が unhealthy になっていた。

### `services/dashboard/frontend/vite.config.ts`
```diff
  proxy: {
+   '/api/auth': {
+     target: 'http://localhost:8006',
+     changeOrigin: true,
+     rewrite: (path) => path.replace(/^\/api\/auth/, ''),
+   },
    '/api': {
      target: 'http://localhost:8000',
```
理由: auth service は port 8006、backend は 8000。旧設定では `/api/auth/*` が backend に届いていた。

### `soms-backend` rebuild
```bash
docker compose -f infra/docker-compose.yml build backend
```
理由: コンテナイメージが古く `jwt` モジュール欠如でクラッシュしていた。

---

## dev UIプレビューページ

- `services/dashboard/frontend/src/UIPreview.tsx` 作成
- `services/dashboard/frontend/src/App.tsx` に `?preview` バイパス追加
- URL: **http://localhost:5173/?preview**
- 認証不要でコンポーネント確認可能

---

## 決定事項

| 項目 | 決定 |
|------|------|
| Card padding | **B = `p-6` (24px)** を維持 = `medium` 変更なし |

---

## 未解決 (次セッション)

- **Badge の視覚的問題**: タスクカードの角付近でバッジが overflow して見える可能性。
  - `border-[var(--color-500)]/40` が Tailwind v4 で CSS 変数に正しく効いているか確認
  - Badge のサイズ・位置・border style の比較選択肢を UIPreview に追加予定

---

## 再起動後の手順

```bash
newgrp docker
docker compose -f infra/docker-compose.yml up -d backend auth

# 別ターミナル
cd services/dashboard/frontend && pnpm run dev   # → http://localhost:5173

# 別ターミナル
cd services/wallet-app && pnpm run dev           # → http://localhost:5174
```
