import { PollyClient, DescribeVoicesCommand, Engine, Voice } from '@aws-sdk/client-polly'
import type { VoiceInfo, LanguageOption } from '../../../shared/types.js'

// Friendly names for language codes that DescribeVoices only exposes via a
// voice's AdditionalLanguageCodes (so we don't have a LanguageName for them).
const EXTRA_LANG_NAMES: Record<string, string> = {
  'hi-IN': 'Hindi',
  'en-IN': 'Indian English',
}

const client = new PollyClient({ region: process.env.AWS_REGION || 'us-east-1' })

// Amazon Transcribe streaming-supported language codes (real-time). This is the
// documented set for streaming transcription; we intersect Polly's languages
// with this so the UI only offers languages that work end-to-end (STT + TTS).
// Ref: https://docs.aws.amazon.com/transcribe/latest/dg/supported-languages.html
const TRANSCRIBE_STREAMING_LANGS = new Set<string>([
  'en-US', 'en-GB', 'en-AU', 'en-IE', 'en-IN', 'en-NZ', 'en-ZA', 'en-AB', 'en-WL',
  'es-US', 'es-ES',
  'fr-FR', 'fr-CA',
  'de-DE', 'de-CH',
  'it-IT',
  'pt-BR', 'pt-PT',
  'ja-JP',
  'ko-KR',
  'zh-CN', 'zh-TW',
  'hi-IN',
  'ar-AE', 'ar-SA',
  'nl-NL',
  'sv-SE',
  'da-DK',
  'fi-FI',
  'pl-PL',
  'ru-RU',
  'tr-TR',
  'he-IL',
  'id-ID',
  'ms-MY',
  'th-TH',
  'vi-VN',
  'nb-NO',
  'ca-ES',
  'cs-CZ',
])

/**
 * Returns languages usable end-to-end (Transcribe streaming + Polly with the
 * viseme-capable neural engine), each with its available neural voices.
 * Queried live from Polly's DescribeVoices so it reflects the account/region.
 */
export async function getSupportedLanguages(): Promise<LanguageOption[]> {
  // Page through all Polly voices.
  const voices: VoiceInfo[] = []
  let nextToken: string | undefined
  do {
    const resp = await client.send(new DescribeVoicesCommand({ NextToken: nextToken }))
    for (const v of resp.Voices ?? []) {
      const engines = (v.SupportedEngines ?? []) as string[]
      // Visemes require neural / long-form / standard — NOT generative. Require
      // neural specifically (best quality with viseme support).
      if (!engines.includes(Engine.NEURAL)) continue
      if (!v.Id) continue

      // A voice can speak its primary language plus any AdditionalLanguageCodes
      // (bilingual voices like Kajal: en-IN + hi-IN). Emit an entry per language
      // so, e.g., Hindi surfaces even though Kajal's primary is en-IN.
      const langCodes: string[] = [
        v.LanguageCode,
        ...(v.AdditionalLanguageCodes ?? []),
      ].filter((c): c is NonNullable<typeof c> => !!c)
      for (const code of langCodes) {
        if (!TRANSCRIBE_STREAMING_LANGS.has(code)) continue
        voices.push({
          id: v.Id,
          name: v.Name ?? v.Id,
          gender: v.Gender ?? '',
          languageCode: code,
          languageName: languageNameFor(code, v),
          engines,
        })
      }
    }
    nextToken = resp.NextToken
  } while (nextToken)

  // Group by language.
  const byLang = new Map<string, LanguageOption>()
  for (const v of voices) {
    let opt = byLang.get(v.languageCode)
    if (!opt) {
      opt = { code: v.languageCode, name: v.languageName, voices: [] }
      byLang.set(v.languageCode, opt)
    }
    opt.voices.push(v)
  }

  // Sort languages by name, voices by name.
  const langs = Array.from(byLang.values())
  langs.sort((a, b) => a.name.localeCompare(b.name))
  for (const l of langs) l.voices.sort((a, b) => a.name.localeCompare(b.name))
  return langs
}

/** Resolve a display name for a language code. For a voice's primary language
 * DescribeVoices gives us LanguageName; for additional (bilingual) codes it
 * doesn't, so fall back to a known-names table, then the code itself. */
function languageNameFor(code: string, voice: Voice): string {
  if (code === voice.LanguageCode && voice.LanguageName) return voice.LanguageName
  return EXTRA_LANG_NAMES[code] ?? code
}
