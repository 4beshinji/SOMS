import { useState, useEffect, useCallback, useRef, type ReactNode } from 'react';
import { AuthContext, type AuthUser } from './AuthContext';

const REFRESH_TOKEN_KEY = 'soms_dashboard_refresh_token';
const AUTH_API = '/api/auth';

// In-memory access token (not persisted to storage for security)
let accessToken: string | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const refreshTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const clearAuth = useCallback(() => {
    accessToken = null;
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    setUser(null);
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
  }, []);

  const scheduleRefresh = useCallback((expiresIn: number) => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    // Refresh 60 seconds before expiry, minimum 10s delay
    const delay = Math.max((expiresIn - 60) * 1000, 10_000);
    refreshTimer.current = setTimeout(() => {
      refreshTokens().catch(() => clearAuth());
    }, delay);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clearAuth]);

  const refreshTokens = useCallback(async (): Promise<boolean> => {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (!refreshToken) return false;

    try {
      const res = await fetch(`${AUTH_API}/token/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!res.ok) {
        clearAuth();
        return false;
      }

      const data = await res.json();
      accessToken = data.access_token;
      localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
      setUser(data.user);
      scheduleRefresh(data.expires_in);
      return true;
    } catch {
      clearAuth();
      return false;
    }
  }, [clearAuth, scheduleRefresh]);

  // Handle OAuth callback: parse tokens from URL hash fragment
  const handleCallback = useCallback(() => {
    if (window.location.pathname !== '/auth/callback') return false;

    const hash = window.location.hash.substring(1);
    const params = new URLSearchParams(hash);

    const tokenValue = params.get('access_token');
    const refreshValue = params.get('refresh_token');
    const expiresIn = parseInt(params.get('expires_in') || '0', 10);
    const userRaw = params.get('user');

    if (tokenValue && refreshValue && userRaw) {
      try {
        const parsedUser = JSON.parse(decodeURIComponent(userRaw));
        accessToken = tokenValue;
        localStorage.setItem(REFRESH_TOKEN_KEY, refreshValue);
        setUser(parsedUser);
        scheduleRefresh(expiresIn);
      } catch {
        // Parse error -- fall through
      }
    }

    // Clean the URL: remove /auth/callback and hash fragment
    window.history.replaceState(null, '', '/');
    return true;
  }, [scheduleRefresh]);

  // On mount: check for callback, then try to restore session
  useEffect(() => {
    const init = async () => {
      // First check if this is an OAuth callback
      if (handleCallback()) {
        setIsLoading(false);
        return;
      }

      // Otherwise try to restore session via stored refresh token
      const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
      if (refreshToken) {
        await refreshTokens();
      }
      setIsLoading(false);
    };
    init();
    return () => {
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
    };
  }, [handleCallback, refreshTokens]);

  // Listen for auth callback events (e.g. from authFetch token refresh)
  useEffect(() => {
    const handler = (e: CustomEvent) => {
      const { access_token, refresh_token, expires_in, user: u } = e.detail;
      accessToken = access_token;
      localStorage.setItem(REFRESH_TOKEN_KEY, refresh_token);
      setUser(u);
      scheduleRefresh(expires_in);
    };
    window.addEventListener('soms-auth-callback', handler as EventListener);
    return () => window.removeEventListener('soms-auth-callback', handler as EventListener);
  }, [scheduleRefresh]);

  // Listen for forced logout events (e.g. from authFetch when 401 refresh fails)
  useEffect(() => {
    const handler = () => {
      clearAuth();
    };
    window.addEventListener('soms-auth-logout', handler as EventListener);
    return () => window.removeEventListener('soms-auth-logout', handler as EventListener);
  }, [clearAuth]);

  const login = useCallback((provider: 'slack' | 'github') => {
    window.location.href = `${AUTH_API}/${provider}/login`;
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (refreshToken) {
      // Best-effort revoke
      fetch(`${AUTH_API}/token/revoke`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      }).catch(() => {});
    }
    clearAuth();
  }, [clearAuth]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
