import { WebSocket } from 'ws'
import type { Agent } from '@strands-agents/sdk'
import type { ClientMessage, ServerMessage, AgentState } from '../../../shared/types.js'
import { startTranscription, stopTranscription } from './transcribeService.js'
import {
  createPollyAgent,
  updateAgentPersona,
  streamAgentResponse,
  historyLength,
  rollbackHistory,
  CONTINUE_SENTINEL,
} from './pollyAgent.js'
import { synthesizeSpeechWithVisemes } from './pollyService.js'
import { isFiller, isSubstantiveBargeIn } from './transcriptClassifier.js'
import { findSentenceBoundary, toSpeakableSsml, toDisplayText } from './ssml.js'


/**
 * Marks where a mid-speech interruption cut off the avatar's previous reply.
 * `spoken` is the portion the user actually heard; `remainder` is what was cut
 * off (empty if the avatar had essentially finished). The agent already has the
 * full reply text in its own history — this only supplies the cutoff boundary,
 * which the agent cannot otherwise infer.
 */
interface InterruptionContext {
  spoken: string
  remainder: string
}

interface Session {
  ws: WebSocket
  state: AgentState
  // The Strands agent for this session. It owns the conversation history and
  // carries the avatar's persona (its name is the selected avatar's name).
  agent: Agent
  // Display name of the current avatar; also the assistant's persona name.
  assistantName: string
  transcribeStream: ReturnType<typeof startTranscription> | null
  isInterrupted: boolean
  // Incrementing id for each agent response turn. Audio produced for an
  // older turn is discarded so a barge-in can't be spoken over.
  turnId: number
  // Selected Polly voice for this session (defaults to server env / Matthew).
  voiceId: string
  // Selected language code (used for both Transcribe and — for bilingual
  // voices — passed to Polly so it picks the right language).
  language: string
  // Sentences of the current (or most recent) assistant turn, kept so we can
  // re-synthesize the tail in a new voice if the user changes voice mid-speech.
  currentTurnSentences: string[]
  // Bumped whenever a synth loop should stop (barge-in or a revoice replacing
  // an in-flight loop). A loop bails as soon as its captured epoch is stale.
  synthEpoch: number
  // Stable id (from the client) used to persist/restore this conversation via
  // the agent's SessionManager. Undefined => ephemeral, in-memory only.
  sessionId?: string
  // Highest sentence index actually sent to the client for playback in the
  // current/most-recent speaking turn. Used to compute what was cut off.
  lastSpokenIndex: number
  // When a speaking turn is interrupted, the boundary between what the avatar
  // actually spoke and what got cut off. Surfaced to the agent on the next turn
  // so it can resume ("sorry, proceed") or recognize it had finished. Cleared
  // once consumed.
  interruption: InterruptionContext | null
  // Timestamp (ms) after which barge-in is permitted for the current speaking
  // turn. Set when the avatar starts speaking; a short grace period keeps the
  // tail of the user's own utterance / echo from cutting off the response.
  bargeInAllowedAt: number
}

// Minimum average per-word confidence (0-1) from Transcribe before a transcript
// is allowed to trigger barge-in. Filters out low-confidence noise/cross-talk.
const BARGE_IN_MIN_CONFIDENCE = 0.5

// Grace period (ms) after the avatar starts speaking during which barge-in is
// suppressed. Absorbs the trailing tail of the user's own utterance and echo
// so the avatar isn't immediately cut off by its own turn.
const BARGE_IN_GRACE_MS = 400

function sendMessage(ws: WebSocket, message: ServerMessage) {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(message))
  }
}

function setState(session: Session, state: AgentState) {
  session.state = state
  sendMessage(session.ws, { type: 'state_change', state })
}

/**
 * Cheap pre-filter for a transcript that arrives while the avatar is mid-turn
 * (thinking or speaking). It rejects obvious noise so we don't spend an LLM call
 * on it: still inside the post-speech-start grace window, too low confidence, or
 * not substantive enough (see isSubstantiveBargeIn). Anything that clears this
 * bar is handed to the agent, which makes the semantic backchannel-vs-real
 * interruption decision.
 */
function shouldBargeIn(session: Session, text: string, confidence: number): boolean {
  if (session.state === 'speaking' && Date.now() < session.bargeInAllowedAt) return false
  if (confidence < BARGE_IN_MIN_CONFIDENCE) return false
  return isSubstantiveBargeIn(text)
}

