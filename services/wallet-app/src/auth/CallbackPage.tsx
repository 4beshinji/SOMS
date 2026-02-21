import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export default function CallbackPage() {
  const navigate = useNavigate();

  useEffect(() => {
    const hash = window.location.hash.substring(1);
    const params = new URLSearchParams(hash);

    const access_token = params.get('access_token');
    const refresh_token = params.get('refresh_token');
    const expires_in = parseInt(params.get('expires_in') || '0', 10);
    const userRaw = params.get('user');

    if (access_token && refresh_token && userRaw) {
      try {
        const user = JSON.parse(decodeURIComponent(userRaw));
        // Dispatch event for AuthProvider to pick up
        window.dispatchEvent(
          new CustomEvent('soms-auth-callback', {
            detail: { access_token, refresh_token, expires_in, user },
          })
        );
      } catch {
        // Parse error — fall through to redirect
      }
    }

    // Clear fragment and go home
    navigate('/', { replace: true });
  }, [navigate]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-gray-400">Signing in...</div>
    </div>
  );
}
