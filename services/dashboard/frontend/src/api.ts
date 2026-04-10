import type {
  Task, TaskReport, SystemStats, SupplyStats, ZoneMultiplierInfo,
  ShoppingItem, ShoppingItemCreate, ShoppingStats, ShoppingShareResponse,
  PurchaseHistory, ChatResponse, ChatChunk,
} from '@soms/types';

export type {
  Task, TaskReport, SystemStats, SupplyStats, ZoneMultiplierInfo,
  ShoppingItem, ShoppingItemCreate, ShoppingStats, ShoppingShareResponse,
  PurchaseHistory, ChatResponse, ChatChunk,
};

export const fetchTasks = async (): Promise<Task[]> => {
  const res = await fetch('/api/tasks/?audience=user');
  if (!res.ok) throw new Error('Failed to fetch tasks');
  const data = await res.json();
  if (!Array.isArray(data)) throw new Error('Invalid tasks response: expected array');
  return data;
};

export const fetchStats = async (): Promise<SystemStats> => {
  const res = await fetch('/api/tasks/stats');
  if (!res.ok) throw new Error('Failed to fetch stats');
  return res.json();
};

export const fetchSupply = async (): Promise<SupplyStats> => {
  const res = await fetch('/api/wallet/supply');
  if (!res.ok) throw new Error('Failed to fetch supply');
  return res.json();
};

export const fetchVoiceEvents = async (displayId?: string): Promise<{ id: number; audio_url: string }[]> => {
  const params = displayId ? `?display_id=${encodeURIComponent(displayId)}` : '';
  const res = await fetch(`/api/voice-events/recent${params}`);
  if (!res.ok) throw new Error('Failed to fetch voice events');
  return res.json();
};

export const acceptTask = async (taskId: number): Promise<void> => {
  const res = await fetch(`/api/tasks/${taskId}/accept`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error('Failed to accept task');
};

export const completeTask = async ({
  taskId,
  report,
}: {
  taskId: number;
  report?: TaskReport;
}): Promise<Task> => {
  const res = await fetch(`/api/tasks/${taskId}/complete`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      report_status: report?.status || null,
      completion_note: report?.note || null,
    }),
  });
  if (!res.ok) throw new Error('Failed to complete task');
  return res.json();
};

export const fetchZoneMultiplier = async (zone: string): Promise<ZoneMultiplierInfo> => {
  const res = await fetch(`/api/wallet/devices/zone-multiplier/${encodeURIComponent(zone)}`);
  if (!res.ok) throw new Error('Failed to fetch zone multiplier');
  return res.json();
};

// ── Shopping / Inventory ────────────────────────────────────────────

export const fetchShopping = async (): Promise<ShoppingItem[]> => {
  const res = await fetch('/api/shopping/');
  if (!res.ok) throw new Error('Failed to fetch shopping items');
  const data = await res.json();
  if (!Array.isArray(data)) throw new Error('Invalid shopping response: expected array');
  return data;
};

export const fetchShoppingStats = async (): Promise<ShoppingStats> => {
  const res = await fetch('/api/shopping/stats');
  if (!res.ok) throw new Error('Failed to fetch shopping stats');
  return res.json();
};

export const addShoppingItem = async (item: ShoppingItemCreate): Promise<ShoppingItem> => {
  const res = await fetch('/api/shopping/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(item),
  });
  if (!res.ok) throw new Error('Failed to add shopping item');
  return res.json();
};

export const purchaseShoppingItem = async (id: number): Promise<ShoppingItem> => {
  const res = await fetch(`/api/shopping/${id}/purchase`, { method: 'PUT' });
  if (!res.ok) throw new Error('Failed to purchase item');
  return res.json();
};

export const deleteShoppingItem = async (id: number): Promise<void> => {
  const res = await fetch(`/api/shopping/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete shopping item');
};

export const createShoppingShareLink = async (): Promise<ShoppingShareResponse> => {
  const res = await fetch('/api/shopping/0/share', { method: 'POST' });
  if (!res.ok) throw new Error('Failed to create share link');
  return res.json();
};

export const fetchShoppingHistory = async (days: number = 30): Promise<PurchaseHistory[]> => {
  const res = await fetch(`/api/shopping/history?days=${days}`);
  if (!res.ok) throw new Error('Failed to fetch shopping history');
  return res.json();
};

export const fetchShoppingDue = async (): Promise<ShoppingItem[]> => {
  const res = await fetch('/api/shopping/due');
  if (!res.ok) throw new Error('Failed to fetch due items');
  return res.json();
};

// ── Inventory Live Status ──────────────────────────────────────────

import type { InventoryLiveStatus } from '@soms/types';
export type { InventoryLiveStatus };

export const fetchInventoryLiveStatus = async (): Promise<InventoryLiveStatus> => {
  const res = await fetch('/api/inventory/live-status');
  if (!res.ok) throw new Error('Failed to fetch inventory status');
  return res.json();
};

// ── Chat ───────────────────────────────────────────────────────────

export const sendChat = async (message: string): Promise<ChatResponse> => {
  const res = await fetch('/api/chat/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error('Chat request failed');
  return res.json();
};

/** SSE streaming chat — calls onChunk for each sentence as it arrives. */
export async function sendChatStream(
  message: string,
  onChunk: (chunk: ChatChunk & { index: number }) => void,
  onDone: () => void,
  onError?: (err: string) => void,
): Promise<void> {
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  if (!res.ok || !res.body) {
    onError?.('Chat stream request failed');
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let eventType = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Parse SSE lines
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        const raw = line.slice(6);
        if (eventType === 'done') {
          onDone();
          return;
        }
        if (eventType === 'error') {
          try { onError?.(JSON.parse(raw).message); } catch { onError?.(raw); }
          return;
        }
        if (eventType === 'chunk') {
          try {
            onChunk(JSON.parse(raw));
          } catch { /* skip malformed */ }
        }
        eventType = '';
      }
    }
  }
  onDone();
}

// ── Display Identity ──────────────────────────────────────────────

export interface DisplayInfo {
  id: number;
  display_id: string;
  display_name: string | null;
  zone: string;
  x: number;
  y: number;
  screen_width_px: number | null;
  screen_height_px: number | null;
  sort_order: number;
  is_active: boolean;
  last_seen_at: string | null;
}

export const fetchDisplay = async (displayId: string): Promise<DisplayInfo> => {
  const res = await fetch(`/api/displays/${encodeURIComponent(displayId)}`);
  if (!res.ok) throw new Error(`Display '${displayId}' not found`);
  return res.json();
};

export const sendDisplayHeartbeat = async (
  displayId: string,
  screenWidth?: number,
  screenHeight?: number,
): Promise<void> => {
  const body: Record<string, number> = {};
  if (screenWidth != null) body.screen_width_px = screenWidth;
  if (screenHeight != null) body.screen_height_px = screenHeight;
  await fetch(`/api/displays/${encodeURIComponent(displayId)}/heartbeat`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
};

export const transcribeAudio = async (audioBlob: Blob): Promise<string> => {
  const form = new FormData();
  form.append('file', audioBlob, 'recording.wav');
  form.append('language', 'ja');
  const res = await fetch('/api/stt/v1/audio/transcriptions', {
    method: 'POST',
    body: form,
  });
  if (!res.ok) throw new Error('STT failed');
  const data = await res.json();
  return data.text;
};
