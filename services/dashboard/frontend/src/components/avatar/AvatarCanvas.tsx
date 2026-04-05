import { Suspense, useEffect } from 'react';
import * as THREE from 'three';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { useAvatarLoader } from '../../hooks/useAvatarLoader';
import { useLipSync } from '../../hooks/useLipSync';
import { useIdleAnimation } from '../../hooks/useIdleAnimation';
import { useExpressionMapping } from './useExpressionMapping';
import { useMotionPlayer } from './useMotionPlayer';
import { useIdleMotionPlayer } from './useIdleMotionPlayer';
import type { AvatarModel } from './types';

interface Props {
  modelUrl: string;
  className?: string;
  onError?: (msg: string) => void;
}

function AvatarModelInner({ modelUrl, onError }: { modelUrl: string; onError?: (msg: string) => void }) {
  const { model, loading, error } = useAvatarLoader(modelUrl);

  useEffect(() => {
    if (error) {
      console.error('Avatar load error:', error);
      onError?.(error);
    }
  }, [error, onError]);

  if (error || loading || !model) return null;

  return <AvatarScene model={model} />;
}

function AutoFrame({ model }: { model: AvatarModel }) {
  const { camera } = useThree();

  useEffect(() => {
    const box = new THREE.Box3().setFromObject(model.scene);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());

    const bustY = box.min.y + size.y * 0.75;
    const dist = size.y * 0.9;

    camera.position.set(center.x, bustY, center.z + dist);
    if ('fov' in camera) {
      (camera as THREE.PerspectiveCamera).fov = 35;
      (camera as THREE.PerspectiveCamera).updateProjectionMatrix();
    }
    camera.lookAt(center.x, bustY, center.z);
  }, [model, camera]);

  return null;
}

function AvatarScene({ model }: { model: AvatarModel }) {
  useLipSync(model);
  useExpressionMapping(model);
  const { isPlayingMotion } = useMotionPlayer(model);
  useIdleMotionPlayer(model, isPlayingMotion);
  useIdleAnimation(model, isPlayingMotion.current);

  useFrame((_, delta) => {
    model.update(delta);
  });

  return (
    <>
      <AutoFrame model={model} />
      <primitive object={model.scene} />
    </>
  );
}

export default function AvatarCanvas({ modelUrl, className, onError }: Props) {
  return (
    <div className={className} style={{ background: 'transparent' }}>
      <Canvas
        camera={{
          position: [0, 12, 8],
          fov: 35,
          near: 0.1,
          far: 1000,
        }}
        gl={{ alpha: true, antialias: true }}
        style={{ background: 'transparent' }}
        onCreated={({ gl }) => {
          gl.setClearColor(0x000000, 0);
        }}
      >
        <ambientLight intensity={0.8} />
        <directionalLight position={[2, 3, 3]} intensity={1.0} />
        <directionalLight position={[-2, 1, 0]} intensity={0.3} />
        <Suspense fallback={null}>
          <AvatarModelInner modelUrl={modelUrl} onError={onError} />
        </Suspense>
      </Canvas>
    </div>
  );
}
