# Use Cases

This section contains end-to-end examples organized around user outcomes. A use case can combine multiple Amazon Polly capabilities and other AWS services into a complete workflow.

## Example scenarios

- Accessible article narration
- Audiobook or long-form content generation
- Interactive voice response prompts
- Multilingual announcements
- Media voice-over workflows
- E-learning narration

## Use-case index

| Use case | What it demonstrates | AWS services | Status |
| --- | --- | --- | --- |
| [Content-to-audio](content-to-audio/) | Two-speaker podcast generation plus an optional source-grounded studio workflow | Bedrock, Polly; optional AgentCore, DynamoDB, S3, and Knowledge Bases | Ready / Experimental |
| [Reachy Mini voice assistant](./reachy-voice-assistant/) | Real-time voice conversation on a Reachy Mini robot using Transcribe + Bedrock + Polly via a pipecat pipeline | Transcribe, Bedrock, Polly | Ready |
| [Cascading Voice Agent](cascading-voice-agent/) | Bidirectional voice agent using the cascading STT→LLM→TTS pattern, deployed on Amazon Bedrock AgentCore | Polly, Transcribe, Bedrock (Nova 2 Lite), AgentCore, ECR/CodeBuild, IAM | Ready |
| [Live Speech Translator](live-speech-translator/) | Foundational local phrase-translation sample using Transcribe Streaming, Translate, and Polly | Transcribe, Translate, Polly | Foundational |
| [Polly avatar](polly-avatar/) | Conversational 3D avatar with real-time lip-sync driven by Polly viseme speech marks | Transcribe, Bedrock, Polly; optional Cognito, CloudFront, and Fargate hosting | Ready |

## Use-case requirements

Each use case should include:

1. The user problem and expected outcome
2. Architecture and service dependencies
3. Setup, deployment, and run instructions
4. Sample inputs and expected outputs
5. IAM, data handling, and operational considerations
6. Tests or validation steps
7. Complete cleanup instructions

For a first synthesis request, begin with [Getting Started](../getting-started/).
For isolated capabilities, see [Features](../features/).

[Back to the project README](../README.md)
