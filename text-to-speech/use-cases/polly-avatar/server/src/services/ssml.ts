/**
 * Turns a model-produced sentence into SSML that is safe to send to Amazon
 * Polly's NEURAL engine.
 *
 * The model is asked to lightly mark up its replies (pauses, pace, tone), but
 * its output is untrusted: a malformed or unsupported tag makes Polly reject
 * the whole request, which would silence a sentence. So we validate strictly
 * against an allowlist of neural-safe tags and, if anything looks wrong, fall
 * back to speaking the text plainly (tags stripped, entities escaped).
 *
 * Neural engine does NOT support the standard-engine-only effects
 * (<amazon:effect name="whispered">, <amazon:breath>, vocal-tract changes, etc.),
 * so those are deliberately excluded — using them would throw or be ignored.
 * Ref: Amazon Polly "Supported SSML tags" (neural vs standard).
 */

// Tags the neural engine supports and we allow the model to use. Values are the
// attributes permitted on each tag; anything else is treated as invalid.
// NOTE: verified against the live neural engine. Neural does NOT support
// <emphasis> or prosody `pitch` (both throw "Unsupported Neural feature"), so
// they are intentionally omitted.
const ALLOWED_TAGS: Record<string, ReadonlySet<string>> = {
  speak: new Set<string>(),
  break: new Set(['time', 'strength']),
  prosody: new Set(['rate', 'volume']),
  'say-as': new Set(['interpret-as', 'format']),
  p: new Set<string>(),
  s: new Set<string>(),
  w: new Set(['role']),
  sub: new Set(['alias']),
}

const TAG_RE = /<\/?([a-z:-]+)((?:\s+[a-z-]+\s*=\s*"[^"]*")*)\s*\/?>/gi

/** Escapes the five XML special characters for safe inclusion in SSML text. */
function escapeXml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

/** Strips all tags and escapes the remaining text — the safe fallback. */
export function toPlainText(markup: string): string {
  return escapeXml(markup.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim())
}

/**
 * Validates that `markup` uses only allowed tags/attributes and that tags are
 * balanced and properly nested. Returns true only if it is safe to send as-is.
 */
function isValidSsml(markup: string): boolean {
  const stack: string[] = []
  let match: RegExpExecArray | null
  const re = new RegExp(TAG_RE) // fresh lastIndex

  while ((match = re.exec(markup)) !== null) {
    const raw = match[0]
    const name = match[1].toLowerCase()
    const attrs = match[2] ?? ''
    const isClose = raw.startsWith('</')
    const isSelfClose = raw.endsWith('/>')

    const allowedAttrs = ALLOWED_TAGS[name]
    if (!allowedAttrs) return false // unknown/unsupported (or standard-only) tag

    if (!isClose) {
      // Validate attribute names against the tag's allowlist.
      const attrNames = [...attrs.matchAll(/([a-z-]+)\s*=/gi)].map((m) => m[1].toLowerCase())
      if (attrNames.some((a) => !allowedAttrs.has(a))) return false
    }

    if (isSelfClose) continue
    if (isClose) {
      if (stack.pop() !== name) return false // mismatched/unbalanced close
    } else {
      stack.push(name)
    }
  }

  // Text outside tags must not contain stray angle brackets, or a bare '&' that
  // isn't a valid XML entity — both make the SSML invalid.
  const withoutTags = markup.replace(TAG_RE, '')
  if (/[<>]/.test(withoutTags)) return false
  if (/&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-f]+);)/i.test(withoutTags)) return false

  return stack.length === 0
}

/**
 * Finds a safe sentence boundary in a streaming buffer that may contain SSML.
 * Returns the index just past the boundary (sentence-ending punctuation followed
 * by whitespace), but only when we are NOT inside a tag and NOT inside any open
 * element — so a split never lands in the middle of markup. Returns -1 if there
 * is no safe boundary yet.
 */
export function findSentenceBoundary(buffer: string): number {
  let depth = 0 // open element nesting depth
  for (let i = 0; i < buffer.length; i++) {
    const ch = buffer[i]
    if (ch === '<') {
      // Consume the whole tag in one step and adjust the nesting depth.
      const close = buffer.indexOf('>', i)
      if (close === -1) return -1 // tag not finished streaming yet
      const tag = buffer.slice(i, close + 1)
      // <speak> is the outer document wrapper, not a phrase span — ignore it for
      // depth so sentences inside a wrapped reply can still be split for TTS.
      const isSpeak = /^<\/?speak[\s>]/i.test(tag)
      if (!isSpeak) {
        if (!tag.startsWith('</') && !tag.endsWith('/>')) depth++
        else if (tag.startsWith('</')) depth = Math.max(0, depth - 1)
      }
      i = close
      continue
    }
    // A sentence end only counts at top level (no open element around it).
    if (depth === 0 && (ch === '.' || ch === '!' || ch === '?')) {
      const nextIsSpaceOrEnd = i + 1 >= buffer.length || /\s/.test(buffer[i + 1])
      if (nextIsSpaceOrEnd && i + 1 < buffer.length) return i + 1
    }
  }
  return -1
}

/** Strips SSML tags for display (client transcript / sentence highlight). */
export function toDisplayText(markup: string): string {
  return markup.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim()
}

/**
 * Prepares a single sentence for synthesis. Returns SSML wrapped in <speak>:
 * the model's markup if it is valid neural-safe SSML, otherwise the sentence
 * spoken as plain (escaped, tag-stripped) text. Either way the result is always
 * valid SSML, so callers can synthesize with TextType 'ssml' unconditionally.
 */
export function toSpeakableSsml(sentence: string): string {
  const trimmed = sentence.trim()

  // Unwrap an outer <speak> if the model included one; we add our own.
  const inner = trimmed.replace(/^<speak>/i, '').replace(/<\/speak>$/i, '').trim()

  const body = isValidSsml(inner) ? inner : toPlainText(inner)
  return `<speak>${body}</speak>`
}