export function handleConnection(ws: WebSocket) {
  const defaultName = 'Polly'
  const session: Session = {
    ws,
    state: 'idle',
    assistantName: defaultName,
    agent: createPollyAgent(defaultName),
    transcribeStream: null,
    isInterrupted: false,
    turnId: 0,
    voiceId: process.env.POLLY_VOICE_ID || 'Matthew',
    language: 'en-US',
    currentTurnSentences: [],
    synthEpoch: 0,
    bargeInAllowedAt: 0,
    lastSpokenIndex: -1,
    interruption: null,
  }

  ws.on('message', async (data) => {
    try {
      const message: ClientMessage = JSON.parse(data.toString())
      await handleMessage(session, message)
    } catch (err) {
      console.error('[Session] Error handling message:', err)
      sendMessage(ws, { type: 'error', message: 'Internal server error' })
    }
  })

  ws.on('close', () => {
    if (session.transcribeStream) {
      stopTranscription(session.transcribeStream)
    }
  })
}

async function handleMessage(session: Session, message: ClientMessage) {
  switch (message.type) {
    case 'start_session':
      await handleStartSession(session, message.config)
      break
    case 'stop_session':
      handleStopSession(session)
      break
    case 'audio_chunk':
      handleAudioChunk(session, message.data)
      break
    case 'interrupt':
      handleInterrupt(session)
      break
    case 'set_voice':
      handleSetVoice(session, message.voiceId)
      break
    case 'revoice':
      // Re-synthesize the current turn's tail (from the sentence the client is
      // currently playing) in the now-current voice.
      await revoiceFrom(session, message.fromIndex)
      break
    case 'set_language':
      handleSetLanguage(session, message.language)
      break
    case 'set_avatar':
      // Change the avatar persona name mid-session (keeps conversation history).
      session.assistantName = message.name
      updateAgentPersona(session.agent, session.assistantName, session.language)
      console.log(`[Session] avatar -> ${message.name}`)
      break
    case 'playback_finished':
      handlePlaybackFinished(session, message.turn)
      break
  }
}

/**
 * The client finished playing all audio for `turn`. If that's still the current
 * turn and we're speaking, the avatar is genuinely done — return to listening.
 * Stale reports (from a turn a barge-in already superseded) are ignored.
 */
function handlePlaybackFinished(session: Session, turn: number) {
  if (turn === session.turnId && session.state === 'speaking') {
    setState(session, 'listening')
  }
}

/**
 * (Re)opens the Transcribe stream for the session's current language. Amazon
 * Transcribe streaming fixes the language when the stream opens, so switching
 * languages requires tearing down the current stream and opening a new one.
 */
function openTranscribeStream(session: Session) {
  session.transcribeStream = startTranscription({
    language: session.language,
    onPartialTranscript: (text) => {
      // Partials are forwarded for the live UI only. We no longer barge in on
      // partials: the decision to stop the avatar is made by the agent on the
      // FINAL transcript (see onFinalTranscript / handleUserUtterance), so the
      // stop and the response are one coordinated decision.
      sendMessage(session.ws, { type: 'transcript_partial', text })
    },
    onFinalTranscript: async (text, confidence) => {
      sendMessage(session.ws, { type: 'transcript_final', text })

      // Pure filler/backchannel ("hmm", "uh huh", "yeah ok") gets no response,
      // in any state — the avatar just stays as it is.
      if (isFiller(text)) return

      const spokenOver = session.state === 'speaking' || session.state === 'thinking'

      // While the avatar is mid-turn, drop obvious noise (see shouldBargeIn)
      // before spending an LLM call. Anything that clears this bar is handed to
      // the agent, which makes the semantic backchannel-vs-real-interruption
      // decision.
      if (spokenOver && !shouldBargeIn(session, text, confidence)) {
        return
      }

      await handleUserUtterance(session, text, { spokenOver })
    },
    onError: (err) => {
      console.error('[Transcribe] Error:', err)
      sendMessage(session.ws, { type: 'error', message: 'Transcription error' })
    },
  })
}

