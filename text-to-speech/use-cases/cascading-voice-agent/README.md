# Cascading Voice Agent

Voice agents built with the **cascading** ("sandwich") pattern — separate
**Speech-to-Text → LLM → Text-to-Speech** services chained together — rather than a
single native speech-to-speech model. Cascading trades some latency for
flexibility: you can swap any component (STT, LLM, or TTS) independently.

Every variant here uses **Amazon Polly** for TTS and **Amazon Transcribe** for STT,
with an Amazon Bedrock model for reasoning.

## Variants

| Folder | Framework | Transport | Deploy target |
|--------|-----------|-----------|---------------|
| [langchain-agentcore-transcribe-polly](langchain-agentcore-transcribe-polly/) | LangChain / LangGraph | WebSocket | **Amazon Bedrock AgentCore Runtime** |
| [pipecat-agentcore-transcribe-bedrock-polly](pipecat-agentcore-transcribe-bedrock-polly/) | Pipecat | WebSocket | **Amazon Bedrock AgentCore Runtime** |
| [livekit-streaming-transcribe-bedrock-polly](livekit-streaming-transcribe-bedrock-polly/) | LiveKit Agents | WebRTC | LiveKit Cloud / self-hosted LiveKit |
| [pipecat-transcribe-bedrock-polly](pipecat-transcribe-bedrock-polly/) | Pipecat | WebRTC / Daily | Local runner / Daily / Pipecat-style container |

The Pipecat AgentCore variant is the AWS-hosted WebSocket path for the cascading
architecture. The LangChain variant remains useful when the reasoning layer is an
existing LangChain/LangGraph text agent. The LiveKit and local/Daily Pipecat
variants use their native real-time media runtimes and are included as framework
alternatives for the same Transcribe → Bedrock → Polly cascade.

## Folder Map

- `langchain-agentcore-transcribe-polly/` shows the original AgentCore-oriented
  cascading pattern with a LangChain/LangGraph reasoning layer, placeholder
  banking tools, deployment scripts, and a browser WebSocket client.
- `pipecat-agentcore-transcribe-bedrock-polly/` is the recommended AWS-hosted
  Pipecat path. It deploys a Pipecat WebSocket runtime to AgentCore and includes
  a local browser helper for signing and opening the AgentCore WebSocket.
- `livekit-streaming-transcribe-bedrock-polly/` is the LiveKit Agents version for
  LiveKit Cloud or self-hosted LiveKit. It is useful when LiveKit should own
  room media, turn handling, transcripts, and playback.
- `pipecat-transcribe-bedrock-polly/` is the lightweight Pipecat local/Daily
  runner for trying the same cascade without AgentCore deployment.

Each sample owns its own README, dependencies, and architecture image under its
folder. The generated diagram source workspace used to produce those images is
not part of the sample runtime path.

## Recommended Path

Start with
[pipecat-agentcore-transcribe-bedrock-polly](pipecat-agentcore-transcribe-bedrock-polly/)
when you want an AWS-hosted cascading voice agent. It follows the AgentCore
WebSocket pattern: a local helper signs the WebSocket URL, the browser connects
to AgentCore Runtime, and the runtime runs a Pipecat pipeline backed by Amazon
Transcribe, Amazon Bedrock, and Amazon Polly.

[Back to Use Cases](../README.md)
