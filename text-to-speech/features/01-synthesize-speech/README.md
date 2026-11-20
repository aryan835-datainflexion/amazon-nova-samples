# SynthesizeSpeech

The core Amazon Polly call. Send text (or SSML), get audio back in one
synchronous request, and write it to a file.

**API:** [`SynthesizeSpeech`](https://docs.aws.amazon.com/polly/latest/APIReference/API_SynthesizeSpeech.html)

## Setup

Complete the [shared setup](../README.md#shared-setup) from the `features/`
directory.

## Run

```bash
cd 01-synthesize-speech

# Simplest possible request (generative Tiffany, mp3)
python synthesize_speech.py

# Pick another generative voice
python synthesize_speech.py --voice Matthew -o matthew.mp3

# Different output format / sample rate
python synthesize_speech.py --format ogg_vorbis --sample-rate 24000

# SSML input
python synthesize_speech.py --text-type ssml \
    --text '<speak>Hello <break time="500ms"/> world.</speak>' \
    -o speech-ssml.mp3
```

## Options

| Flag | Default | Notes |
|---|---|---|
| `--text` | a sample sentence | The text or SSML to synthesize |
| `--voice` | `Tiffany` | Voice ID — list them with [../02-describe-voices/](../02-describe-voices/) |
| `--engine` | `generative` | `standard`, `neural`, `long-form`, or `generative` |
| `--format` | `mp3` | `mp3`, `ogg_vorbis`, or `pcm` |
| `--sample-rate` | voice default | Hz, e.g. `8000`, `16000`, `22050`, `24000` |
| `--text-type` | `text` | `text` or `ssml` (see [../03-voice-control-ssml/](../03-voice-control-ssml/)) |
| `--language-code` | — | Only needed for bilingual voices, e.g. `en-US` |
| `-o/--output` | `speech.<ext>` | Output filename |
| `-p/--profile` | default chain | AWS profile name |
| `-r/--region` | configured Region | Optional AWS Region override |

## What to know

- **Engines differ by voice and region.** Not every voice supports every
  engine, and `generative`/`long-form` voices exist in a subset of regions.
  Use [../02-describe-voices/](../02-describe-voices/) to check what's available where
  you're running.
- **Character limits.** A single request accepts up to 6,000 characters total,
  with no more than 3,000 billed characters. SSML tags do not count as billed
  characters. Longer input must use the async task API in
  [../06-async-synthesis/](../06-async-synthesis/).
- **`pcm` is raw audio** — 16-bit signed little-endian, no header. Players like
  `afplay` won't open a bare `.pcm` file; use `mp3` or `ogg_vorbis` to listen
  directly.
- **Ogg Vorbis playback** uses `ffplay`, which is included with FFmpeg. If it
  is unavailable, the script prints the macOS Homebrew installation command:
  `brew install ffmpeg`.
- **Billing.** Every run makes one billed call. There is no dry-run mode.

## Expected output

```
Synthesizing 100 characters with Tiffany (generative)...
Wrote speech.mp3  (billed characters: 100, content-type: audio/mpeg)
Play it with: afplay speech.mp3   (macOS)  |  ffplay speech.mp3
```

## Cleanup

Delete the generated audio file(s):

```bash
rm -f speech.mp3 speech.ogg speech.pcm matthew.mp3 speech-ssml.mp3
```

[Back to Features](../README.md)
