import { getAccessToken } from './AuthProvider';

const AUTH_API = '/api/auth';
const REFRESH_TOKEN_KEY = 'soms_refresh_token';

/**
 * Authenticated fetch wrapper.
 * - Injects Bearer token into Authorization header
 * - On 401, attempts one token refresh then retries
 */
export async function authFetch(
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
    // Try refresh
    const refreshed = await tryRefresh();
    if (refreshed) {
      res = await doFetch(getAccessToken());
    }
  }

  return res;
}

async function tryRefresh(): Promise<boolean> {
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) return false;

  try {
    const res = await fetch(`${AUTH_API}/token/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!res.ok) return false;

    const data = await res.json();
    // Update in-memory token via module-level setter
    // We need to dispatch the event so AuthProvider picks it up
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
