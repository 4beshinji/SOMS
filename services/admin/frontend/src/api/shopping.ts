import { authFetch } from '@soms/auth';
import type {
  ShoppingItem,
  ShoppingItemCreate,
  ShoppingStats,
  ShoppingShareResponse,
  PurchaseHistory,
} from '@soms/types';

export interface ShoppingItemUpdate {
  name?: string;
  category?: string;
  quantity?: number;
  unit?: string;
  store?: string;
  price?: number;
  is_recurring?: boolean;
  recurrence_days?: number;
  notes?: string;
  priority?: number;
}

export async function fetchShoppingItems(
  category?: string,
  store?: string,
  includePurchased?: boolean,
): Promise<ShoppingItem[]> {
  const params = new URLSearchParams();
  if (category) params.set('category', category);
  if (store) params.set('store', store);
  if (includePurchased) params.set('include_purchased', 'true');
  const qs = params.toString();
  const res = await authFetch(`/api/shopping/${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error('Failed to fetch shopping items');
  return res.json();
}

export async function createShoppingItem(data: ShoppingItemCreate): Promise<ShoppingItem> {
  const res = await authFetch('/api/shopping/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create shopping item');
  return res.json();
}

export async function updateShoppingItem(
  itemId: number,
  data: ShoppingItemUpdate,
): Promise<ShoppingItem> {
  const res = await authFetch(`/api/shopping/${itemId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update shopping item');
  return res.json();
}

export async function purchaseShoppingItem(itemId: number): Promise<ShoppingItem> {
  const res = await authFetch(`/api/shopping/${itemId}/purchase`, { method: 'PUT' });
  if (!res.ok) throw new Error('Failed to purchase item');
  return res.json();
}

export async function deleteShoppingItem(itemId: number): Promise<void> {
  const res = await authFetch(`/api/shopping/${itemId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete shopping item');
}

export async function fetchShoppingStats(): Promise<ShoppingStats> {
  const res = await authFetch('/api/shopping/stats');
  if (!res.ok) throw new Error('Failed to fetch shopping stats');
  return res.json();
}

export async function fetchShoppingCategories(): Promise<string[]> {
  const res = await authFetch('/api/shopping/categories');
  if (!res.ok) throw new Error('Failed to fetch categories');
  return res.json();
}

export async function fetchShoppingStores(): Promise<string[]> {
  const res = await authFetch('/api/shopping/stores');
  if (!res.ok) throw new Error('Failed to fetch stores');
  return res.json();
}

export async function fetchShoppingHistory(
  days: number = 30,
  category?: string,
): Promise<PurchaseHistory[]> {
  const params = new URLSearchParams({ days: String(days) });
  if (category) params.set('category', category);
  const res = await authFetch(`/api/shopping/history?${params}`);
  if (!res.ok) throw new Error('Failed to fetch purchase history');
  return res.json();
}

export async function fetchRecurringItems(): Promise<ShoppingItem[]> {
  const res = await authFetch('/api/shopping/recurring');
  if (!res.ok) throw new Error('Failed to fetch recurring items');
  return res.json();
}

export async function fetchDueItems(): Promise<ShoppingItem[]> {
  const res = await authFetch('/api/shopping/due');
  if (!res.ok) throw new Error('Failed to fetch due items');
  return res.json();
}

export async function shareShoppingItems(itemId: number = 0): Promise<ShoppingShareResponse> {
  const res = await authFetch(`/api/shopping/${itemId}/share`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to create share link');
  return res.json();
}
