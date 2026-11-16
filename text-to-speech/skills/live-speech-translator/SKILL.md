---
name: live-speech-translator
description: Set up, run, configure, and troubleshoot the local Live Speech Translator in text-to-speech/use-cases/live-speech-translator (Amazon Transcribe Streaming -> Amazon Translate -> Amazon Polly, with microphone/speaker device selection and a preflight check). Use when asked to run or demo live speech translation, change source/target languages or the Polly voice, pick audio devices, fix feedback loops, unsupported voice/engine errors, PortAudio/sounddevice errors, or language-detection problems, or to design a similar speech-to-speech translation app on AWS.
---

# Live speech translator

This is a local sample that transcribes finished spoken phrases, translates
them, and plays the translation through Polly. The project lives at
`text-to-speech/use-cases/live-speech-translator/` (paths below are relative to
the `text-to-speech` folder). Its `README.md` is the authority for commands and
options. Read it before making changes.

The sample creates **no AWS infrastructure**, and it has no LLM, dialogue
state, or tools.

## 1. Prerequisites

- Python 3.10+, with a virtual environment inside the sample folder:
  `pip install -r requirements.txt`.
- Working microphone and speaker access. On macOS, the terminal needs
  microphone permission. `sounddevice` needs PortAudio.
- AWS credentials from the default chain (SSO/profile/role/env). Never put
  them in `config.yaml` or code.
- IAM actions: `transcribe:StartStreamTranscription`,
  `translate:TranslateText`, and `polly:SynthesizeSpeech`.
  `polly:DescribeVoices` is needed only for `--check`.
  `comprehend:DetectDominantLanguage` is needed only for the fallback that
  detects the source language automatically.

## 2. Workflow

Run everything from `use-cases/live-speech-translator/`:

1. `python app.py --check`: preflight of the local setup, audio devices, AWS
   configuration, and the voice/engine pair. Run it first, and again after any
   change to configuration.
2. `python app.py --list-devices`, then pass `--input-device` / `--output-device`
   by index or name if the defaults are wrong.
3. Before starting a live session, tell the user that Transcribe is billed per
   streamed audio minute while the app runs, plus Translate and Polly per
   character. Stop it with `Ctrl+C` when done.
4. Run, e.g. `python app.py --source auto --target en --voice Tiffany --mode si`.

Configuration defaults are in `config.yaml`, and command-line flags override
them for a single run.

## 3. Gotchas

- **Feedback loop:** in the default `si` (simultaneous interpretation) mode,
  the mic stays open during playback. Use headphones, or `--mode half-duplex`
  with open speakers; that mode sends silence to Transcribe while Polly
  plays.
- **The target language and voice must match.** When you change `--target`,
  pick a Polly voice for that language and set `--voice-language`, e.g.
  `--target es --voice Lupe --voice-language es-US --engine neural`. Check the
  pair with `--check` or `DescribeVoices` in the same Region.
- **Auto-detecting the source language:** with `--source auto`, keep
  `translator.auto_language_options` in `config.yaml` short. Fewer candidates
  make language identification faster and more accurate. Pause between phrases
  so language labels can switch.
- **Polly output is 16 kHz PCM** for direct playback. Keep the audio sample
  rate consistent if you change the playback path.

| Symptom | Fix |
| --- | --- |
| Unsupported Polly voice or engine | `--check`, then choose a compatible voice, language, and engine |
| The app translates its own playback | Headphones, or `--mode half-duplex` |
| Wrong mic or speaker | `--list-devices`, then select the devices explicitly |
| PortAudio / `sounddevice` error | Check OS audio permissions; reinstall PortAudio and `sounddevice` |
| Live transcription fails after preflight | Check Transcribe permissions, Region availability, and mic access |

## 4. Data handling

Microphone audio and transcripts are sent to AWS. Don't add code that keeps
audio or transcripts without explicit user consent.

## 5. Building your own translator

- Translate **finished** transcript segments only, not partial ones. This
  avoids flicker and re-billing.
- Put a bounded queue between transcription and translation/synthesis for
  backpressure, so a slow downstream stage can't let memory grow without limit.
- Skip translation when the detected source matches the target language.
- Choose the Polly voice from the *target* language, and fall back to another
  engine when the preferred one doesn't support that language (see the
  `amazon-polly` skill).
- For production, move the AWS calls behind a server-side role and give each
  client its own identity. Never ship AWS credentials in browser or mobile
  clients. The README's "Example Production Evolution" section shows one
  possible design (not the only one): CloudFront, Cognito, an ALB, and ECS on
  Fargate.
