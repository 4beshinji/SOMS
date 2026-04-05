/**
 * Mapping tables between MMD (PMX/PMD) Japanese names and VRM standard names.
 */

export const MMD_BONE_TO_VRM: Record<string, string> = {
  // Torso / root
  'センター': 'hips',
  '下半身': 'hips',
  'グルーブ': 'hips',
  '上半身': 'spine',
  '上半身2': 'chest',
  '首': 'neck',
  '頭': 'head',
  '左目': 'leftEye',
  '右目': 'rightEye',
  // Arms
  '左肩': 'leftShoulder',
  '左腕': 'leftUpperArm',
  '左ひじ': 'leftLowerArm',
  '左手首': 'leftHand',
  '右肩': 'rightShoulder',
  '右腕': 'rightUpperArm',
  '右ひじ': 'rightLowerArm',
  '右手首': 'rightHand',
  // Legs
  '左足': 'leftUpperLeg',
  '左ひざ': 'leftLowerLeg',
  '左足首': 'leftFoot',
  '左つま先': 'leftToes',
  '右足': 'rightUpperLeg',
  '右ひざ': 'rightLowerLeg',
  '右足首': 'rightFoot',
  '右つま先': 'rightToes',
  // Left hand fingers (proximal / intermediate / distal)
  '左親指０': 'leftThumbMetacarpal',
  '左親指１': 'leftThumbProximal',
  '左親指２': 'leftThumbDistal',
  '左人指１': 'leftIndexProximal',
  '左人指２': 'leftIndexIntermediate',
  '左人指３': 'leftIndexDistal',
  '左中指１': 'leftMiddleProximal',
  '左中指２': 'leftMiddleIntermediate',
  '左中指３': 'leftMiddleDistal',
  '左薬指１': 'leftRingProximal',
  '左薬指２': 'leftRingIntermediate',
  '左薬指３': 'leftRingDistal',
  '左小指１': 'leftLittleProximal',
  '左小指２': 'leftLittleIntermediate',
  '左小指３': 'leftLittleDistal',
  // Right hand fingers
  '右親指０': 'rightThumbMetacarpal',
  '右親指１': 'rightThumbProximal',
  '右親指２': 'rightThumbDistal',
  '右人指１': 'rightIndexProximal',
  '右人指２': 'rightIndexIntermediate',
  '右人指３': 'rightIndexDistal',
  '右中指１': 'rightMiddleProximal',
  '右中指２': 'rightMiddleIntermediate',
  '右中指３': 'rightMiddleDistal',
  '右薬指１': 'rightRingProximal',
  '右薬指２': 'rightRingIntermediate',
  '右薬指３': 'rightRingDistal',
  '右小指１': 'rightLittleProximal',
  '右小指２': 'rightLittleIntermediate',
  '右小指３': 'rightLittleDistal',
}

export const VRM_EXPR_TO_MMD_CANDIDATES: Record<string, string[]> = {
  'aa':  ['あ', 'a'],
  'ih':  ['い', 'i'],
  'ou':  ['う', 'u'],
  'ee':  ['え', 'e'],
  'oh':  ['お', 'o'],
  'blink':     ['まばたき', '瞬き', 'blink'],
  // Note: MMD ウィンク = character's left eye closed. Convention varies by model.
  'blinkLeft': ['ウィンク', 'ウィンク２', 'wink'],
  'blinkRight':['ウィンク右', 'ウィンク2', 'wink_r'],
  'happy':     ['にこり', '笑い', 'にっこり', 'smile'],
  'angry':     ['怒り', 'angry'],
  'sad':       ['困る', '悲しい', 'sad'],
  'surprised': ['びっくり', '驚き', 'surprised'],
  'relaxed':   ['にこり', '笑い', 'smile'],
}

export function resolveExpressionMap(
  morphDict: Record<string, number>,
): Map<string, string> {
  const resolved = new Map<string, string>()
  for (const [vrmName, candidates] of Object.entries(VRM_EXPR_TO_MMD_CANDIDATES)) {
    for (const candidate of candidates) {
      if (candidate in morphDict) {
        resolved.set(vrmName, candidate)
        break
      }
    }
  }
  return resolved
}
