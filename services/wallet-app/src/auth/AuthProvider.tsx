import { useState, useEffect, useCallback, useRef, type ReactNode } from 'react';
import { AuthContext, type AuthUser } from './AuthContext';

const REFRESH_TOKEN_KEY = 'soms_refresh_token';
const AUTH_API = '/api/auth';

// In-memory access token (not persisted to storage)
let accessToken: string | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const refreshTimer = useRef<ReturnType<typeof setTimeout>>();

  const clearAuth = useCallback(() => {
    accessToken = null;
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    setUser(null);
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
  }, []);

  const scheduleRefresh = useCallback((expiresIn: number) => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    // Refresh 60 seconds before expiry
    const delay = Math.max((expiresIn - 60) * 1000, 10_000);
    refreshTimer.current = setTimeout(() => {
      refreshTokens().catch(() => clearAuth());
    }, delay);
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

  // On mount: try to restore session via refresh token
  useEffect(() => {
    const init = async () => {
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
  }, [refreshTokens]);

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

  // Expose a way to set tokens from CallbackPage
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
