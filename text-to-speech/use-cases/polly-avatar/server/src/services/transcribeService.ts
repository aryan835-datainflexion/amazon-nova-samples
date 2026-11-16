import {
  TranscribeStreamingClient,
  StartStreamTranscriptionCommand,
  AudioStream,
  LanguageCode,
  MediaEncoding,
  Item,
} from '@aws-sdk/client-transcribe-streaming'
import { PassThrough } from 'stream'

/**
 * Averages the confidence of pronounced words in a transcript segment. Returns
 * 1 when there are no scored items (e.g. early partials), so the caller only
 * suppresses transcripts Transcribe has actually flagged as low-confidence.
 */
function averageConfidence(items: Item[] | undefined): number {
  if (!items || items.length === 0) return 1
  const scored = items.filter(
    (it) => it.Type === 'pronunciation' && typeof it.Confidence === 'number'
  )
  if (scored.length === 0) return 1
  const total = scored.reduce((sum, it) => sum + (it.Confidence ?? 0), 0)
  return total / scored.length
}

const client = new TranscribeStreamingClient({
  region: process.env.AWS_REGION || 'us-east-1',
})

interface TranscribeOptions {
  language: string
  onPartialTranscript: (text: string, confidence: number) => void
  onFinalTranscript: (text: string, confidence: number) => void
  onError: (error: Error) => void
}

interface TranscribeHandle {
  write: (audioChunk: Buffer) => void
  close: () => void
}

export function startTranscription(options: TranscribeOptions): TranscribeHandle {
  const audioStream = new PassThrough()
  let isClosed = false

  // Create the async iterable for audio input
  async function* audioGenerator(): AsyncGenerator<AudioStream> {
    const chunks: Buffer[] = []
    let resolve: (() => void) | null = null
    let done = false

    audioStream.on('data', (chunk: Buffer) => {
      chunks.push(chunk)
      if (resolve) {
        resolve()
        resolve = null
      }
    })

    audioStream.on('end', () => {
      done = true
      if (resolve) {
        resolve()
        resolve = null
      }
    })

    while (!done) {
      if (chunks.length === 0) {
        await new Promise<void>((r) => { resolve = r })
      }
      while (chunks.length > 0) {
        const chunk = chunks.shift()!
        yield { AudioEvent: { AudioChunk: chunk } }
      }
    }
  }

  // Start the transcription
  const command = new StartStreamTranscriptionCommand({
    LanguageCode: options.language as LanguageCode,
    MediaEncoding: MediaEncoding.PCM,
    MediaSampleRateHertz: 16000,
    AudioStream: audioGenerator(),
  })

  // Process results asynchronously
  ;(async () => {
    try {
      const response = await client.send(command)

      if (!response.TranscriptResultStream) {
        options.onError(new Error('No transcript result stream'))
        return
      }

      for await (const event of response.TranscriptResultStream) {
        if (event.TranscriptEvent?.Transcript?.Results) {
          for (const result of event.TranscriptEvent.Transcript.Results) {
            const alternative = result.Alternatives?.[0]
            const transcript = alternative?.Transcript
            if (!transcript) continue

            // Average the per-word confidence of pronounced items. Partials
            // often lack confidence scores (Transcribe fills them in as the
            // segment finalizes), so default to 1 when none are present to
            // avoid falsely suppressing legitimate speech.
            const confidence = averageConfidence(alternative?.Items)

            if (result.IsPartial) {
              options.onPartialTranscript(transcript, confidence)
            } else {
              options.onFinalTranscript(transcript, confidence)
            }
          }
        }
      }
    } catch (err) {
      if (!isClosed) {
        options.onError(err instanceof Error ? err : new Error(String(err)))
      }
    }
  })()

  return {
    write: (audioChunk: Buffer) => {
      if (!isClosed) {
        audioStream.write(audioChunk)
      }
    },
    close: () => {
      isClosed = true
      audioStream.end()
    },
  }
}

export function stopTranscription(handle: TranscribeHandle) {
  handle.close()
}
