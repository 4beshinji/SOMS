/**
 * Procedural motion clip generator.
 * Produces THREE.AnimationClip from bone keyframes — no external VMD/VRMA files needed.
 *
 * Track names use bone.name from the scene, looked up via model.getBone(vrmBoneName).
 * Format-agnostic: MMD + VRM both work.
 */
import * as THREE from 'three';
import type { AvatarModel } from '../components/avatar/types';

type BoneKeyframe = {
  vrmBone: string;
  times: number[];
  eulers: [number, number, number][];  // [rx, ry, rz] per keyframe
};

function buildQuatTrack(
  bone: THREE.Object3D,
  times: number[],
  eulers: [number, number, number][],
): THREE.QuaternionKeyframeTrack {
  const values: number[] = [];
  const q = new THREE.Quaternion();
  const e = new THREE.Euler();
  const baseQ = new THREE.Quaternion().copy(bone.quaternion);

  for (const [rx, ry, rz] of eulers) {
    e.set(rx, ry, rz);
    const deltaQ = new THREE.Quaternion().setFromEuler(e);
    q.copy(baseQ).multiply(deltaQ);
    values.push(q.x, q.y, q.z, q.w);
  }

  return new THREE.QuaternionKeyframeTrack(`${bone.name}.quaternion`, times, values);
}

type MotionDefinition = BoneKeyframe[];

const MOTION_DEFS: Record<string, MotionDefinition> = {
  // Nod: head dips forward and returns
  nod_agree: [
    {
      vrmBone: 'head',
      times:  [0,       0.25,       0.55,       0.85,   1.5],
      eulers: [[0,0,0], [-0.28,0,0], [-0.28,0,0], [0,0,0], [0,0,0]],
    },
  ],

  // Head tilt: tilt sideways (curiosity/question)
  head_tilt: [
    {
      vrmBone: 'head',
      times:  [0,       0.3,          0.85,         1.2],
      eulers: [[0,0,0], [0, 0, 0.16], [0, 0, 0.16], [0,0,0]],
    },
  ],

  // Small bow: chest + head lean forward
  small_bow: [
    {
      vrmBone: 'chest',
      times:  [0,       0.4,          1.2,          2.0],
      eulers: [[0,0,0], [0.22, 0, 0], [0.22, 0, 0], [0,0,0]],
    },
    {
      vrmBone: 'head',
      times:  [0,       0.4,          1.2,          2.0],
      eulers: [[0,0,0], [0.15, 0, 0], [0.15, 0, 0], [0,0,0]],
    },
  ],

  // Look around: head sweeps left → right → center
  look_around: [
    {
      vrmBone: 'head',
      times:  [0,       0.5,           1.0,     1.5,            2.0,     2.5],
      eulers: [[0,0,0], [0, 0.25, 0], [0,0,0], [0, -0.25, 0], [0,0,0], [0,0,0]],
    },
  ],

  // Thinking: head tilts with slight chin-down
  thinking_pose: [
    {
      vrmBone: 'head',
      times:  [0,       0.4,                1.5,                2.0],
      eulers: [[0,0,0], [-0.06, 0, 0.13], [-0.06, 0, 0.13], [0,0,0]],
    },
  ],
};

export function createProceduralClip(
  motionId: string,
  model: AvatarModel,
): THREE.AnimationClip | null {
  const def = MOTION_DEFS[motionId];
  if (!def) return null;

  const tracks: THREE.QuaternionKeyframeTrack[] = [];

  for (const boneKf of def) {
    const bone = model.getBone(boneKf.vrmBone);
    if (!bone) continue;
    tracks.push(buildQuatTrack(bone, boneKf.times, boneKf.eulers));
  }

  if (tracks.length === 0) return null;

  const duration = Math.max(...def.flatMap(b => b.times));
  return new THREE.AnimationClip(motionId, duration, tracks);
}
