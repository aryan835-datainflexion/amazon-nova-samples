import { useRef, useState, useCallback } from 'react'
import type { VisemeEvent } from '../../../shared/types'

interface AudioPlaybackState {
  isPlaying: boolean
  currentViseme: string
  elapsedMs: number
  // Sentence index of the audio currently playing (-1 when idle). Exposed so
  // the UI can highlight the sentence being spoken.
  currentSentenceIndex: number
}

interface QueuedAudio {
  audioBuffer: AudioBuffer
  visemes: VisemeEvent[]
  sentenceIndex: number
  turn: number
}

// Silent gap inserted before the first sentence of a NEW turn, so a fresh reply
// doesn't run straight on from the previous one. Skipped for the first-ever turn.
const INTER_RESPONSE_PAUSE_MS = 2000

interface AudioPlaybackOptions {
  // Called when the audio queue fully drains (playback truly finished) for the
  // given turn. Lets the app tell the server the avatar is done speaking.
  onPlaybackFinished?: (turn: number) => void
}

export function useAudioPlayback({ onPlaybackFinished }: AudioPlaybackOptions = {}) {
  const audioContextRef = useRef<AudioContext | null>(null)
  const queueRef = useRef<QueuedAudio[]>([])
  const isPlayingRef = useRef(false)
  const currentVisemeRef = useRef<string>('sil')
  const animFrameRef = useRef<number>(0)
  const playbackStartTimeRef = useRef<number>(0)
  const currentVisemesRef = useRef<VisemeEvent[]>([])
  // The currently-playing source node, so a barge-in can hard-stop it.
  const activeSourceRef = useRef<AudioBufferSourceNode | null>(null)
  // Sentence index of the audio currently playing (-1 when nothing is playing).
  // Used to tell the server where to resume from when re-voicing mid-speech.
  const currentSentenceIndexRef = useRef<number>(-1)
  // Generation counter: bumped on every stop so that audio buffers decoded
  // before the stop are discarded instead of being played over new input.
  const generationRef = useRef(0)
  // The most recent agent turn we've seen. Audio tagged with an older turn is
  // stale (its turn was superseded by a barge-in) and must be dropped so a
  // just-interrupted response can't keep playing to the end.
  const currentTurnRef = useRef(0)
  // The turn of the sentence we most recently started playing. Used to detect a
  // turn boundary in playNext so we can insert a pause before a new response.
  const lastPlayedTurnRef = useRef(-1)
  // True while a playNext loop is active (including during the inter-response
  // pause). Prevents enqueueAudio from spawning a SECOND concurrent playNext —
  // which would start overlapping audio sources ("two voices").
  const playLoopActiveRef = useRef(false)
  // Latest onPlaybackFinished, kept in a ref so playNext's stable closure
  // always calls the current one.
  const onPlaybackFinishedRef = useRef(onPlaybackFinished)
  onPlaybackFinishedRef.current = onPlaybackFinished

  const [state, setState] = useState<AudioPlaybackState>({
    isPlaying: false,
    currentViseme: 'sil',
    elapsedMs: 0,
    currentSentenceIndex: -1,
  })

  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContext()
    }
    return audioContextRef.current
  }, [])

  const updateVisemeState = useCallback(() => {
    if (!isPlayingRef.current) return

    const ctx = audioContextRef.current
    if (!ctx) return

    const elapsed = (ctx.currentTime - playbackStartTimeRef.current) * 1000
    const visemes = currentVisemesRef.current

    // Find the active viseme for current time
    let activeViseme = 'sil'
    for (let i = visemes.length - 1; i >= 0; i--) {
      if (visemes[i].time <= elapsed) {
        activeViseme = visemes[i].value
        break
      }
    }

    if (activeViseme !== currentVisemeRef.current) {
      currentVisemeRef.current = activeViseme
      setState((s) => ({ ...s, currentViseme: activeViseme, elapsedMs: elapsed }))
    }

    animFrameRef.current = requestAnimationFrame(updateVisemeState)
  }, [])

  const playNext = useCallback(async () => {
    // Mark the loop active up front so enqueueAudio can't spawn a second,
    // concurrent playNext (which would overlap audio) while we await below.
    playLoopActiveRef.current = true

    if (queueRef.current.length === 0) {
      const wasPlaying = isPlayingRef.current
      isPlayingRef.current = false
      playLoopActiveRef.current = false
      currentVisemeRef.current = 'sil'
      currentSentenceIndexRef.current = -1
      setState({ isPlaying: false, currentViseme: 'sil', elapsedMs: 0, currentSentenceIndex: -1 })
      cancelAnimationFrame(animFrameRef.current)
      // Queue drained after actually playing — the avatar is truly done making
      // sound for this turn. Tell the app so it can notify the server.
      if (wasPlaying) onPlaybackFinishedRef.current?.(currentTurnRef.current)
      return
    }

    const ctx = getAudioContext()
    if (ctx.state === 'suspended') {
      await ctx.resume()
    }

    const next = queueRef.current[0]!

    // Insert a pause before the FIRST sentence of a new response, so a fresh
    // reply doesn't run straight on from the previous one. Not for the very
    // first turn, and not between sentences of the same turn.
    if (lastPlayedTurnRef.current !== -1 && next.turn !== lastPlayedTurnRef.current) {
      const pauseGeneration = generationRef.current
      await new Promise((r) => setTimeout(r, INTER_RESPONSE_PAUSE_MS))
      // A stop/barge-in during the pause invalidates this playback attempt.
      if (generationRef.current !== pauseGeneration) {
        playLoopActiveRef.current = false
        return
      }
    }

    const { audioBuffer, visemes, sentenceIndex, turn } = queueRef.current.shift()!
    currentVisemesRef.current = visemes
    currentSentenceIndexRef.current = sentenceIndex
    lastPlayedTurnRef.current = turn

    const source = ctx.createBufferSource()
    source.buffer = audioBuffer
    source.connect(ctx.destination)
    activeSourceRef.current = source

    playbackStartTimeRef.current = ctx.currentTime
    isPlayingRef.current = true
    setState((s) => ({ ...s, isPlaying: true, currentSentenceIndex: sentenceIndex }))

    // Start viseme tracking
    animFrameRef.current = requestAnimationFrame(updateVisemeState)

    const startGeneration = generationRef.current
    source.onended = () => {
      // If a stop happened, this handler fires from source.stop(); don't chain.
      if (generationRef.current !== startGeneration) return
      if (activeSourceRef.current === source) activeSourceRef.current = null
      cancelAnimationFrame(animFrameRef.current)
      playNext()
    }

    source.start()
  }, [getAudioContext, updateVisemeState])

  const enqueueAudio = useCallback(
    async (base64Audio: string, visemes: VisemeEvent[], sentenceIndex: number, turn: number) => {
      // Advance our notion of the current turn; drop audio from an older turn
      // that a barge-in has already superseded (prevents the interrupted
      // response from continuing to play).
      if (turn < currentTurnRef.current) return
      currentTurnRef.current = turn

      const ctx = getAudioContext()
      const enqueueGeneration = generationRef.current

      // Decode base64 MP3 to ArrayBuffer
      const binaryString = atob(base64Audio)
      const bytes = new Uint8Array(binaryString.length)
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i)
      }

      const audioBuffer = await ctx.decodeAudioData(bytes.buffer)

      // A barge-in / newer turn may have happened while we were decoding — drop
      // stale audio (either an explicit stop bumped the generation, or a newer
      // turn arrived).
      if (generationRef.current !== enqueueGeneration) return
      if (turn < currentTurnRef.current) return

      queueRef.current.push({ audioBuffer, visemes, sentenceIndex, turn })

      // Start the play loop only if one isn't already running. Checking the
      // loop flag (not isPlayingRef) is what prevents a second concurrent loop
      // from starting during the inter-response pause — the "two voices" bug.
      if (!playLoopActiveRef.current) {
        playNext()
      }
    },
    [getAudioContext, playNext]
  )

  /**
   * Hard-stops any current playback and clears all playback state: bumps the
   * generation (so in-flight decodes and pending onended chaining are dropped),
   * stops the active source, empties the queue, and resets to the neutral pose.
   * Shared by every stop path below.
   */
  const teardownPlayback = useCallback(() => {
    generationRef.current++
    if (activeSourceRef.current) {
      try {
        activeSourceRef.current.onended = null
        activeSourceRef.current.stop()
      } catch {
        // already stopped
      }
      activeSourceRef.current = null
    }
    queueRef.current = []
    isPlayingRef.current = false
    playLoopActiveRef.current = false
    currentVisemeRef.current = 'sil'
    currentSentenceIndexRef.current = -1
    cancelAnimationFrame(animFrameRef.current)
    setState({ isPlaying: false, currentViseme: 'sil', elapsedMs: 0, currentSentenceIndex: -1 })
  }, [])

  /**
   * Prepares for a mid-speech voice change: hard-stops current playback and
   * clears the queue (dropping old-voice audio), and returns the sentence
   * index that was playing so the caller can ask the server to resume from
   * there in the new voice. Unlike stopPlayback, this is not a barge-in — the
   * turn continues; the server will re-send audio for this index onward.
   */
  const resetForRevoice = useCallback((): number => {
    const resumeFrom = currentSentenceIndexRef.current
    teardownPlayback()
    return resumeFrom
  }, [teardownPlayback])

  /** Hard-stops playback immediately (e.g. the manual interrupt button). */
  const stopPlayback = useCallback(() => {
    teardownPlayback()
  }, [teardownPlayback])

  /**
   * Stops playback for a barge-in and adopts `newTurn` as the current turn, so
   * any late-arriving audio from the interrupted (older) turn is dropped by
   * enqueueAudio instead of continuing to play. This is a clean, immediate stop.
   */
  const stopForBargeIn = useCallback(
    (newTurn: number) => {
      currentTurnRef.current = Math.max(currentTurnRef.current, newTurn)
      // The interrupting reply should come back promptly — treat it like a
      // first turn (no inter-response pause).
      lastPlayedTurnRef.current = -1
      teardownPlayback()
    },
    [teardownPlayback]
  )

  return {
    ...state,
    enqueueAudio,
    stopPlayback,
    stopForBargeIn,
    resetForRevoice,
  }
}
