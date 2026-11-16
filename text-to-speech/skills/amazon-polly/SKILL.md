---
name: amazon-polly
description: Best practices for building with Amazon Polly text-to-speech — choosing the right API (SynthesizeSpeech, StartSpeechSynthesisTask, StartSpeechSynthesisStream), choosing an engine (standard, neural, long-form, generative) and a compatible voice, output formats, engine-safe SSML, pronunciation lexicons, speech marks for captions and lip-sync, limits, errors, retries, IAM, and cost. Use when writing, reviewing, or debugging code that calls Polly; when picking a voice or engine; when fixing pronunciation; or when errors such as InvalidSsmlException, TextLengthExceededException, EngineNotSupportedException, or LexiconNotFoundException appear. Not for Transcribe-, Translate-, or Bedrock-only questions.
---

# Amazon Polly — best practices

Use this guide to choose the right Polly API, engine, and voice. It covers
requests that succeed on the first try, and pronunciation and failure
handling. The rules apply in any language and SDK; examples use Python/boto3.

Polly behavior changes over time. Treat the tables here as defaults, and check
anything Region- or engine-specific against the live API (`DescribeVoices`) or
the [Polly developer guide](https://docs.aws.amazon.com/polly/latest/dg/what-is.html).

## 1. Choose the API

| Situation | API | Why |
| --- | --- | --- |
| Up to ~3,000 billed characters, audio needed now | `SynthesizeSpeech` | One synchronous call; audio returned in the response body |
| Longer text (articles, chapters, documents) | `StartSpeechSynthesisTask` → `GetSpeechSynthesisTask` | Async; writes the file to S3; up to 100,000 billed characters |
| Text arrives incrementally (LLM token stream) and first audio must start before the text is complete | `StartSpeechSynthesisStream` | Bidirectional stream: send text events, receive audio events on one connection |
| Real-time agent that already splits text into sentences | `SynthesizeSpeech` per sentence | Simple, widely supported; latency ≈ one sentence |
| Word/sentence timing, viseme lip-sync, `<mark>` events | `SynthesizeSpeech` with `OutputFormat=json` | Speech marks; a separate request from the audio |
| Find voices and their supported engines | `DescribeVoices` | Region-specific roster; never hard-code the full list |
| Custom pronunciation reused across requests | `PutLexicon` + `LexiconNames` on synthesis | Stored PLS lexicons; up to 5 per request |

Rules of thumb:

- Start with `SynthesizeSpeech`. Move to the async task only when the text is
  over the sync limit, or the output belongs in S3 anyway.
- For conversational agents, split the LLM output at sentence boundaries and
  synthesize each sentence as soon as it is complete. Playback can then start
  while the model is still generating. Use `StartSpeechSynthesisStream` when
  you need lower latency than that, and check that your SDK supports it first.
- Don't use speech marks or SSML unless you need them. Each adds a constraint
  on the engine.

## 2. Choose the engine and voice

| Engine | Use for | Constraints |
| --- | --- | --- |
| `generative` | Most expressive, conversational speech; assistants, podcasts | Fewest voices and Regions; **no speech marks**; limited SSML; no prosody `pitch` |
| `long-form` | Narration of long content (articles, e-learning) | Few voices and Regions; limited SSML |
| `neural` | Natural speech with the broadest modern feature set; **required choice when you need speech marks/visemes with natural audio** | Limited SSML (no `emphasis`, no prosody `pitch`) |
| `standard` | Widest voice/language/Region coverage; full SSML (pitch, emphasis, effects) | Least natural; lowest cost |

The cost per character goes up from standard to neural, long-form, and
generative. See [Polly pricing](https://aws.amazon.com/polly/pricing/).

How to pick a voice:

1. Pick the engine your feature needs (speech marks → not generative; full SSML
   → standard).
2. Call `DescribeVoices` with `Engine` and `LanguageCode` in the **same Region you
   will synthesize in**. Follow `NextToken` until it runs out. Add
   `IncludeAdditionalLanguageCodes=True` to find bilingual voices.
3. Validate the voice before synthesis: check that `voice["SupportedEngines"]`
   contains your engine. It's cheaper to fail at this point than on a billed
   call.
4. For bilingual voices, pass `LanguageCode` on synthesis, and use the same
   language code for lexicons.
5. Make the voice, engine, and Region configurable, and give clear errors when
   they are invalid. Defaults that work in `us-east-1` may fail elsewhere.

```python
import boto3

polly = boto3.client("polly")  # credentials + Region from the default chain

def voices_for(engine: str, language_code: str | None = None) -> list[dict]:
    kwargs = {"Engine": engine}
    if language_code:
        kwargs["LanguageCode"] = language_code
    voices, token = [], None
    while True:
        page = polly.describe_voices(**kwargs, **({"NextToken": token} if token else {}))
        voices += page["Voices"]
        token = page.get("NextToken")
        if not token:
            return voices
```

Some capabilities aren't reported by `DescribeVoices`, so you have to check
them in the docs. For example, the neural `newscaster` style works only for
certain voices (such as Joanna, Matthew, Amy, and Lupe).

## 3. Request essentials

**Credentials and Region.** Create the client with the SDK's default credential
chain: IAM Identity Center/SSO profile, role, or environment. Never put access
keys in source, config files, browser code, or mobile apps. Browser and mobile
clients should call your backend, or use short-lived scoped credentials such as
Amazon Cognito identity pools. Let the caller override the Region and profile.

**Limits** (check the API reference for current values):

| API | Total characters | Billed characters |
| --- | --- | --- |
| `SynthesizeSpeech` | 6,000 (incl. SSML tags) | 3,000 (SSML tags not billed) |
| `StartSpeechSynthesisTask` | 200,000 | 100,000 |

**Output formats:**

| `OutputFormat` | Notes |
| --- | --- |
| `mp3` | Default choice for files and browsers |
| `ogg_vorbis` | Smaller files; many players need FFmpeg |
| `pcm` | Raw 16-bit signed little-endian mono, **no header**. Use for real-time pipelines (WebSocket/WebRTC). Most players can't open a `.pcm` file; add a WAV header if a human needs to listen |
| `json` | Speech marks only (see §6) |

Not every format supports every `SampleRate`. PCM supports 8000/16000 Hz, and
MP3/Ogg also support 22050/24000. Match the sample rate your downstream
pipeline expects; otherwise you get `InvalidSampleRateException` or
chipmunk/slow audio. Check the
[`SynthesizeSpeech` reference](https://docs.aws.amazon.com/polly/latest/APIReference/API_SynthesizeSpeech.html)
for the full and current format list.

**Reading the response.** `AudioStream` is a streaming body. Read it once,
close it, and stream it in chunks when the output is large or real-time:

```python
from contextlib import closing

resp = polly.synthesize_speech(
    Text=text, VoiceId="Matthew", Engine="neural",
    OutputFormat="mp3", LanguageCode="en-US",
)
with closing(resp["AudioStream"]) as stream, open("out.mp3", "wb") as f:
    for chunk in iter(lambda: stream.read(64 * 1024), b""):
        f.write(chunk)
print("billed characters:", resp["RequestCharacters"])
```

**Text over the sync limit, but you still want sync calls:** split at
paragraph or sentence boundaries, never mid-word or mid-tag. Keep each chunk
safely under the limit, use the same voice/engine/format for every chunk, and
concatenate in order. MP3 and PCM chunks concatenate cleanly. Use the async
task instead if you don't need the audio inline.

## 4. SSML

Use SSML only for what plain text can't express: pauses, rate/volume,
pronunciation, and reading numbers or dates.

**Rules that always apply:**

- Set `TextType="ssml"` and wrap the document in `<speak>…</speak>`.
- XML-escape spoken `&`, `<`, `>`, `"`, `'` (`&amp;` `&lt;` `&gt;` `&quot;` `&apos;`).
  An unescaped `&` is the most common cause of `InvalidSsmlException`.
- The document must be well-formed XML. Parse it locally before sending it.
- SSML tags count toward the 6,000-character total but aren't billed.

**Engine support (conservative, safe subset):**

| Tag / attribute | standard | neural | long-form | generative |
| --- | --- | --- | --- | --- |
| `break`, `p`, `s`, `say-as`, `sub`, `lang`, `w` | ✅ | ✅ | ✅ | ✅ |
| `phoneme`, `mark` | ✅ | ✅ | ✅ | ⚠️ partial |
| `prosody` `rate`, `volume` | ✅ | ✅ | ✅ | ✅ |
| `prosody` `pitch` | ✅ | ❌ | ❌ | ❌ |
| `emphasis` | ✅ | ❌ | ❌ | ❌ |
| `amazon:effect` (whispered, etc.), `amazon:auto-breaths`, `amazon:breath` | ✅ | ❌ | ❌ | ❌ |
| `amazon:domain name="news"` | ❌ | ⚠️ specific voices | ❌ | ❌ |

On standard, neural, and long-form, an unsupported tag fails the request.
Generative may silently ignore some tags instead, so "no error" doesn't mean
"it worked". There's no API that reports SSML support per engine. Check the
[supported SSML tags](https://docs.aws.amazon.com/polly/latest/dg/supportedtags.html)
table when you change engines.

**When an LLM or users write the SSML,** treat it as untrusted input and guard
it deterministically before synthesis:

1. Tell the model which tags are allowed **for the target engine only**.
2. Parse the output. Remove any element or attribute not on that engine's
   allowlist, keeping the inner text. Escape stray characters, and re-wrap
   the result in `<speak>`.
3. If it still fails to parse, fall back to plain text (`TextType="text"`)
   rather than dropping the utterance.
4. Keep one table of allowed tags per engine and generate both the prompt and
   the guard from it, so the two can't drift apart.

## 5. Pronunciation: SSML or lexicon

| Need | Use |
| --- | --- |
| One-off fix in one request | SSML `<sub alias="…">` or `<phoneme alphabet="ipa" ph="…">` |
| Same term across many requests (brand names, acronyms, domain jargon) | A stored lexicon applied with `LexiconNames=[...]` |
| Acronym read as letters vs. a word | `<say-as interpret-as="characters">` or a lexicon alias like `E G F R` |

**Lexicon rules:**

- Lexicons are W3C PLS XML with `alphabet` (`ipa` or `x-sampa`) and `xml:lang`.
  Malformed files cause `InvalidLexiconException`. Keep each lexicon under the
  40,000-character size limit, and keep replacement text short (≤100 characters).
- A lexicon belongs to one Region. Store it in the Region you synthesize in.
- A lexicon applies only when its `xml:lang` matches the voice's language.
- Names are 1–20 alphanumeric characters. `PutLexicon` with an existing name
  **overwrites** that lexicon, so treat names as owned identifiers.
- Updates are eventually consistent. A synthesis call right after `PutLexicon`
  may fail with `LexiconNotFoundException`. Retry after a few seconds.
- You can apply up to 5 lexicons per request. Earlier lexicons in the list take
  precedence.
- Prefer `alias` entries; they are readable and easy to review. Use `phoneme`
  only when an alias can't express the pronunciation. A wrong phoneme makes
  speech worse, so phoneme entries need careful review.
- Stored lexicons persist and count toward a per-Region quota. Delete the ones
  you no longer use.

**AI-drafted lexicons:** if a model proposes entries from domain text, have a
human review them before publishing. A deterministic builder should then
validate them (exactly one alias or phoneme per entry, no duplicate graphemes,
valid alphabet, well-formed XML, under the size limit) before `PutLexicon`.
Never publish model output to a shared lexicon unreviewed.

## 6. Speech marks (captions, highlighting, lip-sync)

- Request them with `OutputFormat="json"` and `SpeechMarkTypes` (any of `word`,
  `sentence`, `viseme`, `ssml`). The response is newline-delimited JSON with one
  mark per line. `time` is in milliseconds from the start of the audio, and
  `start`/`end` are byte offsets into the input text.
- **A request returns either audio or marks, never both.** Make two calls with
  identical `Text`, `TextType`, `VoiceId`, `Engine`, and `LanguageCode` so the
  timings line up. You can run them in parallel.
- **Generative doesn't support speech marks.** Use neural for natural audio
  with visemes. Don't plan lip-sync on the bidirectional streaming API without
  checking that it emits visemes.
- The `ssml` mark type needs `TextType="ssml"` and `<mark name="…"/>` tags in the
  input.
- For lip-sync, map Polly viseme codes (`p`, `t`, `S`, `a`, `sil`, …) to your
  avatar's mouth shapes and drive animation from the audio clock, not wall time.
- Both calls are billed, so cache marks with the audio when the text repeats.

## 7. Long-form (async) and bidirectional streaming

**Async tasks (`StartSpeechSynthesisTask`):**

- The output goes to an S3 bucket you own **in the same Region**. The caller
  needs `polly:StartSpeechSynthesisTask` plus `s3:PutObject` on the bucket, and
  `s3:GetObject` to download the result.
- Use a unique `OutputS3KeyPrefix` per job. Status goes `scheduled` →
  `inProgress` → `completed`, or `failed` with `TaskStatusReason`.
- In production, use `SnsTopicArn` for completion notifications rather than
  tight polling. When you do poll, use intervals of several seconds and a
  timeout.
- The task record is kept for about 72 hours. The S3 object stays until you
  delete it, so add an S3 Lifecycle rule for generated audio.

**Bidirectional streaming (`StartSpeechSynthesisStream`):**

- Run the sender and receiver at the same time, e.g. `asyncio.gather(send(),
  receive())`. Don't wait for all text to be sent before reading audio. Send
  each text fragment as soon as it's available, then close the input stream so
  the service can flush the final audio.
- The API is generally available, but SDK support varies by language. In
  Python, boto3 doesn't expose it yet; the experimental AWS SDK for Python v4
  Polly client (Python 3.12+) does, and its interface may change. Check your
  SDK's current support before you commit to this design.

## 8. Errors, retries, and quotas

| Error | Usual cause | Fix |
| --- | --- | --- |
| `AccessDeniedException` | Missing IAM action, or wrong account/profile | Grant the specific `polly:*` action; check the caller identity |
| `EngineNotSupportedException` / `ValidationException` on voice/engine | Voice doesn't support that engine, or the engine isn't available in the Region | Validate with `DescribeVoices` in the target Region |
| `InvalidSsmlException` | Unescaped `&`/`<`, missing `<speak>`, or a tag unsupported on this engine | Escape, parse locally, filter by engine (§4) |
| `TextLengthExceededException` | Over the sync limit | Chunk (§3) or use the async task |
| `InvalidSampleRateException` | Sample rate not valid for this format | Use a supported rate for the format |
| `LexiconNotFoundException` | Wrong Region, wrong name, or just uploaded | Check the Region and name; retry after a few seconds |
| `InvalidLexiconException` / `UnsupportedPlsLanguageException` | Malformed PLS or unsupported language | Validate the PLS; match `xml:lang` to the voice |
| `MarksNotSupportedForFormatException` / `SsmlMarksNotSupportedForTextTypeException` | Speech marks with a non-`json` format, or `ssml` marks with plain text | Use `json`; set `TextType="ssml"` |
| `InvalidS3BucketException` / `InvalidS3KeyException` | Bucket in another Region, a bad name, or an `s3://` URI passed | Pass the bucket name only, in the same Region |
| `ThrottlingException` / `ServiceFailureException` | Request rate over quota, or a transient failure | Retry with exponential backoff and jitter |

- Turn on SDK retries, e.g. boto3
  `Config(retries={"mode": "adaptive", "max_attempts": 5})`. Don't build your
  own tight retry loops.
- Don't retry client errors (4xx validation errors) without changing the
  request.
- For high-volume batch work, limit concurrency to your account's transactions
  per second (TPS) quota (see Service Quotas) instead of relying on retries.
- Log the request ID, voice, engine, Region, and character count. Never log
  credentials. Treat text as possibly sensitive.

## 9. IAM, cost, data, and cleanup

- **Least privilege:** grant only the actions the code calls, typically
  `polly:SynthesizeSpeech` and `polly:DescribeVoices`. Add
  `polly:StartSpeechSynthesisTask`, `polly:GetSpeechSynthesisTask`, and
  `polly:ListSpeechSynthesisTasks` (plus S3) for async; the lexicon actions for
  lexicons; and `polly:StartSpeechSynthesisStream` for bidirectional
  streaming. Lexicon actions can be scoped to lexicon ARNs.
- **Cost:** every synthesis call is billed per character, including
  speech-mark calls and retries, and there's no dry-run. Check the
  `RequestCharacters` value returned in the response. Cache audio for repeated
  text, keyed by text + voice + engine + format + sample rate + lexicons. For
  LLM-driven speech, keep responses short, because every generated character
  is spoken and billed.
- **Data:** text sent to Polly may be personal or confidential. Get consent
  before synthesizing user content, and don't keep generated audio longer than
  needed.
- **Cleanup:** delete lexicons you created (`DeleteLexicon`), async output
  objects in S3, and local audio files. Confirm with the owner before deleting
  shared or production resources. Lexicon names and S3 prefixes may be in use
  by other systems.

**When acting as an agent on someone's AWS account:** run read-only checks
first (`sts get-caller-identity`, `DescribeVoices`). Say when the next call is
billed. Get explicit confirmation before creating, overwriting, or deleting
lexicons or S3 objects in an account that may be production.

## 10. Working examples in this folder

When this skill is used inside the `text-to-speech` folder, these runnable
samples (paths relative to that folder) show each practice:

| Topic | Sample |
| --- | --- |
| First request, engines, voice validation | `getting-started/polly_quickstart.py` |
| `SynthesizeSpeech`, formats, sample rates | `features/01-synthesize-speech/` |
| `DescribeVoices` with pagination and filters | `features/02-describe-voices/` |
| SSML examples per tag | `features/03-voice-control-ssml/` |
| Speech marks, with matching audio | `features/04-speech-marks/` |
| Lexicon lifecycle (put/get/list/apply/delete) | `features/05-lexicons/` |
| Async synthesis to S3 | `features/06-async-synthesis/` |
| Bidirectional streaming (experimental Python SDK) | `features/07-bidi-streaming/` |

Each sample's `README.md` lists its setup, IAM, expected output, and cleanup.
Features 01–06 share one Python 3.10+ virtual environment in `features/`.
Feature 07 needs Python 3.12+ and its own environment.
