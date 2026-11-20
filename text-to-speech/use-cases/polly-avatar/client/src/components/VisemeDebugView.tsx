import { useEffect, useRef, useState } from 'react'
import { VISEME_DESCRIPTIONS, VISEME_OPENNESS, VISEME_ROUNDEDNESS } from '../utils/visemeMap'
import type { AgentState } from '../../../shared/types'

interface VisemeDebugViewProps {
  currentViseme: string
  agentState: AgentState
}

// Keep a rolling history of recent visemes for the timeline
const MAX_HISTORY = 24

export function VisemeDebugView({ currentViseme, agentState }: VisemeDebugViewProps) {
  const [history, setHistory] = useState<Array<{ viseme: string; time: number }>>([])
  const lastVisemeRef = useRef(currentViseme)

  useEffect(() => {
    if (currentViseme !== lastVisemeRef.current) {
      lastVisemeRef.current = currentViseme
      setHistory((prev) => {
        const next = [...prev, { viseme: currentViseme, time: Date.now() }]
        return next.slice(-MAX_HISTORY)
      })
    }
  }, [currentViseme])

  // Clear history when state changes to idle
  useEffect(() => {
    if (agentState === 'idle') {
      setHistory([])
    }
  }, [agentState])

  const openness = VISEME_OPENNESS[currentViseme] ?? 0
  const roundedness = VISEME_ROUNDEDNESS[currentViseme] ?? 0
  const description = VISEME_DESCRIPTIONS[currentViseme] ?? ''

  return (
    <div style={styles.container}>
      {/* State indicator */}
      <div style={styles.stateRow}>
        <StateIndicator state={agentState} />
      </div>

      {/* Main viseme display */}
      <div style={styles.visemeDisplay}>
        <div style={styles.visemeLabel}>
          <span style={styles.visemeLabelSmall}>Current Viseme</span>
          <span style={styles.visemeLabelLarge}>{currentViseme}</span>
          <span style={styles.visemeDescription}>{description}</span>
        </div>

        {/* SVG Mouth */}
        <svg width="200" height="140" viewBox="0 0 200 140" style={styles.mouthSvg}>
          <MouthShape openness={openness} roundedness={roundedness} />
        </svg>
      </div>

      {/* Metrics */}
      <div style={styles.metrics}>
        <MetricBar label="Openness" value={openness} color="#ff6b6b" />
        <MetricBar label="Roundedness" value={roundedness} color="#4ecdc4" />
      </div>

      {/* Viseme Timeline */}
      <div style={styles.timeline}>
        <span style={styles.timelineLabel}>Timeline</span>
        <div style={styles.timelineTrack}>
          {history.map((entry, i) => (
            <div
              key={i}
              style={{
                ...styles.timelineItem,
                opacity: 0.3 + (i / history.length) * 0.7,
                background:
                  i === history.length - 1 ? '#6a6aff' : '#3a3a5a',
              }}
            >
              {entry.viseme}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function StateIndicator({ state }: { state: AgentState }) {
  const colors: Record<AgentState, string> = {
    idle: '#666',
    listening: '#4ecdc4',
    thinking: '#ffe66d',
    speaking: '#6a6aff',
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <div
        style={{
          width: '10px',
          height: '10px',
          borderRadius: '50%',
          backgroundColor: colors[state],
          animation: state === 'listening' ? 'pulse 1.5s infinite' : 'none',
          boxShadow: `0 0 8px ${colors[state]}`,
        }}
      />
      <span style={{ color: colors[state], fontSize: '0.9rem', fontWeight: 500 }}>
        {state.charAt(0).toUpperCase() + state.slice(1)}
      </span>
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.6; transform: scale(1.3); }
        }
      `}</style>
    </div>
  )
}

function MouthShape({ openness, roundedness }: { openness: number; roundedness: number }) {
  // Compute mouth dimensions based on openness and roundedness
  const cx = 100
  const cy = 80
  const baseWidth = 60
  const maxHeight = 50

  // Width narrows with roundedness, widens with spread (low roundedness)
  const width = baseWidth * (1 - roundedness * 0.4)
  // Height increases with openness
  const height = maxHeight * openness

  // Compute the SVG path for an elliptical mouth
  const lipThickness = 4

  if (openness < 0.05) {
    // Closed mouth — just a line
    return (
      <g>
        {/* Face outline */}
        <ellipse cx={cx} cy={70} rx={75} ry={65} fill="none" stroke="#3a3a5a" strokeWidth="2" />
        {/* Closed lips */}
        <line
          x1={cx - width / 2}
          y1={cy}
          x2={cx + width / 2}
          y2={cy}
          stroke="#ff6b6b"
          strokeWidth="3"
          strokeLinecap="round"
        />
      </g>
    )
  }

  return (
    <g>
      {/* Face outline */}
      <ellipse cx={cx} cy={70} rx={75} ry={65} fill="none" stroke="#3a3a5a" strokeWidth="2" />
      {/* Mouth opening (dark interior) */}
      <ellipse cx={cx} cy={cy} rx={width / 2} ry={height / 2} fill="#1a0a0a" />
      {/* Upper lip */}
      <ellipse
        cx={cx}
        cy={cy - height / 2}
        rx={width / 2 + 4}
        ry={lipThickness}
        fill="#ff6b6b"
      />
      {/* Lower lip */}
      <ellipse
        cx={cx}
        cy={cy + height / 2}
        rx={width / 2 + 2}
        ry={lipThickness + 1}
        fill="#ff5252"
      />
    </g>
  )
}

function MetricBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={styles.metricRow}>
      <span style={styles.metricLabel}>{label}</span>
      <div style={styles.metricBarBg}>
        <div
          style={{
            ...styles.metricBarFill,
            width: `${value * 100}%`,
            backgroundColor: color,
          }}
        />
      </div>
      <span style={styles.metricValue}>{(value * 100).toFixed(0)}%</span>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '24px',
    padding: '32px',
    width: '100%',
    maxWidth: '500px',
  },
  stateRow: {
    display: 'flex',
    alignItems: 'center',
  },
  visemeDisplay: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '16px',
  },
  visemeLabel: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '4px',
  },
  visemeLabelSmall: {
    fontSize: '0.75rem',
    color: '#888',
    textTransform: 'uppercase' as const,
    letterSpacing: '1px',
  },
  visemeLabelLarge: {
    fontSize: '3rem',
    fontWeight: 700,
    color: '#6a6aff',
    fontFamily: 'monospace',
  },
  visemeDescription: {
    fontSize: '0.85rem',
    color: '#aaa',
  },
  mouthSvg: {
    marginTop: '8px',
  },
  metrics: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    width: '100%',
    maxWidth: '300px',
  },
  metricRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  metricLabel: {
    fontSize: '0.8rem',
    color: '#888',
    width: '90px',
  },
  metricBarBg: {
    flex: 1,
    height: '6px',
    borderRadius: '3px',
    backgroundColor: '#2a2a4a',
    overflow: 'hidden',
  },
  metricBarFill: {
    height: '100%',
    borderRadius: '3px',
    transition: 'width 0.1s ease-out',
  },
  metricValue: {
    fontSize: '0.75rem',
    color: '#aaa',
    width: '36px',
    textAlign: 'right' as const,
  },
  timeline: {
    width: '100%',
    maxWidth: '400px',
  },
  timelineLabel: {
    fontSize: '0.75rem',
    color: '#888',
    textTransform: 'uppercase' as const,
    letterSpacing: '1px',
    marginBottom: '8px',
    display: 'block',
  },
  timelineTrack: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: '4px',
  },
  timelineItem: {
    padding: '2px 6px',
    borderRadius: '4px',
    fontSize: '0.7rem',
    fontFamily: 'monospace',
    color: '#ddd',
  },
}
