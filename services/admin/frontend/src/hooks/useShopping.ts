import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { ShoppingItemCreate } from '@soms/types';
import {
  fetchShoppingItems,
  createShoppingItem,
  updateShoppingItem,
  purchaseShoppingItem,
  deleteShoppingItem,
  fetchShoppingStats,
  fetchShoppingHistory,
  fetchRecurringItems,
  fetchDueItems,
  shareShoppingItems,
  type ShoppingItemUpdate,
} from '../api/shopping';

const KEY = 'shoppingItems';

export function useShoppingItems(category?: string, store?: string, includePurchased?: boolean) {
  return useQuery({
    queryKey: [KEY, category, store, includePurchased],
    queryFn: () => fetchShoppingItems(category, store, includePurchased),
    refetchInterval: 15_000,
  });
}

export function useShoppingStats() {
  return useQuery({
    queryKey: ['shoppingStats'],
    queryFn: fetchShoppingStats,
    refetchInterval: 30_000,
  });
}

export function useShoppingHistory(days: number = 30, category?: string) {
  return useQuery({
    queryKey: ['shoppingHistory', days, category],
    queryFn: () => fetchShoppingHistory(days, category),
    refetchInterval: 60_000,
  });
}

export function useRecurringItems() {
  return useQuery({
    queryKey: ['shoppingRecurring'],
    queryFn: fetchRecurringItems,
    refetchInterval: 30_000,
  });
}

export function useDueItems() {
  return useQuery({
    queryKey: ['shoppingDue'],
    queryFn: fetchDueItems,
    refetchInterval: 30_000,
  });
}

function invalidateAll(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: [KEY] });
  qc.invalidateQueries({ queryKey: ['shoppingStats'] });
  qc.invalidateQueries({ queryKey: ['shoppingRecurring'] });
  qc.invalidateQueries({ queryKey: ['shoppingDue'] });
}

export function useCreateShoppingItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ShoppingItemCreate) => createShoppingItem(data),
    onSuccess: () => invalidateAll(qc),
  });
}

export function useUpdateShoppingItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ShoppingItemUpdate }) =>
      updateShoppingItem(id, data),
    onSuccess: () => invalidateAll(qc),
  });
}

export function usePurchaseShoppingItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => purchaseShoppingItem(id),
    onSuccess: () => {
      invalidateAll(qc);
      qc.invalidateQueries({ queryKey: ['shoppingHistory'] });
    },
  });
}

export function useDeleteShoppingItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteShoppingItem(id),
    onSuccess: () => invalidateAll(qc),
  });
}

export function useShareShoppingItems() {
  return useMutation({
    mutationFn: (itemId: number = 0) => shareShoppingItems(itemId),
  });
}
