import { useQuery } from '@tanstack/react-query';
import { fetchSpatialConfig } from '../api/spatial';
import { useMemo } from 'react';

/**
 * Returns a lookup function that maps zone IDs to display names.
 * Falls back to the raw zone_id if no display_name is configured.
 *
 * Usage:
 *   const zoneName = useZoneName();
 *   zoneName("zone_4d0rct") // => "エントランス"
 *   zoneName("main")        // => "main"
 */
export function useZoneName(): (zoneId: string) => string {
  const { data: config } = useQuery({
    queryKey: ['spatial-config'],
    queryFn: fetchSpatialConfig,
    staleTime: 5 * 60 * 1000, // cache 5 min
  });

  const lookup = useMemo(() => {
    const map = new Map<string, string>();
    if (config?.zones) {
      for (const [id, z] of Object.entries(config.zones)) {
        if (z.display_name && z.display_name !== id) {
          map.set(id, z.display_name);
        }
      }
    }
    return map;
  }, [config]);

  return (zoneId: string) => lookup.get(zoneId) ?? zoneId;
}
