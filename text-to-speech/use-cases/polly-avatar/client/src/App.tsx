import { useState, useCallback, useEffect, useRef } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { useAudioCapture } from './hooks/useAudioCapture'
import { useAudioPlayback } from './hooks/useAudioPlayback'
import { ConversationUI } from './components/ConversationUI'
import { VisemeDebugView } from './components/VisemeDebugView'
import { AvatarCanvas } from './components/AvatarCanvas'
import { Controls } from './components/Controls'
import { HOSTS, getHost } from './avatar/hostCatalog'
import type { Gender } from './avatar/hostCatalog'
import type { VisemeEvent, LanguageOption } from '../../shared/types'

type RenderMode = 'debug' | '3d'

// A fresh session id for each conversation. Every "Start" begins a new session
// so the backend agent starts with a clean history (no persona/topic carried
// over from a previous conversation); the UI transcript is cleared to match.
function newSessionId(): string {
  return crypto.randomUUID()
}

interface AppProps {
  authToken?: string | null
  onLogout?: () => void
}

export default function App({ authToken, onLogout }: AppProps = {}) {
  const [renderMode, setRenderMode] = useState<RenderMode>('3d')
  const [selectedLanguage, setSelectedLanguage] = useState<string>('en-US')
  const [selectedVoice, setSelectedVoice] = useState<string>('Matthew')
  // Currently selected built-in 3D host id.
  const [selectedHostId, setSelectedHostId] = useState<string>('wes')

  // The resolved current host.
  const selectedHost = getHost(selectedHostId) ?? HOSTS[0]
  // The selected avatar's name doubles as the assistant's persona name.
  const avatarName = selectedHost?.name ?? 'Polly'

  // Bridge: useAudioPlayback runs before useWebSocket, so route the
  // playback-finished callback through a ref that we point at the WS sender.
  const playbackFinishedRef = useRef<(turn: number) => void>(() => {})

  const {
    isPlaying,
    currentViseme,
    currentSentenceIndex,
    enqueueAudio,
    stopPlayback,
    stopForBargeIn,
    resetForRevoice,
  } = useAudioPlayback({
    onPlaybackFinished: (turn) => playbackFinishedRef.current(turn),
  })

  const handleAudioResponse = useCallback(
    (audio: string, visemes: VisemeEvent[], sentenceIndex: number, turn: number) => {
      enqueueAudio(audio, visemes, sentenceIndex, turn)
    },
    [enqueueAudio]
  )

  const handleInterrupted = useCallback(
    (turn: number) => {
      // Server detected barge-in — stop immediately and adopt the new turn so
      // any late audio from the interrupted turn is dropped.
      stopForBargeIn(turn)
    },
    [stopForBargeIn]
  )

  const {
    isConnected,
    agentState,
    partialTranscript,
    finalTranscript,
    llmText,
    llmSentences,
    error,
    connect,
    startSession,
    stopSession,
    sendAudioChunk,
    interrupt,
    setVoice,
    setLanguage,
    revoice,
    setAvatar,
    playbackFinished,
    resetConversation,
  } = useWebSocket({
    onAudioResponse: handleAudioResponse,
    onInterrupted: handleInterrupted,
  })
  playbackFinishedRef.current = playbackFinished

  // Language/voice change handlers: update local state AND, if a session is
  // live, push the change to the server so it applies mid-conversation.
  const handleLanguageChange = useCallback(
    (code: string) => {
      setSelectedLanguage(code)
      if (agentState !== 'idle') setLanguage(code)
    },
    [agentState, setLanguage]
  )
  // Tracks the voice the server currently knows about, so we only send
  // set_voice when it actually changes (whether via the dropdown or an
  // automatic same-gender re-pick after a host/language switch).
  const sentVoiceRef = useRef<string | null>(null)
  // Tracks the avatar name the server currently knows, so we only send
  // set_avatar when it actually changes during a live session.
  const sentAvatarRef = useRef<string | null>(null)

  const handleVoiceChange = useCallback(
    (voiceId: string) => {
      setSelectedVoice(voiceId)
    },
    []
  )

  // Language/voice list is baked into a static JSON (no runtime fetch).
  const [languages, setLanguages] = useState<LanguageOption[]>([])
  useEffect(() => {
    fetch('/languages.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: LanguageOption[]) => setLanguages(data))
      .catch((err) => console.warn('[App] Could not load languages.json:', err.message))
  }, [])

  // Gender of the currently-selected host. Every host carries a gender, so
  // voices are always strictly filtered.
  const hostGender: Gender | null = selectedHost?.gender ?? null

  // Voices available for the current language, strictly filtered to the
  // selected host's gender.
  const availableVoices = (() => {
    const lang = languages.find((l) => l.code === selectedLanguage)
    if (!lang) return []
    return hostGender ? lang.voices.filter((v) => v.gender === hostGender) : lang.voices
  })()

  // Keep the selected voice valid for the language + host gender. If the
  // current voice isn't in the allowed set, pick the first same-gender voice.
  useEffect(() => {
    if (languages.length === 0) return
    const lang = languages.find((l) => l.code === selectedLanguage)
    if (!lang) {
      const first = languages[0]
      setSelectedLanguage(first.code)
      return
    }
    const allowed = hostGender ? lang.voices.filter((v) => v.gender === hostGender) : lang.voices
    if (allowed.length > 0 && !allowed.some((v) => v.id === selectedVoice)) {
      setSelectedVoice(allowed[0].id)
    }
  }, [languages, selectedLanguage, selectedVoice, hostGender])

  // Single source of truth for pushing the selected voice to the server.
  // Fires for any voice change during a live session — dropdown selection OR
  // the automatic same-gender re-pick after switching hosts/languages.
  useEffect(() => {
    if (!selectedVoice) return
    if (agentState === 'idle') {
      // No live session: the voice will be sent with start_session instead.
      sentVoiceRef.current = null
      return
    }
    if (sentVoiceRef.current !== selectedVoice) {
      sentVoiceRef.current = selectedVoice
      setVoice(selectedVoice)
      // If audio is currently playing, re-synthesize the tail in the new
      // voice: stop the old-voice playback, then tell the server to resume
      // from the sentence we were playing (replaying it from its start).
      if (isPlaying) {
        const resumeFrom = resetForRevoice()
        if (resumeFrom >= 0) revoice(resumeFrom)
      }
    }
  }, [selectedVoice, agentState, isPlaying, setVoice, resetForRevoice, revoice])

  // Push the avatar/persona name to the server when it changes during a live
  // session (the initial name rides along with start_session).
  useEffect(() => {
    if (agentState === 'idle') {
      sentAvatarRef.current = null
      return
    }
    if (sentAvatarRef.current !== avatarName) {
      sentAvatarRef.current = avatarName
      setAvatar(avatarName)
    }
  }, [avatarName, agentState, setAvatar])

  const { isRecording, start: startRecording, stop: stopRecording } = useAudioCapture({
    onAudioChunk: sendAudioChunk,
  })

  const handleStart = useCallback(async () => {
    // The initial voice + avatar name are sent with start_session, so seed the
    // refs to avoid an immediate redundant set_voice/set_avatar on activation.
    sentVoiceRef.current = selectedVoice
    sentAvatarRef.current = avatarName
    // Every conversation is a fresh session: new id + cleared transcript.
    const sessionId = newSessionId()
    resetConversation()
    if (!isConnected) {
      connect(authToken ?? undefined)
      setTimeout(() => {
        startSession(selectedLanguage, selectedVoice, avatarName, sessionId)
        startRecording()
      }, 500)
    } else {
      startSession(selectedLanguage, selectedVoice, avatarName, sessionId)
      await startRecording()
    }
  }, [isConnected, connect, startSession, startRecording, resetConversation, selectedLanguage, selectedVoice, avatarName, authToken])

  const handleStop = useCallback(() => {
    stopRecording()
    stopSession()
    stopPlayback()
  }, [stopRecording, stopSession, stopPlayback])

  const handleInterrupt = useCallback(() => {
    interrupt()
    stopPlayback()
  }, [interrupt, stopPlayback])

  // Determine the effective state (override with 'speaking' if audio is playing)
  const effectiveState = isPlaying ? 'speaking' : agentState

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <h1 style={styles.title}>Polly Avatar Demo</h1>
        <div style={styles.headerControls}>
          <button
            style={{
              ...styles.modeButton,
              ...(renderMode === 'debug' ? styles.modeButtonActive : {}),
            }}
            onClick={() => setRenderMode('debug')}
          >
            Debug View
          </button>
          <button
            style={{
              ...styles.modeButton,
              ...(renderMode === '3d' ? styles.modeButtonActive : {}),
            }}
            onClick={() => setRenderMode('3d')}
          >
            3D Avatar
          </button>
          {renderMode === '3d' && (
            <select
              style={styles.modeButton}
              value={selectedHostId}
              onChange={(e) => setSelectedHostId(e.target.value)}
              title="3D Hosts"
            >
              {HOSTS.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name}
                </option>
              ))}
            </select>
          )}
          {onLogout && (
            <button style={styles.modeButton} onClick={onLogout}>
              Sign out
            </button>
          )}
        </div>
      </header>

      <main style={styles.main}>
        <div style={styles.avatarSection}>
          {renderMode === 'debug' ? (
            <VisemeDebugView currentViseme={currentViseme} agentState={effectiveState} />
          ) : (
            <AvatarCanvas
              currentViseme={currentViseme}
              agentState={effectiveState}
              hostId={selectedHost?.id ?? null}
            />
          )}
        </div>

        <div style={styles.sidePanel}>
          <ConversationUI
            agentState={effectiveState}
            partialTranscript={partialTranscript}
            finalTranscript={finalTranscript}
            llmText={llmText}
            llmSentences={llmSentences}
            currentSentenceIndex={currentSentenceIndex}
            error={error}
          />
        </div>
      </main>

      <footer style={styles.footer}>
        <Controls
          isConnected={isConnected}
          isRecording={isRecording}
          agentState={effectiveState}
          languages={languages}
          voices={availableVoices}
          selectedLanguage={selectedLanguage}
          selectedVoice={selectedVoice}
          onLanguageChange={handleLanguageChange}
          onVoiceChange={handleVoiceChange}
          onStart={handleStart}
          onStop={handleStop}
          onInterrupt={handleInterrupt}
        />
      </footer>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    backgroundColor: '#1a1a2e',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px 24px',
    borderBottom: '1px solid #2a2a4a',
  },
  title: {
    fontSize: '1.2rem',
    fontWeight: 600,
    color: '#e0e0ff',
  },
  headerControls: {
    display: 'flex',
    gap: '8px',
  },
  modeButton: {
    padding: '6px 14px',
    border: '1px solid #4a4a6a',
    borderRadius: '6px',
    background: 'transparent',
    color: '#aaa',
    cursor: 'pointer',
    fontSize: '0.85rem',
  },
  modeButtonActive: {
    background: '#3a3a6a',
    color: '#fff',
    borderColor: '#6a6aff',
  },
  main: {
    display: 'flex',
    flex: 1,
    overflow: 'hidden',
  },
  avatarSection: {
    flex: 2,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative' as const,
  },
  sidePanel: {
    flex: 1,
    borderLeft: '1px solid #2a2a4a',
    overflow: 'auto',
    minWidth: '300px',
    maxWidth: '400px',
  },
  footer: {
    padding: '16px 24px',
    borderTop: '1px solid #2a2a4a',
  },
}
