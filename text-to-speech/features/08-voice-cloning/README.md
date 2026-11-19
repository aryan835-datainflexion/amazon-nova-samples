# Voice Cloning

Create an Amazon Polly generative voice from pre-recorded audio of one
consenting speaker, wait for it to become active, and use it for synchronous
or long-form speech synthesis. The example also shows how to inspect and
delete the voice.

**APIs:** `CreateVoice`, `GetVoice`, `DeleteVoice`, `SynthesizeSpeech`,
`StartSpeechSynthesisTask`

## Setup

Voice cloning is a gated release and must be enabled for your AWS account.
Complete the [shared setup](../README.md#shared-setup) from the `features/`
directory, then install the latest boto3 release:

```bash
pip install --upgrade boto3
```

The GA SDK service model must include `CreateVoice` with `TermsAccepted`,
`Tags`, and a recording `Format`.

Before creating a voice:

- Obtain the speaker's consent and have your legal team review the applicable
  AWS Service Terms, Biometric Notice and Consent Terms, Responsible AI Policy,
  and Acceptable Use Policy.
- Record the speaker before using the API or console. Neither interface records
  live audio.
- Prepare 1-10 recordings of one speaker, with no more than 15 minutes total.
  Two to ten minutes of natural speech is recommended.
- Prefer clean mono WAV, 16-bit, recorded at 24 kHz, with each take no longer
  than one minute.

`CreateVoice` accepts audio bytes directly in the request or references to
recording files in Amazon S3. The Polly console similarly accepts local file
uploads or S3 objects. This CLI demonstrates the S3-reference workflow: put
the recordings in a bucket in the Region where you will create the voice and
pass each object's `s3://` URI with `--recording`.

The caller needs `polly:CreateVoice`, `polly:GetVoice`,
`polly:SynthesizeSpeech`, and `polly:DeleteVoice`. The S3-reference workflow
also needs `s3:GetObject` for the recordings. Long-form synthesis needs
`polly:StartSpeechSynthesisTask`, `polly:GetSpeechSynthesisTask`, and
`s3:PutObject` on the output bucket.

## Run

Creating a voice provisions an AWS resource. The command requires an explicit
`--accept-terms` confirmation and records your consent reference as a tag.
This sample takes pre-recorded S3 object references:

```bash
cd 08-voice-cloning

python voice_cloning.py create \
    --name MyClonedVoice \
    --language-code en-US \
    --recording s3://my-bucket-polly-outputs/take1.wav \
    --consent-reference speaker-0042 \
    --accept-terms \
    --region us-east-1
```

`CreateVoice` returns a voice ID immediately. By default the command calls
`GetVoice` every 30 seconds until the status changes from `pending` to
`active` or `failed`, with a 20-minute timeout. Creation typically takes 5-10
minutes. Use `--no-wait` to return immediately.

Use the printed voice ID for the remaining commands:

```bash
export POLLY_VOICE_ID=vc-0123456789

# Inspect the voice and its status
python voice_cloning.py get --voice-id "$POLLY_VOICE_ID" --region us-east-1

# Generate short audio synchronously
python voice_cloning.py synthesize \
    --voice-id "$POLLY_VOICE_ID" \
    --language-code en-US \
    --text "Hello! This is my very own Amazon Polly voice." \
    --output my-voice.mp3 \
    --region us-east-1
```

Synthesis uses the `generative` engine. The synchronous call is billed per
character and writes `my-voice.mp3` locally.

## Main options

| Command / flag | Default | Notes |
|---|---|---|
| `create --recording` | required | Repeat for 1-10 pre-recorded S3 object URIs; the API also supports direct audio bytes |
| `create --format` | `wav` | `wav`, `flac`, `ogg_vorbis`, or `mp3` |
| `create --consent-reference` | required | Stored in the `consent-record` voice tag |
| `create --accept-terms` | required | Confirms speaker consent and the applicable AWS terms |
| `create --timeout` | `1200` | Maximum seconds to wait for creation |
| `create --kms-key-arn` | AWS owned key | Optional customer-managed KMS key |
| `synthesize --text` | sample sentence | Text for synchronous synthesis |
| `synthesize --format` | `mp3` | `mp3`, `ogg_vorbis`, or `pcm` |
| `start --text` / `--text-file` | one required | Inline or file input for long-form synthesis |
| `-p/--profile`, `-r/--region` | configured values | AWS profile and Region overrides |

## Long-form synthesis

For audiobook chapters, course modules, or other long text, start an
asynchronous task that writes audio to S3:

```bash
python voice_cloning.py start \
    --voice-id "$POLLY_VOICE_ID" \
    --language-code en-US \
    --bucket my-bucket-polly-outputs \
    --key-prefix narration/chapter-01 \
    --text-file chapter-01.txt \
    --region us-east-1
```

The command prints the task ID and output URI. Poll it with
`GetSpeechSynthesisTask`, or pass `--sns-topic-arn` to receive task
notifications. The output bucket must be in the same Region.

## Optional customer-managed encryption

Polly encrypts cloned voices by default. To use a same-Region symmetric
customer-managed KMS key, add:

```bash
--kms-key-arn arn:aws:kms:us-east-1:111122223333:key/EXAMPLE
```

Callers that create or use the voice need the corresponding
`kms:DescribeKey`, `kms:GenerateDataKey`, and `kms:Decrypt` permissions.

## What to know

- **One consenting speaker per voice.** `--accept-terms` confirms that you
  obtained the required consent and accept the applicable terms for this
  creation request. Keep the consent record associated with the voice ID.
- **Seven launch languages.** Voice cloning supports English, Spanish, German,
  French, Italian, Portuguese, and Hindi. Tested recording locales include
  `en-US`, `es-US`, `de-DE`, `fr-FR`, `it-IT`, `pt-BR`, and `hi-IN`.
- **The voice speaks its recording language.** For multilingual applications,
  create and review a separate approved voice for each language.
- **Record consistently.** Use one microphone position, a quiet room, and the
  speaking style you want the cloned voice to keep. Avoid meeting apps and
  browser recorders that alter the audio.
- **Regional and account scoped.** A cloned voice exists only in the account
  and Region where it was created. IAM controls who can synthesize with it.
- **Generative engine only.** Pass `Engine="generative"` when using a cloned
  voice.
- **Creation is free; usage is billed.** Creating the voice is free.
  Synchronous and long-form synthesis are billed at cloned-voice usage rates.
  Long-form output may also incur S3 storage charges.
- **Quotas.** The initial quota is 10 cloned voices per account per Region.
  `CreateVoice` and `DeleteVoice` share a limit of one request per second.
- **Check before retrying creation.** If `CreateVoice` times out or returns a
  server error, it may still have created the voice. Check `DescribeVoices`
  for the name before retrying so automatic retries do not create duplicates.
- **Data handling.** Polly deletes its copy of the recordings after creation
  and does not use them to train Polly models. `DeleteVoice` removes the stored
  speaker reference embeddings.
- **Watermarking.** Speech from cloned voices carries the watermark used by
  Amazon Polly generative voices.

## Expected output

```text
Voice creation started:
  VoiceId:      vc-0123456789
  Name:         MyClonedVoice
  Status:       pending
  Language:     en-US

Store this voice ID with its Region, language, owner, and consent record.

Waiting for the voice to become active (typically 5-10 minutes)...
Voice vc-0123456789 is pending; checking again in 30s...
  VoiceId:      vc-0123456789
  Name:         MyClonedVoice
  Status:       active
  Language:     en-US
```

## Cleanup

Delete local output:

```bash
rm -f my-voice.mp3
```

Delete any long-form output object from S3 using the exact URI returned by the
synthesis task.

When the voice is no longer needed, or if the speaker withdraws consent,
permanently delete it:

```bash
python voice_cloning.py delete \
    --voice-id "$POLLY_VOICE_ID" \
    --region us-east-1
```

`DeleteVoice` is irreversible. It can be called after the voice is active or
after creation has failed.

[Back to Features](../README.md)
