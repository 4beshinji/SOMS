/**
 * Dev-only Vite middleware that serves mock data for /api/* endpoints
 * so the frontend can run without the backend container.
 * Disable by removing `mockApiPlugin()` from vite.config.ts plugins.
 */
import type { Plugin } from 'vite'
import type { IncomingMessage, ServerResponse } from 'http'

const now = Date.now()
const iso = (msAgo: number) => new Date(now - msAgo).toISOString()

const TASKS = [
  {
    id: 1, title: '会議室Bの冷房が効きすぎている',
    description: 'センサーが室温18℃を検知。空調リモコンで22℃に再設定してください。',
    location: '会議室B / 3F', urgency: 3, is_completed: false,
    announcement_text: '会議室Bが寒すぎます。温度設定を確認してください。',
    created_at: iso(120_000), task_type: ['空調', '快適性'],
    zone: 'meeting_b', estimated_duration: 5, audience: 'user' as const,
  },
  {
    id: 2, title: 'ホワイトボードを消去',
    description: '昨日のミーティングの内容が残ったままです。次回利用前にお願いします。',
    location: '会議室A / 3F', urgency: 1, is_completed: false,
    created_at: iso(900_000), task_type: ['清掃'], zone: 'meeting_a',
    estimated_duration: 2, audience: 'user' as const,
  },
  {
    id: 3, title: 'コーヒー豆の補充', description: '在庫センサが残量低下を検知。新しい袋を開封してください。',
    location: 'パントリー', urgency: 2, is_completed: false,
    created_at: iso(1_800_000), task_type: ['補充', '飲料'], zone: 'pantry',
    estimated_duration: 3, audience: 'user' as const,
  },
  {
    id: 4, title: '受付のゴミ箱回収', description: '満タンを検知。共用ゴミ置き場に運んでください。',
    location: '受付 / 1F', urgency: 1, is_completed: true,
    completed_at: iso(180_000), created_at: iso(3_600_000),
    task_type: ['清掃'], zone: 'reception', audience: 'user' as const,
  },
]

const STATS = {
  tasks_completed: 47, tasks_created: 52, tasks_active: 3,
  tasks_queued: 1, tasks_completed_last_hour: 4,
}

const SHOPPING = [
  { id: 1, name: 'コーヒー豆 (深煎り)', category: '飲料', quantity: 2, unit: '袋', store: 'カルディ', price: 1480, is_purchased: false, is_recurring: true, recurrence_days: 14, priority: 1, created_at: iso(86_400_000), created_by: 'system', notes: '前回と同じブレンドで' },
  { id: 2, name: 'A4コピー用紙', category: '消耗品', quantity: 1, unit: '箱', store: 'アスクル', price: 3200, is_purchased: false, is_recurring: false, priority: 2, created_at: iso(43_200_000), created_by: 'sin' },
  { id: 3, name: 'ハンドソープ', category: '日用品', quantity: 3, store: 'コスモス', price: 248, is_purchased: false, is_recurring: true, recurrence_days: 30, priority: 1, created_at: iso(7_200_000), created_by: 'system' },
  { id: 4, name: '緑茶パック', category: '飲料', quantity: 1, unit: '袋', store: 'カルディ', price: 580, is_purchased: false, is_recurring: false, priority: 0, created_at: iso(3_600_000), created_by: 'sin' },
  { id: 5, name: '消毒用アルコール', category: '消耗品', quantity: 2, store: 'コスモス', price: 398, is_purchased: false, is_recurring: false, priority: 1, created_at: iso(1_800_000), created_by: 'system' },
  { id: 6, name: '油性ペン (黒)', category: '文具', quantity: 5, unit: '本', store: 'ロフト', price: 110, is_purchased: false, is_recurring: false, priority: 0, created_at: iso(900_000), created_by: 'sin' },
]

const SHOPPING_STATS = {
  total_items: 6, purchased_items: 12, pending_items: 6,
  total_spent_this_month: 28_450,
  category_breakdown: { '飲料': 4, '消耗品': 3, '日用品': 3, '文具': 2 },
}

const SHOPPING_HISTORY = [
  { id: 101, item_name: 'コーヒー豆 (深煎り)', category: '飲料', store: 'カルディ', price: 1480, quantity: 2, purchased_at: iso(14 * 86_400_000) },
  { id: 102, item_name: '牛乳 1L', category: '食品', store: 'ローソン100', price: 198, quantity: 3, purchased_at: iso(2 * 86_400_000) },
  { id: 103, item_name: 'A4コピー用紙', category: '消耗品', store: 'アスクル', price: 3200, quantity: 1, purchased_at: iso(7 * 86_400_000) },
]

