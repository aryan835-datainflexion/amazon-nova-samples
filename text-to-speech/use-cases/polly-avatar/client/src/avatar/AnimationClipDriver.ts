import * as THREE from 'three'
import type { VisemeDriver, VisemeFrameInput } from './VisemeDriver'

/**
 * Drives lip-sync by blending VISEME POSE CLIPS (bone poses), the technique
 * used by the built-in "host" characters (Amazon Sumerian Hosts). Their
 * lipsync.glb ships one short pose clip per Polly viseme, named exactly as the
 * viseme ('p', 'a', 'sil', ...).
 *
 * Each viseme clip is treated as a HELD POSE: we pause it at its pose frame and
 * blend its weight up/down. The active viseme is driven toward full weight and
 * all others toward zero, so the mouth clearly forms the current viseme rather
 * than an averaged mush.
 *
 * Blink is triggered occasionally (play once, then wait) rather than looped, so
 * the eyes blink naturally instead of fluttering.
 */

interface AnimationClipDriverOptions {
  root: THREE.Object3D
  /** viseme value -> clip (from lipsync.glb; names match Polly visemes). */
  visemeClips: Map<string, THREE.AnimationClip>
  /** Optional blink clip — triggered occasionally, not looped. */
  blinkClip?: THREE.AnimationClip
}

const BLEND_SPEED = 18 // fast, crisp viseme transitions
// The active viseme is driven slightly past full weight to exaggerate the mouth
// pose so lip movement reads clearly. (Three.js allows weights > 1.) Silence
// stays at 1 so the resting mouth isn't distorted.
const VISEME_GAIN = 1.4
const SIL = 'sil'

export class AnimationClipDriver implements VisemeDriver {
  private mixer: THREE.AnimationMixer
  private visemeActions = new Map<string, THREE.AnimationAction>()
  private available: Set<string>

  // Blink scheduling.
  private blinkAction: THREE.AnimationAction | null = null
  private blinkTimer = 0
  private nextBlink = randomBlinkInterval()

  constructor(opts: AnimationClipDriverOptions) {
    this.mixer = new THREE.AnimationMixer(opts.root)
    this.available = new Set(opts.visemeClips.keys())

    for (const [viseme, clip] of opts.visemeClips) {
      const action = this.mixer.clipAction(clip)
      // Treat each viseme clip as a held pose: play, then pause at the pose
      // frame (end of the short clip is the fully-formed mouth shape).
      action.play()
      action.setEffectiveTimeScale(0) // freeze time — hold the pose
      action.time = clip.duration // hold at the formed-pose frame
      action.setEffectiveWeight(0)
      action.enabled = true
      action.setLoop(THREE.LoopRepeat, Infinity)
      this.visemeActions.set(viseme, action)
    }

    // Rest at silence.
    const silAction = this.visemeActions.get(SIL)
    if (silAction) silAction.setEffectiveWeight(1)

    // Blink: play once per trigger.
    if (opts.blinkClip) {
      this.blinkAction = this.mixer.clipAction(opts.blinkClip)
      this.blinkAction.setLoop(THREE.LoopOnce, 1)
      this.blinkAction.clampWhenFinished = true
    }
  }

  update({ viseme, delta }: VisemeFrameInput): void {
    const active = this.available.has(viseme) ? viseme : SIL

    // Drive the active viseme toward (exaggerated) full weight, others to zero.
    // Silence rests at exactly 1 so the neutral mouth isn't over-driven.
    for (const [v, action] of this.visemeActions) {
      const target = v === active ? (active === SIL ? 1 : VISEME_GAIN) : 0
      const next = THREE.MathUtils.lerp(action.getEffectiveWeight(), target, BLEND_SPEED * delta)
      action.setEffectiveWeight(next)
    }

    // Occasional blink.
    if (this.blinkAction) {
      this.blinkTimer += delta
      if (this.blinkTimer >= this.nextBlink) {
        this.blinkTimer = 0
        this.nextBlink = randomBlinkInterval()
        this.blinkAction.reset()
        this.blinkAction.setEffectiveWeight(1)
        this.blinkAction.play()
      }
    }

    this.mixer.update(delta)
  }

  dispose(): void {
    this.mixer.stopAllAction()
    this.visemeActions.clear()
    this.blinkAction = null
  }
}

function randomBlinkInterval(): number {
  return 3 + Math.random() * 4 // 3-7 seconds
}
