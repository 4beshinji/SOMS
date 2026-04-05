export interface MotionMeta {
  id: string;
  duration: number;  // seconds
  category: 'reaction' | 'greeting' | 'idle';
}

export const MOTION_REGISTRY: Record<string, MotionMeta> = {
  nod_agree:     { id: 'nod_agree',     duration: 1.5, category: 'reaction' },
  head_tilt:     { id: 'head_tilt',     duration: 1.2, category: 'reaction' },
  small_bow:     { id: 'small_bow',     duration: 2.0, category: 'greeting' },
  look_around:   { id: 'look_around',   duration: 2.5, category: 'idle'     },
  thinking_pose: { id: 'thinking_pose', duration: 2.0, category: 'idle'     },
};

export function getMotionMeta(id: string): MotionMeta | null {
  return MOTION_REGISTRY[id] ?? null;
}

export const IDLE_MOTION_IDS = ['look_around', 'thinking_pose'] as const;
