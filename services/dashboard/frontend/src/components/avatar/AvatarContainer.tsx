import { lazy, Suspense, useState, useCallback, useMemo } from 'react';
import AvatarPlaceholder from './AvatarPlaceholder';
import { useCoordination, type TraversalPhase } from '../../hooks/useCoordination';

const AvatarCanvas = lazy(() => import('./AvatarCanvas'));

interface Props {
  modelUrl: string | null;
  className?: string;
}

/** Map traversal phase → CSS transform for slide animation. */
function getTraversalStyle(
  phase: TraversalPhase,
  enterEdge: 'left' | 'right',
  exitEdge: 'left' | 'right',
  progress: number,
): React.CSSProperties {
  switch (phase) {
    case 'entering': {
      // Slide in from enter edge
      const startX = enterEdge === 'left' ? -100 : 100;
      const x = startX * (1 - progress);
      return { transform: `translateX(${x}%)`, transition: 'none' };
    }
    case 'present':
      return { transform: 'translateX(0%)', transition: 'none' };
    case 'exiting': {
      // Slide out toward exit edge
      const endX = exitEdge === 'right' ? 100 : -100;
      const x = endX * progress;
      return { transform: `translateX(${x}%)`, transition: 'none' };
    }
    case 'hidden':
      return { opacity: 0, transform: 'translateX(0%)', transition: 'none' };
    case 'idle':
    default:
      return {};
  }
}

export default function AvatarContainer({ modelUrl, className }: Props) {
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const traversal = useCoordination();

  const handleError = useCallback((msg: string) => {
    console.warn('AvatarContainer: falling back to placeholder —', msg);
    setErrorMsg(msg);
  }, []);

  const traversalStyle = useMemo(
    () => getTraversalStyle(traversal.phase, traversal.enterEdge, traversal.exitEdge, traversal.progress),
    [traversal.phase, traversal.enterEdge, traversal.exitEdge, traversal.progress],
  );

  // No model URL or load failed → always show placeholder
  if (!modelUrl || errorMsg) {
    return <AvatarPlaceholder className={className} />;
  }

  return (
    <div style={traversalStyle} className={className}>
      <Suspense fallback={<AvatarPlaceholder className={className} />}>
        <AvatarCanvas modelUrl={modelUrl} className="w-full h-full" onError={handleError} />
      </Suspense>
    </div>
  );
}
