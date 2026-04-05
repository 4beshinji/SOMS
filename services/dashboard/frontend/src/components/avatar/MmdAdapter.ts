import * as THREE from 'three'
import { MMDLoader } from 'three-stdlib'
import type { AvatarModel } from './types'
import { MMD_BONE_TO_VRM, resolveExpressionMap } from './mmd-maps'

export class MmdAdapter implements AvatarModel {
  readonly format = 'mmd' as const
  private group: THREE.Group
  private boneMap: Map<string, THREE.Bone>
  private exprMap: Map<string, string>
  private loader: MMDLoader
  private grantSolver: { update(): unknown } | null = null
  private physics: { update(delta: number): unknown } | null = null

  constructor(private mesh: THREE.SkinnedMesh) {
    this.loader = new MMDLoader()

    this.group = new THREE.Group()
    this.group.add(mesh)

    this.boneMap = new Map()
    for (const bone of mesh.skeleton.bones) {
      const vrmName = MMD_BONE_TO_VRM[bone.name]
      if (vrmName) {
        this.boneMap.set(vrmName, bone)
      }
    }

    const dict = mesh.morphTargetDictionary ?? {}
    this.exprMap = resolveExpressionMap(dict)
  }

  get scene(): THREE.Object3D {
    return this.group
  }

  update(delta: number): void {
    this.grantSolver?.update()
    this.physics?.update(delta)
  }

  /**
   * Initialize Grant solver and physics asynchronously.
   * MMDAnimationHelper / MMDPhysics are imported dynamically to avoid
   * crashing the module at load time (they pull in heavy dependencies).
   */
  async initSolvers(): Promise<void> {
    const mmdData = (this.mesh.geometry as any).userData?.MMD

    // Grant solver
    if (mmdData?.grants?.length) {
      try {
        const { MMDAnimationHelper } = await import('three-stdlib')
        const helper = new MMDAnimationHelper()
        this.grantSolver = helper.createGrantSolver(this.mesh)
        console.log('[MmdAdapter] Grant solver initialized')
      } catch (e) {
        console.warn('[MmdAdapter] Grant init failed:', e)
      }
    }

    // Physics (requires ammo.js)
    if (mmdData?.rigidBodies?.length) {
      try {
        const { initAmmo } = await import('../../lib/ammo-loader')
        const ok = await initAmmo()
        if (!ok) return

        const { MMDPhysics } = await import('three-stdlib')
        this.physics = new MMDPhysics(
          this.mesh,
          mmdData.rigidBodies,
          mmdData.constraints ?? [],
          { unitStep: 1 / 65, maxStepNum: 3 },
        )
        ;(this.physics as any).warmup?.(60)
        console.log('[MmdAdapter] Physics initialized')
      } catch (e) {
        console.warn('[MmdAdapter] Physics init failed:', e)
      }
    }
  }

  setExpression(name: string, weight: number): void {
    const mmdName = this.exprMap.get(name)
    if (!mmdName) return
    const dict = this.mesh.morphTargetDictionary
    const influences = this.mesh.morphTargetInfluences
    if (!dict || !influences) return
    const idx = dict[mmdName]
    if (idx !== undefined) {
      influences[idx] = Math.min(1, Math.max(0, weight))
    }
  }

  getExpression(name: string): number {
    const mmdName = this.exprMap.get(name)
    if (!mmdName) return 0
    const dict = this.mesh.morphTargetDictionary
    const influences = this.mesh.morphTargetInfluences
    if (!dict || !influences) return 0
    const idx = dict[mmdName]
    return idx !== undefined ? (influences[idx] ?? 0) : 0
  }

  hasExpression(name: string): boolean {
    return this.exprMap.has(name)
  }

  getExpressionKey(name: string): string | null {
    return this.exprMap.get(name) ?? null
  }

  getBone(name: string): THREE.Object3D | null {
    return this.boneMap.get(name) ?? null
  }

  async loadMotionClip(path: string): Promise<THREE.AnimationClip | null> {
    return new Promise((resolve) => {
      this.loader.loadAnimation(
        path,
        this.mesh,
        (clip: THREE.SkinnedMesh | THREE.AnimationClip) => resolve(clip as THREE.AnimationClip),
        undefined,
        () => resolve(null),
      )
    })
  }

  dispose(): void {
    this.mesh.geometry?.dispose()
    const materials = Array.isArray(this.mesh.material)
      ? this.mesh.material
      : [this.mesh.material]
    materials.forEach((m) => m?.dispose())
  }
}
