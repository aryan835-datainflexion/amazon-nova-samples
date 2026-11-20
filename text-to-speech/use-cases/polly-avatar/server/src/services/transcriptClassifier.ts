/**
 * Pure, stateless classification of user transcripts for turn-taking.
 *
 * These helpers decide, from the text alone, whether an utterance is:
 *  - pure filler/backchannel that deserves no response ({@link isFiller}), or
 *  - a short imperative that should interrupt the avatar ({@link isCommand}), or
 *  - substantial enough to count as a barge-in ({@link isSubstantiveBargeIn}).
 *
 * Session state and timing (grace window, confidence) live in the session
 * handler; this module only looks at the words.
 */

/** Minimum words for a non-command utterance to count as a real barge-in. */
export const BARGE_IN_MIN_WORDS = 2

// Short, unambiguous imperatives that count as a real interruption on their own,
// even though they're only one word — interrupting is exactly their purpose.
const COMMAND_WORDS = new Set([
  'stop', 'wait', 'no', 'cancel', 'quiet', 'enough', 'pause', 'hold', 'hey',
  'shush', 'shh',
])

// Pure backchannel / filler tokens. An utterance made ENTIRELY of these carries
// no intent, so the avatar should stay silent rather than respond to it.
const FILLER_WORDS = new Set([
  'hmm', 'hm', 'mm', 'mmm', 'mhm', 'mmhm', 'mmhmm', 'uh', 'uhh', 'um', 'umm',
  'er', 'err', 'ah', 'ahh', 'oh', 'ohh', 'huh', 'eh', 'yeah', 'yep', 'yup',
  'ok', 'okay', 'right', 'sure', 'uhhuh', 'uhuh', 'aha', 'hmmm', 'so', 'well',
  'like',
])

/** Whitespace-separated word tokens (Unicode-aware — keeps non-Latin scripts). */
function words(text: string): string[] {
  return text.trim().split(/\s+/).filter(Boolean)
}

/** Lowercased Latin-letter tokens, for matching the English filler/command lists. */
function latinTokens(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z]+/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
}

/**
 * True if the transcript is nothing but English filler/backchannel (e.g. "hmm",
 * "uh huh", "mm-hmm", "yeah ok"). Such utterances get no spoken response.
 *
 * The filler set is English-only, so this deliberately looks at Latin tokens.
 * Crucially, text with NO Latin letters (e.g. Hindi in Devanagari, or any
 * non-Latin script) is NOT filler — it's real speech that must reach the agent.
 * A single real word ("stop", "why") is likewise not filler.
 */
export function isFiller(text: string): boolean {
  // Any non-ASCII letter (e.g. Devanagari, Cyrillic, accented Latin) means the
  // text is real speech in another script — not English filler. This keeps
  // punctuation and hyphenated fillers like "mm-hmm" on the filler path.
  if (/[^\x00-\x7f]/.test(text)) return false

  const tokens = latinTokens(text)
  if (tokens.length === 0) return true // empty / punctuation only
  return tokens.every((t) => FILLER_WORDS.has(t))
}

/**
 * True for a short English imperative that should interrupt the avatar —
 * "stop", "stop it", "no wait", "hold on". A short phrase (≤3 words) starting
 * with a command word qualifies. (Command matching is English-only; non-Latin
 * interruptions still barge in via the multi-word rule below.)
 */
export function isCommand(text: string): boolean {
  const tokens = latinTokens(text)
  return tokens.length > 0 && tokens.length <= 3 && COMMAND_WORDS.has(tokens[0])
}

/**
 * True if the transcript is substantial enough to be treated as a barge-in:
 * either a short command, or at least {@link BARGE_IN_MIN_WORDS} words. Filters
 * out a single stray word from background noise. Word counting is Unicode-aware,
 * so multi-word utterances in any language/script qualify.
 */
export function isSubstantiveBargeIn(text: string): boolean {
  if (isCommand(text)) return true
  return words(text).length >= BARGE_IN_MIN_WORDS
}
