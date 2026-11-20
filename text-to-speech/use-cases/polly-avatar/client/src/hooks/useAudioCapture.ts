import { useRef, useState, useCallback } from 'react'

interface AudioCaptureOptions {
  onAudioChunk: (base64PCM: string) => void
  sampleRate?: number
}

export function useAudioCapture(options: AudioCaptureOptions) {
  const { onAudioChunk, sampleRate = 16000 } = options
  const [isRecording, setIsRecording] = useState(false)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const workletNodeRef = useRef<AudioWorkletNode | null>(null)
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null)

  const start = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })

      mediaStreamRef.current = stream
      const audioContext = new AudioContext({ sampleRate })
      audioContextRef.current = audioContext

      // Use ScriptProcessorNode for compatibility (AudioWorklet requires served file)
      const source = audioContext.createMediaStreamSource(stream)
      sourceRef.current = source

      const processor = audioContext.createScriptProcessor(4096, 1, 1)
      processor.onaudioprocess = (event) => {
        const inputData = event.inputBuffer.getChannelData(0)
        // Convert Float32 to PCM 16-bit
        const pcm16 = float32ToPCM16(inputData)
        const base64 = bufferToBase64(pcm16)
        onAudioChunk(base64)
      }

      source.connect(processor)
      processor.connect(audioContext.destination)

      setIsRecording(true)
    } catch (err) {
      console.error('[AudioCapture] Error starting:', err)
      throw err
    }
  }, [onAudioChunk, sampleRate])

  const stop = useCallback(() => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop())
      mediaStreamRef.current = null
    }
    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }
    sourceRef.current = null
    workletNodeRef.current = null
    setIsRecording(false)
  }, [])

  return { isRecording, start, stop }
}

function float32ToPCM16(float32Array: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(float32Array.length * 2)
  const view = new DataView(buffer)
  for (let i = 0; i < float32Array.length; i++) {
    const s = Math.max(-1, Math.min(1, float32Array[i]))
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true) // little-endian
  }
  return buffer
}

function bufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}