async function handleStartSession(
  session: Session,
  config?: { language?: string; voiceId?: string; avatarName?: string; sessionId?: string }
) {
  if (config?.voiceId) session.voiceId = config.voiceId
  if (config?.language) session.language = config.language
  if (config?.avatarName) session.assistantName = config.avatarName

  // If the client supplies a stable sessionId, back the agent with a local-file
  // SessionManager so the conversation persists across reconnects/restarts. We
  // (re)create the agent here because the id only arrives with start_session.
  // The SessionManager restores prior history lazily on the agent's first use.
  if (config?.sessionId && config.sessionId !== session.sessionId) {
    session.sessionId = config.sessionId
    session.agent = createPollyAgent(session.assistantName, config.sessionId, session.language)
  } else {
    // No persistence (or same id): just make sure persona + language are current.
    updateAgentPersona(session.agent, session.assistantName, session.language)
  }

  console.log(
    `[Session] start: avatar=${session.assistantName} language=${session.language} voice=${session.voiceId} session=${session.sessionId ?? '(ephemeral)'}`
  )
  setState(session, 'listening')
  openTranscribeStream(session)
  sendMessage(session.ws, { type: 'session_started' })
}

/**
 * Changes the transcription language mid-session by restarting the Transcribe
 * stream, keeping the WebSocket + conversation history intact. If no session
 * is active yet, just records the language for the next start.
 */
function handleSetLanguage(session: Session, language: string) {
  if (language === session.language) return
  session.language = language
  console.log(`[Session] language -> ${language}`)
  // The reply script depends on the language (so Polly can pronounce it), so
  // refresh the agent persona with the new language.
  updateAgentPersona(session.agent, session.assistantName, session.language)
  if (session.transcribeStream) {
    // Restart the stream with the new language. The mic keeps streaming from
    // the client; only the server-side Transcribe stream is replaced.
    stopTranscription(session.transcribeStream)
    session.transcribeStream = null
    openTranscribeStream(session)
  }
}

function handleStopSession(session: Session) {
  if (session.transcribeStream) {
    stopTranscription(session.transcribeStream)
    session.transcribeStream = null
  }
  setState(session, 'idle')
}

function handleAudioChunk(session: Session, base64Audio: string) {
  // Keep the mic hot in every active state (not just listening) so the user
  // can barge in while the agent is thinking or speaking.
  if (session.transcribeStream && session.state !== 'idle') {
    const audioBuffer = Buffer.from(base64Audio, 'base64')
    session.transcribeStream.write(audioBuffer)
  }
}

function handleInterrupt(session: Session) {
  // Explicit interrupt from the client (e.g. the manual button).
  triggerBargeIn(session)
}

/**
 * Aborts the in-flight agent turn. Increments the turn id so any audio still
 * being synthesized for the old turn is discarded (both server-side, via the
 * synth loop's turn guard, and client-side, which drops audio tagged with an
 * older turn). Tells the client to stop playback immediately and returns to
 * listening.
 */
function triggerBargeIn(session: Session) {
  if (session.isInterrupted) return // already interrupting this turn
  session.isInterrupted = true

  // If we were mid-speech, record the cutoff boundary: what the avatar actually
  // spoke vs. what was cut off. The agent uses this on a later turn to resume
  // ("sorry, proceed") or to recognize it had essentially finished. The last
  // sentence delivered for playback (lastSpokenIndex) counts as heard.
  if (session.state === 'speaking') {
    // Use display text (SSML stripped) — this becomes prompt context for resume.
    const sentences = session.currentTurnSentences.map(toDisplayText)
    const cut = Math.max(0, session.lastSpokenIndex + 1)
    session.interruption = {
      spoken: sentences.slice(0, cut).join(' ').trim(),
      remainder: sentences.slice(cut).join(' ').trim(),
    }
  }

  session.turnId++
  sendMessage(session.ws, { type: 'interrupted', turn: session.turnId })
  setState(session, 'listening')
}

