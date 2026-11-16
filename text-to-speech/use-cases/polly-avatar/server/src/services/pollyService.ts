import {
  PollyClient,
  SynthesizeSpeechCommand,
  Engine,
  OutputFormat,
  SpeechMarkType,
  VoiceId,
  LanguageCode,
} from '@aws-sdk/client-polly'
import type { VisemeEvent } from '../../../shared/types.js'

const client = new PollyClient({
  region: process.env.AWS_REGION || 'us-east-1',
})

const DEFAULT_VOICE_ID = process.env.POLLY_VOICE_ID || 'Matthew'
const ENGINE: Engine = (process.env.POLLY_ENGINE || 'neural') as Engine

interface SynthesisResult {
  audio: Buffer
  visemes: VisemeEvent[]
}

/**
 * Synthesizes one sentence to audio + viseme speech marks. `ssml` must be valid
 * SSML wrapped in <speak> (see ssml.toSpeakableSsml). Both Polly calls use the
 * identical SSML so the viseme timings line up with the audio.
 */
export async function synthesizeSpeechWithVisemes(
  ssml: string,
  voiceId: string = DEFAULT_VOICE_ID,
  languageCode?: string
): Promise<SynthesisResult> {
  // Polly requires two separate calls:
  // 1. Get audio
  // 2. Get viseme speech marks (returns JSON instead of audio)

  const [audioResult, visemeResult] = await Promise.all([
    synthesizeAudio(ssml, voiceId, languageCode),
    synthesizeVisemes(ssml, voiceId, languageCode),
  ])

  return {
    audio: audioResult,
    visemes: visemeResult,
  }
}

async function synthesizeAudio(
  ssml: string,
  voiceId: string,
  languageCode?: string
): Promise<Buffer> {
  const command = new SynthesizeSpeechCommand({
    Engine: ENGINE,
    OutputFormat: OutputFormat.MP3,
    SampleRate: '24000',
    Text: ssml,
    TextType: 'ssml',
    VoiceId: voiceId as VoiceId,
    // Needed for bilingual voices (e.g. Kajal) to pick hi-IN vs en-IN.
    ...(languageCode ? { LanguageCode: languageCode as LanguageCode } : {}),
  })

  const response = await client.send(command)

  if (!response.AudioStream) {
    throw new Error('No audio stream in Polly response')
  }

  // Convert the readable stream to a Buffer
  const chunks: Uint8Array[] = []
  const stream = response.AudioStream as AsyncIterable<Uint8Array>

  for await (const chunk of stream) {
    chunks.push(chunk)
  }

  return Buffer.concat(chunks)
}

async function synthesizeVisemes(
  ssml: string,
  voiceId: string,
  languageCode?: string
): Promise<VisemeEvent[]> {
  const command = new SynthesizeSpeechCommand({
    Engine: ENGINE,
    OutputFormat: OutputFormat.JSON,
    SampleRate: '24000',
    Text: ssml,
    TextType: 'ssml',
    VoiceId: voiceId as VoiceId,
    ...(languageCode ? { LanguageCode: languageCode as LanguageCode } : {}),
    SpeechMarkTypes: [SpeechMarkType.VISEME],
  })

  const response = await client.send(command)

  if (!response.AudioStream) {
    throw new Error('No speech marks in Polly response')
  }

  // Parse the line-delimited JSON response
  const chunks: Uint8Array[] = []
  const stream = response.AudioStream as AsyncIterable<Uint8Array>

  for await (const chunk of stream) {
    chunks.push(chunk)
  }

  const jsonText = Buffer.concat(chunks).toString('utf-8')
  const lines = jsonText.trim().split('\n')
  const visemes: VisemeEvent[] = []

  for (const line of lines) {
    if (!line.trim()) continue
    try {
      const mark = JSON.parse(line)
      if (mark.type === 'viseme') {
        visemes.push({
          time: mark.time,
          type: 'viseme',
          value: mark.value,
        })
      }
    } catch {
      // Skip malformed lines
    }
  }

  return visemes
}
