import type { PollyViseme } from '../../../shared/types'

/**
 * Human-readable descriptions for each viseme (for debug view)
 */
export const VISEME_DESCRIPTIONS: Record<string, string> = {
  p: 'Lips pressed (b, m, p)',
  t: 'Tongue tip (d, n, t)',
  S: 'Wide mouth (sh, ch, j)',
  T: 'Dental (th)',
  f: 'Labiodental (f, v)',
  k: 'Velar (g, k, ng)',
  i: 'Smile (ee)',
  r: 'Rounded (r)',
  s: 'Teeth together (s, z)',
  u: 'Tight round (oo)',
  '@': 'Neutral (@)',
  a: 'Wide open (ah)',
  e: 'Slightly open (eh)',
  o: 'Rounded (oh)',
  E: 'Mid-open',
  O: 'Open rounded (ow)',
  sil: 'Silence (rest)',
}

/**
 * Mouth openness factor for each viseme (0 = closed, 1 = fully open)
 * Used for debug visualization and jaw weight calculation
 */
export const VISEME_OPENNESS: Record<string, number> = {
  p: 0.0,
  t: 0.2,
  S: 0.5,
  T: 0.3,
  f: 0.1,
  k: 0.4,
  i: 0.3,
  r: 0.3,
  s: 0.15,
  u: 0.2,
  '@': 0.35,
  a: 1.0,
  e: 0.5,
  o: 0.6,
  E: 0.7,
  O: 0.8,
  sil: 0.0,
}

/**
 * Lip roundedness for each viseme (0 = spread, 1 = fully rounded)
 */
export const VISEME_ROUNDEDNESS: Record<string, number> = {
  p: 0.0,
  t: 0.0,
  S: 0.3,
  T: 0.0,
  f: 0.0,
  k: 0.0,
  i: 0.0,
  r: 0.5,
  s: 0.0,
  u: 1.0,
  '@': 0.2,
  a: 0.0,
  e: 0.0,
  o: 0.8,
  E: 0.0,
  O: 0.7,
  sil: 0.0,
}
