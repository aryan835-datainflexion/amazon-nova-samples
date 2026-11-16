---
name: polly-avatar
description: Set up, run locally, deploy to AWS (CDK), debug, extend, and tear down the Polly Avatar demo in text-to-speech/use-cases/polly-avatar — a conversational 3D avatar with real-time lip-sync driven by Amazon Polly viseme speech marks, Amazon Transcribe streaming STT, and a Strands agent on Amazon Bedrock (React/Three.js client, Node/TypeScript WebSocket server, Cognito/CloudFront/Fargate infrastructure). Use when asked to run or deploy the avatar, fix lip-sync, audio, auth, or deployment problems, change the voice/model/avatar, upload a custom glTF/GLB model, or build lip-sync from Polly visemes.
---

# Polly avatar

This is a 3D avatar that listens, replies through a Bedrock agent, and speaks
with lip-sync driven by Polly **viseme speech marks**. The project lives at
`text-to-speech/use-cases/polly-avatar/` (paths below are relative to the
`text-to-speech` folder). `README.md` and `infra/README.md` are the authority
for its commands. Read them before you run, deploy, or edit anything.

Layout: `client/` (React + Vite + Three.js), `server/` (Node + TypeScript
WebSocket server), `shared/` (types), `infra/` (AWS CDK).

## 1. Choose the mode

| Mode | What it needs | Creates AWS resources? |
| --- | --- | --- |
| **Local** (start here) | Node.js 20+, AWS credentials, Bedrock model access | No — pay-per-use Transcribe/Bedrock/Polly calls only |
| **AWS-hosted** | Above + container runtime (Finch or Docker), CDK bootstrap, permissions to create infrastructure | **Yes** — VPC + endpoints, Cognito, Fargate + ALB, S3 + CloudFront + WAF; **ongoing monthly cost** |

## 2. Local run

```bash
# terminal 1 — from use-cases/polly-avatar/server
npm install
cp ../.env.example .env        # optional overrides
AUTH_ENABLED=false npm run dev # auth is fail-closed by default

# terminal 2 — from use-cases/polly-avatar/client
npm install
npm run dev                    # http://localhost:5173
```

Smoke tests, run from `server/`: `npm run check:creds` (credentials resolve),
`npm run check:polly` (Polly audio + visemes), `npm run check:agent` (Strands
agent). Run these before debugging the UI.

Key server variables: `AWS_REGION` (default `us-east-1`), `BEDROCK_MODEL_ID`
(default `us.anthropic.claude-sonnet-4-6`), `POLLY_VOICE_ID`, `POLLY_ENGINE`
(default `neural`), `AUTH_ENABLED`, and `SESSION_STORE_DIR`.

`AUTH_ENABLED=false` is for local development only. Never disable auth on a
deployed server.

## 3. Safety gates for AWS-hosted mode

- **Deploy** (`infra/deploy.sh [email]`) creates four CloudFormation stacks
  and seeds a demo user. Before running it, state the account, Region
  (default `us-east-1`; the CloudFront WAF has to be there), and the expected
  ongoing cost. `infra/README.md` estimates about $75+/month at demo scale,
  mostly the VPC endpoints, ALB, and Fargate. Get explicit confirmation first.
  It prints a temporary demo password. Don't paste it into files or commits.
- **Destroy** (`infra/destroy.sh`) runs `cdk destroy --all --force`, which
  doesn't prompt. Confirm the account and Region with the user before running
  it. The Cognito user pool (`polly-avatar-users`) is **retained on
  purpose**. Delete it only when the user asks.
- **Don't weaken** the security setup in `infra/` while editing: the
  CloudFront-only ALB access, the origin-verify header, the WAF rate limit,
  private subnets with VPC endpoints, and the least-privilege task role.
- **Data:** mic audio goes to Transcribe, and conversation text goes to
  Bedrock and Polly. The conversation history is saved locally under
  `server/.sessions/` by default. Mention this, and delete it when cleaning up.

## 4. Gotchas

- **Visemes need a speech-mark-capable engine.** Generative and the
  bidirectional streaming API don't emit visemes. Keep `POLLY_ENGINE` set to
  `neural` (or standard/long-form), and pick a voice that supports it.
- **Two Polly calls per sentence:** one for MP3 audio and one for viseme JSON,
  using identical text, voice, and engine. Both are tagged with a
  `sentenceIndex`. Keep the two requests in sync whenever you change
  synthesis.
- **SSML allowlist:** the agent emits SSML that is safe on neural; the
  allowlist is in `server/src/services/ssml.ts` and falls back to plain text.
  Don't add `emphasis`, prosody `pitch`, or `amazon:effect`; they fail or are
  ignored on neural.
- **Custom avatars** need morph targets named for Polly visemes. The mapping is
  in `client/src/utils/visemeMap.ts`. Use the in-app "Manual viseme test" panel
  to inspect a model.
- **Image architecture:** the server image is pinned to `linux/arm64` (Fargate
  on Graviton). A platform mismatch crashes the task with exit code 255 and no
  logs.
- **Languages list:** `npm run gen:languages` regenerates
  `client/public/languages.json` from Polly. Run it in the Region you deploy to.

## 5. Building lip-sync from Polly visemes

- Request `SpeechMarkTypes=["viseme"]` (and `sentence` or `word` if you want
  highlighting) with `OutputFormat="json"`. Make a second call for the audio
  with the same parameters.
- Synthesize per sentence while the LLM is still streaming, so speech starts
  early. Queue the sentences and play them in order.
- Drive mouth shapes from the audio playback clock (Web Audio `currentTime`),
  not from timers. Blend between visemes to avoid snapping.
- Put the animation behind an interface (this sample uses `VisemeDriver` with
  morph-target and animation-clip drivers), so different avatar rigs can
  reuse the same viseme stream.
- See the `amazon-polly` skill for speech-mark rules and the SSML engine
  matrix.
