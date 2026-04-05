import { useEffect, useRef, useState, useCallback } from 'react';
import { audioQueue } from '../../audio';

interface Props {
  className?: string;
}

function computeMouthOpen(analyser: AnalyserNode | null): number {
  if (!analyser) return 0;
  const data = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteFrequencyData(data);
  let sum = 0;
  const start = 2, end = Math.min(20, data.length);
  for (let i = start; i < end; i++) sum += data[i];
  return Math.min(1, sum / ((end - start) * 160));
}

export default function AvatarPlaceholder({ className }: Props) {
  const [mouthOpen, setMouthOpen] = useState(0);
  const [blinkPhase, setBlinkPhase] = useState(1);
  const rafRef = useRef(0);
  const blinkTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Lip sync
  useEffect(() => {
    let prev = 0;
    const tick = () => {
      const analyser = audioQueue.getAnalyser();
      const target = computeMouthOpen(analyser);
      prev += (target - prev) * 0.35;
      setMouthOpen(prev);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  // Blink
  const scheduleBlink = useCallback(() => {
    const delay = 2000 + Math.random() * 4000;
    blinkTimerRef.current = setTimeout(() => {
      setBlinkPhase(0);
      setTimeout(() => {
        setBlinkPhase(1);
        scheduleBlink();
      }, 150);
    }, delay);
  }, []);

  useEffect(() => {
    scheduleBlink();
    return () => clearTimeout(blinkTimerRef.current);
  }, [scheduleBlink]);

  return (
    <div className={className} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
      <svg viewBox="0 0 200 280" width="100%" height="100%" style={{ maxWidth: 160, maxHeight: 240 }}>
        {/* Hair back */}
        <ellipse cx="100" cy="88" rx="62" ry="68" fill="oklch(0.35 0.05 260)" />
        {/* Neck */}
        <rect x="88" y="148" width="24" height="24" rx="4" fill="oklch(0.85 0.03 80)" />
        {/* Body */}
        <path d="M50 172 Q50 162 65 160 L135 160 Q150 162 150 172 L155 240 Q155 250 145 250 L55 250 Q45 250 45 240 Z" fill="oklch(0.55 0.15 260)" />
        <path d="M80 162 L100 180 L120 162" fill="none" stroke="oklch(0.90 0.01 80)" strokeWidth="2" />
        {/* Face */}
        <ellipse cx="100" cy="100" rx="52" ry="58" fill="oklch(0.88 0.03 80)" />
        {/* Hair front */}
        <path d="M48 90 Q48 42 100 38 Q152 42 152 90 L148 72 Q140 52 100 48 Q60 52 52 72 Z" fill="oklch(0.35 0.05 260)" />
        <path d="M58 78 Q65 60 80 68 Q75 55 92 62 Q90 50 108 58 Q110 48 125 60 Q130 52 140 72 L138 82 Q130 65 118 70 Q115 58 100 64 Q88 56 85 68 Q75 60 68 78 Z" fill="oklch(0.30 0.05 260)" />
        {/* Eyebrows */}
        <path d="M68 80 Q75 76 85 78" fill="none" stroke="oklch(0.30 0.03 260)" strokeWidth="2" strokeLinecap="round" />
        <path d="M115 78 Q125 76 132 80" fill="none" stroke="oklch(0.30 0.03 260)" strokeWidth="2" strokeLinecap="round" />
        {/* Left eye */}
        <g transform={`translate(78, 92) scale(1, ${blinkPhase})`}>
          <ellipse cx="0" cy="0" rx="8" ry="9" fill="white" />
          <ellipse cx="1" cy="0" rx="5" ry="6" fill="oklch(0.40 0.15 260)" />
          <ellipse cx="2" cy="-1" rx="2.5" ry="3" fill="oklch(0.15 0.05 260)" />
          <ellipse cx="4" cy="-3" rx="1.5" ry="1.5" fill="white" opacity="0.8" />
        </g>
        {/* Right eye */}
        <g transform={`translate(122, 92) scale(1, ${blinkPhase})`}>
          <ellipse cx="0" cy="0" rx="8" ry="9" fill="white" />
          <ellipse cx="-1" cy="0" rx="5" ry="6" fill="oklch(0.40 0.15 260)" />
          <ellipse cx="0" cy="-1" rx="2.5" ry="3" fill="oklch(0.15 0.05 260)" />
          <ellipse cx="2" cy="-3" rx="1.5" ry="1.5" fill="white" opacity="0.8" />
        </g>
        {/* Nose */}
        <path d="M99 106 L97 112 Q100 114 103 112 Z" fill="oklch(0.80 0.04 60)" opacity="0.5" />
        {/* Mouth */}
        {mouthOpen < 0.05 ? (
          <path d="M92 124 Q100 126 108 124" fill="none" stroke="oklch(0.55 0.10 15)" strokeWidth="2" strokeLinecap="round" />
        ) : (
          <ellipse cx="100" cy={122 + mouthOpen * 3} rx={5 + mouthOpen * 5} ry={2 + mouthOpen * 8} fill="oklch(0.35 0.12 15)" />
        )}
        {/* Ears */}
        <ellipse cx="48" cy="100" rx="6" ry="10" fill="oklch(0.85 0.04 70)" />
        <ellipse cx="152" cy="100" rx="6" ry="10" fill="oklch(0.85 0.04 70)" />
      </svg>
    </div>
  );
}
