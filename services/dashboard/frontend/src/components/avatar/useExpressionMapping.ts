import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import type { AvatarModel } from './types';
import { useAudioAnalyser } from '../../audio/useAudioAnalyser';

interface ExpressionTarget {
  name: string;
  weight: number;
}

const TONE_MAP: Record<string, ExpressionTarget> = {
  neutral:  { name: 'relaxed',   weight: 0.0 },
  caring:   { name: 'happy',     weight: 0.4 },
  humorous: { name: 'happy',     weight: 0.7 },
  alert:    { name: 'surprised', weight: 0.5 },
};

const ONSET_SPEED = 0.08;
const DECAY_SPEED = 0.04;

export function useExpressionMapping(model: AvatarModel | null) {
  const { isActive, currentTone } = useAudioAnalyser();
  const currentWeights = useRef<Record<string, number>>({});
  const prevExpression = useRef<string | null>(null);

  useFrame(() => {
    if (!model) return;

    const tone = (isActive && currentTone) ? currentTone : 'neutral';
    const target = TONE_MAP[tone] ?? TONE_MAP.neutral;

    // Check if previous and new expressions share the same underlying morph
    const sameKey =
      prevExpression.current &&
      prevExpression.current !== target.name &&
      model.getExpressionKey(prevExpression.current) !== null &&
      model.getExpressionKey(prevExpression.current) === model.getExpressionKey(target.name);

    // Decay previous expression if switching (skip if same underlying morph)
    if (prevExpression.current && prevExpression.current !== target.name && !sameKey) {
      const oldWeight = currentWeights.current[prevExpression.current] ?? 0;
      if (oldWeight > 0.01) {
        const newWeight = oldWeight * (1 - DECAY_SPEED);
        currentWeights.current[prevExpression.current] = newWeight;
        model.setExpression(prevExpression.current, newWeight);
      } else {
        currentWeights.current[prevExpression.current] = 0;
        model.setExpression(prevExpression.current, 0);
        prevExpression.current = target.name;
      }
    } else {
      // When sameKey is true, the old and new expressions share the same morph
      // target. Transfer the accumulated weight so the blend block can decay it.
      if (sameKey && prevExpression.current) {
        const carried = currentWeights.current[prevExpression.current] ?? 0;
        if (carried > 0) {
          currentWeights.current[target.name] = carried;
          currentWeights.current[prevExpression.current] = 0;
        }
      }
      prevExpression.current = target.name;
    }

    // Blend toward target weight
    if (target.weight > 0) {
      const current = currentWeights.current[target.name] ?? 0;
      const speed = isActive ? ONSET_SPEED : DECAY_SPEED;
      const next = current + (target.weight - current) * speed;
      currentWeights.current[target.name] = next;
      model.setExpression(target.name, Math.min(1, Math.max(0, next)));
    } else {
      // target.weight === 0 means decay to zero
      const current = currentWeights.current[target.name] ?? 0;
      if (current > 0.01) {
        const next = current * (1 - DECAY_SPEED);
        currentWeights.current[target.name] = next;
        model.setExpression(target.name, next);
      } else if (current > 0) {
        currentWeights.current[target.name] = 0;
        model.setExpression(target.name, 0);
      }
    }
  });
}
