import { Suspense, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { HostModel } from '../avatar/HostModel'
import { getHost } from '../avatar/hostCatalog'
import type { PollyViseme, AgentState } from '../../../shared/types'

const ALL_VISEMES: PollyViseme[] = [
  'p', 't', 'S', 'T', 'f', 'k', 'i', 'r', 's', 'u', '@', 'a', 'e', 'o', 'E', 'O', 'sil',
]

interface AvatarCanvasProps {
  currentViseme: string
  agentState?: AgentState
  /** Which built-in host to render (animation-clip lip-sync). */
  hostId?: string | null
}

/**
 * Public entry point. Keys the whole scene on the selected host so that every
 * host switch fully remounts the canvas — no per-host state (framing, detected
 * clips) can leak from one host into the next. This is the simplest,
 * race-free way to "load fresh every time".
 */
export function AvatarCanvas(props: AvatarCanvasProps) {
  const { hostId = null } = props
  const modelKey = hostId ? `host:${hostId}` : 'none'
  return <AvatarScene key={modelKey} {...props} />
}

function AvatarScene({ currentViseme, agentState = 'idle', hostId = null }: AvatarCanvasProps) {
  const host = hostId ? getHost(hostId) : undefined
  // Manual test override: when set, forces the model into that viseme so you
  // can verify individual clips without holding a conversation.
  const [overrideViseme, setOverrideViseme] = useState<string | null>(null)
  const [testMode, setTestMode] = useState(false)

  if (!host) {
    return (
      <div style={styles.placeholder}>
        <div style={styles.placeholderContent}>
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#555" strokeWidth="1.5">
            <circle cx="12" cy="8" r="4" />
            <path d="M4 20c0-4 4-7 8-7s8 3 8 7" />
          </svg>
          <p style={styles.placeholderText}>No avatar selected</p>
          <p style={styles.placeholderHint}>Pick a built-in host to get started.</p>
        </div>
      </div>
    )
  }

  const effectiveViseme = testMode && overrideViseme ? overrideViseme : currentViseme

  return (
    <div style={styles.canvasContainer}>
      <Canvas
        camera={{ position: [0, 0, 1.8], fov: 30 }}
        style={{ background: '#1a1a2e' }}
        gl={{
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.0,
          outputColorSpace: THREE.SRGBColorSpace,
        }}
      >
        <Suspense fallback={null}>
          <ambientLight intensity={0.6} />
          <directionalLight position={[5, 5, 5]} intensity={2} castShadow />
          <directionalLight position={[-5, 2, 2]} intensity={0.6} />
          <HostModel host={host} currentViseme={effectiveViseme} agentState={agentState} />
        </Suspense>
        {/* Hemisphere light gives a simple, dependency-free ambient fill so
            physical materials aren't reliant on a CDN-loaded HDR environment. */}
        <hemisphereLight args={['#ffffff', '#404050', 1.0]} />
        <OrbitControls
          enablePan={true}
          minDistance={0.8}
          maxDistance={6}
          target={[0, 0, 0]}
        />
      </Canvas>

      {/* Compact toggle to open the tester — stays out of the way. */}
      {!testMode && (
        <button
          style={styles.testerToggleButton}
          onClick={() => setTestMode(true)}
        >
          Manual viseme test
        </button>
      )}

      {/* Right-docked tester panel (only covers a slim strip on the right). */}
      {testMode && (
        <div style={styles.testerSidePanel}>
          <div style={styles.testerSideHeader}>
            <span>Manual Viseme Test</span>
            <button
              style={styles.testerCloseButton}
              onClick={() => {
                setTestMode(false)
                setOverrideViseme(null)
              }}
              title="Close"
            >
              ×
            </button>
          </div>

          <div style={styles.testerSideBody}>
            <div style={styles.detectedLabel}>Click a viseme to force the pose</div>
            <div style={styles.visemeButtons}>
              {ALL_VISEMES.map((v) => {
                const active = overrideViseme === v
                return (
                  <button
                    key={v}
                    onClick={() => setOverrideViseme(overrideViseme === v ? null : v)}
                    title={`→ ${v}`}
                    style={{
                      ...styles.visemeButton,
                      ...(active ? styles.visemeButtonActive : {}),
                    }}
                  >
                    {v}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  canvasContainer: {
    width: '100%',
    height: '100%',
    position: 'relative' as const,
  },
  testerToggleButton: {
    position: 'absolute' as const,
    left: '12px',
    bottom: '12px',
    background: 'rgba(20, 20, 40, 0.85)',
    border: '1px solid #4a4a6a',
    borderRadius: '6px',
    padding: '6px 12px',
    color: '#ccc',
    fontSize: '0.8rem',
    cursor: 'pointer',
    backdropFilter: 'blur(4px)',
  },
  testerSidePanel: {
    position: 'absolute' as const,
    right: '0',
    top: '0',
    bottom: '0',
    width: '260px',
    background: 'rgba(18, 18, 34, 0.95)',
    borderLeft: '1px solid #2a2a4a',
    display: 'flex',
    flexDirection: 'column' as const,
    backdropFilter: 'blur(6px)',
  },
  testerSideHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 14px',
    borderBottom: '1px solid #2a2a4a',
    fontSize: '0.85rem',
    fontWeight: 600,
    color: '#e0e0ff',
  },
  testerCloseButton: {
    background: 'transparent',
    border: 'none',
    color: '#aaa',
    fontSize: '1.2rem',
    lineHeight: 1,
    cursor: 'pointer',
    padding: '0 4px',
  },
  testerSideBody: {
    padding: '12px 14px',
    overflowY: 'auto' as const,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '14px',
  },
  visemeButtons: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: '4px',
    marginBottom: '8px',
  },
  visemeButton: {
    minWidth: '28px',
    padding: '4px 6px',
    borderRadius: '4px',
    border: '1px solid #4a4a6a',
    background: '#2a2a4a',
    color: '#ddd',
    fontFamily: 'monospace',
    fontSize: '0.8rem',
    cursor: 'pointer',
  },
  visemeButtonActive: {
    background: '#6a6aff',
    borderColor: '#8a8aff',
    color: '#fff',
  },
  detectedLabel: {
    fontSize: '0.7rem',
    color: '#888',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
  },
  placeholder: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '100%',
    height: '100%',
  },
  placeholderContent: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '12px',
  },
  placeholderText: {
    fontSize: '1rem',
    color: '#666',
  },
  placeholderHint: {
    fontSize: '0.8rem',
    color: '#555',
    textAlign: 'center' as const,
    maxWidth: '250px',
  },
}
