import type { AgentState } from '../../../shared/types'

/**
 * A VisemeDriver applies lip-sync (and related facial motion) to a loaded 3D
 * model each frame. `AnimationClipDriver` implements it for the built-in
 * "host" characters (Amazon Sumerian Hosts), cross-fading one animation clip
 * per Polly viseme from each host's lipsync.glb.
 *
 * The rendering component owns the render loop and calls `update` every frame
 * with the current viseme and agent state; the driver does the rest.
 * (HostModel uses AnimationClipDriver.) The interface stays decoupled from any
 * one driver implementation so other lip-sync techniques could be added later.
 */
export interface VisemeFrameInput {
  /** Current Polly viseme value (e.g. 'p', 'a', 'sil'). */
  viseme: string
  /** Conversation state — drives idle/listening/speaking behaviors. */
  agentState: AgentState
  /** Seconds since last frame. */
  delta: number
  /** Absolute clock time (seconds) for time-based effects. */
  elapsed: number
}

export interface VisemeDriver {
  /** Advance the animation one frame. */
  update(input: VisemeFrameInput): void
  /** Release any resources (mixers, actions, etc.). Optional. */
  dispose?(): void
}