async function handleUserUtterance(
  session: Session,
  text: string,
  opts: { spokenOver?: boolean } = {}
) {
  if (!text.trim()) return
  const spokenOver = opts.spokenOver ?? false

  // For a spoken-over utterance we classify FIRST without disturbing the
  // in-progress turn: we don't claim a new turn id, don't change state, and —
  // crucially — don't stop playback. Only once the agent emits real (non
  // sentinel) text do we commit: bump the turn (barge-in), stop the avatar,
  // and render the reply. If the whole reply is the CONTINUE sentinel, it was
  // backchannel — we roll back history and the avatar keeps talking.
  const historyMark = historyLength(session.agent)
  let committed = !spokenOver
  let myTurn: number

  // Consume any "cut off mid-response" context from a prior barge-in so the
  // agent can resume it if the user asks to (e.g. "sorry, go on"). Cleared
  // immediately: it's only relevant to the very next utterance.
  const interruption = session.interruption
  session.interruption = null

  if (spokenOver) {
    // Provisional turn id: not yet claimed. We claim on commit.
    myTurn = session.turnId
  } else {
    session.isInterrupted = false
    // Claim a fresh turn id for this response. If a barge-in happens, turnId
    // advances and any work tagged with myTurn becomes stale.
    session.turnId++
    myTurn = session.turnId
    setState(session, 'thinking')
  }

  // Generate the reply via the Strands agent (it owns the conversation history
  // and the avatar persona). We stream text deltas to split into sentences for
  // per-sentence TTS.
  let fullResponse = ''
  let seenText = '' // accumulates until we know it isn't the sentinel
  const sentences: string[] = []
  let currentSentence = ''
  let chunkDisplayBuffer = '' // holds partial SSML tags across chunks for display

  // Commits a spoken-over turn to a real interruption: stops the avatar,
  // claims a fresh turn id, and switches to thinking. Idempotent.
  const commitInterruption = () => {
    if (committed) return
    committed = true
    triggerBargeIn(session) // bumps turnId + tells client to stop playback
    session.isInterrupted = false
    myTurn = session.turnId
    setState(session, 'thinking')
  }

  try {
    await streamAgentResponse(session.agent, text, {
      spokenOver,
      interruption,
      onChunk: (chunk) => {
        // For a not-yet-committed spoken-over turn, buffer text until we can
        // tell whether it's the CONTINUE sentinel. The sentinel only ever
        // appears at the very start, so once we've seen non-sentinel-prefix
        // text we commit and flush the buffer.
        if (!committed) {
          seenText += chunk
          // Ignore a leading <speak> the model may have added, so the sentinel
          // is still detected even when the reply is SSML-wrapped.
          const trimmed = seenText.trimStart().replace(/^<speak>\s*/i, '')
          if (CONTINUE_SENTINEL.startsWith(trimmed) && trimmed.length < CONTINUE_SENTINEL.length) {
            // Still could be the sentinel — keep buffering.
            return
          }
          if (trimmed.startsWith(CONTINUE_SENTINEL)) {
            // Backchannel confirmed — ignore the rest of this reply.
            return
          }
          // Real content — commit and flush the buffered text as the reply.
          // Defensively strip any stray sentinel token so it's never spoken.
          commitInterruption()
          chunk = seenText.split(CONTINUE_SENTINEL).join('')
          seenText = ''
        }

        // Stop streaming text the moment this turn is superseded.
        if (session.turnId !== myTurn) return

        fullResponse += chunk
        currentSentence += chunk

        // For the live transcript, stream display text (SSML stripped). Hold
        // back any trailing partial "<...": it completes on a later chunk, and
        // llm_done later replaces the whole block with clean text anyway.
        chunkDisplayBuffer += chunk
        const lastOpen = chunkDisplayBuffer.lastIndexOf('<')
        const safeUntil =
          lastOpen !== -1 && chunkDisplayBuffer.indexOf('>', lastOpen) === -1
            ? lastOpen
            : chunkDisplayBuffer.length
        const emit = toDisplayText(chunkDisplayBuffer.slice(0, safeUntil))
        chunkDisplayBuffer = chunkDisplayBuffer.slice(safeUntil)
        if (emit) sendMessage(session.ws, { type: 'llm_chunk', text: emit + ' ' })

        // Check for a sentence boundary to enable per-sentence TTS. The buffer
        // may contain SSML, so we use a tag-aware boundary that never splits
        // inside markup.
        const boundary = findSentenceBoundary(currentSentence)
        if (boundary !== -1) {
          const completeSentence = currentSentence.slice(0, boundary).trim()
          if (completeSentence) {
            sentences.push(completeSentence)
          }
          currentSentence = currentSentence.slice(boundary)
        }
      },
      onDone: () => {
        // Flush remaining text as final sentence
        if (committed && currentSentence.trim()) {
          sentences.push(currentSentence.trim())
        }
      },
    })

    // Never committed → the whole reply was backchannel. Roll the throwaway
    // filler exchange out of history and leave the avatar talking.
    if (!committed) {
      rollbackHistory(session.agent, historyMark)
      return
    }

    // Interrupted during generation — abandon this turn.
    if (session.turnId !== myTurn) {
      return
    }

    // Send the full reply plus its per-sentence split. The sentence indices
    // match the sentenceIndex on each audio_response, so the client can
    // highlight the sentence currently being spoken. The reply may contain
    // SSML markup, which is for Polly only — send the client plain display text.
    const displaySentences = sentences.map(toDisplayText)
    sendMessage(session.ws, {
      type: 'llm_done',
      fullText: displaySentences.join(' '),
      sentences: displaySentences,
    })

    // Remember this turn's sentences (raw markup) so a mid-speech voice change
    // can re-synthesize the tail in a new voice.
    session.currentTurnSentences = sentences

    // Synthesize speech for each sentence with visemes
    setState(session, 'speaking')
    session.lastSpokenIndex = -1 // reset for this fresh speaking turn
    // Open a short grace window before barge-in is allowed so the tail of the
    // user's own utterance / echo doesn't immediately cut off the response.
    session.bargeInAllowedAt = Date.now() + BARGE_IN_GRACE_MS
    await synthesizeSentences(session, sentences, 0, myTurn)

    if (session.turnId === myTurn) {
      // All audio for this turn has been SENT, but the client is still playing
      // it. Stay in 'speaking' so a barge-in ("stop") during the audible tail
      // is still recognized. We leave 'speaking' only when the client reports
      // playback_finished for this turn (or a barge-in supersedes it).
      sendMessage(session.ws, { type: 'response_done' })
    }
  } catch (err) {
    console.error('[Session] Error processing utterance:', err)
    // A spoken-over classification that failed before committing must not
    // disturb the still-valid in-progress turn — leave it running.
    if (!committed) {
      rollbackHistory(session.agent, historyMark)
      return
    }
    sendMessage(session.ws, { type: 'error', message: 'Failed to generate response' })
    setState(session, 'listening')
  }
}

