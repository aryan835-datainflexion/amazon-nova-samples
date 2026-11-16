# Skills

This section contains **agent skills**: task instructions that an AI coding
agent loads on demand to work with Amazon Polly and the samples in this
repository. They follow the open
[Agent Skills](https://agentskills.io) format, so the same files work with any
agent that supports it.

## Skill index

| Skill | Outcome | Scope |
| --- | --- | --- |
| [amazon-polly](amazon-polly/SKILL.md) | Choose the right Polly API, engine, and voice; write engine-safe SSML; manage lexicons; use speech marks; handle errors, limits, IAM, and cost | Any project that uses Polly (self-contained, portable) |
| [cascading-voice-agent](cascading-voice-agent/SKILL.md) | Pick, run, deploy, and clean up a Transcribe → Bedrock → Polly voice agent (Pipecat, LangChain, LiveKit, AgentCore) | [`use-cases/cascading-voice-agent/`](../use-cases/cascading-voice-agent/) |
| [content-to-audio](content-to-audio/SKILL.md) | Generate a two-speaker podcast; run or tear down the grounded podcast studio | [`use-cases/content-to-audio/`](../use-cases/content-to-audio/) |
| [live-speech-translator](live-speech-translator/SKILL.md) | Run and tune local Transcribe → Translate → Polly translation | [`use-cases/live-speech-translator/`](../use-cases/live-speech-translator/) |
| [polly-avatar](polly-avatar/SKILL.md) | Run, deploy, and debug a lip-synced 3D avatar driven by Polly visemes | [`use-cases/polly-avatar/`](../use-cases/polly-avatar/) |
| [reachy-voice-assistant](reachy-voice-assistant/SKILL.md) | Set up, run, and troubleshoot a Reachy Mini voice assistant | [`use-cases/reachy-voice-assistant/`](../use-cases/reachy-voice-assistant/) |

## Quick start

1. Clone this repository, change to `text-to-speech/`, and open your coding
   agent from that folder.
2. Ask for what you want in plain language. The agent matches your request to a
   skill's description and loads it automatically, for example:
   - "Run the live speech translator from English to Spanish."
   - "Deploy the Polly avatar to my AWS account."
   - "Which Polly voices support the generative engine in German?"
   - "Fix the `InvalidSsmlException` in my synthesis code."
3. If the agent doesn't pick up a skill, name it: "Use the `content-to-audio`
   skill to generate a podcast about this document."

The skills check your credentials and tell you which steps are billed. They
ask for confirmation before deploying or deleting AWS resources, so review
each step before you approve it.

## Using the skills with your coding agent

Each skill is a folder whose `SKILL.md` has YAML frontmatter (`name`,
`description`) and Markdown instructions. The `text-to-speech` folder makes
the skills discoverable in several places. All of them point to this folder:

| Location | Discovered by |
| --- | --- |
| `.claude/skills/<name>` → `skills/<name>` | Claude Code |
| `.agents/skills/<name>` → `skills/<name>` | Codex and other agents that read the open `.agents/skills` location |
| `.kiro/skills/<name>` → `skills/<name>` | Kiro |
| [`AGENTS.md`](../AGENTS.md) (`text-to-speech` root) | Agents that read `AGENTS.md` (e.g. Cursor, GitHub Copilot, Codex), and any agent you point at it |

If your agent uses another location, symlink or copy the skill folder there.
You can also tell the agent to read `skills/<name>/SKILL.md` directly.

To use `amazon-polly` in your own project, copy `skills/amazon-polly/` into
that project's skills folder. It doesn't depend on files in this repository.

> **Windows:** the discovery locations are git symlinks. Clone with
> `git config --global core.symlinks true` (this requires Developer Mode or
> admin rights), or copy the skill folders instead.

## Authoring rules

- One kebab-case folder per skill under `skills/`, matching the frontmatter
  `name`. Frontmatter has only `name` and a `description` that says what the
  skill does and when to use it.
- Keep it in one `SKILL.md` (under ~500 lines). Link to the sample `README.md`
  instead of copying it, and don't hard-code values that change often.
- Stay agent-neutral: no agent-specific tools or commands,
  `text-to-speech`-relative paths only, and state the working directory for
  commands.
- For AWS work: no credentials, least-privilege IAM, flag billed calls,
  confirm before creating or deleting resources, and include cleanup.
- Register a new skill in the table above, in [`AGENTS.md`](../AGENTS.md), and
  with a symlink from the `text-to-speech` folder:

  ```bash
  for d in .claude .agents .kiro; do ln -s ../../skills/<name> "$d/skills/<name>"; done
  ```

[Back to the project README](../README.md)
