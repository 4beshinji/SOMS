import { getAccessToken } from './AuthProvider';

export interface AuthFetchConfig {
  /** localStorage key for the refresh token. Defaults to 'soms_refresh_token'. */
  refreshTokenKey?: string;
  /** Base path for auth API. Defaults to '/api/auth'. */
  authApiBase?: string;
}

export function createAuthFetch(config: AuthFetchConfig = {}) {
  const {
    refreshTokenKey = 'soms_refresh_token',
    authApiBase = '/api/auth',
  } = config;

  async function tryRefresh(): Promise<boolean> {
    const refreshToken = localStorage.getItem(refreshTokenKey);
    if (!refreshToken) return false;

    try {
      const res = await fetch(`${authApiBase}/token/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!res.ok) return false;

      const data = await res.json();
      window.dispatchEvent(
        new CustomEvent('soms-auth-callback', {
          detail: {
            access_token: data.access_token,
            refresh_token: data.refresh_token,
            expires_in: data.expires_in,
            user: data.user,
          },
        })
      );
      return true;
    } catch {
      return false;
    }
  }

  return async function authFetch(
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> {
    const doFetch = (token: string | null) => {
      const headers = new Headers(init?.headers);
      if (token) {
        headers.set('Authorization', `Bearer ${token}`);
      }
      return fetch(input, { ...init, headers });
    };

    let res = await doFetch(getAccessToken());

    if (res.status === 401) {
      const refreshed = await tryRefresh();
      if (refreshed) {
        res = await doFetch(getAccessToken());
      } else {
        window.dispatchEvent(new CustomEvent('soms-auth-logout'));
      }
    }

    return res;
  };
}

// Default authFetch instance for convenience
export const authFetch = createAuthFetch();
