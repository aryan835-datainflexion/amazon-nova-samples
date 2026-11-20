# Getting started with Amazon Polly

This quickstart introduces Amazon Polly's four speech engines, discovers
compatible voices in your AWS Region, synthesizes plain text, and saves the
audio in your chosen format. MP3 playback is optional.

## Prerequisites

- An AWS account with credentials and a Region configured
- The `polly:DescribeVoices` and `polly:SynthesizeSpeech` IAM permissions
- Python 3.10 or later

## Set up the environment

From the `getting-started` directory:

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows PowerShell
pip install -r requirements.txt
```

## Configure AWS access

The script creates a standard `boto3.client("polly")`, so boto3 obtains the
Region and credentials from its
[default credential chain](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html).
If AWS access is already configured in your environment, no additional setup is
needed.

For local development, prefer temporary credentials through AWS IAM Identity
Center instead of long-term IAM user access keys:

```bash
aws configure sso --profile my-polly-profile
aws sso login --profile my-polly-profile

export AWS_PROFILE=my-polly-profile
export AWS_DEFAULT_REGION=us-east-1
```

See [IAM Identity Center authentication](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html)
for the complete setup. Other standard boto3 credential sources, such as an
assumed role, container credentials, or instance credentials, also work.

Alternatively, provide credentials through environment variables in your
current shell:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...       # Required for temporary credentials
export AWS_DEFAULT_REGION=us-east-1
```

Do not put credential values in source files or commit them to version control.

The configured identity needs these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "polly:DescribeVoices",
        "polly:SynthesizeSpeech"
      ],
      "Resource": "*"
    }
  ]
}
```

The policy follows least privilege by granting only the two actions used by
this quickstart.

## Choose the speech settings

Edit the configuration near the top of `polly_quickstart.py`:

```python
TEXT = "Hello, welcome to this demonstration of Amazon Polly."
ENGINE = "generative"
VOICE_ID = "Tiffany"
OUTPUT_FORMAT = "mp3"
PLAY_AUDIO = False
```

Run the script once to list the voices that support the selected engine in your
Region. Choose a compatible engine and voice from that list.

| Engine | Best suited for |
| --- | --- |
| `standard` | Broad voice availability and general-purpose speech |
| `neural` | Natural speech for customer-facing and conversational audio |
| `long-form` | Longer content such as articles and training material |
| `generative` | Expressive, conversational delivery for supported voices |

Voice and engine availability varies by Region. The default generative engine
is available only in supported Regions. To pin the Region in code instead of
setting `AWS_DEFAULT_REGION`, use:

```python
polly = boto3.client("polly", region_name="us-east-1")
```

The supported output settings in this example are:

| `OUTPUT_FORMAT` | Saved extension | Playback |
| --- | --- | --- |
| `"mp3"` | `.mp3` | Optional with `PLAY_AUDIO = True` |
| `"ogg_vorbis"` | `.ogg` | Save only |
| `"pcm"` | `.pcm` | Save only |

See the [`SynthesizeSpeech` API reference](https://docs.aws.amazon.com/polly/latest/APIReference/API_SynthesizeSpeech.html)
for the full list of supported output formats.

## Run the quickstart

```bash
python polly_quickstart.py
```

The script:

1. Introduces the four speech engines.
2. Lists voices that support the selected engine.
3. Validates the configured voice and engine.
4. Calls `SynthesizeSpeech`.
5. Saves the result under `audio_output/`.
6. Plays the MP3 when `PLAY_AUDIO` is `True`.

`SynthesizeSpeech` accepts up to 6,000 characters total per request, with no
more than 3,000 billed characters. SSML tags do not count as billed characters.
For longer content, use
[`StartSpeechSynthesisTask`](https://docs.aws.amazon.com/polly/latest/dg/API_StartSpeechSynthesisTask.html).

## Troubleshooting

- **Access denied** — allow `polly:DescribeVoices` and
  `polly:SynthesizeSpeech` for your AWS identity.
- **Missing credentials or Region** — authenticate and configure an AWS Region.
- **Voice or engine unavailable** — choose a compatible pair from the printed
  voice list.
- **No playback backend** — install a supported local audio backend or open the
  saved MP3 in another player.

## Next steps and cleanup

See [`features/`](../features/) for focused examples covering SSML, speech
marks, lexicons, asynchronous synthesis, streaming, and other Polly APIs.

Amazon Polly charges for synthesized characters. This example creates no
persistent AWS resources. Remove its generated audio with:

```bash
rm -rf audio_output
```

Never commit credentials or generated audio files.

[Back to the project README](../README.md)
