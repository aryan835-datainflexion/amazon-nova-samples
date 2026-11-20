import { useEffect, useRef } from 'react'
import type { AgentState } from '../../../shared/types'

interface ConversationUIProps {
  agentState: AgentState
  partialTranscript: string
  finalTranscript: string
  llmText: string
  /** The reply split into sentences (available once generation finishes). */
  llmSentences: string[]
  /** Index of the sentence currently being spoken, or -1. */
  currentSentenceIndex: number
  error: string | null
}

export function ConversationUI({
  agentState,
  partialTranscript,
  finalTranscript,
  llmText,
  llmSentences,
  currentSentenceIndex,
  error,
}: ConversationUIProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [llmText, finalTranscript, partialTranscript, currentSentenceIndex])

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h3 style={styles.title}>Conversation</h3>
      </div>

      <div style={styles.messages} ref={scrollRef}>
        {/* User's speech */}
        {(finalTranscript || partialTranscript) && (
          <div style={styles.messageBlock}>
            <div style={styles.messageRole}>You</div>
            <div style={styles.messageText}>
              {finalTranscript && <span>{finalTranscript}</span>}
              {partialTranscript && (
                <span style={styles.partialText}>{partialTranscript}</span>
              )}
            </div>
          </div>
        )}

        {/* Thinking indicator */}
        {agentState === 'thinking' && !llmText && (
          <div style={styles.messageBlock}>
            <div style={styles.messageRole}>Assistant</div>
            <div style={styles.thinkingDots}>
              <span style={styles.dot}>.</span>
              <span style={styles.dot}>.</span>
              <span style={styles.dot}>.</span>
              <style>{`
                @keyframes dotBounce {
                  0%, 60%, 100% { transform: translateY(0); }
                  30% { transform: translateY(-4px); }
                }
              `}</style>
            </div>
          </div>
        )}

        {/* LLM response. Once generation finishes we have the per-sentence
            split and highlight the sentence currently being spoken (keyed by
            the same sentenceIndex the audio carries). While still streaming we
            just show the raw text with a cursor. */}
        {(llmText || llmSentences.length > 0) && (
          <div style={styles.messageBlock}>
            <div style={styles.messageRole}>Assistant</div>
            <div style={styles.messageText}>
              {llmSentences.length > 0 ? (
                llmSentences.map((sentence, i) => {
                  // While a sentence is playing, highlight it and dim the rest.
                  // When nothing is playing (index -1), show the full reply at
                  // normal emphasis rather than leaving everything dimmed.
                  const isSpeaking = currentSentenceIndex >= 0
                  const style = !isSpeaking
                    ? undefined
                    : i === currentSentenceIndex
                      ? styles.sentenceActive
                      : styles.sentence
                  return (
                    <span key={i} style={style}>
                      {sentence}{' '}
                    </span>
                  )
                })
              ) : (
                <>
                  {llmText}
                  {agentState === 'thinking' && <span style={styles.cursor}>|</span>}
                </>
              )}
            </div>
          </div>
        )}

        {/* Error display */}
        {error && (
          <div style={styles.errorBlock}>
            <span style={styles.errorIcon}>!</span>
            <span>{error}</span>
          </div>
        )}
      </div>

      {/* Status bar */}
      <div style={styles.statusBar}>
        <StatusDot state={agentState} />
        <span style={styles.statusText}>
          {agentState === 'idle' && 'Ready to start'}
          {agentState === 'listening' && 'Listening...'}
          {agentState === 'thinking' && 'Generating response...'}
          {agentState === 'speaking' && 'Speaking...'}
        </span>
      </div>
    </div>
  )
}

function StatusDot({ state }: { state: AgentState }) {
  const colors: Record<AgentState, string> = {
    idle: '#555',
    listening: '#4ecdc4',
    thinking: '#ffe66d',
    speaking: '#6a6aff',
  }
  return (
    <div
      style={{
        width: '8px',
        height: '8px',
        borderRadius: '50%',
        backgroundColor: colors[state],
        boxShadow: state !== 'idle' ? `0 0 6px ${colors[state]}` : 'none',
      }}
    />
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
  },
  header: {
    padding: '16px',
    borderBottom: '1px solid #2a2a4a',
  },
  title: {
    fontSize: '0.9rem',
    fontWeight: 600,
    color: '#ccc',
  },
  messages: {
    flex: 1,
    padding: '16px',
    overflowY: 'auto' as const,
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
  },
  messageBlock: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  messageRole: {
    fontSize: '0.7rem',
    fontWeight: 600,
    color: '#888',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
  },
  messageText: {
    fontSize: '0.9rem',
    lineHeight: 1.5,
    color: '#ddd',
  },
  sentence: {
    color: '#888',
    transition: 'color 0.2s ease',
  },
  sentenceActive: {
    color: '#fff',
    background: 'rgba(106, 106, 255, 0.25)',
    borderRadius: '3px',
    boxShadow: '0 0 0 2px rgba(106, 106, 255, 0.25)',
    transition: 'color 0.2s ease, background 0.2s ease',
  },
  partialText: {
    color: '#888',
    fontStyle: 'italic',
  },
  thinkingDots: {
    display: 'flex',
    gap: '2px',
    fontSize: '1.5rem',
    color: '#888',
  },
  dot: {
    display: 'inline-block',
    animation: 'dotBounce 1.4s infinite',
  },
  cursor: {
    color: '#6a6aff',
    animation: 'blink 1s step-end infinite',
  },
  errorBlock: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '10px 12px',
    borderRadius: '8px',
    backgroundColor: 'rgba(255, 80, 80, 0.1)',
    border: '1px solid rgba(255, 80, 80, 0.3)',
    fontSize: '0.85rem',
    color: '#ff6b6b',
  },
  errorIcon: {
    width: '18px',
    height: '18px',
    borderRadius: '50%',
    backgroundColor: '#ff6b6b',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '0.7rem',
    fontWeight: 700,
    flexShrink: 0,
  },
  statusBar: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '12px 16px',
    borderTop: '1px solid #2a2a4a',
  },
  statusText: {
    fontSize: '0.8rem',
    color: '#888',
  },
}
