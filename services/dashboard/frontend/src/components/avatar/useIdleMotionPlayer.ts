/**
 * Periodically triggers idle motions when the avatar is not busy (no audio, no reaction motion).
 */
import { useRef, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { AvatarModel } from './types';
import { getMotionMeta, IDLE_MOTION_IDS } from '../../lib/motion-registry';
import { createProceduralClip } from '../../lib/procedural-motions';

const IDLE_INTERVAL_MIN = 8000;
const IDLE_INTERVAL_MAX = 18000;

function randomInterval(): number {
  return IDLE_INTERVAL_MIN + Math.random() * (IDLE_INTERVAL_MAX - IDLE_INTERVAL_MIN);
}

function randomIdleMotion(): string {
  return IDLE_MOTION_IDS[Math.floor(Math.random() * IDLE_MOTION_IDS.length)];
}

export function useIdleMotionPlayer(
  model: AvatarModel | null,
  isReactionPlaying: React.MutableRefObject<boolean>,
) {
  const mixerRef = useRef<THREE.AnimationMixer | null>(null);
  const currentActionRef = useRef<THREE.AnimationAction | null>(null);
  const cacheRef = useRef(new Map<string, THREE.AnimationClip>());
  const isPlayingRef = useRef(false);
  const nextIdleAt = useRef(performance.now() + randomInterval());
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    if (!model) return;
    const mixer = new THREE.AnimationMixer(model.scene);
    mixerRef.current = mixer;
    return () => {
      mixer.stopAllAction();
      mixerRef.current = null;
    };
  }, [model]);

  useEffect(() => {
    if (!model) return;

    const check = setInterval(() => {
      if (isReactionPlaying.current || isPlayingRef.current) return;
      if (performance.now() < nextIdleAt.current) return;
      if (!mixerRef.current) return;

      const motionId = randomIdleMotion();
      const meta = getMotionMeta(motionId);
      if (!meta) return;

      let clip = cacheRef.current.get(motionId);
      if (!clip) {
        clip = createProceduralClip(motionId, model) ?? undefined;
        if (!clip) return;
        cacheRef.current.set(motionId, clip);
      }

      const mixer = mixerRef.current;
      const action = mixer.clipAction(clip);
      action.clampWhenFinished = true;
      action.loop = THREE.LoopOnce;

      if (currentActionRef.current?.isRunning()) {
        currentActionRef.current.crossFadeTo(action, 0.5, true);
        action.reset().play();
      } else {
        action.reset().fadeIn(0.5).play();
      }

      currentActionRef.current = action;
      isPlayingRef.current = true;

      clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => {
        if (currentActionRef.current === action) {
          action.fadeOut(0.5);
          isPlayingRef.current = false;
          currentActionRef.current = null;
        }
        nextIdleAt.current = performance.now() + randomInterval();
      }, meta.duration * 1000);
    }, 1000);

    return () => clearInterval(check);
  }, [model, isReactionPlaying]);

  useFrame((_, delta) => {
    mixerRef.current?.update(delta);
  });

  useEffect(() => {
    return () => {
      clearTimeout(timeoutRef.current);
      cacheRef.current.clear();
    };
  }, []);

  return { isIdlePlaying: isPlayingRef };
}
