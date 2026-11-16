---
name: cascading-voice-agent
description: Choose, set up, run, deploy, debug, and clean up the cascading (STT -> LLM -> TTS) voice agent samples in text-to-speech/use-cases/cascading-voice-agent — Amazon Transcribe -> Amazon Bedrock -> Amazon Polly built with Pipecat (local/Daily or on Amazon Bedrock AgentCore Runtime), LangChain/LangGraph on AgentCore, or LiveKit Agents. Use when asked to try or deploy one of these voice agents, pick between the variants, debug no audio / AccessDeniedException / WebSocket or deployment failures, change the Polly voice or Bedrock model, or build a similar voice agent with Transcribe, Bedrock, and Polly. Not for speech-to-speech models such as Nova Sonic.
---

# Cascading voice agent

There are four implementations of the same pipeline: **Amazon Transcribe
(STT) → Amazon Bedrock (LLM) → Amazon Polly (TTS)**. They differ in framework,
media transport, and where they run. The project lives at
`text-to-speech/use-cases/cascading-voice-agent/` (paths below are relative to
the `text-to-speech` folder).

Each variant's `README.md` is the authority for its commands and files. Read
the selected variant's README before you run, edit, or deploy anything. This
skill helps choose a variant and lists the safety gates and gotchas the
READMEs don't spell out.

## 1. Choose the variant

| Customer wants | Variant (folder) | Runs where | Creates AWS resources? |
| --- | --- | --- | --- |
| Quickest local try-out with Pipecat; browser WebRTC or Daily | `pipecat-transcribe-bedrock-polly/` | Local Pipecat runner | No |
| An AWS-hosted voice agent (**recommended hosted path**) | `pipecat-agentcore-transcribe-bedrock-polly/` | Amazon Bedrock AgentCore Runtime (WebSocket) | **Yes** — IAM role, AgentCore runtime, ECR image, CodeBuild |
| An existing LangChain/LangGraph text agent (tools, ReAct) to put behind voice | `langchain-agentcore-transcribe-polly/` | AgentCore Runtime, or local server | **Yes** when deployed (optional MCP Gateway) |
| LiveKit to own room media, turn handling, interruptions | `livekit-streaming-transcribe-bedrock-polly/` | LiveKit Cloud or self-hosted LiveKit | No AWS infrastructure (LiveKit account needed) |

If the user doesn't have a preference, start with the local Pipecat variant to
check credentials and model access. Then move to the Pipecat AgentCore variant
if they need hosting.

## 2. Shared prerequisites (all variants)

- **Python:** the local Pipecat variant needs 3.11+. Use 3.12 for the
  AgentCore variants; the READMEs show a Homebrew path
  (`/opt/homebrew/bin/python3.12`), but any Python 3.12 interpreter works.
  Create a separate virtual environment inside the selected variant folder.
- **AWS credentials** from the default chain (SSO/profile/role/env). Check
  with `aws sts get-caller-identity`. Never write keys into files.
- **Bedrock model access** for the configured model in the Region. The default
  is Amazon Nova 2 Lite via the `us.amazon.nova-2-lite-v1:0` inference
  profile, and `us-east-1` works. Missing access shows up as
  `AccessDeniedException` from Bedrock.
- **IAM actions** at runtime: `transcribe:StartStreamTranscription`,
  `bedrock:InvokeModel*`, `polly:SynthesizeSpeech`. Deploying to AgentCore also
  needs permissions to create IAM roles, ECR repositories, CodeBuild projects,
  and AgentCore runtimes.
- **Voice and engine:** defaults are `POLLY_ENGINE=generative`, with Tiffany
  or Joanna. Before changing them, check the pair in the target Region with
  `DescribeVoices` (see the `amazon-polly` skill).

## 3. Safety gates

- **Billing:** a live conversation bills Transcribe per audio minute, Bedrock
  per token, and Polly per character for as long as a session is open. Say so
  before starting one, and stop the process when finished.
