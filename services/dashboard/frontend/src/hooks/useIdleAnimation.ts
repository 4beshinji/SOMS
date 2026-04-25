import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import type { AvatarModel } from '../components/avatar/types';

const BLINK_CLOSE_MS = 60;
const BLINK_HOLD_MS = 80;
const BLINK_OPEN_MS = 80;

type BlinkState = 'idle' | 'closing' | 'closed' | 'opening';

function randomBlinkDelay(): number {
  return 2000 + Math.random() * 4000;
}

export function useIdleAnimation(model: AvatarModel | null, isPlayingMotion = false) {
  const blinkState = useRef<BlinkState>('idle');
  const blinkTimer = useRef(0);
  const nextBlinkAt = useRef(randomBlinkDelay());
  const blinkValue = useRef(0);
  const elapsed = useRef(0);

  const initialized = useRef(false);
  const spineBaseY = useRef(0);
  const headBaseX = useRef(0);
  const headBaseY = useRef(0);

  useFrame((_, delta) => {
    if (!model) return;
    elapsed.current += delta;

    if (!initialized.current) {
      const spine = model.getBone('spine');
      const head = model.getBone('head');
      if (spine) spineBaseY.current = spine.position.y;
      if (head) {
        headBaseX.current = head.rotation.x;
        headBaseY.current = head.rotation.y;
      }

      // Relax arms from rest pose to natural standing position
      // MMD models start in A-pose (~40° relax), VRM in T-pose (~70° relax)
      const lUpperArm = model.getBone('leftUpperArm');
      const rUpperArm = model.getBone('rightUpperArm');
      const lLowerArm = model.getBone('leftLowerArm');
      const rLowerArm = model.getBone('rightLowerArm');
      if (model.format === 'mmd') {
        if (lUpperArm) lUpperArm.rotation.z -= 0.70;
        if (rUpperArm) rUpperArm.rotation.z += 0.70;
        if (lLowerArm) lLowerArm.rotation.z -= 0.12;
        if (rLowerArm) rLowerArm.rotation.z += 0.12;
      } else if (model.format === 'vrm') {
        // VRM normalized humanoid: arms point along ±X in T-pose; rotate around Z to swing down
        if (lUpperArm) { lUpperArm.rotation.z = 1.25; lUpperArm.rotation.y = 0.05; }
        if (rUpperArm) { rUpperArm.rotation.z = -1.25; rUpperArm.rotation.y = -0.05; }
        if (lLowerArm) lLowerArm.rotation.y = 0.10;
        if (rLowerArm) rLowerArm.rotation.y = -0.10;
        // Re-baseline so breathing/idle deltas apply on top of the relaxed pose
        if (spine) spineBaseY.current = spine.position.y;
      }

      initialized.current = true;
    }

    // --- Blink ---
    blinkTimer.current += delta * 1000;

    switch (blinkState.current) {
      case 'idle':
        if (blinkTimer.current >= nextBlinkAt.current) {
          blinkState.current = 'closing';
          blinkTimer.current = 0;
        }
        break;
      case 'closing': {
        const t = Math.min(1, blinkTimer.current / BLINK_CLOSE_MS);
        blinkValue.current = t;
        if (t >= 1) { blinkState.current = 'closed'; blinkTimer.current = 0; }
        break;
      }
      case 'closed':
        blinkValue.current = 1;
        if (blinkTimer.current >= BLINK_HOLD_MS) {
          blinkState.current = 'opening';
          blinkTimer.current = 0;
        }
        break;
      case 'opening': {
        const t = Math.min(1, blinkTimer.current / BLINK_OPEN_MS);
        blinkValue.current = 1 - t;
        if (t >= 1) {
          blinkState.current = 'idle';
          blinkTimer.current = 0;
          nextBlinkAt.current = randomBlinkDelay();
          blinkValue.current = 0;
        }
        break;
      }
    }

    model.setExpression('blink', blinkValue.current);

    if (isPlayingMotion) return;

    // --- Breathing (spine bobbing) ---
    const spine = model.getBone('spine');
    if (spine) {
      spine.position.y = spineBaseY.current + Math.sin(elapsed.current * 1.5) * 0.002;
    }

    // --- Head micro-movement ---
    const head = model.getBone('head');
    if (head) {
      head.rotation.x = headBaseX.current + Math.sin(elapsed.current * 0.9) * 0.015;
      head.rotation.y = headBaseY.current + Math.sin(elapsed.current * 0.57) * 0.02;
    }
  });
}