/**
 * Synthesizes sentences[fromIndex..] with the session's current voice/language
 * and streams them to the client tagged with their sentence index. Bails early
 * if the turn changes (barge-in) or the synth epoch is bumped (a newer synth
 * loop — e.g. a revoice — has superseded this one).
 */
async function synthesizeSentences(
  session: Session,
  sentences: string[],
  fromIndex: number,
  myTurn: number
) {
  const myEpoch = ++session.synthEpoch
  for (let i = fromIndex; i < sentences.length; i++) {
    // Bail if a newer turn started or a newer synth loop superseded this one.
    if (session.turnId !== myTurn || session.synthEpoch !== myEpoch) break

    // Convert the (possibly SSML-marked) sentence into valid <speak> SSML,
    // falling back to plain text if the model's markup isn't neural-safe.
    const ssml = toSpeakableSsml(sentences[i])
    // Log metadata only: never the conversation text itself, which would end
    // up in CloudWatch Logs.
    console.log(
      `[Session] synth[${i}]: voice=${session.voiceId} lang=${session.language} chars=${ssml.length}`
    )
    const { audio, visemes } = await synthesizeSpeechWithVisemes(
      ssml,
      session.voiceId,
      session.language
    )

    // Re-check after the (async) Polly call.
    if (session.turnId !== myTurn || session.synthEpoch !== myEpoch) break

    sendMessage(session.ws, {
      type: 'audio_response',
      audio: audio.toString('base64'),
      visemes,
      sentenceIndex: i,
      turn: myTurn,
    })
    // Track the furthest sentence actually delivered for playback, so a later
    // barge-in can tell what the avatar managed to say vs. what was cut off.
    session.lastSpokenIndex = i
  }
}

/** Changes the Polly voice. Applies to the next synthesized sentence. */
function handleSetVoice(session: Session, voiceId: string) {
  session.voiceId = voiceId
  console.log(`[Session] voice -> ${session.voiceId}`)
}

/**
 * Re-synthesizes the current turn's tail starting at `fromIndex` (the sentence
 * the client is currently playing) using the now-current voice. Used when the
 * user changes voice mid-speech: the client stops old-voice playback, and we
 * replay from the current sentence onward in the new voice.
 */
async function revoiceFrom(session: Session, fromIndex: number) {
  const sentences = session.currentTurnSentences
  // The client only sends `revoice` while it is actively playing audio, so we
  // trust that signal rather than the server-side state — the server often
  // finishes synthesizing (and flips to 'listening') long before the client
  // has finished playing the queued sentences.
  if (sentences.length === 0) return
  const start = Math.max(0, Math.min(fromIndex, sentences.length - 1))
  const myTurn = session.turnId
  console.log(`[Session] revoice from sentence ${start} in voice ${session.voiceId}`)
  setState(session, 'speaking')
  // Bumping the epoch (inside synthesizeSentences) cancels the original loop
  // if it's still running, then this loop takes over from `start`.
  await synthesizeSentences(session, sentences, start, myTurn)
  if (session.turnId === myTurn) {
    sendMessage(session.ws, { type: 'response_done' })
    setState(session, 'listening')
  }
}
