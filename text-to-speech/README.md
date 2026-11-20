# Text-to-speech with Amazon Polly

Build speech experiences with [Amazon Polly](https://aws.amazon.com/polly/) and
related AWS AI services. The samples in this folder range from a guided first
request, through focused Polly capabilities, to complete applications that use
Amazon Transcribe, Amazon Translate, Amazon Bedrock, and Amazon Bedrock
AgentCore.

> **Note:** These samples are for demonstration purposes and are not
> intended for production use.

> These samples can make billed AWS API calls. Some use cases can also deploy
> infrastructure with ongoing costs. Review the sample README before running or
> deploying it, and follow its cleanup instructions when finished.

## Choose where to start

| Goal | Start here |
| --- | --- |
| Make a first Polly request | [Getting started](getting-started/) |
| Explore a specific Polly API or capability | [Features](features/) |
| Build or evaluate a complete speech application | [Use cases](use-cases/) |
| Work with the samples using an AI coding agent | [Skills](skills/) |

## Getting started

The [guided quickstart](getting-started/) introduces the four Polly engines,
discovers compatible voices with `DescribeVoices`, validates the selected voice
and engine, synthesizes speech, and saves the resulting audio.

Use this sample first if you need help configuring AWS access, selecting a
Region, comparing engines, or troubleshooting an initial request.

## Feature samples

The [features](features/) directory contains focused Python examples with
minimal surrounding setup.

| Example | What it demonstrates | Status |
| --- | --- | --- |
| [01-synthesize-speech](features/01-synthesize-speech/) | Audio formats, sample rates, engines, and `SynthesizeSpeech` | Ready |
| [02-describe-voices](features/02-describe-voices/) | Voice discovery, filtering, and pagination with `DescribeVoices` | Ready |
| [03-voice-control-ssml](features/03-voice-control-ssml/) | Controlling pronunciation and delivery with SSML | Ready |
| [04-speech-marks](features/04-speech-marks/) | Sentence, word, viseme, and SSML speech marks | Ready |
| [05-lexicons](features/05-lexicons/) | Creating, listing, applying, retrieving, and deleting lexicons | Ready |
| [06-async-synthesis](features/06-async-synthesis/) | Long-form asynchronous synthesis to Amazon S3 | Ready |
| [07-bidi-streaming](features/07-bidi-streaming/) | Bidirectional streaming with `StartSpeechSynthesisStream` | Experimental Python SDK |
| [08-voice-cloning](features/08-voice-cloning/) | Creating, inspecting, using, and deleting a cloned voice | Ready |

Examples 01–06 and 08 require Python 3.10 or later and share the dependencies
in [`features/requirements.txt`](features/requirements.txt). Example 07
requires Python 3.12 or later and has separate setup instructions.

## Use cases

The [use-cases](use-cases/) directory contains end-to-end applications
organized around user outcomes. Each use case maintains its own dependencies,
setup, validation, deployment, and cleanup instructions.

| Use case | What it demonstrates | AWS services | Runs |
| --- | --- | --- | --- |
| [Cascading voice agent](use-cases/cascading-voice-agent/) | Interchangeable speech-to-text → LLM → text-to-speech voice-agent variants using Pipecat, LangChain, LiveKit, and AgentCore | Transcribe, Bedrock, Polly, AgentCore | Local, LiveKit, or AgentCore |
| [Content to audio](use-cases/content-to-audio/) | A two-speaker podcast generator and an experimental source-grounded podcast studio | Bedrock, Polly; optional AgentCore, DynamoDB, Amazon S3, and Knowledge Bases | Local; optional AWS resources |
| [Live speech translator](use-cases/live-speech-translator/) | Local phrase translation with microphone and speaker selection | Transcribe, Translate, Comprehend, Polly | Local |
| [Polly avatar](use-cases/polly-avatar/) | A conversational 3D avatar with real-time lip-sync driven by Polly viseme speech marks | Transcribe, Bedrock, Polly; optional Cognito, CloudFront, WAF, and Fargate | Local or AWS-hosted |
| [Reachy voice assistant](use-cases/reachy-voice-assistant/) | A real-time voice assistant for a Reachy Mini robot, simulator, or no-hardware mode | Transcribe, Bedrock, Polly | Local |

## Agent skills

The [skills](skills/) directory contains reusable instructions for AI coding
agents:

| Skill | Use it for |
| --- | --- |
| [`amazon-polly`](skills/amazon-polly/SKILL.md) | Polly API, engine, voice, SSML, lexicon, speech-mark, IAM, error-handling, and cost guidance |
| [`cascading-voice-agent`](skills/cascading-voice-agent/SKILL.md) | Running, deploying, and troubleshooting the cascading voice-agent variants |
| [`content-to-audio`](skills/content-to-audio/SKILL.md) | Generating podcasts or operating the grounded podcast studio |
| [`live-speech-translator`](skills/live-speech-translator/SKILL.md) | Running and tuning the live speech translator |
| [`polly-avatar`](skills/polly-avatar/SKILL.md) | Running, deploying, and debugging the Polly avatar |
| [`reachy-voice-assistant`](skills/reachy-voice-assistant/SKILL.md) | Setting up and troubleshooting the Reachy Mini assistant |

`skills/` is the source of truth. Discovery symlinks are provided for:

- Codex and compatible agents: `.agents/skills/`
- Claude Code: `.claude/skills/`
- Kiro: `.kiro/skills/`

For automatic discovery of these nested skills, start your coding agent from
`text-to-speech/` or one of its subdirectories. The nested
[`AGENTS.md`](AGENTS.md) supplies the shared working and safety instructions.

## Prerequisites and safety

Requirements vary by sample, but most require:

- An AWS account and a supported AWS Region
- AWS credentials configured through the standard credential chain
- Least-privilege permissions for the services used by the sample
- The Python, Node.js, browser, audio-device, or robot requirements documented
  in that sample's README

Never store credentials in source files or commit generated audio, `.env`
files, virtual environments, or caches. Polly is billed per character;
Transcribe per audio duration; Translate per character; and Bedrock per model
usage. Deployed infrastructure can incur additional charges.

There is no repository-wide build or test command for this folder. Run setup
and validation commands from the individual sample directory and follow its
README.
