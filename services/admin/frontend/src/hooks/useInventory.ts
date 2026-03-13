import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { InventoryItemCreate, InventoryItemUpdate } from '@soms/types';
import {
  fetchInventoryItems,
  createInventoryItem,
  updateInventoryItem,
  deleteInventoryItem,
} from '../api/inventory';

export function useInventoryItems(zone?: string, activeOnly: boolean = true) {
  return useQuery({
    queryKey: ['inventoryItems', zone, activeOnly],
    queryFn: () => fetchInventoryItems(zone, activeOnly),
    refetchInterval: 30_000,
  });
}

export function useCreateInventoryItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: InventoryItemCreate) => createInventoryItem(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventoryItems'] }),
  });
}

export function useUpdateInventoryItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: InventoryItemUpdate }) =>
      updateInventoryItem(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventoryItems'] }),
  });
}

export function useDeleteInventoryItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteInventoryItem(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventoryItems'] }),
  });
}
