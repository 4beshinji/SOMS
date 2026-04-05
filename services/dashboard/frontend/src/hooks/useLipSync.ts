import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useAudioAnalyser } from '../audio/useAudioAnalyser';
import type { AvatarModel } from '../components/avatar/types';

export function useLipSync(model: AvatarModel | null) {
  const { getFrequencyData, isActive } = useAudioAnalyser();
  const prevRef = useRef(0);

  useFrame(() => {
    if (!model) return;

    if (isActive) {
      const data = getFrequencyData();
      let sum = 0;
      const start = 2;
      const end = Math.min(20, data.length);
      for (let i = start; i < end; i++) sum += data[i];
      const avg = end > start ? sum / (end - start) : 0;
      const target = Math.min(1, avg / 160);
      prevRef.current += (target - prevRef.current) * 0.35;
      model.setExpression('aa', prevRef.current);
    } else if (prevRef.current > 0.01) {
      prevRef.current *= 0.85;
      model.setExpression('aa', prevRef.current);
    } else if (prevRef.current > 0) {
      prevRef.current = 0;
      model.setExpression('aa', 0);
    }
  });
}
