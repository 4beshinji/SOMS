import { authFetch } from '@soms/auth';
import type { InventoryItem, InventoryItemCreate, InventoryItemUpdate } from '@soms/types';

export async function fetchInventoryItems(
  zone?: string,
  activeOnly: boolean = true,
): Promise<InventoryItem[]> {
  const params = new URLSearchParams();
  if (zone) params.set('zone', zone);
  params.set('active_only', String(activeOnly));
  const qs = params.toString();
  const res = await authFetch(`/api/inventory/?${qs}`);
  if (!res.ok) throw new Error('Failed to fetch inventory items');
  return res.json();
}

export async function fetchInventoryItem(itemId: number): Promise<InventoryItem> {
  const res = await authFetch(`/api/inventory/${itemId}`);
  if (!res.ok) throw new Error('Failed to fetch inventory item');
  return res.json();
}

export async function createInventoryItem(data: InventoryItemCreate): Promise<InventoryItem> {
  const res = await authFetch('/api/inventory/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create inventory item');
  return res.json();
}

export async function updateInventoryItem(
  itemId: number,
  data: InventoryItemUpdate,
): Promise<InventoryItem> {
  const res = await authFetch(`/api/inventory/${itemId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update inventory item');
  return res.json();
}

export async function deleteInventoryItem(itemId: number): Promise<void> {
  const res = await authFetch(`/api/inventory/${itemId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete inventory item');
}
