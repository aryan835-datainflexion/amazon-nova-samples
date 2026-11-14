# Speech Marks

Get word/sentence timing, viseme (lip-sync) cues, and SSML `<mark>` positions
alongside your audio. Same `SynthesizeSpeech` call, but with
`OutputFormat=json` and one or more `SpeechMarkTypes`. Polly returns
newline-delimited JSON — one mark per line. Each command saves that raw
response to a `.txt` file and also prints a readable table.

**API:** `SynthesizeSpeech` (`OutputFormat=json`) · [Speech marks docs](https://docs.aws.amazon.com/polly/latest/dg/speechmarks.html)

## Setup

Complete the [shared setup](../README.md#shared-setup) from the `features/`
directory.

## Run

```bash
cd 04-speech-marks

# Speech marks do not currently support the generative engine.
# These examples use Matthew with the neural engine by default.

# Word + sentence timings for the default text:
# "Mary had a little lamb. Its fleece was white as snow."
# Output: speech-marks-word-sentence.txt
python speech_marks.py

# Viseme cues for lip-sync animation
# Output: speech-marks-viseme.txt
python speech_marks.py --mark-types viseme --text "Hello there."

# SSML mark positions
# Output: speech-marks-ssml.txt
python speech_marks.py --mark-types ssml --text-type ssml \
    --text '<speak>Hello <mark name="example"/> world.</speak>'

# Marks plus the matching audio, so captions align with playback
# Outputs: speech-marks-word-sentence-with-audio.txt and speech-marks.mp3
python speech_marks.py --with-audio
```

## Mark types

| Type | What it gives you | Common use |
|---|---|---|
| `word` | Byte + time offset of each word | Karaoke-style word highlighting |
| `sentence` | Same, per sentence | Scrolling captions |
| `viseme` | Mouth-shape code per sound | Avatar / character lip-sync |
| `ssml` | Location of `<mark>` tags in SSML | Triggering events at set points |

## Options

| Flag | Default | Notes |
|---|---|---|
| `--text` | `Mary had a little lamb. Its fleece was white as snow.` | Text used to generate the speech marks |
| `--mark-types` | `word sentence` | One to four unique values: `word`, `sentence`, `viseme`, `ssml` |
| `--voice` | `Matthew` | Voice used to generate the timing metadata |
| `--engine` | `neural` | `standard`, `neural`, or `long-form`; generative is not supported |
| `--text-type` | `text` | Use `ssml` when requesting the `ssml` mark type |
| `--marks-output` | based on mark types | Override the speech marks `.txt` filename |
| `--with-audio` | off | Make a second request for matching MP3 audio |
| `-o/--output` | `speech-marks.mp3` | Audio filename used with `--with-audio` |

## What to know

- **Speech marks do not currently support the generative engine.** This
  example therefore defaults to the neural engine with Matthew.
- **Two calls if you want audio too.** A single request returns *either* audio
  *or* JSON marks, not both. Use identical `Text`, `VoiceId`, and `Engine` for
  both calls so the timings match — `--with-audio` does exactly this.
- **Every command saves the raw response.** The `.txt` file contains one JSON
  object per line, matching Polly's response format. The script also prints
  the marks as a table for quick inspection.
- **`--with-audio` creates two files.** It writes the speech marks `.txt` file
  and makes a second request for matching `speech-marks.mp3` audio.
- **The `ssml` mark type needs `--text-type ssml`** and `<mark name="...">`
  tags in the input.
- **Character limits.** A request accepts up to 6,000 characters total, with no
  more than 3,000 billed characters. SSML tags do not count as billed
  characters.
- **`time` is milliseconds** from the start of the audio.

## Expected output

```
13 speech mark(s) for types ['word', 'sentence']:

 time(ms)  type       start    end  value / info
----------------------------------------------------------------------------
        0  sentence       0     23  Mary had a little lamb.
        6  word           0      4  Mary
      373  word           5      8  had
      ...

Wrote raw speech marks: speech-marks-word-sentence.txt
```

Timing values vary by voice and engine.

## Cleanup

```bash
rm -f speech-marks-word-sentence.txt speech-marks-viseme.txt
rm -f speech-marks-ssml.txt speech-marks-word-sentence-with-audio.txt
rm -f speech-marks.mp3
```

[Back to Features](../README.md)
