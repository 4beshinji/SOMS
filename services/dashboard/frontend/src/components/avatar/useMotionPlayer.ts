/**
 * Plays reaction motions triggered by chat responses (via AudioAnalyser.currentMotionId).
 * Uses procedural AnimationClips — no external motion files required.
 */
import { useRef, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { AvatarModel } from './types';
import { useAudioAnalyser } from '../../audio/useAudioAnalyser';
import { getMotionMeta } from '../../lib/motion-registry';
import { createProceduralClip } from '../../lib/procedural-motions';

export function useMotionPlayer(model: AvatarModel | null) {
  const { currentMotionId } = useAudioAnalyser();
  const mixerRef = useRef<THREE.AnimationMixer | null>(null);
  const currentActionRef = useRef<THREE.AnimationAction | null>(null);
  const isPlayingRef = useRef(false);
  const lastMotionIdRef = useRef<string | null>(null);
  const cacheRef = useRef(new Map<string, THREE.AnimationClip>());
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
    if (!model || !mixerRef.current || !currentMotionId) return;
    if (currentMotionId === lastMotionIdRef.current) return;

    lastMotionIdRef.current = currentMotionId;
    const meta = getMotionMeta(currentMotionId);
    if (!meta) return;

    // Get or generate procedural clip
    let clip = cacheRef.current.get(currentMotionId);
    if (!clip) {
      clip = createProceduralClip(currentMotionId, model) ?? undefined;
      if (!clip) return;
      cacheRef.current.set(currentMotionId, clip);
    }

    const mixer = mixerRef.current;
    const action = mixer.clipAction(clip);
    action.clampWhenFinished = true;
    action.loop = THREE.LoopOnce;

    if (currentActionRef.current?.isRunning()) {
      currentActionRef.current.crossFadeTo(action, 0.3, true);
      action.reset().play();
    } else {
      action.reset().fadeIn(0.3).play();
    }

    currentActionRef.current = action;
    isPlayingRef.current = true;

    clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => {
      if (currentActionRef.current === action) {
        action.fadeOut(0.4);
        isPlayingRef.current = false;
        currentActionRef.current = null;
        lastMotionIdRef.current = null;
      }
    }, meta.duration * 1000);
  }, [model, currentMotionId]);

  useFrame((_, delta) => {
    mixerRef.current?.update(delta);
  });

  useEffect(() => {
    return () => {
      clearTimeout(timeoutRef.current);
      cacheRef.current.clear();
    };
  }, []);

  return { isPlayingMotion: isPlayingRef };
}
