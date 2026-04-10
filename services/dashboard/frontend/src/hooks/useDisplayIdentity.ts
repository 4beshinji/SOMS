/**
 * Manages dashboard display identity — reads display_id from URL param or localStorage,
 * validates with backend, provides context, and sends periodic heartbeats.
 */
import { createContext, useContext, useEffect, useState, useRef, useCallback } from 'react';
import { fetchDisplay, sendDisplayHeartbeat, type DisplayInfo } from '../api';

const STORAGE_KEY = 'soms-display-id';
const HEARTBEAT_INTERVAL = 60_000; // 60 seconds

export interface DisplayIdentity {
  displayId: string | null;
  zone: string | null;
  sortOrder: number;
  display: DisplayInfo | null;
  loading: boolean;
}

export const DisplayIdentityContext = createContext<DisplayIdentity>({
  displayId: null,
  zone: null,
  sortOrder: 0,
  display: null,
  loading: false,
});

export function useDisplayIdentity() {
  return useContext(DisplayIdentityContext);
}

export function useDisplayIdentityProvider(): DisplayIdentity {
  const [display, setDisplay] = useState<DisplayInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const heartbeatRef = useRef<ReturnType<typeof setInterval>>();

  // Resolve display_id: URL param > localStorage
  const resolveDisplayId = useCallback((): string | null => {
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get('display');
    if (fromUrl) {
      localStorage.setItem(STORAGE_KEY, fromUrl);
      return fromUrl;
    }
    return localStorage.getItem(STORAGE_KEY);
  }, []);

  useEffect(() => {
    const displayId = resolveDisplayId();
    if (!displayId) return;

    setLoading(true);
    fetchDisplay(displayId)
      .then((info) => {
        setDisplay(info);
        localStorage.setItem(STORAGE_KEY, displayId);
      })
      .catch((err) => {
        console.warn('Display identity validation failed:', err.message);
        // Don't clear localStorage — display may be temporarily unavailable
      })
      .finally(() => setLoading(false));
  }, [resolveDisplayId]);

  // Periodic heartbeat
  useEffect(() => {
    if (!display) return;

    const sendHb = () => {
      sendDisplayHeartbeat(
        display.display_id,
        window.innerWidth,
        window.innerHeight,
      ).catch(() => {});
    };

    // Send initial heartbeat
    sendHb();
    heartbeatRef.current = setInterval(sendHb, HEARTBEAT_INTERVAL);
    return () => clearInterval(heartbeatRef.current);
  }, [display]);

  return {
    displayId: display?.display_id ?? null,
    zone: display?.zone ?? null,
    sortOrder: display?.sort_order ?? 0,
    display,
    loading,
  };
}
