/**
 * Catalog of built-in "host" characters (Amazon Sumerian Hosts). Each host is a
 * character glTF plus a body-type animation pack (lipsync/blink/idle), shared
 * across all characters of the same body type. These use the AnimationClipDriver.
 */

export type HostBodyType = 'adult_female' | 'adult_male'

// Matches Polly's DescribeVoices Gender casing so we can filter voices directly.
export type Gender = 'Female' | 'Male'

export interface HostDefinition {
  id: string
  name: string
  bodyType: HostBodyType
  gender: Gender
  /** Path to the character glTF (relative to /public). */
  modelPath: string
}

const BASE = '/hosts'

function female(id: string, name: string): HostDefinition {
  return {
    id,
    name,
    bodyType: 'adult_female',
    gender: 'Female',
    modelPath: `${BASE}/characters/adult_female/${id}/${id}.gltf`,
  }
}
function male(id: string, name: string): HostDefinition {
  return {
    id,
    name,
    bodyType: 'adult_male',
    gender: 'Male',
    modelPath: `${BASE}/characters/adult_male/${id}/${id}.gltf`,
  }
}

export const HOSTS: HostDefinition[] = [
  female('cristine', 'Cristine'),
  female('fiona', 'Fiona'),
  female('grace', 'Grace'),
  male('preston', 'Preston'),
  male('jay', 'Jay'),
  male('luke', 'Luke'),
  male('wes', 'Wes'),
]

/**
 * Animation pack paths for a body type. Only the animations the host renderer
 * actually plays are listed (lip-sync viseme clips + blink).
 */
export function animationPackPaths(bodyType: HostBodyType) {
  const dir = `${BASE}/animations/${bodyType}`
  return {
    lipsync: `${dir}/lipsync.glb`,
    blink: `${dir}/blink.glb`,
  }
}

export function getHost(id: string): HostDefinition | undefined {
  return HOSTS.find((h) => h.id === id)
}
