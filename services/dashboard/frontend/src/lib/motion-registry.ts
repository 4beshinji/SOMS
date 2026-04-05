export interface MotionMeta {
  id: string;
  duration: number;  // seconds
  category: 'reaction' | 'greeting' | 'idle' | 'alert';
}

export const MOTION_REGISTRY: Record<string, MotionMeta> = {
  nod_agree:     { id: 'nod_agree',     duration: 1.5, category: 'reaction' },
  head_tilt:     { id: 'head_tilt',     duration: 1.2, category: 'reaction' },
  small_bow:     { id: 'small_bow',     duration: 2.0, category: 'greeting' },
  look_around:   { id: 'look_around',   duration: 2.5, category: 'idle'     },
  thinking_pose: { id: 'thinking_pose', duration: 2.0, category: 'idle'     },
  surprise_back: { id: 'surprise_back', duration: 1.3, category: 'reaction' },
  emphatic_nod:  { id: 'emphatic_nod',  duration: 1.8, category: 'reaction' },
  slow_shake:    { id: 'slow_shake',    duration: 2.0, category: 'reaction' },
  perk_up:       { id: 'perk_up',       duration: 1.4, category: 'alert'    },
};

export function getMotionMeta(id: string): MotionMeta | null {
  return MOTION_REGISTRY[id] ?? null;
}

export const IDLE_MOTION_IDS = ['look_around', 'thinking_pose'] as const;
