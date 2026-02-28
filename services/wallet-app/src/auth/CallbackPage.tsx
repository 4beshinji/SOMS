import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Spinner } from '@soms/ui';

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
        window.dispatchEvent(
          new CustomEvent('soms-auth-callback', {
            detail: { access_token, refresh_token, expires_in, user },
          })
        );
      } catch {
        // Parse error — fall through to redirect
      }
    }

    navigate('/', { replace: true });
  }, [navigate]);

  return (
    <div className="flex items-center justify-center min-h-screen bg-[var(--gray-50)]">
      <div className="text-center">
        <Spinner size="large" className="text-[var(--primary-500)] mx-auto" />
        <p className="text-[var(--gray-500)] mt-4">ログイン中...</p>
      </div>
    </div>
  );
}
