import { lazy, Suspense, useState, useCallback } from 'react';
import AvatarPlaceholder from './AvatarPlaceholder';

const AvatarCanvas = lazy(() => import('./AvatarCanvas'));

interface Props {
  modelUrl: string | null;
  className?: string;
}

export default function AvatarContainer({ modelUrl, className }: Props) {
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleError = useCallback((msg: string) => {
    console.warn('AvatarContainer: falling back to placeholder —', msg);
    setErrorMsg(msg);
  }, []);

  // No model URL or load failed → always show placeholder
  if (!modelUrl || errorMsg) {
    return <AvatarPlaceholder className={className} />;
  }

  return (
    <Suspense fallback={<AvatarPlaceholder className={className} />}>
      <AvatarCanvas modelUrl={modelUrl} className={className} onError={handleError} />
    </Suspense>
  );
}
