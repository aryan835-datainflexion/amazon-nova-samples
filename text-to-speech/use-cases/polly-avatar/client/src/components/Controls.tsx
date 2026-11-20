import type { AgentState, LanguageOption, VoiceInfo } from '../../../shared/types'

interface ControlsProps {
  isConnected: boolean
  isRecording: boolean
  agentState: AgentState
  languages: LanguageOption[]
  /** Voices for the current language, already filtered to the host gender. */
  voices: VoiceInfo[]
  selectedLanguage: string
  selectedVoice: string
  onLanguageChange: (code: string) => void
  onVoiceChange: (voiceId: string) => void
  onStart: () => void
  onStop: () => void
  onInterrupt: () => void
}

export function Controls({
  isConnected,
  isRecording,
  agentState,
  languages,
  voices,
  selectedLanguage,
  selectedVoice,
  onLanguageChange,
  onVoiceChange,
  onStart,
  onStop,
  onInterrupt,
}: ControlsProps) {
  const isActive = isRecording || agentState !== 'idle'

  return (
    <div style={styles.container}>
      <div style={styles.leftGroup}>
        {/* Main action button */}
        {!isActive ? (
          <button style={styles.startButton} onClick={onStart}>
            <MicIcon />
            <span>Start Conversation</span>
          </button>
        ) : (
          <div style={styles.activeControls}>
            <button style={styles.stopButton} onClick={onStop}>
              <StopIcon />
              <span>End</span>
            </button>
            {agentState === 'speaking' && (
              <button style={styles.interruptButton} onClick={onInterrupt}>
                <InterruptIcon />
                <span>Interrupt</span>
              </button>
            )}
          </div>
        )}

        {/* Language + voice selectors (disabled once a session is active). */}
        <div style={styles.selectorGroup}>
          <label style={styles.selectorLabel}>
            Language
            <select
              style={styles.select}
              value={selectedLanguage}
              disabled={languages.length === 0}
              onChange={(e) => onLanguageChange(e.target.value)}
            >
              {languages.length === 0 && <option>Loading…</option>}
              {languages.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
          <label style={styles.selectorLabel}>
            Voice
            <select
              style={styles.select}
              value={selectedVoice}
              disabled={voices.length === 0}
              onChange={(e) => onVoiceChange(e.target.value)}
            >
              {voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name} ({v.gender})
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div style={styles.rightGroup}>
        {/* Connection indicator */}
        <div style={styles.connectionStatus}>
          <div
            style={{
              ...styles.connectionDot,
              backgroundColor: isConnected ? '#4ecdc4' : '#666',
            }}
          />
          <span style={styles.connectionText}>
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>
    </div>
  )
}

function MicIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  )
}

function StopIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <rect x="4" y="4" width="16" height="16" rx="2" />
    </svg>
  )
}

function InterruptIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 6L6 18M6 6l12 12" />
    </svg>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  leftGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  rightGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
  },
  startButton: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '10px 20px',
    borderRadius: '8px',
    border: 'none',
    background: 'linear-gradient(135deg, #6a6aff, #4a4adf)',
    color: '#fff',
    fontSize: '0.9rem',
    fontWeight: 500,
    cursor: 'pointer',
  },
  activeControls: {
    display: 'flex',
    gap: '8px',
  },
  selectorGroup: {
    display: 'flex',
    gap: '12px',
    marginLeft: '4px',
  },
  selectorLabel: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '3px',
    fontSize: '0.65rem',
    color: '#888',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
  },
  select: {
    background: '#2a2a4a',
    border: '1px solid #4a4a6a',
    borderRadius: '6px',
    color: '#ddd',
    fontSize: '0.85rem',
    padding: '6px 8px',
    cursor: 'pointer',
    minWidth: '130px',
  },
  stopButton: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '10px 16px',
    borderRadius: '8px',
    border: 'none',
    background: '#ff4444',
    color: '#fff',
    fontSize: '0.85rem',
    fontWeight: 500,
    cursor: 'pointer',
  },
  interruptButton: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '10px 16px',
    borderRadius: '8px',
    border: '1px solid #666',
    background: 'transparent',
    color: '#ccc',
    fontSize: '0.85rem',
    cursor: 'pointer',
  },
  connectionStatus: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  connectionDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
  },
  connectionText: {
    fontSize: '0.8rem',
    color: '#888',
  },
}