const INVENTORY = {
  items: [
    { device_id: 'scale_01', channel: 'weight', zone: 'pantry', item_name: 'コーヒー豆', quantity: 1, min_threshold: 2, current_weight_g: 180, status: 'low' as const },
    { device_id: 'scale_02', channel: 'weight', zone: 'pantry', item_name: '緑茶ティーバッグ', quantity: 8, min_threshold: 5, current_weight_g: 120, status: 'ok' as const },
    { device_id: 'scale_03', channel: 'weight', zone: 'lavatory', item_name: 'トイレットペーパー', quantity: 12, min_threshold: 6, current_weight_g: 1500, status: 'ok' as const },
    { device_id: 'scale_04', channel: 'weight', zone: 'kitchen', item_name: 'ハンドソープ', quantity: 1, min_threshold: 2, current_weight_g: 60, status: 'low' as const },
  ],
  updated_at: Math.floor(now / 1000) - 30,
}

const CHAT_REPLIES = [
  '会議室Bが少し寒いみたいですよ。冷房をチェックしてみますか？',
  'お疲れさまです。今日は4件のタスクを完了しました。',
  'コーヒー豆の在庫が残り少なくなっています。',
  '了解しました。後ほど対応しますね。',
  'はい、確認しました。何か他にお手伝いできることはありますか？',
]

function send(res: ServerResponse, data: unknown, status = 200) {
  res.statusCode = status
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.end(JSON.stringify(data))
}

function sendStream(res: ServerResponse, text: string) {
  res.statusCode = 200
  res.setHeader('Content-Type', 'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache')
  res.setHeader('Connection', 'keep-alive')

  // Split into ~2-3 chunks to simulate streaming
  const sentences = text.match(/[^。！？]+[。！？]?/g) ?? [text]
  let i = 0
  const tick = () => {
    if (i >= sentences.length) {
      res.write(`event: done\ndata: {}\n\n`)
      res.end()
      return
    }
    const chunk = { text: sentences[i], audio_url: null, tone: 'neutral', motion_id: i === 0 ? 'nod_agree' : null, index: i }
    res.write(`event: chunk\ndata: ${JSON.stringify(chunk)}\n\n`)
    i++
    setTimeout(tick, 350)
  }
  tick()
}

export function mockApiPlugin(): Plugin {
  return {
    name: 'soms-dev-mock-api',
    configureServer(server) {
      server.middlewares.use((req: IncomingMessage, res: ServerResponse, next) => {
        const url = req.url ?? ''

        // Tasks
        if (url.startsWith('/api/tasks/stats')) return send(res, STATS)
        if (url === '/api/tasks/queue') return send(res, [])
        if (url.startsWith('/api/tasks/audit')) return send(res, [])
        if (url.match(/^\/api\/tasks\/\d+\/(accept|complete|reminded|dispatch)/)) {
          // Mutations: just echo success
          let body = ''
          req.on('data', (c) => (body += c))
          req.on('end', () => send(res, { ok: true }))
          return
        }
        if (url.startsWith('/api/tasks')) return send(res, TASKS)

        // Shopping
        if (url.startsWith('/api/shopping/stats')) return send(res, SHOPPING_STATS)
        if (url.startsWith('/api/shopping/due')) return send(res, [SHOPPING[0]])
        if (url.startsWith('/api/shopping/history')) return send(res, SHOPPING_HISTORY)
        if (url.match(/^\/api\/shopping\/\d+\/purchase/)) {
          return send(res, { ...SHOPPING[0], is_purchased: true })
        }
        if (url.match(/^\/api\/shopping\/\d+\/share/)) {
          return send(res, { share_url: 'http://localhost:5173/share/mock', token: 'mock', items: SHOPPING })
        }
        if (url.match(/^\/api\/shopping\/\d+$/) && req.method === 'DELETE') {
          return send(res, { ok: true })
        }
        if (url.startsWith('/api/shopping')) return send(res, SHOPPING)

        // Inventory
        if (url.startsWith('/api/inventory/live-status')) return send(res, INVENTORY)

        // Voice events
        if (url.startsWith('/api/voice-events/recent')) return send(res, [])
        if (url.startsWith('/api/voice-events/chitchat-stock/random')) {
          return send(res, { ok: false })
        }
        if (url.startsWith('/api/voice/rejection/random')) return send(res, { audio_url: null })
        if (url.startsWith('/api/voice/acceptance/random')) return send(res, { audio_url: null })
        if (url.startsWith('/api/voice/')) return send(res, { ok: true })

        // Displays
        if (url.match(/^\/api\/displays\/[^/]+\/heartbeat/)) {
          let body = ''
          req.on('data', (c) => (body += c))
          req.on('end', () => send(res, { ok: true }))
          return
        }
        if (url.match(/^\/api\/displays\/[^/]+/)) {
          return send(res, {
            id: 1, display_id: 'mock-display', display_name: 'Mock Display',
            zone: 'meeting_b', x: 0, y: 0, screen_width_px: 1920, screen_height_px: 1080,
            sort_order: 0, is_active: true, last_seen_at: iso(0),
          })
        }

        // Chat (SSE stream)
        if (url.startsWith('/api/chat/stream') && req.method === 'POST') {
          const reply = CHAT_REPLIES[Math.floor(Math.random() * CHAT_REPLIES.length)]
          return sendStream(res, reply)
        }
        if (url.startsWith('/api/chat')) {
          return send(res, { content: CHAT_REPLIES[0], audio_url: null, tone: 'neutral' })
        }

        next()
      })
    },
  }
}
