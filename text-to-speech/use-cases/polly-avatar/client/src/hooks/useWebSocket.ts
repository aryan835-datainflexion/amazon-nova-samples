import { useRef, useState, useCallback, useEffect } from 'react'
import type { ClientMessage, ServerMessage, AgentState, VisemeEvent } from '../../../shared/types'
import { getWebSocketUrl } from '../config'

interface WebSocketHookState {
  isConnected: boolean
  agentState: AgentState
  partialTranscript: string
  finalTranscript: string
  llmText: string
  // The reply split into sentences (from llm_done). Indices line up with the
  // sentenceIndex on audio_response, so the UI can highlight the spoken one.
  llmSentences: string[]
  error: string | null
}

interface WebSocketHookActions {
  connect: (token?: string) => void
  startSession: (
    language?: string,
    voiceId?: string,
    avatarName?: string,
    sessionId?: string
  ) => void
  stopSession: () => void
  sendAudioChunk: (base64Audio: string) => void
  interrupt: () => void
  setVoice: (voiceId: string) => void
  setLanguage: (language: string) => void
  revoice: (fromIndex: number) => void
  setAvatar: (name: string) => void
  playbackFinished: (turn: number) => void
  resetConversation: () => void
}

interface WebSocketHookCallbacks {
  onAudioResponse?: (
    audio: string,
    visemes: VisemeEvent[],
    sentenceIndex: number,
    turn: number
  ) => void
  onInterrupted?: (turn: number) => void
}

export function useWebSocket(
  callbacks: WebSocketHookCallbacks = {}
): WebSocketHookState & WebSocketHookActions {
  const wsRef = useRef<WebSocket | null>(null)
  const callbacksRef = useRef(callbacks)
  callbacksRef.current = callbacks

  const [state, setState] = useState<WebSocketHookState>({
    isConnected: false,
    agentState: 'idle',
    partialTranscript: '',
    finalTranscript: '',
    llmText: '',
    llmSentences: [],
    error: null,
  })

  const send = useCallback((message: ClientMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message))
    }
  }, [])

  const handleMessage = useCallback((event: MessageEvent) => {
    const message: ServerMessage = JSON.parse(event.data)

    switch (message.type) {
      case 'session_started':
        setState((s) => ({ ...s, error: null }))
        break
      case 'state_change':
        setState((s) => ({
          ...s,
          agentState: message.state,
          // Clear partial transcript when moving to thinking
          partialTranscript: message.state === 'thinking' ? '' : s.partialTranscript,
          // Clear LLM text + sentences when a new turn starts.
          llmText: message.state === 'thinking' ? '' : s.llmText,
          llmSentences: message.state === 'thinking' ? [] : s.llmSentences,
        }))
        break
      case 'transcript_partial':
        setState((s) => ({ ...s, partialTranscript: message.text }))
        break
      case 'transcript_final':
        setState((s) => ({ ...s, finalTranscript: message.text, partialTranscript: '' }))
        break
      case 'llm_chunk':
        setState((s) => ({ ...s, llmText: s.llmText + message.text }))
        break
      case 'llm_done':
        setState((s) => ({ ...s, llmText: message.fullText, llmSentences: message.sentences }))
        break
      case 'audio_response':
        callbacksRef.current.onAudioResponse?.(
          message.audio,
          message.visemes,
          message.sentenceIndex,
          message.turn
        )
        break
      case 'response_done':
        // Playback finishes naturally as the audio queue drains; nothing to do.
        break
      case 'interrupted':
        callbacksRef.current.onInterrupted?.(message.turn)
        break
      case 'error':
        setState((s) => ({ ...s, error: message.message }))
        break
    }
  }, [])

  const connect = useCallback((token?: string) => {
    if (wsRef.current) return

    const wsUrl = getWebSocketUrl(token)
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      if (wsRef.current !== ws) return // superseded
      setState((s) => ({ ...s, isConnected: true, error: null }))
    }

    ws.onclose = () => {
      if (wsRef.current !== ws) return // torn-down / superseded socket
      setState((s) => ({ ...s, isConnected: false, agentState: 'idle' }))
      wsRef.current = null
    }

    ws.onerror = () => {
      // Only report a real failure for the active socket that never opened.
      // (StrictMode dev double-mount closes the first socket, which we detach
      // in cleanup so its error can't reach here.)
      if (wsRef.current !== ws) return
      if (ws.readyState === WebSocket.OPEN) return
      setState((s) => ({ ...s, error: 'WebSocket connection failed' }))
    }

    ws.onmessage = handleMessage
    wsRef.current = ws
  }, [handleMessage])

  // Detach handlers before closing so a torn-down socket can't fire a
  // false error/close into React state.
  const closeSocket = useCallback((ws: WebSocket | null) => {
    if (!ws) return
    ws.onopen = null
    ws.onclose = null
    ws.onerror = null
    ws.onmessage = null
    try {
      ws.close()
    } catch {
      /* ignore */
    }
  }, [])

  const startSession = useCallback(
    (language?: string, voiceId?: string, avatarName?: string, sessionId?: string) => {
      send({ type: 'start_session', config: { language, voiceId, avatarName, sessionId } })
    },
    [send]
  )

  const stopSession = useCallback(() => {
    send({ type: 'stop_session' })
  }, [send])

  const sendAudioChunk = useCallback((base64Audio: string) => {
    send({ type: 'audio_chunk', data: base64Audio })
  }, [send])

  const interrupt = useCallback(() => {
    send({ type: 'interrupt' })
  }, [send])

  const setVoice = useCallback((voiceId: string) => {
    send({ type: 'set_voice', voiceId })
  }, [send])

  const setLanguage = useCallback((language: string) => {
    send({ type: 'set_language', language })
  }, [send])

  const revoice = useCallback((fromIndex: number) => {
    send({ type: 'revoice', fromIndex })
  }, [send])

  const setAvatar = useCallback((name: string) => {
    send({ type: 'set_avatar', name })
  }, [send])

  const playbackFinished = useCallback((turn: number) => {
    send({ type: 'playback_finished', turn })
  }, [send])

  // Clears the transcript/reply state shown in the conversation panel. Used when
  // starting a new conversation so a previous session's messages don't linger.
  const resetConversation = useCallback(() => {
    setState((s) => ({
      ...s,
      partialTranscript: '',
      finalTranscript: '',
      llmText: '',
      llmSentences: [],
      error: null,
    }))
  }, [])

  useEffect(() => {
    return () => {
      closeSocket(wsRef.current)
      wsRef.current = null
    }
  }, [closeSocket])

  return {
    ...state,
    connect,
    startSession,
    stopSession,
    sendAudioChunk,
    interrupt,
    setVoice,
    setLanguage,
    revoice,
    setAvatar,
    playbackFinished,
    resetConversation,
  }
}