- **Deploying:** `deployment/deploy.py` (AgentCore variants) creates an IAM
  role (`PipecatCascadingVoiceAgentRole` or `CascadingVoiceAgentRole`), builds
  and pushes an image, and launches a runtime. Before running it, state the
  account, Region, and resources it will create, and get explicit
  confirmation. Review `deployment/agent_role.json` with the user. It is a
  sample policy and should be tightened before any non-sample use.
- **Cleanup deletes without prompting.** `deployment/cleanup.py` removes the
  runtime, gateway, IAM role, and local state files immediately. Confirm the
  account and Region with the user before running it. The ECR repository and
  image may remain and need deleting by hand.
- **Data:** microphone audio goes to Transcribe and text goes to Bedrock and
  Polly. The samples don't store audio. Tell users before they speak if they
  might share personal data.
- **Placeholder tools:** the banking tools in the LangChain, LiveKit,
  and local Pipecat variants return fake data. Don't present them as real integrations.

## 4. Variant gotchas

**`pipecat-transcribe-bedrock-polly/` (local)**

- Run `python bot.py --transport webrtc` and open the URL it prints. Daily
  transport needs `DAILY_API_KEY`.
- Leave `BEDROCK_LATENCY` unset. Some model/Region pairs, including the default
  Nova 2 Lite in `us-east-1`, reject the latency-optimized setting.
- Placeholder tools are `FunctionSchema`s registered with
  `llm.register_function`. Add new tools the same way.

**`pipecat-agentcore-transcribe-bedrock-polly/` (hosted)**

- `deploy.py` writes `setup_config.json`. `./deployment/start_client.sh` reads
  that file, signs the AgentCore WebSocket URL with SigV4, and opens the
  browser client. The script needs `jq`.
- The runtime container must be ARM64 (an AgentCore requirement).
- Configuration is through environment variables only (`BEDROCK_MODEL_ID`,
  `POLLY_VOICE_ID`, `POLLY_ENGINE`, `AUDIO_*_SAMPLE_RATE`, …). Per-session
  configuration isn't implemented.
- You can test locally without deploying: run `websocket/server.py`, then
  `client/client.py --ws-url ws://localhost:8080/ws`.

**`langchain-agentcore-transcribe-polly/`**

- The AgentCore WebSocket proxy echoes messages and limits frames to about
  32 KB. The code already handles both. Keep the echo filtering and the TTS
  audio chunking when you edit `websocket/agent.py`.
- There's no barge-in, and the client mutes the mic during playback to avoid a
  TTS → STT feedback loop.
- `--with-gateway` also creates an MCP Gateway, so include it in the
  confirmation and cleanup.

**`livekit-streaming-transcribe-bedrock-polly/`**

- Needs `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET`. Keep them
  in the environment, never in code.
- `python agent.py console` is the quickest smoke test. Job metadata JSON can
  override the Region, model, voice, language, and system prompt.

## 5. Validation

For the AgentCore variants, run this from the variant folder (no AWS calls):

```bash
python3 -m py_compile websocket/*.py client/client.py deployment/*.py
bash -n deployment/start_client.sh
```

After a deploy, the `/ping` endpoint should report `Healthy`. The end-to-end
check is speaking through the client and hearing a Polly reply. For the local
variants, a successful console or WebRTC conversation is the check.

## 6. Building your own cascading agent

These lessons apply beyond the samples:

- **Latency:** stream LLM tokens and synthesize sentence by sentence. Don't
  wait for the full reply. Keep system prompts asking for short spoken
  replies; every token is spoken, adds delay, and is billed.
- **Audio format:** use Polly `pcm` at the sample rate your transport expects
  (16 kHz or 24 kHz in these samples). That avoids decoding and resampling.
- **Echo:** without acoustic echo cancellation, mute or gate the mic while
  the agent speaks. Otherwise Transcribe hears Polly and the agent answers
  itself. Barge-in needs echo cancellation, cancellation of in-flight LLM and
  TTS work, and tracking of what was actually spoken.
- **Swappability:** that's the point of the cascading pattern. Swap the
  Bedrock model or Polly voice through configuration, not code changes.
- **Voice, engine, and SSML:** see the `amazon-polly` skill.
