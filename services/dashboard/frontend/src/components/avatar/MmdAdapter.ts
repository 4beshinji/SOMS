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

  update(_delta: number): void {}

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
