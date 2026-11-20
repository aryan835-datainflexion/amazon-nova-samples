import { useRef, useEffect, useState, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import { useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { AnimationClipDriver } from './AnimationClipDriver'
import { animationPackPaths, type HostDefinition } from './hostCatalog'
import type { AgentState } from '../../../shared/types'

interface HostModelProps {
  host: HostDefinition
  currentViseme: string
  agentState: AgentState
  onReady?: (visemeNames: string[]) => void
}

/**
 * Renders a built-in host character and drives lip-sync via animation clips.
 * Loads the character glTF plus its body-type animation pack (lipsync + blink +
 * face idle). The lipsync.glb contains one bone-pose clip per Polly viseme.
 */
export function HostModel({ host, currentViseme, agentState, onReady }: HostModelProps) {
  const paths = useMemo(() => animationPackPaths(host.bodyType), [host.bodyType])

  const character = useGLTF(host.modelPath)
  const lipsync = useGLTF(paths.lipsync)
  const blink = useGLTF(paths.blink)

  const driverRef = useRef<AnimationClipDriver | null>(null)
  const [fit, setFit] = useState<{ scale: number; offset: [number, number, number] }>({
    scale: 1,
    offset: [0, 0, 0],
  })
  const onReadyRef = useRef(onReady)
  onReadyRef.current = onReady

  useEffect(() => {
    const root = character.scene
    if (!root) return

    // Neutralize any embedded lights and fix texture color space (same hygiene
    // as the external-model path).
    root.traverse((child) => {
      if (child instanceof THREE.Light) child.intensity = 0
      if (child instanceof THREE.Mesh) {
        const mats = Array.isArray(child.material) ? child.material : [child.material]
        for (const mat of mats) {
          const m = mat as THREE.MeshStandardMaterial
          if (m?.map) m.map.colorSpace = THREE.SRGBColorSpace
          if (m?.emissiveMap) m.emissiveMap.colorSpace = THREE.SRGBColorSpace
          if (m) m.needsUpdate = true
        }
      }
    })

    // Build viseme clip map from lipsync.glb (clips named exactly as visemes).
    const visemeClips = new Map<string, THREE.AnimationClip>()
    for (const clip of lipsync.animations ?? []) {
      visemeClips.set(clip.name, clip)
    }

    // Blink clip (triggered occasionally, not looped).
    const blinkClip = (blink.animations ?? [])[0]

    driverRef.current = new AnimationClipDriver({
      root,
      visemeClips,
      blinkClip,
    })

    onReadyRef.current?.([...visemeClips.keys()])


    // Auto-frame on the head. Sumerian characters stand ~1.7 units tall; frame
    // the upper portion for a talking-head view.
    root.updateWorldMatrix(true, true)
    const box = new THREE.Box3().setFromObject(root)
    const size = new THREE.Vector3()
    const center = new THREE.Vector3()
    box.getSize(size)
    box.getCenter(center)
    // Head is near the top of the bounding box. Target a point ~90% up.
    const headY = box.min.y + size.y * 0.9
    const maxDim = Math.max(size.x, size.y) || 1
    const scale = 1.0 / (maxDim * 0.28) // zoom toward the head region
    setFit({
      scale,
      offset: [-center.x * scale, -headY * scale, -center.z * scale],
    })

    return () => {
      driverRef.current?.dispose()
      driverRef.current = null
    }
  }, [character.scene, lipsync.animations, blink.animations, host.name])

  useFrame((state, delta) => {
    driverRef.current?.update({
      viseme: currentViseme,
      agentState,
      delta,
      elapsed: state.clock.elapsedTime,
    })
  })

  return (
    <group scale={fit.scale} position={fit.offset}>
      <primitive object={character.scene} />
    </group>
  )
}
