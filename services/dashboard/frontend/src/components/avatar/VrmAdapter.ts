import * as THREE from 'three'
import type { VRM, VRMHumanBoneName } from '@pixiv/three-vrm'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import type { AvatarModel } from './types'

export class VrmAdapter implements AvatarModel {
  readonly format = 'vrm' as const
  private loader: GLTFLoader

  constructor(private vrm: VRM) {
    this.loader = new GLTFLoader()
  }

  get scene(): THREE.Object3D {
    return this.vrm.scene
  }

  update(delta: number): void {
    this.vrm.update(delta)
  }

  setExpression(name: string, weight: number): void {
    this.vrm.expressionManager?.setValue(name, Math.min(1, Math.max(0, weight)))
  }

  getExpression(name: string): number {
    return this.vrm.expressionManager?.getValue(name) ?? 0
  }

  hasExpression(name: string): boolean {
    return this.vrm.expressionManager?.getExpression(name) !== undefined
  }

  getExpressionKey(name: string): string | null {
    // VRM expressions are 1:1 — key is the name itself
    return this.vrm.expressionManager?.getExpression(name) ? name : null
  }

  getBone(name: string): THREE.Object3D | null {
    return this.vrm.humanoid?.getNormalizedBoneNode(name as VRMHumanBoneName) ?? null
  }

  async loadMotionClip(_path: string): Promise<THREE.AnimationClip | null> {
    // VRM animation loading requires @pixiv/three-vrm-animation (not yet installed)
    return null
  }

  dispose(): void {
    this.vrm.scene.traverse((obj) => {
      if (obj instanceof THREE.Mesh) {
        obj.geometry?.dispose()
        const materials = Array.isArray(obj.material) ? obj.material : [obj.material]
        materials.forEach((m) => m?.dispose())
      }
    })
  }
}
