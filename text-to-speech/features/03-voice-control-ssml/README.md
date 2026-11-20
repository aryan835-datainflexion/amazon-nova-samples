# Voice Control with SSML

Use Speech Synthesis Markup Language to control pauses, emphasis, pitch and
rate, pronunciation, and domain styles. Same `SynthesizeSpeech` call as
[../01-synthesize-speech/](../01-synthesize-speech/), but with
`TextType=ssml`.

**API:** `SynthesizeSpeech` (`TextType=ssml`) · [Supported SSML tags](https://docs.aws.amazon.com/polly/latest/dg/supportedtags.html)

## Setup

Complete the [shared setup](../README.md#shared-setup) from the `features/`
directory.

## Run

```bash
cd 03-voice-control-ssml

# The default engine is generative unless --engine is specified

# See every built-in SSML enhanced example
python voice_control_ssml.py --list

# Generate an example with pauses
# Output: ssml-break.mp3
python voice_control_ssml.py --tag break

# Generate an example with speaking-rate and volume changes
# Output: ssml-prosody.mp3
python voice_control_ssml.py --tag prosody --voice Matthew

# Generate a newscaster-style example with a neural voice
# Output: ssml-newscaster.mp3
python voice_control_ssml.py --tag newscaster --engine neural --voice Joanna

# Generate audio from your own SSML
# Output: ssml-custom.mp3
python voice_control_ssml.py --ssml '<speak>Hi <break time="1s"/> there.</speak>'
```

## Built-in samples

| `--tag` | Demonstrates |
|---|---|
| `break` | Inserting pauses of a set time or strength |
| `prosody` | Changing speaking rate and volume |
| `emphasis` | Stressing or de-emphasizing words |
| `say-as` | Reading digits as a phone number, a date, or spelling out |
| `phoneme` | Explicit IPA pronunciation |
| `newscaster` | The `<amazon:domain name="news">` speaking style |

## What to know

- **Tag support varies by engine.** The Run examples use the default
  generative engine. See the
  [supported SSML tags](https://docs.aws.amazon.com/polly/latest/dg/supportedtags.html)
  table and its **Generative voice availability** column before using another
  built-in tag. This prosody sample changes rate and volume; generative voices
  do not support the `pitch` attribute.
- **Escape special characters.** Any `&`, `<`, or `>` inside your spoken text
  must be XML-escaped (`&amp;`, `&lt;`, `&gt;`) or Polly returns
  `InvalidSsmlException`.
- **A document must be wrapped in `<speak>...</speak>`.**
- **Output names identify the example.** A built-in tag writes
  `ssml-<tag>.mp3`; inline SSML writes `ssml-custom.mp3`. Use `-o` to choose a
  different filename.

## Expected output

```
Synthesizing SSML with Tiffany (generative):
  <speak>There is a pause <break time="1s"/> right there, ...</speak>

Wrote ssml-break.mp3  (billed characters: 78)
Play it with: afplay ssml-break.mp3
```

## Cleanup

```bash
rm -f ssml-break.mp3 ssml-prosody.mp3 ssml-newscaster.mp3 ssml-custom.mp3
```

[Back to Features](../README.md)
