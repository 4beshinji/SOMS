import type * as THREE from 'three'

export type ModelFormat = 'vrm' | 'mmd'

/**
 * Format-agnostic 3D avatar model interface.
 * Implemented by VrmAdapter (VRM) and MmdAdapter (MMD/PMX).
 */
export interface AvatarModel {
  readonly scene: THREE.Object3D
  readonly format: ModelFormat

  /** Per-frame update (VRM spring bones, MMD physics, etc.) */
  update(delta: number): void

  /** Set a named expression/morph weight (0-1). Names use VRM conventions (aa, blink, happy, etc.) */
  setExpression(name: string, weight: number): void

  /** Get a named expression/morph weight */
  getExpression(name: string): number

  /** Get bone by VRM humanoid bone name (e.g. 'spine', 'head', 'leftUpperArm') */
  getBone(name: string): THREE.Object3D | null

  /** Load a motion clip from a file path (.vrma for VRM, .vmd for MMD) */
  loadMotionClip(path: string): Promise<THREE.AnimationClip | null>

  dispose(): void
}
