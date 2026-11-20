---
name: content-to-audio
description: Set up, run, customize, debug, and clean up the content-to-audio samples in text-to-speech/use-cases/content-to-audio — a two-speaker podcast generator (Amazon Bedrock writes a host/co-host script, Amazon Polly voices each speaker, output joined into one MP3) and the experimental Grounded Podcast Studio (web research, claim extraction, Bedrock Knowledge Base, fact-check report, browser UI, DynamoDB/S3/AgentCore resources). Use when asked to generate a podcast or multi-voice audio from a topic or document, pick between these samples, change models/voices/styles, troubleshoot Bedrock access or Polly voice errors, or build a similar multi-speaker narration workflow.
---

# Content to audio

There are two samples that turn a topic into a two-speaker podcast episode.
The project lives at `text-to-speech/use-cases/content-to-audio/` (paths below
are relative to the `text-to-speech` folder). Each sample's `README.md` is the
authority for its commands. Read it before you run or change anything.

## 1. Choose the sample

| Customer wants | Sample | Creates AWS resources? |
| --- | --- | --- |
| A focused, local example: script generation + multi-voice Polly synthesis | `two-speaker-podcast/` | **No** — only Bedrock and Polly API calls |
| Source-grounded content: web research, traceable claims, style-guide retrieval, fact-check report, browser UI, run history | `grounded-podcast-studio/` (**experimental**) | **Yes** — IAM roles, DynamoDB table, S3 buckets, S3 Vectors index, Bedrock Knowledge Base, AgentCore Gateway with Web Search |

Start with `two-speaker-podcast/` unless the user specifically needs grounding.
The studio is a separate solution, not a required next step. Its fact-check
report is informational only: it **doesn't** revise or block unsupported
claims before synthesis. Make sure users know that before they rely on its
output.

## 2. Shared prerequisites

- Python 3.10+ (the READMEs use 3.12), with a virtual environment inside the
  selected sample folder.
- AWS credentials from the default chain (SSO/profile/role/env). Both samples
  accept a named profile. Never write keys into files.
- **Bedrock model access** for the inference profiles the sample uses. These
  are `global.` cross-Region profiles listed in each sample's `config.py` /
  `settings.py` and README. Missing access shows up as `AccessDeniedException`.
- **Region:** Polly synthesis is pinned to `us-east-1` for generative voices.
  `two-speaker-podcast/config.py` and `grounded-podcast-studio/polly_audio.py`
  (`POLLY_REGION`) set this.

## 3. Safety gates

- **Billing:** each episode bills Bedrock tokens (several model calls in the
  studio) and Polly characters for every dialogue turn. The two-speaker
  wizard prints token and character usage at the end.
- **Provisioning (studio only):** `python setup_resources.py` creates the
  resources listed above and writes `./.env`. Before running it, state the
  account, Region, and resource list, and get explicit confirmation. Mention
  `--skip-kb` if the user doesn't need reference-material grounding; it
  provisions fewer resources.
- **Teardown (studio only):** `cleanup_resources.py` is a dry run by default.
  Run it without `--yes` first and show the plan. Run it with `--yes` only
  after the user approves. It targets resources derived from `--prefix`
  (default `polly-podcast`). Local `.env` and `_audio/` files stay and need
  deleting by hand.
- **Data:** topics, research results, and scripts go to Bedrock and Polly.
  The studio stores claims and run artifacts in DynamoDB until teardown.

## 4. Sample gotchas

**`two-speaker-podcast/`**

- Run `python wizard.py` (add `--profile <name>` if needed). It asks for the
  topic, model, style, voices, and output file name.
- The script parser requires exactly **four alternating `host`/`cohost`
  turns**. Changing the turn count or number of speakers means updating the
  prompt (`podcast_script.build_prompt()`), voice selection, and the synthesis
  mapping together.
- Styles map to engines. *Conversational* uses `generative` with plain text and
  the live `DescribeVoices` roster. *Newscaster* uses `neural` with newscaster
  SSML, limited to Amy, Joanna, Matthew, and Lupe (the newscaster capability
  isn't reported by `DescribeVoices`).
- Tests are in `tests/`.

**`grounded-podcast-studio/`**

- Run it with the virtual environment's interpreter:
  `python -m uvicorn server:app --reload`. A bare `uvicorn` may resolve to a
  system install without the dependencies. Then open
  <http://localhost:8000>.
- `AGENT_REGION` (in `.env`) can differ from the Polly Region if AgentCore Web
  Search or S3 Vectors isn't available in `us-east-1`. Re-run setup after
  changing it.
- Re-running setup keeps an existing Knowledge Base and its original embedding
  model. To change the embedding model, the user has to tear down and
  re-provision it on purpose.
- The Gateway uses IAM (SigV4) inbound auth. If the account requires JWT,
  create the Gateway in the console and set `GATEWAY_URL` in `.env` by hand.
- To smoke-test one stage: `python -m agents.research "<topic>"`.

## 5. Building your own multi-speaker narration

- Ask the LLM for **structured output** (speaker + text per turn) and
  validate it before synthesis. Never send unparsed model output to Polly.
- Synthesize one Polly request per turn with that speaker's voice, then
  concatenate the segments in order. MP3 segments join cleanly. Use the same
  engine, format, and sample rate for all speakers.
- Fetch the voice roster from `DescribeVoices` at runtime instead of
  hard-coding it, and check that each voice supports the chosen engine.
- If the model writes SSML, filter it to the engine's allowed tags (see the
  `amazon-polly` skill). Newscaster style is neural-only and works only for
  certain voices.
- For long scripts, think about async synthesis to S3, and cache audio per
  turn so editing one line doesn't re-bill the whole episode.
