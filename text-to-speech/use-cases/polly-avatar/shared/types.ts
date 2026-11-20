// Shared types between client and server

export type PollyViseme = 'p' | 't' | 'S' | 'T' | 'f' | 'k' | 'i' | 'r' | 's' | 'u' | '@' | 'a' | 'e' | 'o' | 'E' | 'O' | 'sil'

export interface VisemeEvent {
  time: number // milliseconds from start of audio chunk
  type: 'viseme'
  value: PollyViseme
}

export type AgentState = 'idle' | 'listening' | 'thinking' | 'speaking'

export interface VoiceInfo {
  id: string
  name: string
  gender: string
  languageCode: string
  languageName: string
  engines: string[]
}

export interface LanguageOption {
  code: string
  name: string
  voices: VoiceInfo[]
}

// Client → Server messages
export type ClientMessage =
  | {
      type: 'start_session'
      config?: { language?: string; voiceId?: string; avatarName?: string; sessionId?: string }
    }
  | { type: 'stop_session' }
  | { type: 'audio_chunk'; data: string } // base64-encoded PCM
  | { type: 'interrupt' } // user interrupts the agent
  | { type: 'set_voice'; voiceId: string } // change Polly voice mid-session (live)
  | { type: 'set_language'; language: string } // change language (restarts Transcribe stream)
  | { type: 'revoice'; fromIndex: number } // re-synthesize current turn's tail from this sentence in the new voice
  | { type: 'set_avatar'; name: string } // change the avatar (assistant persona name) mid-session
  // The client's audio queue for `turn` has fully drained (playback truly
  // finished). The server uses this to leave 'speaking' only once the avatar is
  // actually done making sound — not merely when synthesis was sent.
  | { type: 'playback_finished'; turn: number }

// Server → Client messages
export type ServerMessage =
  | { type: 'session_started' }
  | { type: 'state_change'; state: AgentState }
  | { type: 'transcript_partial'; text: string }
  | { type: 'transcript_final'; text: string }
  | { type: 'llm_chunk'; text: string }
  // fullText is the whole reply; sentences is the same reply split into the
  // per-sentence chunks used for TTS. Their indices match the sentenceIndex on
  // audio_response, so the UI can highlight the sentence currently being spoken.
  | { type: 'llm_done'; fullText: string; sentences: string[] }
  // `turn` identifies the agent turn this audio belongs to, so the client can
  // drop stale audio from a turn that was superseded by a barge-in.
  | { type: 'audio_response'; audio: string; visemes: VisemeEvent[]; sentenceIndex: number; turn: number }
  | { type: 'response_done' }
  // Agent turn aborted due to barge-in. `turn` is the new (post-barge-in) turn
  // id; the client stops playback immediately and ignores any audio tagged with
  // an earlier turn.
  | { type: 'interrupted'; turn: number }
  | { type: 'error'; message: string }
